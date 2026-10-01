"""Synthetic-only contract tests; no GCP client or customer records."""

import json
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
        "report_from": policy.report_from,
        "report_to": policy.report_to,
        "source_watermark": "b" * 64,
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
        if query.name == "head":
            return [head(self.policy)]
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


def test_head_missing_and_duplicate(setup: tuple[DashboardService, FakeReader]):
    service, reader = setup
    reader.override["head"] = []
    with pytest.raises(ReadError, match="publication_head_missing"):
        service.customers(PRINCIPAL, GRANT)
    reader.override["head"] = [head(reader.policy), head(reader.policy)]
    with pytest.raises(ReadError, match="publication_head_duplicate_or_invalid"):
        service.customers(PRINCIPAL, GRANT)


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
    with pytest.raises(ReadError, match="geography_coverage_not_certified"):
        service.geography(PRINCIPAL, GRANT)


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
