"""Bounded pure performance reference. No exclusive attribution or paid revenue."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from src.analytics.engine import Row, instant, total
from src.analytics.policy import Policy
from src.connectors.meta.config import Account, validate_accounts
from src.influence.engine import InfluenceScope
from src.influence.engine import build as influence_build
from src.performance.schema import SCHEMAS
from src.quality.meta import validate_foundation
from src.utils.data import canonical, digest, numeric, timestamp


@dataclass(frozen=True)
class MediaCoverage:
    store_id: str
    account_id: str
    period_start: str
    period_end: str
    configuration_hash: str
    complete: bool
    evidence_ref: str


def divide(n: Decimal | int | None, d: Decimal | int | None) -> Decimal | None:
    if n is None or d is None or d == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 78
        return (Decimal(n) / Decimal(d)).quantize(Decimal("0.000000001"), rounding=ROUND_HALF_EVEN)


def build(
    policy: Policy,
    snapshot: Row,
    *,
    accounts: tuple[Account, ...],
    meta_insights: list[Row],
    meta_campaigns: list[Row],
    coverage: MediaCoverage,
    calculated_at: str,
    influence_scope: InfluenceScope = InfluenceScope.LIFETIME,
) -> Row:
    with localcontext() as ctx:
        ctx.prec = 78
        return _build(
            policy,
            snapshot,
            accounts,
            meta_insights,
            meta_campaigns,
            coverage,
            calculated_at,
            influence_scope,
        )


def _build(
    p: Policy,
    snapshot: Row,
    accounts: tuple[Account, ...],
    insights: list[Row],
    campaigns: list[Row],
    coverage: MediaCoverage,
    at: str,
    scope: InfluenceScope,
    precomputed: dict[str, Iterable[Row]] | None = None,
    source_snapshot_hash: str | None = None,
) -> Row:
    if (
        sum(len(snapshot[k]) for k in ("customers", "orders", "events", "identity_links"))
        + len(insights)
        + len(campaigns)
        > 100000
    ):
        raise ValueError("bounded_performance_snapshot_required")
    validate_accounts(accounts)
    local = [a for a in accounts if a.store_id == p.store_id]
    if len(local) != 1:
        raise ValueError("one_explicit_meta_account_per_store_required")
    account = local[0]
    if account.currency != p.currency or account.timezone != p.timezone:
        raise ValueError("incompatible_currency_or_timezone")
    if (
        coverage.store_id != p.store_id
        or coverage.account_id != account.account_id
        or coverage.period_start != p.report_from
        or coverage.period_end != p.report_to
        or type(coverage.complete) is not bool
        or not coverage.configuration_hash
        or (coverage.complete and not coverage.evidence_ref.strip())
    ):
        raise ValueError("invalid_media_coverage")
    scope = InfluenceScope(scope)
    at = timestamp(at)
    insights = [r for r in insights if r.get("store_id") == p.store_id]
    campaigns = [r for r in campaigns if r.get("store_id") == p.store_id]
    validate_foundation("insights", insights, account)
    validate_foundation("campaigns", campaigns, account)
    if any(instant(r["observed_at"]) > instant(at) for r in insights + campaigns):
        raise ValueError("snapshot_after_calculation")
    if any(
        r["level"] != "campaign"
        or r["breakdown_values"]
        or r["configuration_hash"] != coverage.configuration_hash
        for r in insights
    ):
        raise ValueError("campaign_level_single_configuration_no_breakdowns_required")
    campaign_map = {r["campaign_id"]: r for r in campaigns}
    if len(campaign_map) != len(campaigns):
        raise ValueError("duplicate_campaign_identity")
    insights = [r for r in insights if p.report_from <= r["date_start"] < p.report_to]
    if any(r["campaign_id"] not in campaign_map for r in insights):
        raise ValueError("insight_campaign_not_in_account_catalog")
    by_day: dict[tuple[str, str], Row] = {}
    for row in insights:
        key = (row["campaign_id"], row["date_start"])
        if key in by_day:
            raise ValueError("duplicate_campaign_day")
        by_day[key] = row
    # Existing resolver validates identity and strict paid-touch-before-conversion.
    influence = (
        precomputed
        if precomputed is not None
        else influence_build(p, **snapshot, calculated_at=at, influence_scope=scope)
    )
    candidates: list[Row] = []
    candidate_bytes = 0
    for row in influence["analytics_order_paid_influence"]:
        candidate_bytes += len(canonical(row).encode()) if precomputed is not None else 0
        if precomputed is not None and (
            len(candidates) >= 100000 or candidate_bytes > 32 * 1024 * 1024
        ):
            raise ValueError("bounded_performance_commercial_aggregates_required")
        candidates.append(row)
    matched = [r for r in candidates if r["campaign_id"] in campaign_map]
    unmapped = len(candidates) - len(matched)
    complete = p.facts_complete and unmapped == 0
    source = {
        k: sorted([r for r in snapshot[k] if r.get("store_id") == p.store_id], key=canonical)
        for k in ("customers", "orders", "events", "identity_links")
    }
    generation = digest(
        [
            source_snapshot_hash if source_snapshot_hash is not None else source,
            sorted(insights, key=canonical),
            sorted(campaigns, key=canonical),
            asdict(coverage),
            p.key,
            p.as_of,
            p.report_from,
            p.report_to,
            at,
            scope.value,
            asdict(p.history_coverage) if p.history_coverage else None,
            p.history_complete,
            p.facts_complete,
        ]
    )
    base = {
        "store_id": p.store_id,
        "account_id": account.account_id,
        "policy_hash": p.key,
        "generation": generation,
        "currency": p.currency,
        "timezone": p.timezone,
        "influence_scope": scope.value,
        "period_start": p.report_from,
        "period_end": p.report_to,
        "as_of": timestamp(p.as_of),
        "calculated_at": at,
        "history_complete": p.history_complete,
        "facts_complete": p.facts_complete,
        "spend_complete": coverage.complete,
        "influence_complete": complete,
    }
    orders = {
        r["order_id"]: r
        for r in source["orders"]
        if instant(r["created_at"]) < instant(p.as_of) and r["order_status"] in p.purchase_statuses
    }
    history: dict[str, list[Row]] = defaultdict(list)
    for order in orders.values():
        history[order["customer_id"]].append(order)
    sequence = {}
    for rows in history.values():
        rows.sort(key=lambda o: (instant(o["created_at"]), o["order_id"]))
        sequence.update({r["order_id"]: i for i, r in enumerate(rows)})

    def new_status(order: Row) -> Row:
        count = sequence[order["order_id"]]
        first = history[order["customer_id"]][0]
        return {
            "is_new_customer": False if count else True if p.history_complete else None,
            "previous_purchase_exists": True if count else False if p.history_complete else None,
            "first_purchase_at": timestamp(first["created_at"]),
            "first_qualified_order_id": first["order_id"],
            "classification_order_id": order["order_id"],
            "historical_purchase_count_before_first_purchase": count,
        }

    def metrics(rows: list[Row], spend: Decimal | None) -> Row:
        unique = {r["order_id"]: r for r in rows}
        customers = {r["customer_id"] for r in rows}
        unknown = False
        newcomers = set()
        for row in unique.values():
            status = new_status(orders[row["order_id"]])["is_new_customer"]
            unknown |= status is None
            if status is True:
                newcomers.add(row["customer_id"])
        new_count = None if unknown or not complete else len(newcomers)
        sums = {
            out: total([r.get(field) for r in unique.values()])
            for out, field in (
                ("requested_revenue_influenced", "requested_total"),
                ("fulfilled_revenue_influenced", "fulfilled_total"),
                ("requested_quantity_influenced", "requested_items_qty"),
                ("fulfilled_quantity_influenced", "fulfilled_items_qty"),
            )
        }
        return {
            **sums,
            "influenced_orders": len(unique),
            "influenced_customers": len(customers),
            "new_customers_influenced": new_count,
            "roas_requested": divide(sums["requested_revenue_influenced"], spend)
            if complete
            else None,
            "roas_fulfilled": divide(sums["fulfilled_revenue_influenced"], spend)
            if complete
            else None,
            "cac_new_customer": divide(spend, new_count),
            "fulfillment_rate": divide(
                sums["fulfilled_revenue_influenced"], sums["requested_revenue_influenced"]
            ),
        }

    out: dict[str, list[Row]] = {name: [] for name in SCHEMAS}

    def append(name: str, key: list[object], data: Row) -> None:
        out[name].append(
            {
                **base,
                "row_key": digest(
                    [
                        p.store_id,
                        account.account_id,
                        name,
                        p.report_from,
                        p.report_to,
                        scope.value,
                        *key,
                    ]
                ),
                **data,
            }
        )

    for row in matched:
        fields = "campaign_id order_id customer_id purchase_number first_paid_touch_at last_paid_touch_at touch_count evidence_type identity_path requested_total fulfilled_total requested_items_qty fulfilled_items_qty".split()
        append(
            "analytics_campaign_order_performance",
            [row["campaign_id"], row["order_id"]],
            {**{k: row[k] for k in fields}, **new_status(orders[row["order_id"]])},
        )
    groups: dict[tuple[str, str], list[Row]] = defaultdict(list)
    daily: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in matched:
        groups[row["campaign_id"], row["customer_id"]].append(row)
        daily[row["campaign_id"], p.local_date(orders[row["order_id"]]["created_at"])].append(row)
    for (campaign, cid), rows in sorted(groups.items()):
        m = metrics(rows, None)
        anchor = min(
            (orders[r["order_id"]] for r in rows),
            key=lambda o: (instant(o["created_at"]), o["order_id"]),
        )
        append(
            "analytics_campaign_customer_performance",
            [campaign, cid],
            {
                "campaign_id": campaign,
                "customer_id": cid,
                "paid_media_influenced": True,
                "first_paid_touch_at": min(r["first_paid_touch_at"] for r in rows),
                "last_paid_touch_at": max(r["last_paid_touch_at"] for r in rows),
                "orders_influenced": m["influenced_orders"],
                **{
                    k: m[k + "_influenced"]
                    for k in (
                        "requested_revenue",
                        "fulfilled_revenue",
                        "requested_quantity",
                        "fulfilled_quantity",
                    )
                },
                **new_status(anchor),
            },
        )
    for campaign, day in sorted(set(by_day) | set(daily)):
        media = by_day.get((campaign, day))
        observed = Decimal(media["spend"]) if media else Decimal(0)
        spend = observed if coverage.complete else None
        impressions = media["impressions"] if media else 0 if coverage.complete else None
        clicks = media["clicks"] if media else 0 if coverage.complete else None
        append(
            "analytics_campaign_performance_daily",
            [campaign, day],
            {
                "date": day,
                "campaign_id": campaign,
                "campaign_name": campaign_map[campaign]["campaign_name"],
                "adset_id": None,
                "ad_id": None,
                "spend": spend,
                "observed_spend": observed,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": divide(clicks * 100 if clicks is not None else None, impressions),
                "cpc": divide(spend, clicks),
                "cpm": divide(spend * 1000 if spend is not None else None, impressions),
                **metrics(daily.get((campaign, day), []), spend),
            },
        )
    observed_total = total([r["spend"] for r in insights])
    spend_total = observed_total if coverage.complete else None
    append(
        "analytics_performance_summary",
        [],
        {
            "meta_spend": spend_total,
            "observed_meta_spend": observed_total,
            **metrics(matched, spend_total),
        },
    )
    for name, rows in out.items():
        for row in rows:
            if set(row) != set(SCHEMAS[name]):
                raise ValueError("performance_schema_mismatch")
            for field, typ in SCHEMAS[name].items():
                if typ == "NUMERIC":
                    row[field] = numeric(row[field])
    return {
        "tables": out,
        "metadata": {
            **base,
            "contract_version": "1.0.0",
            "history_evidence_ref": p.history_coverage.evidence_ref if p.history_coverage else None,
            "media_coverage": asdict(coverage),
            "unmapped_influenced_order_campaign_pairs": unmapped,
            "status": "completed_offline",
            "content_sha256": digest(out),
        },
    }


def build_from_influence(
    policy: Policy,
    snapshot: Row,
    *,
    influence: dict[str, Iterable[Row]],
    source_snapshot_hash: str,
    accounts: tuple[Account, ...],
    meta_insights: list[Row],
    meta_campaigns: list[Row],
    coverage: MediaCoverage,
    calculated_at: str,
    influence_scope: InfluenceScope = InfluenceScope.LIFETIME,
) -> Row:
    """Additive bounded commercial aggregate API; never resolves/replays raw Facts."""
    if snapshot.get("events"):
        raise ValueError("precomputed_performance_does_not_accept_events")
    with localcontext() as ctx:
        ctx.prec = 78
        return _build(
            policy,
            snapshot,
            accounts,
            meta_insights,
            meta_campaigns,
            coverage,
            calculated_at,
            influence_scope,
            influence,
            source_snapshot_hash,
        )
