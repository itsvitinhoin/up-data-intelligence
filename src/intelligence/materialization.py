"""Four separated Customer 360 read models. No identity heuristics or cloud IO."""

from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Protocol

from src.analytics.engine import Row, amount, instant, product_key, total
from src.analytics.policy import Policy
from src.analytics.quality import unique
from src.influence.engine import RANK, Evidence, InfluenceScope
from src.intelligence.schema import SCHEMAS
from src.utils.data import canonical, digest, numeric, timestamp


class RowBuffer(Protocol):
    def append(self, row: Row) -> None: ...
    def __iter__(self) -> Iterator[Row]: ...


class Journeys(Protocol):
    def get(self, cid: str) -> Row: ...


@dataclass(frozen=True)
class PrecomputedCustomer:
    source_snapshot_hash: str
    content_hashes: Mapping[str, str]
    paid: Mapping[str, Row]
    journeys: Journeys
    output_factory: Callable[[str], RowBuffer]


def summarize_influence(rows: list[Row], paid: Mapping[str, Row]) -> Row:
    points = sorted(
        {
            path["paid_fact_id"]: paid[path["paid_fact_id"]]
            for row in rows
            for path in row["identity_path"]
        }.values(),
        key=lambda r: (instant(r["occurred_at"]), r["fact_id"]),
    )
    campaigns = sorted({r["campaign_id"] for r in rows if r["campaign_id"] is not None})
    return {
        "influenced": bool(rows),
        "campaigns": campaigns,
        "campaign_count": len(campaigns),
        "first_campaign_id": points[0]["campaign_id"] if points else None,
        "last_campaign_id": points[-1]["campaign_id"] if points else None,
        "evidence_type": min(
            (Evidence(r["evidence_type"]) for r in rows), key=RANK.__getitem__
        ).value
        if rows
        else None,
    }


def materialize(
    policy: Policy,
    *,
    customers: list[Row],
    orders: list[Row],
    items: list[Row],
    influence: dict[str, Row],
    events: list[Row],
    identity_links: list[Row],
    calculated_at: str,
    precomputed: PrecomputedCustomer | None = None,
) -> Row:
    with localcontext() as ctx:
        ctx.prec = 78
        return _build(
            policy,
            customers,
            orders,
            items,
            influence,
            events,
            identity_links,
            calculated_at,
            precomputed,
        )


