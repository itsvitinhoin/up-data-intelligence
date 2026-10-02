"""Durable logical units. Checkpoints alone own cursors/pending RAW."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.utils.data import digest

VERSION = "1.0.0"
PLAN_STATES = frozenset("PLANNING RUNNING PARTIAL COMPLETE BLOCKED OUTCOME_UNKNOWN".split())
WORK_STATES = frozenset(
    "PENDING DISPATCHING RUNNING DEFERRED COMPLETE BLOCKED DISPATCH_UNKNOWN OUTCOME_UNKNOWN".split()
)
ACTIVE = frozenset({"DISPATCHING", "RUNNING", "DISPATCH_UNKNOWN", "OUTCOME_UNKNOWN"})
AMBIGUOUS = frozenset({"DISPATCH_UNKNOWN", "OUTCOME_UNKNOWN"})
KINDS = frozenset(
    "VERIFY_SOURCE SYNC_SNAPSHOT SYNC_WINDOW LEGACY_RESUME PUBLISH_ANALYTICS META_CATALOG META_INSIGHTS".split()
)
Row = dict[str, Any]


@dataclass(frozen=True)
class Limits:
    global_parallel_store_limit: int = 2
    max_stores: int = 10
    max_dispatches: int = 20
    max_units: int = 10000
    page_budget: int = 20
    soft_time_budget_seconds: float = 600
    max_failures: int = 3
    publication_days: int = 7

    def __post_init__(self) -> None:
        if (
            any(
                type(v) is not int or v < 1
                for k, v in asdict(self).items()
                if k != "soft_time_budget_seconds"
            )
            or not 0 < self.soft_time_budget_seconds <= 600
            or self.global_parallel_store_limit > 10
            or self.max_stores > 10
            or self.max_dispatches > 20
            or self.page_budget > 20
        ):
            raise SafeError("invalid_installation_limits")


DEFAULT_LIMITS = Limits()


def local_days(start: str, end: str, timezone: str) -> list[tuple[str, str]]:
    a, b, zone = instant(start), instant(end), ZoneInfo(timezone)
    if a >= b:
        raise SafeError("invalid_installation_range")
    day, stop = a.astimezone(zone).date(), b.astimezone(zone).date()
    if a != datetime.combine(day, time(), zone).astimezone(UTC) or b != datetime.combine(
        stop, time(), zone
    ).astimezone(UTC):
        raise SafeError("closed_local_days_required")
    if (stop - day).days > 3660:
        raise SafeError("installation_range_too_large")
    windows = []
    while day < stop:
        nxt = day + timedelta(days=1)
        windows.append(
            (
                datetime.combine(day, time(), zone).astimezone(UTC).isoformat(),
                datetime.combine(nxt, time(), zone).astimezone(UTC).isoformat(),
            )
        )
        day = nxt
    return windows


def config_hash(config: StoreConfig) -> str:
    # Own coverage/status/revision changes are CASed with the plan, never lifetime proof.
    excluded = {
        "row_key",
        "revision",
        "updated_at",
        "status",
        "sync_enabled",
        "facts_complete",
        "facts_coverage_from",
        "facts_coverage_to",
        "analytics_enabled",
    }
    return digest({k: v for k, v in config.row().items() if k not in excluded})


def unit(
    plan: Row,
    source: str,
    connection: str,
    resource: str,
    kind: str,
    filters: Row,
    dependencies: list[str],
    sequence: int,
    *,
    mode: str = "backfill",
    required: bool = True,
    checkpoint: Row | None = None,
) -> Row:
    if kind not in KINDS:
        raise SafeError("invalid_work_kind")
    key = digest([plan["plan_id"], source, connection, resource, kind, filters, mode])
    return {
        "row_key": key,
        "work_unit_id": key,
        "plan_id": plan["plan_id"],
        "store_id": plan["store_id"],
        "source": source,
        "connection_id": connection,
        "pipeline": "analytics" if kind == "PUBLISH_ANALYTICS" else source,
        "resource": resource,
        "unit_kind": kind,
        "mode": mode,
        "sequence": sequence,
        "filters": filters,
        "dependencies": dependencies,
        "required": required,
        "status": "PENDING",
        "revision": 1,
        "reservation_revision": None,
        "attempt_count": 0,
        "failure_count": 0,
        "next_eligible_at": None,
        "dispatch_token": None,
        "dispatch_operation_name": None,
        "execution_name": None,
        "checkpoint_plan_key": checkpoint.get("plan_key") if checkpoint else None,
        "run_id": checkpoint.get("run_id") if checkpoint else None,
        "records_processed": 0,
        "pages_processed": 0,
        "started_at": None,
        "updated_at": plan["created_at"],
        "finished_at": None,
        "last_error_code": None,
        "duration_seconds": 0,
        "slice_seconds": 0,
    }


def interval(resource: str, filters: Row, timezone: str) -> tuple[str, str] | None:
    if resource == "analytics_facts" and filters.get("from") and filters.get("to"):
        return instant(filters["from"]).isoformat(), instant(filters["to"]).isoformat()
    if resource == "orders" and filters.get("start_date") and filters.get("end_date"):
        zone = ZoneInfo(timezone)
        start = date.fromisoformat(filters["start_date"])
        end = date.fromisoformat(filters["end_date"]) + timedelta(days=1)
        return datetime.combine(start, time(), zone).astimezone(UTC).isoformat(), datetime.combine(
            end, time(), zone
        ).astimezone(UTC).isoformat()
    return None
