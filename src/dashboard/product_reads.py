"""Product-facing read projections, with explicit coverage and decimal semantics."""

import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.dashboard.contracts import Grant, Principal, ReadError, decimal_string, integer

if TYPE_CHECKING:
    from src.dashboard.service import DashboardService

STATES = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


def _money_sum(rows: list[dict[str, Any]], field: str) -> str | None:
    values = [decimal_string(r.get(field)) for r in rows]
    if any(v is None for v in values):
        return None
    return format(sum((Decimal(v) for v in values if v is not None), Decimal(0)), "f")


def _difference(total: Any, gross: str | None) -> str | None:
    value = decimal_string(total)
    return None if value is None or gross is None else format(Decimal(value) - Decimal(gross), "f")


def order(
    service: "DashboardService", principal: Principal | None, grant: Grant, order_id: str
) -> dict[str, Any]:
    service._scope(principal, grant)
    if not order_id.strip() or len(order_id) > 200:
        raise ReadError(400, "invalid_order_id")
    rows = service._rows("order_detail", order=order_id, as_of=service.publication.as_of)
    if not rows:
        raise ReadError(404, "order_not_found")
    if len(rows) != 1:
        raise ReadError(503, "duplicate_order_or_customer_profile")
    row = rows[0]
    if row.get("store_id") != grant.store_id or row.get("order_id") != order_id:
        raise ReadError(503, "order_scope_mismatch")
    items = service._rows("order_detail_items", order=order_id)
    if len(items) > 1000:
        raise ReadError(503, "order_detail_item_limit")
    if len({i.get("item_id") for i in items}) != len(items):
        raise ReadError(503, "duplicate_order_item")
    projected = []
    for item in items:
        if (
            item.get("order_id") != order_id
            or not item.get("item_id")
            or not row.get("version_id")
            or item.get("parent_order_version_id") != row["version_id"]
            or item.get("status") not in {"active", "attended", "removed"}
        ):
            raise ReadError(503, "order_item_snapshot_mismatch")
        requested = decimal_string(item.get("original_qty"))
        fulfilled = "0" if item["status"] == "removed" else decimal_string(item.get("qty"))
        price = decimal_string(item.get("unit_price"))
        if any(Decimal(v) < 0 for v in (requested, fulfilled, price) if v is not None):
            raise ReadError(503, "invalid_order_item_amount")
        projected.append(
            {
                "item_id": item["item_id"],
                "product_key": item["product_key"],
                "product_id": None,
                "asset_id": item.get("asset_id"),
                "variant_id": item.get("variant_id"),
                "name": item.get("asset_name"),
                "sku": item.get("sku"),
                "image": item.get("asset_image_url") or item.get("image_url"),
                "color": None,
                "size": None,
                "status": item["status"],
                "requested_quantity": requested,
                "fulfilled_quantity": fulfilled,
                "unit_price": price,
                "requested_value": None
                if requested is None or price is None
                else format(Decimal(requested) * Decimal(price), "f"),
                "fulfilled_value": None
                if fulfilled is None or price is None
                else format(Decimal(fulfilled) * Decimal(price), "f"),
            }
        )
    expected_count = integer(row.get("items_count"))
    if expected_count is not None and expected_count != len(items):
        raise ReadError(503, "order_item_count_mismatch")
    quantity_reconciled: bool | None = True
    for field, total_field in (
        ("requested_quantity", "requested_items_qty"),
        ("fulfilled_quantity", "fulfilled_items_qty"),
    ):
        total = decimal_string(row.get(total_field))
        summed = _money_sum(projected, field)
        if total is None or summed is None:
            quantity_reconciled = None
        if total is not None and summed is not None and Decimal(total) != Decimal(summed):
            raise ReadError(503, "order_item_quantity_mismatch")
    gross_requested = _money_sum(projected, "requested_value")
    gross_fulfilled = _money_sum(projected, "fulfilled_value")
    name = (
        row.get("customer_company_name")
        or row.get("customer_trade_name")
        or row.get("customer_name")
    )
    return service._response(
        {
            "order": service._order(row),
            "customer": None
            if row.get("customer_id") is None
            else {
                "customer_id": row["customer_id"],
                "name": name,
                "state": row.get("customer_state"),
                "city": row.get("customer_city"),
                "cnpj": None,
                "email": None,
                "phone": None,
            },
            "items": projected,
            "reconciliation": {
                "item_value_basis": "line_gross_at_current_unit_price",
                "gross_requested": gross_requested,
                "gross_fulfilled": gross_fulfilled,
                "requested_order_adjustment": _difference(
                    row.get("requested_total"), gross_requested
                ),
                "fulfilled_order_adjustment": _difference(
                    row.get("fulfilled_total"), gross_fulfilled
                ),
                "quantity_reconciled": quantity_reconciled,
            },
        },
        limitations=[
            "core_orders_not_source_generation_pinned",
            "fulfilled_is_not_paid",
            "contact_projection_not_permitted",
            "color_size_not_certified",
            "item_gross_differs_from_order_net",
        ],
    )


