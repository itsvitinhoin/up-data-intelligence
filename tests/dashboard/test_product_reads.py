"""Synthetic scoped drill-down and geographic coverage contracts."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, ReadError
from src.dashboard.http import dispatch
from src.dashboard.queries import build
from src.dashboard.service import DashboardService
from tests.dashboard.test_read_api import GRANT, KEY, PRINCIPAL, PROJECT, FakeReader


@pytest.fixture
def setup():
    policy = AnalyticsPolicy.from_dict(
        json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    )
    reader = FakeReader(policy)
    reader.override["order_detail"] = [
        {
            "store_id": GRANT.store_id,
            "order_id": "o1",
            "customer_id": "c1",
            "version_id": "v1",
            "created_at": "2026-09-01T12:00:00Z",
            "order_status": "CANCELED",
            "payment_status": "unpaid",
            "requested_total": Decimal("8.99"),
            "fulfilled_total": Decimal("0.00"),
            "requested_items_qty": 3,
            "fulfilled_items_qty": 0,
            "items_count": 1,
            "customer_company_name": "Empresa sintética",
        }
    ]
    reader.override["order_detail_items"] = [
        {
            "order_id": "o1",
            "item_id": "i1",
            "parent_order_version_id": "v1",
            "product_key": "d" * 64,
            "variant_id": "variant-1",
            "sku": "SKU",
            "status": "removed",
            "original_qty": 3,
            "qty": 3,
            "unit_price": Decimal("3.33"),
        }
    ]
    reader.override["geography"] = []
    return DashboardService(PROJECT, {policy.store_id: policy}, lambda: reader, KEY), reader


def test_order_detail_decimal_requested_fulfilled_and_safe_profile(setup):
    service, reader = setup
    response = service.order(PRINCIPAL, GRANT, "o1")
    data = response["data"]
    assert data["order"]["order_status"] == "CANCELED"
    assert data["order"]["payment_status"] == "unpaid"
    assert data["items"][0]["requested_value"] == "9.99"
    assert data["items"][0]["fulfilled_value"] == "0.00"
    assert data["reconciliation"]["requested_order_adjustment"] == "-1.00"
    assert data["reconciliation"]["quantity_reconciled"] is True
    assert data["customer"]["name"] == "Empresa sintética"
    assert all(data["customer"][k] is None for k in ("cnpj", "email", "phone"))
    assert response["metadata"]["history_complete"] is False
    assert all(c.parameters["snapshot_at"][1] == "2026-09-30T00:00:00Z" for c in reader.calls[1:])


def test_order_unknown_is_not_zero_or_reconciled(setup):
    service, reader = setup
    reader.override["order_detail"][0]["requested_items_qty"] = None
    reader.override["order_detail"][0]["customer_id"] = None
    reader.override["order_detail_items"][0]["original_qty"] = None
    data = service.order(PRINCIPAL, GRANT, "o1")["data"]
    assert data["customer"] is None
    assert data["items"][0]["requested_quantity"] is None
    assert data["items"][0]["requested_value"] is None
    assert data["reconciliation"]["quantity_reconciled"] is None
    assert data["reconciliation"]["gross_requested"] is None


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("parent_order_version_id", "old-version", "order_item_snapshot_mismatch"),
        ("original_qty", 4, "order_item_quantity_mismatch"),
        ("status", "unknown", "order_item_snapshot_mismatch"),
        ("unit_price", 3.33, "invalid_numeric_value"),
    ],
)
def test_order_detail_invalid_evidence_fails_closed(setup, field, value, error):
    service, reader = setup
    reader.override["order_detail_items"][0][field] = value
    with pytest.raises(ReadError, match=error):
        service.order(PRINCIPAL, GRANT, "o1")


def test_order_duplicate_and_foreign_entity_not_exposed(setup):
    service, reader = setup
    reader.override["order_detail"][0]["store_id"] = "foreign-store"
    with pytest.raises(ReadError, match="order_scope_mismatch"):
        service.order(PRINCIPAL, GRANT, "o1")
    reader.override["order_detail"] = []
    with pytest.raises(ReadError, match="order_not_found"):
        service.order(PRINCIPAL, GRANT, "foreign-order")


@pytest.mark.parametrize(
    "resource,entity", [("order", "o1"), ("product", "d" * 64), ("geography", None)]
)
def test_product_resources_authorize_before_query(setup, resource, entity):
    service, reader = setup
    foreign = Grant(GRANT.tenant_id, "other-store", "B2B")
    with pytest.raises(ReadError, match="store_forbidden"):
        if entity is None:
            service.geography(PRINCIPAL, foreign)
        else:
            getattr(service, resource)(PRINCIPAL, foreign, entity)
    assert reader.calls == []


def test_product_key_detail_preserves_unknown_stock_and_exact_buyers(setup):
    service, reader = setup
    row = reader.query(
        build(PROJECT, "products"), request_id="test", store_id=GRANT.store_id, generation=4
    )[0]
    reader.override["products"] = [dict(row, product_key="d" * 64)]
    reader.override["product_evidence"] = [
        {
            "product_key": "d" * 64,
            "duplicate_items": 0,
            "buyers_unique": 1,
            "variant_id": "variant-1",
            "name": None,
            "image": None,
        }
    ]
    data = service.product(PRINCIPAL, GRANT, "d" * 64)["data"]
    assert data["product_id"] is None and data["name"] is None and data["image"] is None
    assert data["sku"] == "SKU-TEST" and data["buyers_unique"] == 1
    assert data["requested_revenue"] == "100.25" and data["fulfilled_revenue"] == "75.50"
    assert data["stock"] is None and data["sizes"] is None and data["abc"] is None
    query = next(q for q in reader.calls if q.name == "product_evidence")
    assert query.parameters["product"] == ("STRING", "d" * 64)
    assert "d" * 64 not in query.sql


def test_geography_period_shipping_and_missing_location_are_explicit(setup):
    service, reader = setup
    reader.override["geography"] = [
        {
            "state": "SP",
            "orders": 2,
            "customers": 1,
            "requested": Decimal("10.25"),
            "fulfilled": Decimal("8.20"),
            "orders_without_customer": 0,
            "cities": [
                {
                    "city": "Cidade sintética",
                    "orders": 2,
                    "customers": 1,
                    "requested": Decimal("10.25"),
                    "fulfilled": Decimal("8.20"),
                }
            ],
        },
        {
            "state": None,
            "orders": 1,
            "customers": 0,
            "requested": None,
            "fulfilled": None,
            "orders_without_customer": 1,
            "cities": [],
        },
    ]
    data = service.geography(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")["data"]
    assert data["coverage"] == {
        "basis": "order_shipping_location",
        "orders_observed": 3,
        "mapped_orders": 2,
        "unmapped_orders": 1,
        "orders_without_customer": 1,
    }
    assert len(data["states"]) == 1
    state = data["states"][0]
    assert state["requested_revenue"] == "10.25" and state["average_ticket_requested"] == "5.125"
    assert state["approved_without_purchase"] is None and state["conversion_rate"] is None
    query = reader.calls[-1]
    assert query.parameters["from"] == ("DATE", "2026-09-01")
    assert query.parameters["to"] == ("DATE", "2026-09-02")


def test_geography_empty_period_is_valid_and_outside_publication_rejected(setup):
    service, _ = setup
    assert service.geography(PRINCIPAL, GRANT)["data"]["states"] == []
    with pytest.raises(ReadError, match="interval_outside_publication"):
        service.geography(PRINCIPAL, GRANT, from_day="2020-01-01", to_day="2020-01-02")


@pytest.mark.parametrize(
    "name", ["order_detail", "order_detail_items", "product_evidence", "geography"]
)
def test_product_sql_scope_time_travel_and_values_are_parameterized(name):
    query = build(
        PROJECT,
        name,
        store="store' injected",
        order="order' injected",
        product="d" * 64,
        from_day="2026-09-01",
        to_day="2026-09-02",
        snapshot_at="private-time",
    )
    assert "store_id=@store" in query.sql
    assert "store' injected" not in query.sql and "order' injected" not in query.sql
    assert "2026-09-01" not in query.sql and "private-time" not in query.sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at" in query.sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at o" not in query.sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at i" not in query.sql
    if name == "product_evidence":
        assert "o.version_id=i.parent_order_version_id" in query.sql
        assert "present_in_latest_snapshot" in query.sql
        assert "WHERE product_key=@product" in query.sql


def test_product_http_entity_routes_and_geography_period(setup):
    service, _ = setup
    query = {"store_id": [GRANT.store_id], "tenant_id": [GRANT.tenant_id], "operation": ["B2B"]}
    status, response = dispatch(service, "GET", "/v1/orders/o1", query, PRINCIPAL)
    assert status == 200 and response["data"]["order"]["order_id"] == "o1"
    status, response = dispatch(
        service,
        "GET",
        "/v1/geography",
        dict(query, **{"from": ["2026-09-01"], "to": ["2026-09-02"]}),
        PRINCIPAL,
    )
    assert status == 200 and response["data"]["coverage"]["orders_observed"] == 0
    with pytest.raises(ReadError, match="invalid_product_key"):
        dispatch(service, "GET", "/v1/products/name-fuzzy", query, PRINCIPAL)


def test_first_purchase_orders_existence_is_correlated_and_values_are_parameters(setup):
    service, reader = setup
    reader.override["store_orders"] = [
        dict(
            reader.query(
                build(PROJECT, "orders", customer="c1"),
                request_id="x",
                store_id=GRANT.store_id,
                generation=4,
            )[0],
            order_status="CONFIRMED",
        )
    ]
    out = service.orders(
        PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02", first_purchase=True
    )
    assert len(out["data"]) == 1
    q = next(q for q in reader.calls if q.name == "store_orders")
    assert q.parameters["first_purchase"] == ("BOOL", True)
    assert q.parameters["from"] == ("DATE", "2026-09-01")
    assert "EXISTS" in q.sql and "s.purchase_number=1" in q.sql
    assert "s.order_id=o.order_id" in q.sql and "s.customer_id=o.customer_id" in q.sql
    assert "s.source_order_version_id=o.version_id" in q.sql
    assert "s.store_id=o.store_id" in q.sql
    assert "2026-09-01" not in q.sql
    reader.override["store_orders"] = []
    assert service.orders(PRINCIPAL, GRANT, first_purchase=True)["data"] == []
    with pytest.raises(ReadError):
        service.orders(PRINCIPAL, GRANT, first_purchase="true")


def test_product_list_uses_unique_core_buyers_without_adding_daily_counts(setup):
    service, reader = setup
    row = reader.query(
        build(PROJECT, "products"), request_id="x", store_id=GRANT.store_id, generation=4
    )[0]
    reader.override["products"] = [dict(row, buyers_unique=1, name=None)]
    out = service.products(PRINCIPAL, GRANT)
    assert out["data"][0]["buyers_unique"] == 1
    assert out["data"][0]["name"] is None
    q = reader.calls[-1]
    assert "COUNT(DISTINCT o.customer_id)" in q.sql
    assert "o.version_id=i.parent_order_version_id" in q.sql
    assert "SUM(buyers)" not in q.sql
    assert q.parameters["as_of"] == ("TIMESTAMP", service.publication.as_of)


def test_geography_cities_use_preaggregated_join_without_correlated_subquery():
    # BigQuery cannot de-correlate the former ARRAY(SELECT FROM cities ...) form.
    q = build(PROJECT, "geography")
    assert "ARRAY_AGG(STRUCT(city,orders,customers,requested,fulfilled)" in q.sql
    assert "JOIN city_groups c ON c.state IS NOT DISTINCT FROM s.state" in q.sql
    assert "ARRAY(SELECT" not in q.sql
    assert "COUNT(DISTINCT customer_id)" in q.sql
    assert "shipping_address" in q.sql


def test_variant_family_commercial_identity_and_null_unobserved_sales(setup, monkeypatch):
    service, reader = setup
    reader.override["products"] = [
        {
            "product_key": "d" * 64,
            "sku": "SKU",
            "requested": Decimal("9.99"),
            "fulfilled": Decimal("6.66"),
            "units_requested": Decimal("3"),
            "units_fulfilled": Decimal("2"),
            "orders": 1,
        }
    ]
    reader.override["product_evidence"] = [
        {"product_key": "d" * 64, "duplicate_items": 0, "variant_id": "v1", "buyers_unique": 1}
    ]
    proof = {
        "basis": "current_source_snapshot",
        "snapshot_as_of": "2026-10-05T03:00:00Z",
        "evidence_hash": "e" * 64,
    }
    family = {
        v: {
            "variant_id": v,
            "product_id": "parent",
            "name": "Fonte",
            "stock": "5",
            "catalog": proof,
        }
        for v in ("v1", "v2")
    }
    monkeypatch.setattr(service, "_catalog", lambda ids: family)
    monkeypatch.setattr(
        service, "_catalog_family", lambda parent: family if parent == "parent" else {}
    )
    reader.override["variant_sales"] = [
        {
            "variant_id": "v1",
            "duplicate_items": 0,
            "units_requested": Decimal("3"),
            "units_fulfilled": Decimal("2"),
            "requested": Decimal("9.99"),
            "fulfilled": Decimal("6.66"),
            "orders": 1,
            "buyers": 1,
        }
    ]
    data = service.product(PRINCIPAL, GRANT, "d" * 64)["data"]
    assert data["product_id"] == "parent" and len(data["variants"]) == 2
    assert data["variants"][0]["fulfilled_revenue"] == "6.66"
    assert data["variants"][1]["units_fulfilled"] is None
    assert data["sizes"] is None and data["sell_through"] is None
    query = reader.calls[-1]
    assert query.parameters["variants"] == ("STRING", '["v1", "v2"]')
    assert "o.version_id=i.parent_order_version_id" in query.sql
    assert "v1" not in query.sql
    reader.override["variant_sales"][0]["variant_id"] = "foreign"
    with pytest.raises(ReadError, match="variant_commercial_identity_invalid"):
        service.product(PRINCIPAL, GRANT, "d" * 64)


@pytest.mark.parametrize("stock", ["0", "5.25", None])
def test_product_list_keeps_certified_current_sku_fields_without_extra_queries(
    setup, monkeypatch, stock
):
    service, reader = setup
    reader.override["products"] = [
        {
            "store_id": GRANT.store_id,
            "product_key": "d" * 64,
            "product_id": None,
            "sku": "EXPLICIT-SKU",
            "variant_id": "variant-1",
            "name": None,
            "requested": Decimal("10.00"),
            "fulfilled": None,
            "units_requested": Decimal("2"),
            "units_fulfilled": None,
            "orders": 1,
        }
    ]
    proof = {
        "basis": "current_source_snapshot",
        "snapshot_as_of": "2026-10-05T03:00:00Z",
        "evidence_hash": "e" * 64,
    }
    calls = []

    def catalog(ids):
        calls.append(ids)
        return {
            "variant-1": {
                "product_id": "parent",
                "variant_id": "variant-1",
                "catalog": proof,
                "stock": stock,
                "color": "Azul",
                "size": "M",
                "color_hex": "#123abc",
                "active": False,
                "sale_price": "25.00",
            }
        }

    monkeypatch.setattr(service, "_catalog", catalog)
    row = service.products(PRINCIPAL, GRANT)["data"][0]
    assert row["stock"] == stock and row["active"] is False
    assert row["color"] == "Azul" and row["size"] == "M"
    assert row["sale_price"] == "25.00" and row["catalog"] == proof
    assert row["fulfilled_revenue"] is None
    assert calls == [["variant-1"]]
    assert [q.name for q in reader.calls] == ["head", "products"]
