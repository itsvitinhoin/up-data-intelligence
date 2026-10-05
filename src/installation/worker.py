"""Exactly one logical work unit per invocation; checkpoint remains authoritative."""

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta

from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.installation.model import DEFAULT_LIMITS, VERSION, Limits, Row, config_hash
from src.installation.repository import Ledger
from src.observability.logging import event
from src.utils.data import now

RETRYABLE = frozenset(
    {
        "retry_after_deferred",
        "meta_retry_deferred",
        "store_execution_budget_exhausted",
        "analytics_execution_query_budget_exhausted",
    }
)
UNKNOWN = frozenset(
    {
        "bigquery_write_outcome_unknown",
        "registry_write_outcome_unknown",
        "source_verification_outcome_unknown",
        "work_execution_outcome_unknown",
    }
)


class Worker:
    def __init__(
        self,
        ledger: Ledger,
        action: Callable[[StoreConfig, Row, Limits], Row],
        lease: Callable[[str], AbstractContextManager[None]],
        *,
        limits: Limits = DEFAULT_LIMITS,
        clock: Callable[[], str] = now,
        verification_source: Callable[[StoreConfig, str], Row] | None = None,
    ):
        self.verification_source = verification_source
        self.ledger, self.action, self.lease, self.limits, self.clock = (
            ledger,
            action,
            lease,
            limits,
            clock,
        )

    def current(self, row: Row) -> Row:
        matches = [
            r for r in self.ledger.units(row["plan_id"]) if r["work_unit_id"] == row["work_unit_id"]
        ]
        if (
            len(matches) != 1
            or matches[0]["status"] != "RUNNING"
            or matches[0].get("dispatch_token") != row.get("dispatch_token")
        ):
            raise SafeError("work_execution_outcome_unknown")
        return matches[0]

    def configuration_valid(self, plan: Row, config: StoreConfig) -> bool:
        return (
            plan["status"] in {"RUNNING", "PARTIAL"}
            and plan["planner_version"] == VERSION
            and config.revision == plan["registry_revision"]
            and config_hash(config) == plan["config_hash"]
            and not config.sync_enabled
        )

    def execute(self, store: str, work_id: str, revision: int, token: str, pipeline: str) -> Row:
        with self.lease("installation-work:" + store), self.lease(store):
            plans = self.ledger.plans(store)
            rows = [
                r
                for p in plans
                for r in self.ledger.units(p["plan_id"])
                if r["work_unit_id"] == work_id
            ]
            if len(rows) != 1:
                raise SafeError("installation_work_conflict")
            row = rows[0]
            if (
                row["store_id"] != store
                or row["status"] != "DISPATCHING"
                or row.get("reservation_revision") != revision
                or row.get("dispatch_token") != token
                or row["pipeline"] != pipeline
            ):
                raise SafeError("installation_work_conflict")
            plan = next(p for p in plans if p["plan_id"] == row["plan_id"])
            c = self.ledger.config(store)
            if not self.configuration_valid(plan, c):
                self.ledger.transition(
                    row,
                    status="BLOCKED",
                    last_error_code="installation_configuration_changed",
                    updated_at=self.clock(),
                )
                raise SafeError("installation_configuration_changed")
            row = self.ledger.transition(
                row,
                status="RUNNING",
                started_at=row.get("started_at") or self.clock(),
                updated_at=self.clock(),
            )
            start = time.monotonic()
            try:
                result = self.action(c, row, self.limits)
                if result.get("verified_source"):
                    return self.ledger.verified(
                        self.current(row), result["verified_source"], self.clock()
                    )
                if not result.get("complete") and not result.get("yielded"):
                    raise SafeError("installation_work_incomplete")
                # Exact cumulative run metrics: never sum the same previous slices again.
                updated = self.ledger.transition(
                    self.current(row),
                    status="COMPLETE" if result.get("complete") else "PENDING",
                    records_processed=result.get("records_processed", row["records_processed"]),
                    pages_processed=result.get("pages_processed", row["pages_processed"]),
                    run_id=result.get("run_id", row.get("run_id")),
                    checkpoint_plan_key=result.get(
                        "checkpoint_plan_key", row.get("checkpoint_plan_key")
                    ),
                    finished_at=self.clock() if result.get("complete") else None,
                    updated_at=self.clock(),
                    duration_seconds=row["duration_seconds"] + time.monotonic() - start,
                    slice_seconds=time.monotonic() - start,
                    next_eligible_at=None,
                )
                event(
                    "installation_work_completed"
                    if result.get("complete")
                    else "installation_slice_yielded",
                    store_id=store,
                    plan_id=row["plan_id"],
                    work_unit_id=work_id,
                    resource=row["resource"],
                    source=row["source"],
                    status=updated["status"],
                    records_processed=updated["records_processed"],
                    pages=updated["pages_processed"],
                )
                return updated
            except Exception as exc:
                code = exc.code if isinstance(exc, SafeError) else "installation_blocked"
                if code == "bigquery_write_outcome_unknown":
                    # Preserve RUNNING + non-expiring leases if even ledger outcome is unknown.
                    raise
                if (
                    row["unit_kind"] == "VERIFY_SOURCE"
                    and code not in UNKNOWN
                    and code not in RETRYABLE
                    and self.verification_source
                ):
                    self.ledger.verified(
                        self.current(row),
                        self.verification_source(c, row["source"]),
                        self.clock(),
                        success=False,
                    )
                    raise SafeError("source_verification_failed") from None
                failures = row["failure_count"] + 1
                state = (
                    "OUTCOME_UNKNOWN"
                    if code in UNKNOWN
                    else "DEFERRED"
                    if code in RETRYABLE and failures < self.limits.max_failures
                    else "BLOCKED"
                )
                self.ledger.transition(
                    self.current(row),
                    status=state,
                    failure_count=failures,
                    last_error_code="work_retry_exhausted"
                    if code in RETRYABLE and state == "BLOCKED"
                    else code,
                    updated_at=self.clock(),
                    next_eligible_at=(
                        instant(self.clock())
                        + timedelta(seconds=min(900, 30 * 2 ** min(failures, 5)))
                    ).isoformat()
                    if state == "DEFERRED"
                    else None,
                )
                raise SafeError(code) from None
