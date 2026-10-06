"""A completed HEAD/RECEIPT is the authority; work status alone grants no visibility."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from src.analytics.config import AnalyticsPolicy
from src.control_plane.model import StoreConfig, Window, instant
from src.dashboard.contracts import Grant, Publication, ReadError
from src.dashboard.installation_queries import build_installation
from src.dashboard.queries import Query, build, table
from src.dashboard.repository import Reader
from src.dashboard.service import resolve_publication
from src.installation.model import Row


def policy_for(config: StoreConfig, row: Row, snapshot: str) -> AnalyticsPolicy:
    f = row["filters"]
    boundary = datetime.combine(
        date.fromisoformat(f["report_from"]), time(), ZoneInfo(config.timezone or "")
    ).astimezone(UTC)
    return replace(
        config,
        facts_complete=f["facts_complete"],
        facts_coverage_from=min(instant(config.history_from or ""), boundary).isoformat(),
        facts_coverage_to=f["as_of"],
    ).policy(Window(f["report_from"], f["report_to"], f["as_of"], snapshot, snapshot))


def available(
    reader: Reader,
    project: str,
    config: StoreConfig,
    rows: list[Row],
    snapshot: str,
    request: str,
    *,
    head_evidence: list[Row] | None = None,
) -> tuple[AnalyticsPolicy | None, Any]:
    publications = sorted(
        (r for r in rows if r["unit_kind"] == "PUBLISH_ANALYTICS"),
        key=lambda r: instant(r["filters"]["as_of"]),
        reverse=True,
    )
    if not publications:
        return None, None
    # Hash identifies the commercial contract, not a period/coverage claim.
    probe = policy_for(config, publications[0], snapshot)
    heads = (
        reader.query(
            build(
                project,
                "head",
                store=config.store_id,
                policy=probe.policy_hash,
                snapshot_at=snapshot,
            ),
            request_id=request,
            store_id=config.store_id,
            generation=None,
        )
        if head_evidence is None
        else [h for h in head_evidence if h.get("policy_hash") == probe.policy_hash]
    )
    if not heads:
        if any(r["status"] == "COMPLETE" for r in publications):
            raise ReadError(503, "publication_invalid")
        return None, None
    if len(heads) != 1:
        raise ReadError(503, "publication_invalid")
    h = heads[0]
    start, end = str(h.get("receipt_from")), str(h.get("receipt_to"))
    cutoff = str(h.get("receipt_as_of"))
    recurring = (
        config.status == "ACTIVE"
        and config.sync_enabled
        and all(r["status"] == "COMPLETE" for r in rows)
    )
    if not recurring and instant(cutoff) > instant(publications[0]["filters"]["as_of"]):
        raise ReadError(503, "publication_invalid")
    # Coverage flags come from the materialized snapshot, including legacy HEADs.
    # Never infer published facts_complete from a newly adopted global registry flag.
    daily = table(project, "up_analytics", "analytics_store_daily")
    funnel = table(project, "up_analytics", "analytics_funnel_daily")
    flags_query = Query(
        "installation_publication_flags",
        f"""SELECT s.history_complete,s.currency,s.reporting_timezone,f.observation_complete AS facts_complete
