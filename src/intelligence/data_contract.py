"""CHANGE #12 executable reference only; not wired into API or materialization."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from src.analytics.engine import Row, instant, total
from src.utils.data import timestamp

CONTRACT_VERSION = "1.0.0"
EVIDENCE = frozenset({"DIRECT", "CUSTOMER_JOURNEY", "SUPPORTED"})
EVENT_GROUPS = {
    "MARKETING": ("paid_touch", "campaign_interaction", "page_view", "product_view"),
    "IDENTITY": ("register_submitted", "register_approved", "login"),
    "COMMERCIAL": (
        "cart_created",
        "checkout_started",
        "purchase",
        "order_created",
        "order_updated",
    ),
    "RETENTION": ("repeat_purchase", "reactivation"),
}
IDENTITY_FIELDS = "customer_id store_id customer_type company_name trade_name state city".split()


def identity(customer: Row, *, store_id: str) -> Row:
    if not store_id or customer.get("store_id") != store_id:
        raise ValueError("store_access_denied")
    cid = customer.get("customer_id")
    if not isinstance(cid, str) or not cid.strip():
        raise ValueError("explicit_customer_id_required")
    return {field: customer.get(field) for field in IDENTITY_FIELDS}


def commercial(
    orders: list[Row],
    *,
    store_id: str,
    customer_id: str,
    qualifying_statuses: frozenset[str],
    as_of: str,
) -> Row:
    """All-order commercial totals; qualifying purchase count; no campaign joins."""
    if not store_id.strip() or not customer_id.strip():
        raise ValueError("explicit_tenant_customer_required")
    if any(o.get("store_id") != store_id or o.get("customer_id") != customer_id for o in orders):
        raise ValueError("mixed_customer_or_store")
    if any(not isinstance(o.get("order_id"), str) or not o["order_id"].strip() for o in orders):
        raise ValueError("explicit_order_id_required")
    if len({o["order_id"] for o in orders}) != len(orders):
        raise ValueError("duplicate_order")
    selected = sorted(
        (o for o in orders if instant(o["created_at"]) < instant(as_of)),
        key=lambda o: (instant(o["created_at"]), o["order_id"]),
    )
    with localcontext() as ctx:
        ctx.prec = 78
        values = {
            out: total([o.get(field) for o in selected])
            for out, field in (
                ("requested_revenue", "requested_total"),
                ("fulfilled_revenue", "fulfilled_total"),
                ("requested_quantity", "requested_items_qty"),
                ("fulfilled_quantity", "fulfilled_items_qty"),
            )
        }

        def rate(fulfilled: Decimal | None, requested: Decimal | None) -> str | None:
            if fulfilled is None or requested is None or requested == 0:
                return None
            return format(
                (fulfilled / requested).quantize(Decimal("0.000000001"), rounding=ROUND_HALF_EVEN),
                "f",
            )

        def gap(requested: Decimal | None, fulfilled: Decimal | None) -> str | None:
            return (
                None
                if requested is None or fulfilled is None
                else format(requested - fulfilled, "f")
            )

        return {
            "store_id": store_id,
            "customer_id": customer_id,
            "orders_count": len(selected),
            "first_order_at": timestamp(selected[0]["created_at"]) if selected else None,
            "last_order_at": timestamp(selected[-1]["created_at"]) if selected else None,
            "purchase_count": sum(o["order_status"] in qualifying_statuses for o in selected),
            **{k: format(v, "f") if v is not None else None for k, v in values.items()},
            "fulfillment_rate": rate(values["fulfilled_revenue"], values["requested_revenue"]),
            "quantity_fulfillment_rate": rate(
                values["fulfilled_quantity"], values["requested_quantity"]
            ),
            "revenue_gap": gap(values["requested_revenue"], values["fulfilled_revenue"]),
            "quantity_gap": gap(values["requested_quantity"], values["fulfilled_quantity"]),
        }


def segmentation(*, purchase_count: int, paid_acquired: bool | None) -> Row:
    if (
        not isinstance(purchase_count, int)
        or isinstance(purchase_count, bool)
        or purchase_count < 0
    ):
        raise ValueError("invalid_purchase_count")
    return {
        "NEW_CUSTOMER": purchase_count == 1,
        "REPEAT_CUSTOMER": purchase_count > 1,
        "PAID_ACQUIRED": paid_acquired,
        "ACTIVE_CUSTOMER": None,
        "HIGH_VALUE_CUSTOMER": None,
        "AT_RISK": None,
    }


def timeline(events: list[Row], *, store_id: str, customer_id: str, as_of: str) -> list[Row]:
    """Validate already resolved contract events. Never creates identity or evidence."""
    if not store_id.strip() or not customer_id.strip():
        raise ValueError("explicit_tenant_customer_required")
    known = {event for group in EVENT_GROUPS.values() for event in group}
    seen = set()
    for event in events:
        if event.get("store_id") != store_id or event.get("customer_id") != customer_id:
            raise ValueError("mixed_customer_or_store")
        refs = event.get("evidence_refs")
        if (
            event.get("evidence_type") not in EVIDENCE
            or not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
        ):
            raise ValueError("evidence_required")
        if event.get("event_type") not in known:
            raise ValueError("unsupported_event_type")
        eid = event.get("event_key")
        if not isinstance(eid, str) or not eid.strip() or eid in seen:
            raise ValueError("invalid_or_duplicate_event_key")
        seen.add(eid)
    fields = "event_key store_id customer_id event_type occurred_at order_id campaign_id evidence_type".split()
    return [
        {k: timestamp(e[k]) if k == "occurred_at" else e.get(k) for k in fields}
        for e in sorted(events, key=lambda e: (instant(e["occurred_at"]), e["event_key"]))
        if instant(e["occurred_at"]) < instant(as_of)
    ]
