"""Pure daily/cumulative scheduling and certified source coverage; no SDK discovery."""

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from src.connectors.meta.config import Account, Insights
from src.control_plane.model import StoreConfig, Window, instant
from src.dashboard.contracts import ReadError
from src.dashboard.service import resolve_publication
from src.domain.models import SafeError
from src.installation.adoption import inspect, prefix
from src.utils.data import digest

Row = dict[str, Any]


def certified_window(config: StoreConfig, rows: list[Row], snapshot: str) -> Window:
    """Validate the linked receipt, including legacy HEADs with NULL report dates."""
    try:
        if len(rows) != 1:
            raise ValueError("head")
        r = rows[0]
        current = Window(
            str(r["receipt_from"]),
            str(r["receipt_to"]),
            str(r["receipt_as_of"]),
            snapshot,
            snapshot,
        )
        # Coverage flags do not define the commercial hash. Validate identity/window
        # against the receipt without fabricating future coverage from Registry.
        resolve_publication(rows, replace(config, facts_complete=False).policy(current))
        return current
    except (ReadError, KeyError, TypeError, ValueError, SafeError):
        raise SafeError("recurring_publication_required") from None


def monotonic(current: Window, proposed: Window) -> None:
    if (
        proposed.report_from != current.report_from
        or proposed.report_to < current.report_to
        or instant(proposed.as_of) < instant(current.as_of)
    ):
        raise SafeError("recurring_publication_regression")


def cumulative(config: StoreConfig, daily: Window, rows: list[Row]) -> Window:
    current = certified_window(config, rows, daily.source_snapshot_at)
    proposed = replace(daily, report_from=current.report_from)
    monotonic(current, proposed)
    return proposed


def facts_coverage(
    config: StoreConfig, checkpoints: list[Row], runs: list[Row], target: str, at: str
) -> StoreConfig:
    evidence = inspect(config, checkpoints, runs, target)
    start = min(
        instant(config.history_from or ""),
        instant(config.facts_coverage_from or config.history_from or ""),
    ).isoformat()
    if evidence["pending"]:
        raise SafeError("upzero_source_not_complete")
    if not evidence["customers_fresh"]:
        raise SafeError("customers_complete_scan_required")
    for resource in ("orders", "analytics_facts"):
        if instant(prefix(start, target, evidence["coverage"][resource])) < instant(target):
            raise SafeError("upzero_history_window_not_covered")
    # A replay for an older closed day cannot regress previously certified coverage.
    end = max(instant(target), instant(config.facts_coverage_to or target)).isoformat()
    if instant(prefix(start, end, evidence["coverage"]["analytics_facts"])) < instant(end):
        raise SafeError("upzero_history_window_not_covered")
    updated = replace(config, facts_coverage_from=start, facts_coverage_to=end, facts_complete=True)
    return (
        replace(updated, revision=config.revision + 1, updated_at=at)
        if updated != config
        else config
    )


def meta_coverage(
    account: Account,
    report: Insights,
    checkpoints: list[Row],
    runs: list[Row],
    *,
    level: str = "campaign",
    resource: str = "meta_live_insights_daily",
) -> list[Row]:
    """Prove a contiguous union of exact compatible daily/range evidence.

    Only since/until vary; unknown definition fields remain incompatible. Additional
    certified intervals outside the request are allowed. Every selected row needs
    its own completed, same-store/source/resource/connection run.
    """
    if (level, resource) not in {
        ("campaign", "meta_live_insights_daily"),
        ("ad", "meta_creative_insights_daily"),
    }:
        raise SafeError("meta_coverage_grain_invalid")
    definition = {**report.definition(), "level": level}
    matching: list[Row] = []
    intervals: list[tuple[str, str]] = []
    for cp in checkpoints:
        if (
            cp.get("store_id") != account.store_id
            or cp.get("connection_id") != account.connection_id
            or cp.get("resource") != resource
        ):
            continue
        f = cp.get("filters") or {}
        spec = f.get("insights") or {}
        if (
            f.get("account") != account.snapshot()
            or {k: v for k, v in spec.items() if k not in {"since", "until"}} != definition
        ):
            continue
        try:
            start, last = date.fromisoformat(spec["since"]), date.fromisoformat(spec["until"])
        except (KeyError, ValueError, TypeError):
            raise SafeError("meta_complete_checkpoint_required") from None
        if start > last:
            raise SafeError("meta_complete_checkpoint_required")
        if last < date.fromisoformat(report.since) or start > date.fromisoformat(report.until):
            continue
        linked = [r for r in runs if r.get("run_id") == cp.get("run_id")]
        if (
            cp.get("status") != "complete"
            or cp.get("pending_raw_id")
            or len(linked) != 1
            or linked[0].get("store_id") != account.store_id
            or linked[0].get("plan_key") != cp.get("plan_key")
            or linked[0].get("source") != "meta"
            or linked[0].get("resource") != resource
            or linked[0].get("status") != "completed"
            or linked[0].get("core_records_failed") != 0
        ):
            raise SafeError("meta_complete_checkpoint_required")
        # Canonical date union has inclusive until, represented as exclusive next day.
        intervals.append(
            (
                start.isoformat() + "T00:00:00Z",
                (last + timedelta(days=1)).isoformat() + "T00:00:00Z",
            )
        )
        matching.append(cp)
    end = (date.fromisoformat(report.until) + timedelta(days=1)).isoformat() + "T00:00:00Z"
    if instant(prefix(report.since + "T00:00:00Z", end, intervals)) != instant(end):
        raise SafeError("meta_complete_checkpoint_required")
    if len({r.get("plan_key") for r in matching}) != len(matching):
        raise SafeError("meta_complete_checkpoint_required")
    return sorted(
        matching,
        key=lambda r: (
            r["filters"]["insights"]["since"],
            r["filters"]["insights"]["until"],
            r["plan_key"],
            r["run_id"],
        ),
    )


def meta_evidence_hash(rows: list[Row]) -> str:
    return digest(
        sorted(
            (
                {
                    "plan_key": r["plan_key"],
                    "run_id": r["run_id"],
                    "filters": r["filters"],
                    "status": r["status"],
                    "pending_raw_id": r.get("pending_raw_id"),
                }
                for r in rows
            ),
            key=lambda r: (r["plan_key"], r["run_id"]),
        )
    )