FROM (SELECT DISTINCT history_complete,currency,reporting_timezone FROM {daily} FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND policy_hash=@policy AND order_date>=@from AND order_date<@to) s
CROSS JOIN (SELECT DISTINCT observation_complete FROM {funnel} FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND policy_hash=@policy AND event_date>=@from AND event_date<@to) f LIMIT 3""",
        {
            "store": ("STRING", config.store_id),
            "policy": ("STRING", probe.policy_hash),
            "snapshot_at": ("TIMESTAMP", snapshot),
            "from": ("DATE", start),
            "to": ("DATE", end),
        },
    )
    if head_evidence is None:
        flags = reader.query(
            flags_query,
            request_id=request,
            store_id=config.store_id,
            generation=h.get("generation"),
        )
    else:
        try:
            if any(
                type(h.get(key)) is not int or h[key] < 1
                for key in ("store_observed_rows", "facts_observed_rows")
            ) or any(
                not isinstance(h.get(key), list) or len(h[key]) != 1
                for key in ("store_flags", "facts_flags")
            ):
                raise ValueError
            store_flags = json.loads(h["store_flags"][0])
            facts_flags = json.loads(h["facts_flags"][0])
            if not isinstance(store_flags, dict) or not isinstance(facts_flags, dict):
                raise ValueError
            flags = [{**store_flags, **facts_flags}]
        except (ValueError, TypeError, KeyError):
            raise ReadError(503, "publication_invalid") from None
    if (
        len(flags) != 1
        or type(flags[0].get("history_complete")) is not bool
        or type(flags[0].get("facts_complete")) is not bool
        or flags[0]["history_complete"] != config.history_complete
        or flags[0].get("currency") != config.currency
        or flags[0].get("reporting_timezone") != config.timezone
    ):
        raise ReadError(503, "publication_invalid")
    publication_row = {
        "filters": {
            "report_from": start,
            "report_to": end,
            "as_of": cutoff,
            "facts_complete": flags[0]["facts_complete"],
        }
    }
    policy = policy_for(config, publication_row, snapshot)
    try:
        heads[0]["snapshot_at"] = snapshot
        return policy, resolve_publication(heads, policy)
    except ReadError:
        raise ReadError(503, "publication_invalid") from None


def resolve_policy(
    reader: Reader, project: str, grant: Grant, request: str, *, consolidated: bool = False
) -> tuple[AnalyticsPolicy, Publication] | None:
    """Optional server composition for V2. Authorization MUST precede this call."""
    context = reader.query(
        build_installation(
            project,
            "installation_context" if consolidated else "installation_registry",
            grant.store_id,
            None,
        ),
        request_id=request,
        store_id=grant.store_id,
        generation=None,
    )
    if consolidated:
        if len(context) != 1 or any(
            not isinstance(context[0].get(key), list)
            or any(not isinstance(row, dict) for row in context[0][key])
            for key in ("registry", "plans", "units", "heads")
        ):
            raise ReadError(503, "installation_metadata_invalid")
        registry = context[0]["registry"]
        if len(context[0]["heads"]) > 1000 or any(
            h.get("store_id") != grant.store_id for h in context[0]["heads"]
        ):
            raise ReadError(503, "publication_invalid")
        for row in registry:
            row["snapshot_at"] = context[0].get("snapshot_at")
    else:
        registry = context
    if len(registry) != 1 or registry[0].get("store_id") != grant.store_id:
        raise ReadError(503, "installation_registry_invalid")
    snapshot = str(registry[0]["snapshot_at"])
    plans = (
        context[0]["plans"]
        if consolidated
        else reader.query(
            build_installation(project, "installation_plans", grant.store_id, snapshot),
            request_id=request,
            store_id=grant.store_id,
            generation=None,
        )
    )
    if not plans:
        return None  # Explicit legacy fallback, not a forged policy.
    if len(plans) != 1:
        raise ReadError(503, "installation_metadata_invalid")
    units = (
        context[0]["units"]
        if consolidated
        else reader.query(
            build_installation(project, "installation_units", grant.store_id, snapshot),
            request_id=request,
            store_id=grant.store_id,
            generation=None,
        )
    )
    if len(units) > 10000 or any(
        r.get("store_id") != grant.store_id or r.get("plan_id") != plans[0]["plan_id"]
        for r in units
    ):
        raise ReadError(503, "installation_metadata_invalid")
    row = {k: v for k, v in registry[0].items() if k != "snapshot_at"}
    policy, publication = available(
        reader,
        project,
        StoreConfig.from_row(row),
        units,
        snapshot,
        request,
        head_evidence=context[0]["heads"] if consolidated else None,
    )
    if policy is None:
        raise ReadError(503, "publication_unavailable")
    return policy, publication
