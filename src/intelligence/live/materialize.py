"""Bounded pure #16 calculation; no cloud IO or invented identity relationships."""

from typing import Any

from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row, total
from src.connectors.meta.config import Account
from src.influence.engine import InfluenceScope
from src.influence.materialization import materialize as influence_build
from src.intelligence.live.schema import PUBLICATION, SCHEMAS
from src.intelligence.materialization import materialize as customer_build
from src.performance.engine import MediaCoverage, divide
from src.performance.engine import build as performance_build
from src.utils.data import canonical, digest, numeric, timestamp


def build(
    policy: AnalyticsPolicy,
    snapshot: Row,
    *,
    account: Account,
    meta_insights: list[Row],
    meta_campaigns: list[Row],
    coverage: MediaCoverage,
    calculated_at: str,
    source_snapshot_at: str,
    base_publication: Row,
    generation: int,
) -> Row:
    if type(generation) is not int or not 1 <= generation < 2**63:
        raise ValueError("intelligence_generation_required")
    if set(snapshot) != {"customers", "orders", "items", "events", "identity_links"}:
        raise ValueError("intelligence_source_set_incomplete")
    if len(canonical(snapshot).encode()) > 32 * 1024 * 1024:
        raise ValueError("bounded_intelligence_payload_required")
    if sum(map(len, snapshot.values())) + len(meta_insights) + len(meta_campaigns) > 100000:
        raise ValueError("bounded_intelligence_snapshot_required")
    if any(r.get("store_id") != policy.store_id for rows in snapshot.values() for r in rows):
        raise ValueError("mixed_intelligence_store")
    if any(
        r.get("store_id") != policy.store_id or r.get("account_id") != account.account_id
        for r in meta_insights + meta_campaigns
    ):
        raise ValueError("mixed_meta_store_or_account")
    at, snap = timestamp(calculated_at), timestamp(source_snapshot_at)
    if snap > at:
        raise ValueError("source_snapshot_after_calculation")
    if (
        base_publication.get("store_id") != policy.store_id
        or base_publication.get("policy_hash") != policy.policy_hash
        or base_publication.get("generation", 0) < 1
        or timestamp(base_publication.get("as_of")) != timestamp(policy.as_of)
        or base_publication.get("report_from") != policy.report_from
        or base_publication.get("report_to") != policy.report_to
    ):
        raise ValueError("incompatible_analytics_base")
    p = policy.reference()
    sources = {k: v for k, v in snapshot.items() if k != "items"}
    influence = {
        s.value: influence_build(p, sources, calculated_at=at, influence_scope=s)
        for s in InfluenceScope
    }
    customers = customer_build(p, **snapshot, influence=influence, calculated_at=at)
    perf = performance_build(
        p,
        sources,
        accounts=(account,),
        meta_insights=meta_insights,
        meta_campaigns=meta_campaigns,
        coverage=coverage,
        calculated_at=at,
    )
    tables = {k: v for k, v in customers["tables"].items()}
    lifetime = influence["LIFETIME"]["tables"]
    tables["analytics_paid_touchpoints"] = lifetime["analytics_paid_touchpoints"]
    for name in ("analytics_customer_paid_influence", "analytics_order_paid_influence"):
        tables[name] = [r for a in influence.values() for r in a["tables"][name]]
    tables.update(perf["tables"])
    # Store totals include all proven participation, even when campaign mapping is absent.
    # Campaign rows remain restricted to the explicitly bound Meta account catalog.
    selected = {r["order_id"]: r for r in lifetime["analytics_order_paid_influence"]}
    summary = tables["analytics_performance_summary"][0]
    summary["influenced_orders"] = len(selected)
    summary["influenced_customers"] = len({r["customer_id"] for r in selected.values()})
    for key, field in [
        ("requested_revenue_influenced", "requested_total"),
        ("fulfilled_revenue_influenced", "fulfilled_total"),
        ("requested_quantity_influenced", "requested_items_qty"),
        ("fulfilled_quantity_influenced", "fulfilled_items_qty"),
    ]:
        summary[key] = numeric(total([r.get(field) for r in selected.values()]))
    summary["fulfillment_rate"] = numeric(
        divide(
            total([r.get("fulfilled_total") for r in selected.values()]),
            total([r.get("requested_total") for r in selected.values()]),
        )
    )
    unresolved = sum(not t["identity_path"] for t in tables["analytics_paid_touchpoints"])
    complete = policy.facts_complete and unresolved == 0 and perf["metadata"]["influence_complete"]
    for name, rows in tables.items():
        for row in rows:
            row["generation"] = generation
            if name == "analytics_campaign_performance_daily":
                campaign = next(
                    (c for c in meta_campaigns if c["campaign_id"] == row["campaign_id"]), {}
                )
                row["campaign_status"] = campaign.get("effective_status") or campaign.get("status")
            if name in {"analytics_customer_paid_influence", "analytics_order_paid_influence"}:
                row["row_key"] = digest([row["row_key"], row["influence_scope"]])
            if name.startswith("analytics_campaign_") or name == "analytics_performance_summary":
                row["influence_complete"] = complete
                if not complete:
                    for key in ("roas_requested", "roas_fulfilled", "cac_new_customer"):
                        if key in row:
                            row[key] = None
                if not policy.history_complete:
                    for key in ("new_customers_influenced", "cac_new_customer"):
                        if key in row:
                            row[key] = None
            if not complete:
                for key in (
                    "paid_media_influenced",
                    "acquisition_influenced",
                    "repeat_purchase_influenced",
                ):
                    if row.get(key) is False:
                        row[key] = None
                if isinstance(row.get("influence_by_scope"), dict):
                    for scoped in row["influence_by_scope"].values():
                        if scoped.get("influenced") is False:
                            scoped["influenced"] = None
            if set(row) != set(SCHEMAS[name].fields):
                raise ValueError("intelligence_schema_mismatch")
        keys = [(r["store_id"], r.get("influence_scope"), r["row_key"]) for r in rows]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate_intelligence_grain")
    publication: dict[str, Any] = {
        "record_kind": "RECEIPT",
        "store_id": policy.store_id,
        "policy_hash": policy.policy_hash,
        "generation": generation,
        "status": "completed",
        "as_of": timestamp(policy.as_of),
        "calculated_at": at,
        "report_from": policy.report_from,
        "report_to": policy.report_to,
        "source_snapshot_at": snap,
        "source_snapshot_hash": digest({k: sorted(v, key=canonical) for k, v in snapshot.items()}),
        "meta_configuration_hash": coverage.configuration_hash,
        "meta_account_id": account.account_id,
        "base_publication_id": base_publication["publication_id"],
        "base_generation": base_publication["generation"],
        "history_complete": policy.history_complete,
        "facts_complete": policy.facts_complete,
        "meta_complete": coverage.complete,
        "influence_complete": complete,
        "customer_intelligence_complete": True,
        "performance_complete": True,
        "row_counts": {k: len(v) for k, v in tables.items()},
        "limitations": (["history_incomplete"] if not policy.history_complete else [])
        + (["unresolved_or_unmapped_paid_influence"] if not complete else [])
        + (["meta_spend_incomplete"] if not coverage.complete else []),
    }
    # Generation is a physical sequence; logical identity covers inputs/config/policy/cutoffs.
    publication_id = digest(
        [
            {k: v for k, v in publication.items() if k != "generation"},
            {
                n: [{k: v for k, v in r.items() if k != "generation"} for r in rows]
                for n, rows in tables.items()
            },
        ]
    )
    publication.update(publication_id=publication_id, row_key=publication_id)
    tables[PUBLICATION] = [publication]
    return {"tables": tables, "publication": publication}
