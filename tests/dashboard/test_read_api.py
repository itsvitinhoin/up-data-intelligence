"""Synthetic-only contract tests; no GCP client or customer records."""

import json
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import BadRequest

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal, ReadError
from src.dashboard.http import create_wsgi_app, dispatch
from src.dashboard.queries import Query, build
from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.dashboard.service import DashboardService

PROJECT = "up-data-intelligence-dev"
KEY = b"synthetic-test-cursor-key-32-bytes-long"
GRANT = Grant("tenant-test", "mx-fashion", "B2B")
PRINCIPAL = Principal("synthetic-user", "CLIENT_USER", frozenset({GRANT}))


@pytest.fixture
def policy() -> AnalyticsPolicy:
    return AnalyticsPolicy.from_dict(
        json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    )


def head(policy: AnalyticsPolicy) -> dict[str, Any]:
    return {
        "store_id": policy.store_id,
        "policy_hash": policy.policy_hash,
        "generation": 4,
        "publication_id": "a" * 64,
        "status": "completed",
        "as_of": policy.as_of,
        "report_from": None,
        "report_to": None,
        "source_watermark": "b" * 64,
        "receipt_store_id": policy.store_id,
        "receipt_policy_hash": policy.policy_hash,
        "receipt_id": "a" * 64,
        "receipt_generation": 4,
        "receipt_status": "completed",
        "receipt_version": "1.0.0",
        "receipt_watermark": "b" * 64,
        "receipt_as_of": policy.as_of,
        "receipt_from": policy.report_from,
        "receipt_to": policy.report_to,
        "snapshot_at": "2026-09-30T00:00:00Z",
    }


def customer_row(id: str = "c1", key: str = "a" * 64) -> dict[str, Any]:
    return {
        "customer_id": id,
        "customer_type": "B2B",
        "purchases": 2,
        "qualifying_orders": 2,
        "first_observed_at": "2026-09-01T12:00:00Z",
        "last_observed_at": "2026-09-03T12:00:00Z",
        "summary_requested": Decimal("100.25"),
        "summary_fulfilled": Decimal("75.50"),
        "first_purchase_at": "2026-09-01T12:00:00Z",
        "first_purchase_date": date(2026, 9, 1),
        "ltv_lifetime_observed": Decimal("100.25"),
        "ltv_paid": None,
        "cursor_key": key,
        "name": "Loja Sintética",
        "company_name": None,
        "trade_name": None,
        "state": None,
        "city": None,
    }


class FakeReader:
    def __init__(self, policy: AnalyticsPolicy):
        self.policy = policy
        self.override: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[Query] = []

    def query(
        self, query: Query, *, request_id: str, store_id: str, generation: int | None
    ) -> list[dict[str, Any]]:
        self.calls.append(query)
        if query.name in self.override:
            return self.override[query.name]
        if query.name == "overview_details":
            original_calls = list(self.calls)
            data = {}
            for field, model in (
                ("daily", "store_daily"),
                ("population", "customer_period"),
                ("quantities", "order_quantity_summary"),
                ("leads", "operational_leads"),
            ):
                data[field] = self.query(
                    Query(model, "", query.parameters),
                    request_id=request_id,
                    store_id=store_id,
                    generation=generation,
                )
            self.calls = original_calls
            return [data]
        if query.name == "head":
            return [head(self.policy)]
        if query.name == "operational_leads":
            return [
                dict(
                    generated=0,
                    approved=0,
                    converted=0,
                    conflicts=0,
                    invalid_identity=0,
                    unresolved_approved=0,
                )
            ]
        if query.name == "order_quantity_summary":
            return [
                {
                    "orders": 2,
                    "duplicate_orders": 0,
                    "invalid_identity": 0,
                    "paid_orders": 1,
                    "unknown_payment_status": 0,
                    "requested_pieces": 11,
                    "fulfilled_pieces": 7,
                }
            ]
        if query.name == "store_daily":
            return [
                {
                    "order_date": date(2026, 9, 1),
                    "currency": "BRL",
                    "reporting_timezone": "America/Sao_Paulo",
                    "history_complete": False,
                    "observation_complete": False,
                    "orders_generated": 2,
                    "orders_cancelled": 1,
                    "approved_orders": 1,
                    "new_customers": None,
                    "revenue_generated": Decimal("100.25"),
                    "revenue_fulfilled": Decimal("75.50"),
                    "revenue_cancelled": Decimal("20.00"),
                }
            ]
        if query.name == "customer_period":
            return [
                {
                    "buyers": 1,
                    "recurring_buyers": 1,
                    "qualifying_orders": 2,
                    "recurring_orders": 1,
                    "recurring_fulfilled": Decimal("50.25"),
                }
            ]
        if query.name == "customers":
            after = query.parameters["after"][1]
            size = query.parameters["limit"][1]
            return [
                row
                for row in [customer_row(), customer_row("c2", "b" * 64)]
                if row["cursor_key"] > after
            ][:size]
        if query.name == "customer":
            return [customer_row()] if query.parameters["customer"][1] == "c1" else []
        if query.name == "customer_summary":
            return [
                {
                    "qualifying_orders": 2,
                    "first_purchase_at": "2026-09-01T12:00:00Z",
                    "last_purchase_at": "2026-09-03T12:00:00Z",
                    "requested": Decimal("100.25"),
                    "fulfilled": Decimal("75.50"),
                }
            ]
        if query.name == "orders":
            return [
                {
                    "order_id": "o1",
                    "customer_id": "c1",
                    "created_at": "2026-09-01T12:00:00Z",
                    "order_status": "CANCELED",
                    "payment_status": "unpaid",
                    "requested_total": Decimal("20.00"),
                    "fulfilled_total": Decimal("0.00"),
                    "requested_items_qty": 2,
                    "fulfilled_items_qty": 0,
                    "cursor_key": "2026-09-01T12:00:00.000000Z:" + "c" * 64,
                }
            ]
        if query.name == "retention_details":
            original_calls = list(self.calls)
            data = {}
            for field, model in (
                ("distribution", "retention_distribution"),
                ("cohorts", "retention_cohorts"),
                ("gaps", "retention_gaps"),
            ):
                data[field] = self.query(
                    build(PROJECT, model),
                    request_id=request_id,
                    store_id=store_id,
                    generation=generation,
                )
            self.calls = original_calls
            data["series"] = [
                {
                    "order_date": date(2026, 9, 1),
                    "buyers": 1,
                    "recurring_buyers": 1,
                    "recurring_orders": 1,
                    "recurring_fulfilled": Decimal("50.25"),
                }
            ]
            return [data]
        if query.name == "retention_distribution":
            return [
                {
                    "cohort_month": date(2026, 9, 1),
                    "purchase_bucket": str(stage),
                    "customers": 1 if stage <= 2 else 0,
                    "original_cohort_customers": 1,
                    "revenue": Decimal("10"),
                }
                for stage in range(1, 5)
            ] + [
                {
                    "cohort_month": date(2026, 9, 1),
                    "purchase_bucket": "5+",
                    "customers": 0,
                    "original_cohort_customers": 1,
                    "revenue": Decimal("0"),
                }
            ]
        if query.name == "retention_cohorts":
            return [
                {
                    "cohort_month": date(2026, 9, 1),
                    "reporting_month": date(2026, 9, 1),
                    "months_since_first_purchase": 0,
                    "customers_in_cohort": 1,
                    "retention_rate": None,
                    "observed_retention_rate": Decimal("1"),
                    "period_complete": False,
                }
            ]
        if query.name == "retention_gaps":
            return [{"stage": 2, "transitions": 1, "mean_days": 2.0, "median_days": 2.0}]
        if query.name == "products":
            return [
                {
                    "product_key": "synthetic-product-key",
                    "product_id": None,
                    "sku": "SKU-TEST",
                    "requested": Decimal("100.25"),
                    "fulfilled": Decimal("75.50"),
                    "units_requested": Decimal("3"),
                    "units_fulfilled": Decimal("2"),
                    "orders": 1,
                    "cursor_key": "d" * 64,
                }
            ]
        if query.name == "funnel_daily":
            return [
                {
                    "event_date": date(2026, 9, 1),
                    "observation_complete": True,
                    "sessions": 10,
                    "product_views": 8,
                    "add_to_cart": 4,
                    "checkout_started": 2,
                    "purchase": 1,
                    "sessions_with_cart": 4,
                    "sessions_cart_then_checkout": 2,
                    "sessions_cart_checkout_purchase": 1,
                    "sessions_with_purchase": 1,
                    "events_without_session": 0,
                }
            ]
        raise AssertionError(query.name)


