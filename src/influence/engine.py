"""Offline influence and timeline over bounded, coherent CORE snapshots. No IO."""

import re
from collections import defaultdict
from decimal import Decimal, localcontext
from enum import StrEnum

from src.analytics.engine import Row, amount, instant, total
from src.analytics.policy import ORDER_STATUSES, Policy
from src.analytics.quality import unique
from src.influence.identity import Resolution, resolve, value
from src.utils.data import digest, numeric, timestamp


class Evidence(StrEnum):
    DIRECT = "DIRECT"
    CUSTOMER_JOURNEY = "CUSTOMER_JOURNEY"
    SUPPORTED = "SUPPORTED"


class InfluenceScope(StrEnum):
    LIFETIME = "LIFETIME"
    ACQUISITION = "ACQUISITION"
    REPEAT_PURCHASE = "REPEAT_PURCHASE"


RANK = {Evidence.DIRECT: 0, Evidence.CUSTOMER_JOURNEY: 1, Evidence.SUPPORTED: 2}
MARKERS = ("meta_campaign_id", "meta_adset_id", "meta_ad_id", "fbclid", "fbc", "gclid")


def _local(rows: list[Row], policy: Policy, key: str) -> list[Row]:
    selected = [r for r in rows if r.get("store_id") == policy.store_id]
    if any(r.get("source_system") != "upzero" for r in selected):
        raise ValueError("unsupported_influence_source")
    unique(selected, key, "duplicate_or_missing_" + key)
    return selected


def paid_markers(fact: Row) -> list[str]:
    """CHANGE #08 observed tracking rule. No API validation or billing assertion."""
    result = []
    for field in MARKERS:
        token = value(fact, field)
        if (
            token is None
            or token.lower() in {"null", "none", "undefined"}
            or re.search(r"[\s{}<>\[\]]", token)
            or "placeholder" in token.lower()
        ):
            continue
        if field.startswith("meta_") and not re.fullmatch(r"[0-9]+", token):
            continue
        result.append(field)
    return result


def _media(fact: Row) -> Row:
    # IDs already structured by the CORE parser; never derive campaign from a click token.
    markers = paid_markers(fact)
    return {
        k: fact.get("meta_" + k) if "meta_" + k in markers else None
        for k in ("campaign_id", "adset_id", "ad_id")
    }


def _signed(v: object) -> Decimal | None:
    parsed = numeric(v)
    return Decimal(parsed) if parsed is not None else None


def _one(points: list[Row], field: str) -> str | None:
    values = {value(t, field) for t in points}
    return next(iter(values)) if len(values) == 1 else None


def _timeline(
    base: Row,
    events: list[Row],
    orders: list[Row],
    resolutions: dict[str, Resolution],
    cids: set[str],
) -> list[Row]:
    rows = []
    marketing = ("utm_source", "utm_medium", "utm_campaign")
    financial = ("requested_total", "fulfilled_total", "requested_items_qty", "fulfilled_items_qty")
    for f in events:
        resolution = resolutions[f["fact_id"]]
        if resolution.customer_id is None:
            continue
        rows.append(
            {
                **base,
                "row_key": digest(
                    [base["store_id"], "timeline-fact", resolution.customer_id, f["fact_id"]]
                ),
                "customer_id": resolution.customer_id,
                "record_type": "FACT",
                **{
                    k: f.get(k)
                    for k in (
                        "event_id",
                        "fact_id",
                        "event_name",
                        "session_id",
                        "visitor_id",
                        "user_id",
                        *marketing,
                        "product_id",
                        "order_id",
                        "channel",
                        "source",
                        "device_type",
                    )
                },
                **_media(f),
                "variant_id": f.get("product_variant_id"),
                "occurred_at": timestamp(f["occurred_at"]),
                "value": _signed(f.get("value")),
                "quantity": _signed(f.get("quantity")),
                "identity_path": resolution.paths,
                "confidence_type": resolution.confidence_type,
                "order_status": None,
                **dict.fromkeys(financial),
            }
        )
    for o in orders:
        if o.get("customer_id") not in cids:
            continue
        rows.append(
            {
                **base,
                "row_key": digest(
                    [base["store_id"], "timeline-order", o["customer_id"], o["order_id"]]
                ),
                "customer_id": o["customer_id"],
                "record_type": "ORDER",
                "event_name": "order_created",
                "order_id": o["order_id"],
                "occurred_at": timestamp(o["created_at"]),
                "order_status": o.get("order_status"),
                **dict.fromkeys(
                    (
                        "event_id",
                        "fact_id",
                        "session_id",
                        "visitor_id",
                        "user_id",
                        "campaign_id",
                        "adset_id",
                        "ad_id",
                        *marketing,
                        "product_id",
                        "variant_id",
                        "value",
                        "quantity",
                        "channel",
                        "source",
                        "device_type",
                    )
                ),
                **{k: amount(o.get(k)) for k in financial},
                "confidence_type": "DIRECT",
                "identity_path": [
                    {
                        "via": "order_id",
                        "order_id": o["order_id"],
                        "customer_id": o["customer_id"],
                        "order_version_id": o.get("version_id"),
                    }
                ],
            }
        )
    return sorted(rows, key=lambda r: (r["customer_id"], instant(r["occurred_at"]), r["row_key"]))