def product(
    service: "DashboardService",
    principal: Principal | None,
    grant: Grant,
    product_key: str,
    from_day: str | None,
    to_day: str | None,
) -> dict[str, Any]:
    service._scope(principal, grant)
    if not re.fullmatch(r"[a-f0-9]{64}", product_key):
        raise ReadError(400, "invalid_product_key")
    start, end = service._interval(from_day, to_day)
    rows = service._rows(
        "products",
        from_day=start,
        to_day=end,
        product=product_key,
        limit=2,
        as_of=service.publication.as_of,
        timezone=service.policy.reporting_timezone,
    )
    if not rows:
        raise ReadError(404, "product_not_found")
    if len(rows) != 1 or rows[0].get("product_key") != product_key:
        raise ReadError(503, "duplicate_product_identity")
    row = rows[0]
    evidence = service._rows(
        "product_evidence",
        product=product_key,
        from_day=start,
        to_day=end,
        timezone=service.policy.reporting_timezone,
        as_of=service.publication.as_of,
    )
    if len(evidence) != 1 or evidence[0].get("duplicate_items") != 0:
        raise ReadError(503, "product_evidence_missing_or_duplicate")
    profile = evidence[0]
    return service._response(
        {
            "store_id": grant.store_id,
            "product_key": product_key,
            "product_id": row.get("product_id"),
            "variant_id": profile.get("variant_id"),
            "sku": row.get("sku"),
            "name": profile.get("name"),
            "image": profile.get("image"),
            "requested_revenue": decimal_string(row.get("requested")),
            "fulfilled_revenue": decimal_string(row.get("fulfilled")),
            "units_requested": decimal_string(row.get("units_requested")),
            "units_fulfilled": decimal_string(row.get("units_fulfilled")),
            "orders_observed": integer(row.get("orders")),
            "buyers_unique": integer(profile.get("buyers_unique")),
            "stock": None,
            "sizes": None,
            "colors": None,
            "abc": None,
            "sell_through": None,
            "revenue_basis": "line_gross_at_current_unit_price",
        },
        limitations=[
            "core_product_profile_not_source_generation_pinned",
            "inventory_not_certified",
            "color_size_not_certified",
        ],
    )


def geography(
    service: "DashboardService",
    principal: Principal | None,
    grant: Grant,
    from_day: str | None,
    to_day: str | None,
) -> dict[str, Any]:
    service._scope(principal, grant)
    start, end = service._interval(from_day, to_day)
    rows = service._rows(
        "geography",
        from_day=start,
        to_day=end,
        timezone=service.policy.reporting_timezone,
        as_of=service.publication.as_of,
    )
    states, total, unmapped, without_customer = [], 0, 0, 0
    if len({r.get("state") for r in rows}) != len(rows):
        raise ReadError(503, "duplicate_geography_state")
    for row in rows:
        count = integer(row.get("orders"))
        if count is None:
            raise ReadError(503, "invalid_geography_count")
        total += count
        missing_customer = integer(row.get("orders_without_customer"))
        if missing_customer is None or missing_customer > count:
            raise ReadError(503, "invalid_geography_count")
        without_customer += missing_customer
        if row.get("state") not in STATES:
            unmapped += count
            continue
        requested = decimal_string(row.get("requested"))
        states.append(
            {
                "state": row["state"],
                "customers": integer(row.get("customers")),
                "orders": count,
                "requested_revenue": requested,
                "fulfilled_revenue": decimal_string(row.get("fulfilled")),
                "average_ticket_requested": None
                if requested is None or count == 0
                else format(Decimal(requested) / Decimal(count), "f"),
                "new_customers": None,
                "influenced_customers": None,
                "approved_without_purchase": None,
                "conversion_rate": None,
                "top_cities": [
                    {
                        "city": c.get("city"),
                        "customers": integer(c.get("customers")),
                        "orders": integer(c.get("orders")),
                        "requested_revenue": decimal_string(c.get("requested")),
                        "fulfilled_revenue": decimal_string(c.get("fulfilled")),
                    }
                    for c in row["cities"]
                ],
            }
        )
    return service._response(
        {
            "states": states,
            "coverage": {
                "basis": "order_shipping_location",
                "orders_observed": total,
                "mapped_orders": total - unmapped,
                "unmapped_orders": unmapped,
                "orders_without_customer": without_customer,
            },
        },
        limitations=[
            "shipping_geography_not_current_customer_address",
            "core_orders_not_source_generation_pinned",
            "lead_geography_not_certified",
        ],
    )