@pytest.fixture
def setup(policy: AnalyticsPolicy) -> tuple[DashboardService, FakeReader]:
    reader = FakeReader(policy)
    return DashboardService(PROJECT, {policy.store_id: policy}, lambda: reader, KEY), reader


def test_overview_uses_one_generation_and_preserves_money_and_unknown(
    setup: tuple[DashboardService, FakeReader],
):
    service, reader = setup
    response = service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    data, meta = response["data"], response["metadata"]
    assert (data["requested_revenue"], data["fulfilled_revenue"], data["fulfillment_gap"]) == (
        "100.25",
        "75.50",
        "24.75",
    )
    assert data["new_customers_confirmed"] is None and data["ltv_complete"] is None
    assert data["cac"] is None and data["revenue_paid"] is None
    assert data["orders_cancelled"] == 1 and data["cancelled_requested_revenue"] == "20.00"
    assert meta["history_complete"] is False and meta["facts_complete"] is True
    assert meta["generation"] == 4 and meta["policy_hash"] == reader.policy.policy_hash
    assert all(
        call.parameters["snapshot_at"][1] == "2026-09-30T00:00:00Z" for call in reader.calls[1:]
    )
    assert all(call.parameters["store"][1] == "mx-fashion" for call in reader.calls)


def test_optional_null_is_not_zero(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    reader.override["store_daily"] = [
        {
            **reader.query(
                build(PROJECT, "store_daily"), request_id="x", store_id="mx-fashion", generation=4
            )[0],
            "revenue_fulfilled": None,
        }
    ]
    data = service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"]
    assert data["fulfilled_revenue"] is None
    assert data["fulfillment_rate"] is None and data["fulfillment_gap"] is None


@pytest.mark.parametrize(
    "principal,grant,status",
    [
        (None, GRANT, 401),
        (PRINCIPAL, Grant("other", "mx-fashion", "B2B"), 403),
        (PRINCIPAL, Grant("tenant-test", "other-store", "B2B"), 403),
        (PRINCIPAL, Grant("tenant-test", "mx-fashion", "B2C"), 400),
    ],
)
def test_access_before_query(
    setup: tuple[DashboardService, FakeReader],
    principal: Principal | None,
    grant: Grant,
    status: int,
):
    service, reader = setup
    with pytest.raises(ReadError) as exc:
        service.customers(principal, grant)
    assert exc.value.status == status and reader.calls == []


def test_admin_still_needs_explicit_grant(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    admin = Principal("admin", "ADMIN_UP", frozenset())
    with pytest.raises(ReadError, match="store_forbidden"):
        service.customers(admin, GRANT)
    assert reader.calls == []


@pytest.mark.parametrize(
    "change,code",
    [
        ({"status": "initialized"}, "publication_head_invalid"),
        ({"receipt_status": None}, "publication_head_invalid"),
        ({"receipt_version": "0.9.0"}, "publication_head_invalid"),
        ({"receipt_generation": 3}, "publication_head_invalid"),
        ({"receipt_id": "b" * 64}, "publication_head_invalid"),
        ({"generation": 0, "receipt_generation": 0}, "invalid_publication"),
    ],
)
def test_invalid_head_fails_closed(
    setup: tuple[DashboardService, FakeReader], change: dict[str, Any], code: str
):
    service, reader = setup
    reader.override["head"] = [{**head(reader.policy), **change}]
    with pytest.raises(ReadError, match=code):
        service.customers(PRINCIPAL, GRANT)


def test_receipt_window_resolves_null_head_without_extra_query(
    setup: tuple[DashboardService, FakeReader],
):
    service, reader = setup
    result = service.customers(PRINCIPAL, GRANT)
    assert result["metadata"]["report_from"] == reader.policy.report_from
    assert result["metadata"]["report_to"] == reader.policy.report_to
    assert [call.name for call in reader.calls] == ["head", "customers"]
    sql = reader.calls[0].sql
    assert "r.record_kind='RECEIPT'" in sql
    assert "r.store_id=h.store_id" in sql
    assert "r.policy_hash=h.policy_hash" in sql
    assert "r.publication_id=h.publication_id" in sql


def test_matching_head_window_remains_valid(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    reader.override["head"] = [
        {
            **head(reader.policy),
            "report_from": reader.policy.report_from,
            "report_to": reader.policy.report_to,
        }
    ]
    result = service.customers(PRINCIPAL, GRANT)
    assert result["metadata"]["report_from"] == reader.policy.report_from
    assert result["metadata"]["report_to"] == reader.policy.report_to


@pytest.mark.parametrize(
    "change",
    [
        {"report_from": "2026-09-02"},
        {"report_to": "2026-09-27"},
        {"receipt_from": None},
        {"receipt_to": None},
        {"receipt_from": "not-a-date"},
        {"receipt_to": "2026-09-01"},
        {"receipt_store_id": "another-store"},
        {"receipt_policy_hash": "c" * 64},
        {"receipt_watermark": "c" * 64},
        {"receipt_as_of": "2026-09-27T03:00:00Z"},
    ],
)
def test_inconsistent_publication_fails_closed(
    setup: tuple[DashboardService, FakeReader], change: dict[str, Any]
):
    service, reader = setup
    reader.override["head"] = [{**head(reader.policy), **change}]
    with pytest.raises(ReadError, match="publication_head_invalid"):
        service.customers(PRINCIPAL, GRANT)
    assert [call.name for call in reader.calls] == ["head"]


def test_receipt_window_must_match_approved_policy(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    reader.override["head"] = [{**head(reader.policy), "receipt_from": "2026-09-02"}]
    with pytest.raises(ReadError, match="invalid_publication"):
        service.customers(PRINCIPAL, GRANT)


def test_head_missing_and_duplicate(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    reader.override["head"] = []
    with pytest.raises(ReadError, match="publication_head_missing"):
        service.customers(PRINCIPAL, GRANT)
    reader.override["head"] = [head(reader.policy), head(reader.policy)]
    with pytest.raises(ReadError, match="publication_head_duplicate_or_invalid"):
        service.customers(PRINCIPAL, GRANT)


def test_duplicate_receipt_join_fails_closed(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    # A duplicate RECEIPT produces two joined rows for the same HEAD.
    reader.override["head"] = [
        head(reader.policy),
        {**head(reader.policy), "receipt_to": "2026-09-27"},
    ]
    with pytest.raises(ReadError, match="publication_head_duplicate_or_invalid"):
        service.customers(PRINCIPAL, GRANT)


def test_publication_resolution_is_store_and_generation_agnostic(policy: AnalyticsPolicy):
    another = replace(
        policy,
        store_id="synthetic-second-store",
        report_from="2026-09-02",
        report_to="2026-09-05",
    )
    grant = Grant("synthetic-second-tenant", another.store_id, "B2B")
    principal = Principal("synthetic-second-user", "CLIENT_USER", frozenset({grant}))
    reader = FakeReader(another)
    reader.override["head"] = [
        {
            **head(another),
            "generation": 9,
            "receipt_generation": 9,
            "publication_id": "c" * 64,
            "receipt_id": "c" * 64,
        }
    ]
    service = DashboardService(PROJECT, {another.store_id: another}, lambda: reader, KEY)
    result = service.customers(principal, grant)
    assert result["metadata"]["store_id"] == another.store_id
    assert result["metadata"]["generation"] == 9
    assert result["metadata"]["report_from"] == another.report_from
    assert result["metadata"]["report_to"] == another.report_to
    assert reader.calls[0].parameters["store"][1] == another.store_id
    assert reader.calls[0].parameters["policy"][1] == another.policy_hash


def test_customer_cursor_and_isolation(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    first = service.customers(PRINCIPAL, GRANT, size="1")
    assert [r["customer_id"] for r in first["data"]] == ["c1"]
    assert first["pagination"]["has_more"] is True
    second = service.customers(PRINCIPAL, GRANT, size="1", cursor=first["pagination"]["cursor"])
    assert [r["customer_id"] for r in second["data"]] == ["c2"]
    assert second["pagination"]["cursor"] is None
    assert all("email" not in r and "cnpj" not in r for r in first["data"])
    with pytest.raises(ReadError, match="invalid_cursor"):
        service.customers(PRINCIPAL, GRANT, size="2", cursor=first["pagination"]["cursor"])
    with pytest.raises(ReadError, match="invalid_cursor"):
        service.customers(PRINCIPAL, GRANT, size="1", cursor="tampered")
    with pytest.raises(ReadError, match="invalid_cursor"):
        service.customers(PRINCIPAL, GRANT, size="1", cursor="!")
    assert reader.calls[-1].name == "head"


def test_customer_foreign_store_is_not_found(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    with pytest.raises(ReadError, match="customer_not_found"):
        service.customer(PRINCIPAL, GRANT, "foreign-customer")
    assert not any(call.name == "customer_summary" for call in reader.calls)


def test_customer_summary_and_canceled_order(setup: tuple[DashboardService, FakeReader]):
    service, _ = setup
    detail = service.customer(PRINCIPAL, GRANT, "c1")
    assert detail["data"]["commercial"]["requested_revenue_observed"] == "100.25"
    assert detail["data"]["commercial"]["fulfilled_revenue_observed"] == "75.50"
    assert detail["data"]["commercial"]["ltv_complete"] is None
    orders = service.customer_orders(PRINCIPAL, GRANT, "c1", size="1")
    assert orders["data"][0]["order_status"] == "CANCELED"
    assert orders["data"][0]["requested_total"] == "20.00"
    assert orders["data"][0]["fulfilled_total"] == "0.00"
    assert "core_orders_not_source_generation_pinned" in orders["metadata"]["limitations"]


def test_retention_cohort_immaturity_and_product_id(setup: tuple[DashboardService, FakeReader]):
    service, _ = setup
    retention = service.retention(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    assert retention["data"]["progression"][0]["customers_reached_observed"] == 1
    assert retention["data"]["cohorts"][0]["rate"] is None
    products = service.products(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    assert products["data"][0]["product_id"] is None
    assert products["data"][0]["buyers_unique"] is None


@pytest.mark.parametrize("share", [Decimal("0.25"), Decimal("0"), None])
def test_product_share_preserves_decimal_null_and_full_period_denominator(setup, share):
    service, reader = setup
    original = reader.query

    def query(q, **kwargs):
        rows = original(q, **kwargs)
        if q.name == "products":
            rows[0]["requested_share_observed"] = share
            assert "FROM grouped" in q.sql
            assert "COUNTIF(requested IS NULL)>0,NULL,SUM(requested)" in q.sql
            assert "SAFE_DIVIDE(g.requested,t.requested_total)" in q.sql
            assert q.sql.index("FROM grouped") < q.sql.index("g.cursor_key>@after")
        return rows

    reader.query = query
    data = service.products(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"]
    assert data[0]["requested_share_observed"] == (None if share is None else format(share, "f"))


def test_funnel_event_grain_and_geography_gate(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    funnel = service.funnel(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    assert funnel["data"]["totals"]["purchase"] == 1
    reader.override["funnel_daily"] = [
        {
            **reader.query(
                build(PROJECT, "funnel_daily"), request_id="x", store_id="mx-fashion", generation=4
            )[0],
            "observation_complete": False,
        }
    ]
    with pytest.raises(ReadError, match="analytics_facts_coverage_incomplete"):
        service.funnel(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    reader.override["geography"] = []
    geography = service.geography(PRINCIPAL, GRANT)
    assert geography["data"]["states"] == []
    assert geography["data"]["coverage"]["basis"] == "order_shipping_location"


def test_scope_values_are_parameters_not_sql(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    service.customer(PRINCIPAL, GRANT, "c1")
    query = next(call for call in reader.calls if call.name == "customer")
    assert "c1" not in query.sql and "mx-fashion" not in query.sql
    assert query.parameters["store"] == ("STRING", "mx-fashion")
    assert query.parameters["customer"] == ("STRING", "c1")
    assert "FOR SYSTEM_TIME AS OF @snapshot_at" in query.sql


def test_page_size_and_interval_validation(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    with pytest.raises(ReadError, match="invalid_page_size"):
        service.customers(PRINCIPAL, GRANT, size="101")
    with pytest.raises(ReadError, match="interval_outside_publication"):
        service.overview(PRINCIPAL, GRANT, from_day="2026-08-01", to_day="2026-09-02")
    assert [c.name for c in reader.calls] == ["head", "head"]


def test_transport_budget_and_sanitized_errors():
    budget = ReadBudget(PROJECT, "southamerica-east1", 100, 100)
    job = Mock()
    job.result.return_value = []
    job.total_bytes_processed = 7
    client = Mock()
    client.query.return_value = job
    session = BigQueryReadSession(client, budget)
    query = build(PROJECT, "head", store="mx-fashion", policy="a" * 64)
    session.query(query, request_id="synthetic", store_id="mx-fashion", generation=None)
    assert client.query.call_args.kwargs["job_config"].maximum_bytes_billed == 100
    assert client.query.call_args.kwargs["job_retry"] is None
    with pytest.raises(ReadError, match="query_budget_exceeded"):
        session.query(query, request_id="synthetic", store_id="mx-fashion", generation=None)
    client.query.side_effect = BadRequest("Query exceeded maximum bytes billed: secret-customer")
    with pytest.raises(ReadError) as exc:
        BigQueryReadSession(client, budget).query(
            query, request_id="synthetic", store_id="mx-fashion", generation=None
        )
    assert exc.value.code == "query_budget_exceeded" and "secret-customer" not in str(exc.value)
    client.query.side_effect = RuntimeError("raw SQL and private@email.invalid")
    with pytest.raises(ReadError) as exc:
        BigQueryReadSession(client, budget).query(
            query, request_id="synthetic", store_id="mx-fashion", generation=None
        )
    assert exc.value.code == "bigquery_read_failed" and "private@email.invalid" not in str(
        exc.value
    )


def test_wsgi_requires_injected_auth_and_never_leaks_exception(
    setup: tuple[DashboardService, FakeReader],
):
    service, _ = setup
    app = create_wsgi_app(lambda: service, lambda _: None)
    response: list[str] = []
    body = b"".join(
        app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/v1/customers",
                "QUERY_STRING": "tenant_id=tenant-test&store_id=mx-fashion&operation=B2B",
            },
            lambda status, headers: response.append(status),
        )
    )
    assert (
        response == ["401 Unauthorized"] and json.loads(body)["error"]["code"] == "unauthenticated"
    )
    with pytest.raises(ReadError, match="unsupported_filter"):
        dispatch(
            service,
            "GET",
            "/v1/customers",
            {
                "tenant_id": ["tenant-test"],
                "store_id": ["mx-fashion"],
                "operation": ["B2B"],
                "paid_media_influenced": ["false"],
            },
            PRINCIPAL,
        )


class ExtendedReader(FakeReader):
    """Deterministic synthetic source rows, filtered like the read projections."""

    def query(self, query: Query, **kwargs: Any) -> list[dict[str, Any]]:
        if query.name == "store_orders":
            self.calls.append(query)
            p = {k: v[1] for k, v in query.parameters.items()}
            rows = [
                {
                    "order_id": f"order-{i}",
                    "customer_id": "c1" if i < 2 else None,
                    "created_at": f"2026-09-0{i + 1}T12:00:00Z",
                    "order_status": status,
                    "payment_status": "unpaid",
                    "requested_total": Decimal("20.00"),
                    "fulfilled_total": None if i == 1 else Decimal("0.00"),
                    "requested_items_qty": 2,
                    "fulfilled_items_qty": None,
                    "cursor_key": f"2026-09-0{i + 1}T12:00:00.000000Z:order-{i}",
                }
                for i, status in enumerate(["CANCELED", "CONFIRMED", "SHIPPED"])
            ]
            return [
                r
                for r in rows
                if p["from"] <= r["created_at"][:10] < p["to"]
                and (p["status"] is None or p["status"] == r["order_status"])
                and r["cursor_key"] > p["after"]
            ][: p["limit"]]
        if query.name == "acquisition_first":
            self.calls.append(query)
            if query.name in self.override:
                return self.override[query.name]
            # c1 has its first purchase before the selected period, not a new first purchase.
            start, end = query.parameters["from"][1], query.parameters["to"][1]
            first = [
                {"customer": "c1", "day": "2026-09-01", "requested": Decimal("40.25")},
                {"customer": "c2", "day": "2026-09-03", "requested": Decimal("50.00")},
            ]
            selected = [r for r in first if start <= r["day"] < end]
            return [
                {
                    "customers": len(selected),
                    "orders": len(selected),
                    "invalid_first_orders": 0,
                    "requested": sum((r["requested"] for r in selected), Decimal(0)),
                    "fulfilled": Decimal("0.00"),
                }
            ]
        return super().query(query, **kwargs)


@pytest.fixture
def extended(policy: AnalyticsPolicy) -> tuple[DashboardService, ExtendedReader]:
    reader = ExtendedReader(policy)
    return DashboardService(PROJECT, {policy.store_id: policy}, lambda: reader, KEY), reader


def test_store_orders_route_scope_period_status_null_and_cancelled(extended):
    service, reader = extended
    query = {
        "tenant_id": [GRANT.tenant_id],
        "store_id": [GRANT.store_id],
        "operation": ["B2B"],
        "from": ["2026-09-01"],
        "to": ["2026-09-03"],
        "page_size": ["100"],
    }
    status, response = dispatch(service, "GET", "/v1/orders", query, PRINCIPAL)
    assert status == 200
    assert [o["order_status"] for o in response["data"]] == ["CANCELED", "CONFIRMED"]
    assert response["data"][1]["fulfilled_total"] is None
    assert response["data"][0]["fulfilled_total"] == "0.00"
    assert response["data"][0]["requested_total"] == "20.00"
    assert response["data"][0]["payment_status"] == "unpaid"
    sql = reader.calls[-1]
    assert "store_id=@store AND source_system='upzero'" in sql.sql
    assert "DATE(created_at,@timezone)>=@from" in sql.sql
    assert "ORDER BY created_at,order_id LIMIT @limit" in sql.sql
    assert sql.parameters["timezone"][1] == "America/Sao_Paulo"
    assert sql.parameters["snapshot_at"][1] == head(reader.policy)["snapshot_at"]
    assert sql.parameters["as_of"][1] == reader.policy.as_of
    _, filtered = dispatch(
        service, "GET", "/v1/orders", {**query, "status": ["CANCELED"]}, PRINCIPAL
    )
    assert len(filtered["data"]) == 1 and filtered["data"][0]["order_status"] == "CANCELED"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size": "0"},
        {"size": "101"},
        {"size": "bad"},
        {"status": "x' OR 1=1"},
        {"from_day": "2026-08-01"},
        {"cursor": "invalid"},
    ],
)
def test_orders_invalid_filters_fail_without_orders_query(extended, kwargs):
    service, reader = extended
    with pytest.raises(ReadError):
        service.orders(PRINCIPAL, GRANT, **kwargs)
    assert not any(q.name == "store_orders" for q in reader.calls)


@pytest.mark.parametrize("resource", ["orders", "acquisition"])
def test_new_endpoints_isolate_store_before_read(extended, resource):
    service, reader = extended
    with pytest.raises(ReadError, match="store_forbidden"):
        getattr(service, resource)(PRINCIPAL, Grant(GRANT.tenant_id, "foreign-store", "B2B"))
    assert reader.calls == []


def test_orders_cursor_binds_period_status_size_and_generation(extended):
    service, reader = extended
    first = service.orders(PRINCIPAL, GRANT, size="1")
    token = first["pagination"]["cursor"]
    assert token and first["pagination"]["has_more"]
    second = service.orders(PRINCIPAL, GRANT, size="1", cursor=token)
    assert first["data"][0]["order_id"] != second["data"][0]["order_id"]
    for changes in [{"status": "CANCELED"}, {"from_day": "2026-09-02"}, {"size": "2"}]:
        with pytest.raises(ReadError, match="invalid_cursor"):
            service.orders(PRINCIPAL, GRANT, **{"size": "1", "cursor": token, **changes})
    reader.override["head"] = [{**head(reader.policy), "generation": 5, "receipt_generation": 5}]
    with pytest.raises(ReadError, match="invalid_cursor"):
        service.orders(PRINCIPAL, GRANT, size="1", cursor=token)


def test_acquisition_first_purchase_full_history_then_period(extended):
    service, reader = extended
    response = service.acquisition(PRINCIPAL, GRANT, from_day="2026-09-02", to_day="2026-09-04")
    data = response["data"]
    assert data["first_purchase_customers_observed"] == data["first_purchase_orders_observed"] == 1
    assert data["requested_first_purchase_observed"] == "50.00"
    assert data["fulfilled_first_purchase_observed"] == "0.00"
    assert data["confirmed_new_customers"] is None
    assert response["metadata"]["history_complete"] is False
    sql = reader.calls[-1].sql
    assert "purchase_number=1" in sql
    assert "FROM first_orders WHERE order_date>=@from AND order_date<@to" in sql
    assert "COUNT(*) OVER(PARTITION BY customer_id)" in sql
    assert "COUNT(*) OVER(PARTITION BY order_id)" in sql
    assert all(
        q.parameters["snapshot_at"][1] == head(reader.policy)["snapshot_at"]
        for q in reader.calls[1:]
    )


def test_acquisition_null_and_duplicate_first_purchase_fail_closed(extended):
    service, reader = extended
    row = {
        "customers": 1,
        "orders": 1,
        "invalid_first_orders": 0,
        "requested": None,
        "fulfilled": None,
    }
    reader.override["acquisition_first"] = [row]
    result = service.acquisition(PRINCIPAL, GRANT)["data"]
    assert result["requested_first_purchase_observed"] is None
    assert result["fulfilled_first_purchase_observed"] is None
    reader.override["acquisition_first"] = [{**row, "invalid_first_orders": 1}]
    with pytest.raises(ReadError, match="invalid_first_purchase_sequence"):
        service.acquisition(PRINCIPAL, GRANT)


def test_customer_period_filter_is_parameterized_and_cursor_bound(setup):
    service, reader = setup
    first = service.customers(
        PRINCIPAL, GRANT, size="1", from_day="2026-09-01", to_day="2026-09-02"
    )
    sql = reader.calls[-1]
    assert "AND EXISTS" in sql.sql and "s.customer_id=m.customer_id" in sql.sql
    assert sql.parameters["from"][1] == "2026-09-01"
    assert sql.parameters["to"][1] == "2026-09-02"
    assert sql.sql.count("FOR SYSTEM_TIME AS OF @snapshot_at") == 4
    with pytest.raises(ReadError, match="invalid_cursor"):
        service.customers(
            PRINCIPAL,
            GRANT,
            size="1",
            cursor=first["pagination"]["cursor"],
            from_day="2026-09-02",
            to_day="2026-09-03",
        )


def test_acquisition_http_route(extended):
    service, _ = extended
    status, result = dispatch(
        service,
        "GET",
        "/v1/acquisition",
        {"store_id": [GRANT.store_id], "tenant_id": [GRANT.tenant_id], "operation": ["B2B"]},
        PRINCIPAL,
    )
    assert status == 200 and result["data"]["first_purchase_orders_observed"] == 2


class CustomerPeriodReader(FakeReader):
    """Synthetic observed qualifying purchases; model the EXISTS selection only."""

    def query(
        self, query: Query, *, request_id: str, store_id: str, generation: int | None
    ) -> list[dict[str, Any]]:
        if query.name != "customers" or "from" not in query.parameters:
            return super().query(
                query, request_id=request_id, store_id=store_id, generation=generation
            )
        self.calls.append(query)
        p = {key: value[1] for key, value in query.parameters.items()}
        purchases = [
            (self.policy.store_id, "c1", "2026-09-01"),
            (self.policy.store_id, "c1", "2026-09-02"),
            (self.policy.store_id, "c2", "2026-09-02"),
            ("synthetic-foreign-store", "c1", "2026-09-10"),
        ]
        buyers = {
            customer
            for store, customer, day in purchases
            if store == p["store"] and p["from"] <= day < p["to"]
        }
        return [
            row
            for row in [customer_row(), customer_row("c2", "b" * 64)]
            if row["customer_id"] in buyers and row["cursor_key"] > p["after"]
        ][: p["limit"]]


@pytest.fixture
def customer_period_setup(policy: AnalyticsPolicy) -> tuple[DashboardService, CustomerPeriodReader]:
    reader = CustomerPeriodReader(policy)
    return DashboardService(PROJECT, {policy.store_id: policy}, lambda: reader, KEY), reader


def test_customer_period_sql_alias_snapshot_correlation_and_parameters():
    query = build(
        PROJECT,
        "customers",
        store="synthetic-store' OR TRUE --",
        policy="synthetic-policy' OR TRUE --",
        from_day="2026-09-01' OR TRUE --",
        to_day="2026-09-28' OR TRUE --",
        after="synthetic-cursor' OR TRUE --",
        limit=26,
        snapshot_at="2026-09-30T00:00:00Z",
    )
    sql = " ".join(query.sql.split())
    assert "AS s FOR SYSTEM_TIME AS OF @snapshot_at" in sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at s" not in sql
    assert "SELECT 1 FROM" in sql and "AND EXISTS (" in sql
    assert "s.store_id=m.store_id" in sql and "store_id=@store" in sql
    assert "s.policy_hash=@policy" in sql
    assert "s.customer_id=m.customer_id" in sql
    assert "s.order_date>=@from AND s.order_date<@to" in sql
    assert query.parameters["store"][0] == "STRING"
    assert query.parameters["from"][0] == query.parameters["to"][0] == "DATE"
    for name in ("store", "policy", "from", "to", "after", "snapshot_at"):
        assert query.parameters[name][1] not in query.sql


@pytest.mark.parametrize(
    "name",
    [
        "head",
        "store_daily",
        "customer_period",
        "customers",
        "customer",
        "store_orders",
        "acquisition_first",
        "orders",
        "customer_summary",
        "retention_distribution",
        "retention_cohorts",
        "retention_gaps",
        "products",
        "funnel_daily",
    ],
)
def test_dashboard_time_travel_has_no_trailing_alias(name: str):
    query = build(PROJECT, name, from_day="2026-09-01", to_day="2026-09-28")
    # Time-travel ends at a SQL clause; aliases must precede FOR SYSTEM_TIME.
    following_tokens = re.findall(r"FOR SYSTEM_TIME AS OF @snapshot_at\s+(\w+)", query.sql)
    assert all(token in {"WHERE", "JOIN", "ON"} for token in following_tokens)
    assert len(following_tokens) == query.sql.count("FOR SYSTEM_TIME AS OF @snapshot_at")


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2026-09-01", "2026-09-02", ["c1"]),
        ("2026-09-01", "2026-09-03", ["c1", "c2"]),
        ("2026-09-03", "2026-09-04", []),
        # A purchase from another store must not select the same customer ID here.
        ("2026-09-10", "2026-09-11", []),
    ],
)
def test_customer_period_http_valid_rows_or_empty_list(customer_period_setup, start, end, expected):
    service, reader = customer_period_setup
    status, result = dispatch(
        service,
        "GET",
        "/v1/customers",
        {
            "tenant_id": [GRANT.tenant_id],
            "store_id": [GRANT.store_id],
            "operation": ["B2B"],
            "from": [start],
            "to": [end],
            "page_size": ["25"],
        },
        PRINCIPAL,
    )
    assert status == 200
    assert [row["customer_id"] for row in result["data"]] == expected
    assert result["pagination"] == {"page_size": 25, "cursor": None, "has_more": False}
    assert reader.calls[-1].parameters["store"] == ("STRING", GRANT.store_id)
    assert reader.calls[-1].parameters["from"] == ("DATE", start)
    assert reader.calls[-1].parameters["to"] == ("DATE", end)


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-08-31", "2026-09-02"), ("2026-09-01", "2026-09-29")],
)
def test_customer_period_outside_publication_is_400(customer_period_setup, start, end):
    service, reader = customer_period_setup
    with pytest.raises(ReadError, match="interval_outside_publication") as error:
        service.customers(PRINCIPAL, GRANT, from_day=start, to_day=end)
    assert error.value.status == 400
    assert not any(query.name == "customers" for query in reader.calls)


def test_customer_period_cursor_valid_and_bound_to_period(customer_period_setup):
    service, reader = customer_period_setup
    args = {"from_day": "2026-09-01", "to_day": "2026-09-03", "size": "1"}
    first = service.customers(PRINCIPAL, GRANT, **args)
    assert [row["customer_id"] for row in first["data"]] == ["c1"]
    token = first["pagination"]["cursor"]
    assert token is not None and first["pagination"]["has_more"]
    second = service.customers(PRINCIPAL, GRANT, cursor=token, **args)
    assert [row["customer_id"] for row in second["data"]] == ["c2"]
    assert second["pagination"]["cursor"] is None
    assert second["metadata"]["generation"] == first["metadata"]["generation"]
    reader.calls.clear()
    with pytest.raises(ReadError, match="invalid_cursor") as error:
        service.customers(PRINCIPAL, GRANT, cursor=token, **{**args, "from_day": "2026-09-02"})
    assert error.value.status == 400
    assert not any(query.name == "customers" for query in reader.calls)


def test_customer_period_unauthorized_store_fails_before_any_read(customer_period_setup):
    service, reader = customer_period_setup
    with pytest.raises(ReadError, match="store_forbidden") as error:
        service.customers(
            PRINCIPAL,
            Grant(GRANT.tenant_id, "synthetic-foreign-store", "B2B"),
            from_day="2026-09-01",
            to_day="2026-09-28",
        )
    assert error.value.status == 403
    assert reader.calls == []


def test_read_diagnostics_do_not_change_query_budget_or_cache_policy():
    budget = ReadBudget(PROJECT, "southamerica-east1", 100, 200)
    client = Mock()
    client.query.return_value = Mock(total_bytes_processed=7, slot_millis=11, cache_hit=False)
    client.query.return_value.result.return_value = []
    session = BigQueryReadSession(client, budget)
    for _ in range(2):
        session.query(
            build(PROJECT, "head"), request_id="synthetic", store_id="mx-fashion", generation=None
        )
    assert session.query_count == 2
    assert session.bytes_processed == 14 and session.slot_ms == 22
    assert session.cache_hits == 0 and session.query_duration_ms >= 0
    assert session.reserved_bytes == 200
    assert all(
        call.kwargs["job_config"].use_query_cache is False for call in client.query.call_args_list
    )


def test_overview_quantity_and_retention_fields_use_existing_evidence(setup):
    service, reader = setup
    service.catalog_enabled = True
    reader.override["operational_leads"] = [
        {
            "generated": 0,
            "approved": 0,
            "converted": 0,
            "conflicts": 0,
            "invalid_identity": 0,
            "unresolved_approved": 0,
        }
    ]
    data = service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"]
    assert data["requested_pieces"] == 11
    assert data["fulfilled_pieces"] == 7
    assert data["requested_pieces_per_order"] == "5.5"
    assert data["retention_ticket_observed"] == "50.25"
    assert data["repeat_mean_days_observed"] is None
    assert data["revenue_paid"] is None and data["ltv_complete"] is None
    reader.override["order_quantity_summary"] = [
        {
            "orders": 2,
            "duplicate_orders": 0,
            "invalid_identity": 0,
            "requested_pieces": None,
            "fulfilled_pieces": 0,
        }
    ]
    data = service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"]
    assert data["requested_pieces"] is None and data["requested_pieces_per_order"] is None
    assert data["fulfilled_pieces"] == 0


@pytest.mark.parametrize(
    "field,value", [("orders", 3), ("duplicate_orders", 1), ("invalid_identity", 1)]
)
def test_overview_quantity_summary_must_reconcile_with_analytics(setup, field, value):
    service, reader = setup
    service.catalog_enabled = True
    reader.override["order_quantity_summary"] = [
        {
            "orders": 2,
            "duplicate_orders": 0,
            "invalid_identity": 0,
            "requested_pieces": 11,
            "fulfilled_pieces": 7,
            field: value,
        }
    ]
    with pytest.raises(ReadError, match="order_quantity_summary_not_reconciled"):
        service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")


def test_overview_bundle_is_one_pinned_aggregate_read(setup):
    service, reader = setup
    service.catalog_enabled = True
    result = service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    assert [q.name for q in reader.calls] == ["head", "overview_details"]
    query = reader.calls[-1]
    assert query.parameters["snapshot_at"][1] == service.publication.snapshot_at
    assert query.parameters["store"][1] == GRANT.store_id
    assert result["metadata"]["generation"] == 4
    assert result["data"]["requested_revenue"] == "100.25"
    assert result["data"]["fulfilled_revenue"] == "75.50"
    assert result["data"]["revenue_paid"] is None


@pytest.mark.parametrize("value", [[], [{"daily": []}], [{"daily": "invalid"}]])
def test_overview_bundle_malformed_envelope_fails_closed(setup, value):
    service, reader = setup
    service.catalog_enabled = True
    reader.override["overview_details"] = value
    with pytest.raises(ReadError, match="overview_details_invalid"):
        service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")


def test_overview_bundle_retains_daily_coverage_and_policy_guards(setup):
    service, reader = setup
    service.catalog_enabled = True
    reader.override["store_daily"] = []
    with pytest.raises(ReadError, match="analytics_daily_coverage_incomplete"):
        service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    reader.override["store_daily"] = [{"order_date": "2026-09-01", "currency": "USD"}]
    with pytest.raises(ReadError, match="analytics_policy_mismatch"):
        service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")


def test_overview_bundle_sql_is_bounded_and_parameterized():
    query = build(
        PROJECT,
        "overview_details",
        store="synthetic-store-not-in-sql",
        policy="synthetic-policy-not-in-sql",
        snapshot_at="2026-09-30T00:00:00Z",
        as_of="2026-09-28T03:00:00Z",
        from_day="2026-09-01",
        to_day="2026-09-02",
        timezone="America/Sao_Paulo",
    )
    assert "synthetic-store-not-in-sql" not in query.sql
    assert "synthetic-policy-not-in-sql" not in query.sql
    assert query.sql.count("FOR SYSTEM_TIME AS OF @snapshot_at") >= 4
    assert "@from" in query.sql and "@to" in query.sql
    assert "@store" in query.sql and "@policy" in query.sql
    for field in ("daily", "population", "quantities", "leads"):
        assert f"AS {field}" in query.sql


def test_paid_order_count_never_becomes_paid_money(setup):
    svc, reader = setup
    svc.catalog_enabled = True
    data = svc.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"]
    assert data["orders_paid"] == 1
    assert data["orders_paid_rate"] == "50"
    assert data["revenue_paid"] is None
    assert data["fulfilled_revenue"] == "75.50"
    reader.override["order_quantity_summary"] = [
        {
            "orders": 2,
            "paid_orders": 1,
            "unknown_payment_status": 1,
            "duplicate_orders": 0,
            "invalid_identity": 0,
            "requested_pieces": 11,
            "fulfilled_pieces": 7,
        }
    ]
    assert (
        svc.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"][
            "orders_paid"
        ]
        is None
    )
    assert (
        svc.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"][
            "orders_paid_rate"
        ]
        is None
    )
    reader.override["order_quantity_summary"][0]["paid_orders"] = 3
    with pytest.raises(ReadError, match="order_payment_summary_invalid"):
        svc.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")


def test_exact_purchase_progression_preserves_fifth_and_sixth_and_null_money(setup):
    svc, reader = setup
    svc.catalog_enabled = True
    reader.override["retention_exact_stages"] = [
        {
            "stage": 5,
            "buyers": 2,
            "orders": 2,
            "duplicate_orders": 0,
            "invalid_identity": 0,
            "requested": Decimal("20.01"),
            "mean_days": 3,
        },
        {
            "stage": 6,
            "buyers": 1,
            "orders": 1,
            "duplicate_orders": 0,
            "invalid_identity": 0,
            "requested": None,
            "mean_days": 4,
        },
    ]
    r = svc.retention(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    data = r["data"]
    assert len(data["exact_purchase_stages"]) == 6
    assert data["exact_purchase_stages"][4]["buyers_observed"] == 2
    assert data["exact_purchase_stages"][5]["buyers_observed"] == 1
    assert data["exact_purchase_stages"][4]["requested_revenue_observed"] == "20.01"
    assert data["exact_purchase_stages"][5]["requested_revenue_observed"] is None
    assert data["exact_purchase_stages"][5]["accumulated_requested_revenue_observed"] is None
    assert all(s["continuation_observed"] is None for s in data["exact_purchase_stages"])
    assert r["metadata"]["history_complete"] is False
    reader.override["retention_exact_stages"].append(reader.override["retention_exact_stages"][0])
    with pytest.raises(ReadError, match="retention_exact_stages_invalid"):
        svc.retention(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")


def test_exact_progression_sql_uses_sequence_not_five_plus_bucket():
    q = build(
        PROJECT,
        "retention_exact_stages",
        store="synthetic-user-input",
        from_day="2026-09-01",
        to_day="2026-09-02",
    )
    assert "synthetic-user-input" not in q.sql
    for guard in (
        "purchase_number BETWEEN 1 AND 6",
        "order_date>=@from",
        "order_date<@to",
        "store_id=@store",
        "policy_hash=@policy",
        "FOR SYSTEM_TIME AS OF @snapshot_at",
        "LAG(order_at)",
        "COUNT(DISTINCT order_id)",
        "LIMIT 7",
    ):
        assert guard in q.sql
    assert "purchase_bucket" not in q.sql and "5+" not in q.sql