def _build(
    policy: Policy,
    *,
    customers: list[Row],
    orders: list[Row],
    events: list[Row],
    identity_links: list[Row],
    calculated_at: str,
    influence_scope: InfluenceScope,
    paid_evidence: list[Row] | None,
) -> dict[str, list[Row]]:
    if sum(map(len, (customers, orders, events, identity_links, paid_evidence or []))) > 100000:
        raise ValueError("influence_reference_requires_bounded_inputs")
    at = timestamp(calculated_at)
    if instant(at) < instant(policy.as_of):
        raise ValueError("calculation_before_observation_cutoff")
    customers = _local(customers, policy, "customer_id")
    orders = _local(orders, policy, "order_id")
    events = _local(events, policy, "fact_id")
    links = _local(identity_links, policy, "link_id")
    for rows in (customers, orders, events, links):
        if any(r.get("observed_at") and instant(r["observed_at"]) > instant(at) for r in rows):
            raise ValueError("snapshot_observation_after_calculation")
    orders = [o for o in orders if instant(o["created_at"]) < instant(policy.as_of)]
    if any(o.get("order_status") not in ORDER_STATUSES for o in orders):
        raise ValueError("unknown_order_status")
    events = [e for e in events if instant(e["occurred_at"]) < instant(policy.as_of)]
    cids = {c["customer_id"] for c in customers}
    resolutions = resolve(events, orders, customers, links)
    base = {
        "store_id": policy.store_id,
        "calculated_at": at,
        "policy_hash": policy.key,
        "currency": policy.currency,
        "history_complete": policy.history_complete,
        "facts_complete": policy.facts_complete,
        "as_of": timestamp(policy.as_of),
    }
    commerce = [
        o
        for o in orders
        if o.get("customer_id") in cids and o["order_status"] in policy.purchase_statuses
    ]
    order_map = {o["order_id"]: o for o in commerce}
    by_customer: dict[str, list[Row]] = defaultdict(list)
    for o in commerce:
        by_customer[o["customer_id"]].append(o)
    sequence: dict[str, int] = {}
    previous: dict[str, str] = {}
    for rows in by_customer.values():
        ordered = sorted(rows, key=lambda o: (instant(o["created_at"]), o["order_id"]))
        for i, o in enumerate(ordered):
            sequence[o["order_id"]] = i + 1
            if i:
                previous[o["order_id"]] = ordered[i - 1]["created_at"]
    touches = []
    groups: dict[tuple[str, str | None], list[Row]] = defaultdict(list)
    for f in sorted(events, key=lambda r: (instant(r["occurred_at"]), r["fact_id"])):
        markers = paid_markers(f)
        if not markers:
            continue
        resolution = resolutions[f["fact_id"]]
        touch = {
            **base,
            "row_key": digest([policy.store_id, "paid-touch", f["fact_id"]]),
            **{
                k: f.get(k)
                for k in (
                    "fact_id",
                    "event_id",
                    "session_id",
                    "visitor_id",
                    "user_id",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                )
            },
            **_media(f),
            "occurred_at": timestamp(f["occurred_at"]),
            "touch_type": "PAID_TRACKING",
            "evidence_type": Evidence.SUPPORTED.value
            if resolution.reason == "explicit_order"
            else resolution.confidence_type,
            "paid_signal_types": markers,
            "identity_path": resolution.paths,
        }
        touches.append(touch)
        if resolution.customer_id is None:
            continue
        for o in by_customer[resolution.customer_id]:
            oid = o["order_id"]
            if not policy.report_from <= policy.local_date(o["created_at"]) < policy.report_to:
                continue
            if instant(f["occurred_at"]) >= instant(o["created_at"]):
                continue
            if influence_scope == InfluenceScope.ACQUISITION and sequence[oid] != 1:
                continue
            if influence_scope == InfluenceScope.REPEAT_PURCHASE and (
                oid not in previous or instant(f["occurred_at"]) < instant(previous[oid])
            ):
                continue
            paths = []
            for path in resolution.paths:
                same_order = path.get("anchor_order_id") == oid
                # Explicit order references are reliable identity at the observed Fact's time;
                # temporal anchors for a different order must precede the target order.
                if not same_order and instant(path["anchor_at"]) > instant(o["created_at"]):
                    continue
                level = (
                    Evidence.DIRECT
                    if same_order and path["via"] == "session_id"
                    else Evidence.SUPPORTED
                    if path["via"] in {"user_id", "order_id"}
                    else Evidence.CUSTOMER_JOURNEY
                )
                paths.append(
                    {
                        **path,
                        "level": level.value,
                        "paid_fact_id": f["fact_id"],
                        "paid_fact_version_id": f.get("version_id"),
                        "order_id": oid,
                    }
                )
            if paths:
                best = min(paths, key=lambda p: (RANK[Evidence(p["level"])], digest(p)))
                groups[oid, touch["campaign_id"]].append({"touch": touch, "path": best})
    order_rows = []
    for (oid, campaign), matches in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")
    ):
        o = order_map[oid]
        ts, paths = [m["touch"] for m in matches], [m["path"] for m in matches]
        order_rows.append(
            {
                **base,
                "row_key": digest([policy.store_id, "order-paid", oid, campaign]),
                "order_id": oid,
                "customer_id": o["customer_id"],
                "purchase_number": sequence[oid],
                "influence_scope": influence_scope.value,
                "campaign_id": campaign,
                "adset_id": _one(ts, "adset_id"),
                "ad_id": _one(ts, "ad_id"),
                "first_paid_touch_at": ts[0]["occurred_at"],
                "last_paid_touch_at": ts[-1]["occurred_at"],
                "touch_count": len(ts),
                **{
                    k: amount(o.get(k))
                    for k in (
                        "requested_total",
                        "fulfilled_total",
                        "requested_items_qty",
                        "fulfilled_items_qty",
                    )
                },
                "evidence_type": min(
                    (Evidence(p["level"]) for p in paths), key=RANK.__getitem__
                ).value,
                "identity_path": paths,
                "participating_ads": sorted(
                    [
                        dict(zip(("adset_id", "ad_id"), pair, strict=True))
                        for pair in {(t["adset_id"], t["ad_id"]) for t in ts}
                    ],
                    key=digest,
                ),
            }
        )
    customer_rows = []
    for c in sorted(customers, key=lambda c: c["customer_id"]):
        cid = c["customer_id"]
        selected = [r for r in order_rows if r["customer_id"] == cid]
        ids = {r["order_id"] for r in selected}
        fact_ids = {p["paid_fact_id"] for r in selected for p in r["identity_path"]}
        ts = [t for t in touches if t["fact_id"] in fact_ids]
        values = [order_map[oid] for oid in sorted(ids)]
        customer_rows.append(
            {
                **base,
                "row_key": digest([policy.store_id, "customer-paid", cid]),
                "customer_id": cid,
                "influence_scope": influence_scope.value,
                "paid_media_influenced": bool(ids),
                "first_paid_touch_at": ts[0]["occurred_at"] if ts else None,
                "last_paid_touch_at": ts[-1]["occurred_at"] if ts else None,
                "paid_touch_count": len(ts),
                **{
                    name: len({t[field] for t in ts if t[field] is not None})
                    for name, field in (
                        ("campaign_count", "campaign_id"),
                        ("adset_count", "adset_id"),
                        ("ad_count", "ad_id"),
                    )
                },
                "first_campaign_id": ts[0]["campaign_id"] if ts else None,
                "last_campaign_id": ts[-1]["campaign_id"] if ts else None,
                "influenced_orders": len(ids),
                **{
                    name: total([o.get(field) for o in values])
                    for name, field in (
                        ("requested_revenue_influenced", "requested_total"),
                        ("fulfilled_revenue_influenced", "fulfilled_total"),
                        ("requested_quantity_influenced", "requested_items_qty"),
                        ("fulfilled_quantity_influenced", "fulfilled_items_qty"),
                    )
                },
                "evidence_type": min(
                    (Evidence(r["evidence_type"]) for r in selected), key=RANK.__getitem__
                ).value
                if selected
                else None,
                "identity_path": [p for r in selected for p in r["identity_path"]],
            }
        )
    return {
        "analytics_paid_touchpoints": touches,
        "analytics_order_paid_influence": order_rows,
        "analytics_customer_paid_influence": customer_rows,
        "analytics_customer_timeline": _timeline(base, events, orders, resolutions, cids),
    }


def build(
    policy: Policy,
    *,
    customers: list[Row],
    orders: list[Row],
    events: list[Row],
    identity_links: list[Row],
    calculated_at: str,
    influence_scope: InfluenceScope | str = InfluenceScope.LIFETIME,
    paid_evidence: list[Row] | None = None,
) -> dict[str, list[Row]]:
    """paid_evidence is a legacy optional input, no longer a prerequisite in CHANGE #08."""
    with localcontext() as context:
        context.prec = 78
        return _build(
            policy,
            customers=customers,
            orders=orders,
            events=events,
            identity_links=identity_links,
            calculated_at=calculated_at,
            influence_scope=InfluenceScope(influence_scope),
            paid_evidence=paid_evidence,
        )