def _build(
    p: Policy,
    customers: list[Row],
    orders: list[Row],
    items: list[Row],
    influence: dict[str, Row],
    events: list[Row],
    identity_links: list[Row],
    calculated: str,
    precomputed: PrecomputedCustomer | None = None,
) -> Row:
    if precomputed is not None and events:
        raise ValueError("precomputed_customer360_requires_streamed_events")
    if sum(map(len, (customers, orders, items, events, identity_links))) > 100000:
        raise ValueError("bounded_customer360_snapshot_required")
    at = timestamp(calculated)
    if instant(at) < instant(p.as_of):
        raise ValueError("invalid_calculation_cutoff")
    customers, orders, items = [
        [r for r in rows if r.get("store_id") == p.store_id] for rows in (customers, orders, items)
    ]
    if any(r.get("source_system") != "upzero" for rows in (customers, orders, items) for r in rows):
        raise ValueError("unsupported_source")
    if any(i.get("observed_at") and instant(i["observed_at"]) > instant(at) for i in items):
        raise ValueError("snapshot_observation_after_calculation")
    unique(customers, "customer_id", "duplicate_customer")
    unique(orders, "order_id", "duplicate_order")
    if len({(i.get("order_id"), i.get("item_id")) for i in items}) != len(items):
        raise ValueError("duplicate_item")
    if set(influence) != {s.value for s in InfluenceScope}:
        raise ValueError("all_influence_scopes_required")
    expected_source = (
        precomputed.source_snapshot_hash
        if precomputed
        else digest(
            {
                name: sorted([r for r in rows if r.get("store_id") == p.store_id], key=canonical)
                for name, rows in (
                    ("customers", customers),
                    ("orders", orders),
                    ("events", events),
                    ("identity_links", identity_links),
                )
            }
        )
    )
    receipts = []
    for scope, artifact in influence.items():
        receipt = artifact["receipt"]
        if (
            receipt["source_snapshot_hash"] != expected_source
            or receipt["store_id"] != p.store_id
            or receipt["policy_hash"] != p.key
            or receipt["history_complete"] != p.history_complete
            or receipt["facts_complete"] != p.facts_complete
            or instant(receipt["calculated_at"]) > instant(at)
            or receipt["as_of"] != timestamp(p.as_of)
            or receipt["influence_scope"] != scope
            or receipt["report_from"] != p.report_from
            or receipt["report_to"] != p.report_to
            or receipt["content_sha256"]
            != (precomputed.content_hashes[scope] if precomputed else digest(artifact["tables"]))
        ):
            raise ValueError("incompatible_influence_snapshot")
        receipts.append(receipt)
    if len({r["source_snapshot_hash"] for r in receipts}) != 1:
        raise ValueError("mixed_influence_generations")
    source = {
        "customers": sorted(customers, key=canonical),
        "orders": sorted(orders, key=canonical),
        "items": sorted(items, key=canonical),
    }
    generation = digest([source, sorted(r["publication_id"] for r in receipts), p.key, at])
    base = {
        "store_id": p.store_id,
        "policy_hash": p.key,
        "generation": generation,
        "currency": p.currency,
        "calculated_at": at,
        "as_of": timestamp(p.as_of),
    }
    by_customer: dict[str, list[Row]] = defaultdict(list)
    cids = {c["customer_id"] for c in customers}
    orders = [
        o
        for o in orders
        if o.get("customer_id") in cids and instant(o["created_at"]) < instant(p.as_of)
    ]
    for o in orders:
        by_customer[o["customer_id"]].append(o)
    lifetime = influence["LIFETIME"]["tables"]
    timeline = lifetime["analytics_customer_timeline"]
    paid: Mapping[str, Row] = (
        precomputed.paid
        if precomputed
        else {t["fact_id"]: t for t in lifetime["analytics_paid_touchpoints"]}
    )
    flags = {
        s: {
            r["customer_id"]: r["paid_media_influenced"]
            for r in a["tables"]["analytics_customer_paid_influence"]
        }
        for s, a in influence.items()
    }
    infl_orders = {s: a["tables"]["analytics_order_paid_influence"] for s, a in influence.items()}
    output: dict[str, RowBuffer] = {
        name: precomputed.output_factory(name) if precomputed else [] for name in SCHEMAS
    }
    sequence: dict[str, int] = {}
    for c in sorted(customers, key=lambda r: r["customer_id"]):
        cid = c["customer_id"]
        os = sorted(by_customer[cid], key=lambda o: (instant(o["created_at"]), o["order_id"]))
        purchases = [o for o in os if o["order_status"] in p.purchase_statuses]
        sequence.update({o["order_id"]: i for i, o in enumerate(purchases, 1)})
        first, last = (purchases[0], purchases[-1]) if purchases else (None, None)
        output["analytics_customer_360_profile"].append(
            {
                **base,
                "row_key": digest([p.store_id, "profile", cid]),
                **{
                    k: c.get(k)
                    for k in (
                        "customer_id",
                        "customer_type",
                        "company_name",
                        "trade_name",
                        "state",
                        "city",
                    )
                },
                "first_order_at": timestamp(first["created_at"]) if first else None,
                "last_purchase_at": timestamp(last["created_at"]) if last else None,
                "first_purchase_requested_revenue": amount(first.get("requested_total"))
                if first
                else None,
                "first_purchase_fulfilled_revenue": amount(first.get("fulfilled_total"))
                if first
                else None,
                "total_orders": len(os),
                **{
                    name: total([o.get(field) for o in os])
                    for name, field in (
                        ("total_requested_revenue", "requested_total"),
                        ("total_fulfilled_revenue", "fulfilled_total"),
                        ("total_requested_quantity", "requested_items_qty"),
                        ("total_fulfilled_quantity", "fulfilled_items_qty"),
                    )
                },
                "purchase_count": len(purchases),
                "has_repurchase": len(purchases) > 1,
                "days_since_last_purchase": (
                    date.fromisoformat(p.local_date(p.as_of))
                    - date.fromisoformat(p.local_date(last["created_at"]))
                ).days
                if last
                else None,
                "paid_media_influenced": flags["LIFETIME"].get(cid, False),
                "acquisition_influenced": flags["ACQUISITION"].get(cid, False),
                "repeat_purchase_influenced": flags["REPEAT_PURCHASE"].get(cid, False),
                "ltv_observed": total([o.get("requested_total") for o in purchases]),
                "ltv_basis": "requested_qualifying_orders_observed",
                "history_complete": p.history_complete,
            }
        )
        if precomputed:
            output["analytics_customer_journey_summary"].append(
                {
                    **base,
                    "row_key": digest([p.store_id, "journey", cid]),
                    "customer_id": cid,
                    **precomputed.journeys.get(cid),
                }
            )
        else:
            journey = sorted(
                [r for r in timeline if r["customer_id"] == cid],
                key=lambda r: (instant(r["occurred_at"]), r["row_key"]),
            )
            events = [r for r in journey if r["record_type"] == "FACT"]
            pts = sorted(
                [paid[r["fact_id"]] for r in events if r["fact_id"] in paid],
                key=lambda r: (instant(r["occurred_at"]), r["fact_id"]),
            )
            output["analytics_customer_journey_summary"].append(
                {
                    **base,
                    "row_key": digest([p.store_id, "journey", cid]),
                    "customer_id": cid,
                    "first_touch_at": events[0]["occurred_at"] if events else None,
                    "first_paid_touch_at": pts[0]["occurred_at"] if pts else None,
                    "last_paid_touch_at": pts[-1]["occurred_at"] if pts else None,
                    "first_campaign_id": pts[0]["campaign_id"] if pts else None,
                    "last_campaign_id": pts[-1]["campaign_id"] if pts else None,
                    "total_events": len(events),
                    "total_sessions": len(
                        {
                            r["session_id"]
                            for r in events
                            if r.get("session_id") and r["session_id"].strip()
                        }
                    ),
                    "total_products_viewed": len(
                        {
                            r["product_id"]
                            for r in events
                            if r["event_name"] == "product_view" and r.get("product_id")
                        }
                    ),
                    "total_cart_events": sum(r["event_name"] == "add_to_cart" for r in events),
                    "total_checkout_events": sum(
                        r["event_name"] == "checkout_started" for r in events
                    ),
                    "timeline_start": journey[0]["occurred_at"] if journey else None,
                    "timeline_end": journey[-1]["occurred_at"] if journey else None,
                }
            )
    for o in sorted(orders, key=lambda o: (instant(o["created_at"]), o["order_id"])):
        oid = o["order_id"]
        scope_rows = {
            s: [r for r in rows if r["order_id"] == oid] for s, rows in infl_orders.items()
        }
        rows = scope_rows["LIFETIME"]
        summary = summarize_influence(rows, paid)
        output["analytics_customer_orders_summary"].append(
            {
                **base,
                "row_key": digest([p.store_id, "order", oid]),
                "customer_id": o["customer_id"],
                "order_id": oid,
                "purchase_number": sequence.get(oid),
                "created_at": timestamp(o["created_at"]),
                "order_status": o["order_status"],
                **{
                    k: amount(o.get(k))
                    for k in (
                        "requested_total",
                        "fulfilled_total",
                        "requested_items_qty",
                        "fulfilled_items_qty",
                    )
                },
                "paid_media_influenced": bool(rows),
                **{k: v for k, v in summary.items() if k != "influenced"},
                "identity_path": [path for r in rows for path in r["identity_path"]],
                "campaigns": sorted(
                    {r["campaign_id"] for r in rows if r["campaign_id"] is not None}
                ),
                "influence_scope": "LIFETIME",
                "influence_by_scope": {
                    s: summarize_influence(rs, paid) for s, rs in scope_rows.items()
                },
            }
        )
    # CORE items have no canonical product_id; never infer it from asset_id or SKU.
    order_map = {o["order_id"]: o for o in orders if o["order_status"] in p.purchase_statuses}
    groups: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for item in items:
        order = order_map.get(item.get("order_id"))
        if not order or not item.get("present_in_latest_snapshot"):
            continue
        if (
            not order.get("version_id")
            or item.get("parent_order_version_id") != order["version_id"]
        ):
            raise ValueError("item_order_snapshot_mismatch")
        if item.get("status") not in {"active", "attended", "removed"}:
            raise ValueError("unsupported_item_status")
        groups[order["customer_id"], product_key(item)].append(item)
    for (cid, key), rows in sorted(groups.items()):
        requested, fulfilled = [], []
        for i in rows:
            price, qty, original = (
                amount(i.get("unit_price")),
                amount(i.get("qty")),
                amount(i.get("original_qty")),
            )
            requested.append(
                price * original if price is not None and original is not None else None
            )
            fulfilled.append(
                Decimal(0)
                if i["status"] == "removed"
                else price * qty
                if price is not None and qty is not None
                else None
            )
        dates = sorted((order_map[i["order_id"]]["created_at"] for i in rows), key=instant)
        output["analytics_customer_products_summary"].append(
            {
                **base,
                "row_key": digest([p.store_id, "product", cid, key]),
                "customer_id": cid,
                "product_key": key,
                "product_id": None,
                "variant_id": rows[0].get("variant_id"),
                "sku": rows[0].get("sku"),
                "resolution_status": "UNRESOLVED_CANONICAL_PRODUCT",
                "orders_count": len({i["order_id"] for i in rows}),
                "requested_quantity": total([i.get("original_qty") for i in rows]),
                "fulfilled_quantity": total(
                    [0 if i["status"] == "removed" else i.get("qty") for i in rows]
                ),
                "requested_revenue": total(requested),
                "fulfilled_revenue": total(fulfilled),
                "first_purchase_at": timestamp(dates[0]),
                "last_purchase_at": timestamp(dates[-1]),
                "revenue_basis": "line_gross_at_current_unit_price",
            }
        )
    for name, materialized_rows in output.items():
        for row in materialized_rows:
            if set(row) != set(SCHEMAS[name].fields):
                raise ValueError("customer360_schema_mismatch")
            for field, typ in SCHEMAS[name].fields.items():
                if typ == "NUMERIC":
                    row[field] = numeric(row[field])
    return {
        "metadata": {
            **base,
            "report_from": p.report_from,
            "report_to": p.report_to,
            "timezone": p.timezone,
            "unresolved_facts": influence["LIFETIME"]["receipt"]["unresolved_facts"],
        },
        "tables": {**output, "analytics_customer_timeline": timeline},
    }
