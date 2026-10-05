"""Single leased selector. Durable outcomes, not process memory, govern admission."""

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace

from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.installation.adoption import prefix
from src.installation.gateway import InstallationGateway
from src.installation.model import (
    ACTIVE,
    AMBIGUOUS,
    DEFAULT_LIMITS,
    VERSION,
    Limits,
    Row,
    config_hash,
    interval,
)
from src.installation.progress import plan_state
from src.installation.repository import Ledger
from src.observability.logging import event
from src.utils.data import now


class Orchestrator:
    def __init__(
        self,
        ledger: Ledger,
        gateway: InstallationGateway,
        lease: Callable[[str], AbstractContextManager[None]],
        publication: Callable[[Row, list[Row]], tuple[bool, bool]],
        *,
        limits: Limits = DEFAULT_LIMITS,
        clock: Callable[[], str] = now,
        prepare: Callable[[str | None], None] | None = None,
        auto_activate: bool = False,
        activation: Callable[[StoreConfig], None] | None = None,
    ):
        self.ledger, self.gateway, self.lease, self.publication = (
            ledger,
            gateway,
            lease,
            publication,
        )
        self.limits, self.clock = limits, clock
        self.prepare, self.auto_activate, self.activation = prepare, auto_activate, activation

    def refresh(self, plan: Row) -> Row:
        config = self.ledger.config(plan["store_id"])
        rows = self.ledger.units(plan["plan_id"])
        if (
            config.revision != plan["registry_revision"]
            or config_hash(config) != plan["config_hash"]
            or config.sync_enabled
            or plan["planner_version"] != VERSION
        ):
            return self.ledger.update_plan(
                plan,
                status="BLOCKED",
                error_code="installation_configuration_changed",
                updated_at=self.clock(),
            )
        published, final = self.publication(plan, rows)
        state = plan_state(rows, publication_valid=published, final_valid=final)
        coverage = plan["adopted_coverage"].get("analytics_facts", []) + [
            v
            for r in rows
            if r["source"] == "upzero"
            and r["resource"] == "analytics_facts"
            and r["status"] == "COMPLETE"
            and (v := interval(r["resource"], r["filters"], config.timezone or ""))
        ]
        end = prefix(plan["requested_from"], plan["target_as_of"], coverage)
        changes: Row = {
            "facts_complete": end == instant(plan["target_as_of"]).isoformat(),
            "facts_coverage_from": plan["requested_from"]
            if instant(end) != instant(plan["requested_from"])
            else None,
            "facts_coverage_to": end if instant(end) != instant(plan["requested_from"]) else None,
            "status": "READY" if state == "COMPLETE" else "DRAFT",
            "sync_enabled": False,
        }
        updated: StoreConfig | None = replace(config, **changes)
        if updated is not None and updated != config:
            updated = replace(updated, revision=config.revision + 1, updated_at=self.clock())
        else:
            updated = None
        if state == plan["status"] and updated is None:
            return plan
        result = self.ledger.update_plan(
            plan,
            updated,
            status=state,
            updated_at=self.clock(),
            completed_at=self.clock() if state == "COMPLETE" else None,
        )
        event(
            "installation_plan_"
            + {"PARTIAL": "partial", "COMPLETE": "completed", "BLOCKED": "blocked"}.get(
                state, "updated"
            ),
            store_id=plan["store_id"],
            plan_id=plan["plan_id"],
            status=state,
        )
        return result

    def current(self, row: Row) -> Row:
        matches = [
            r for r in self.ledger.units(row["plan_id"]) if r["work_unit_id"] == row["work_unit_id"]
        ]
        if len(matches) != 1 or matches[0].get("dispatch_token") != row.get("dispatch_token"):
            raise SafeError("installation_work_conflict")
        return matches[0]

    def reconcile(self, row: Row) -> None:
        if row["status"] in AMBIGUOUS:
            return
        try:
            execution = row.get("execution_name")
            if not execution and row.get("dispatch_operation_name"):
                op = self.gateway.operation(row["dispatch_operation_name"])
                if not op.get("done"):
                    return
                if op.get("error") or not op.get("response", {}).get("name"):
                    self.ledger.transition(
                        self.current(row),
                        status="OUTCOME_UNKNOWN",
                        last_error_code="work_execution_outcome_unknown",
                        updated_at=self.clock(),
                    )
                    return
                execution = op["response"]["name"]
                self.gateway.validate(execution, "execution", row["pipeline"])
                row = self.ledger.transition(
                    self.current(row), execution_name=execution, updated_at=self.clock()
                )
            if not execution:
                # A crash after reserve is indistinguishable from a lost accepted POST.
                self.ledger.transition(
                    self.current(row),
                    status="DISPATCH_UNKNOWN",
                    last_error_code="work_dispatch_unknown",
                    updated_at=self.clock(),
                )
                return
            state = self.gateway.execution(execution, row["pipeline"])
            if not state.get("completionTime"):
                return
            current = self.current(row)
            if current["status"] in {"PENDING", "COMPLETE", "DEFERRED", "BLOCKED", *AMBIGUOUS}:
                return  # worker durable transition is authoritative, including a successful yield
            self.ledger.transition(
                current,
                status="OUTCOME_UNKNOWN",
                last_error_code="work_execution_outcome_unknown",
                updated_at=self.clock(),
            )
        except SafeError as exc:
            if exc.code == "bigquery_write_outcome_unknown":
                raise
            # A GET failure leaves the known operation intact; no new POST is possible.
            return

    def dispatch_plans(self) -> list[Row]:
        return self.ledger.plans()

    def dispatch(self, store: str | None = None) -> int:
        with self.lease("installation-orchestrator-global"):
            if self.prepare:
                self.prepare(store)
            plans = self.dispatch_plans()
            selected = sorted(
                (p for p in plans if store is None or p["store_id"] == store),
                key=lambda p: (p["priority"], p["created_at"], p["plan_id"]),
            )[: self.limits.max_stores]
            selected_ids = {p["plan_id"] for p in selected}
            rows = self.ledger.units()
            for row in rows:
                if row["status"] in ACTIVE and row["plan_id"] in selected_ids:
                    self.reconcile(row)
            rows = self.ledger.units()
            plans = []
            busy = {r["store_id"] for r in rows if r["status"] in ACTIVE}
            for p in selected:
                if any(r["plan_id"] == p["plan_id"] and r["status"] in AMBIGUOUS for r in rows):
                    updated = self.ledger.update_plan(
                        p,
                        status="OUTCOME_UNKNOWN",
                        error_code="work_execution_outcome_unknown",
                        updated_at=self.clock(),
                    )
                    if self.auto_activate:
                        raise SafeError("work_execution_outcome_unknown")
                    plans.append(updated)
                    continue
                if p["store_id"] in busy:
                    plans.append(p)
                    continue
                updated = p
                try:
                    with self.lease(p["store_id"]):
                        updated = self.refresh(p)
                        if updated["status"] == "OUTCOME_UNKNOWN":
                            raise SafeError("work_execution_outcome_unknown")
                        if (
                            self.auto_activate
                            and updated["status"] == "COMPLETE"
                            and updated.get("onboarding_operation_id")
                        ):
                            c = self.ledger.config(p["store_id"])
                            if not self.activation:
                                raise SafeError("installation_activation_required")
                            self.activation(c)
                            updated = self.ledger.activate(updated, c, self.clock())
                        plans.append(updated)
                except SafeError as exc:
                    if exc.code.endswith("outcome_unknown"):
                        raise
                    if exc.code in {"store_busy_or_lease_unavailable", "store_busy"}:
                        plans.append(p)
                        continue
                    if store is not None:
                        raise
                    self.ledger.update_plan(
                        updated, status="BLOCKED", error_code=exc.code, updated_at=self.clock()
                    )
                    event("installation_onboarding_blocked", store_id=p["store_id"], code=exc.code)
            rows = self.ledger.units()
            active = {r["store_id"] for r in rows if r["status"] in ACTIVE}
            complete = {r["work_unit_id"] for r in rows if r["status"] == "COMPLETE"}
            eligible = {p["plan_id"]: p for p in plans if p["status"] in {"RUNNING", "PARTIAL"}}
            candidates = sorted(
                (
                    r
                    for r in rows
                    if r["plan_id"] in eligible and r["status"] in {"PENDING", "DEFERRED"}
                ),
                key=lambda r: (
                    eligible[r["plan_id"]]["priority"],
                    r["sequence"],
                    eligible[r["plan_id"]]["created_at"],
                    r["work_unit_id"],
                ),
            )
            count = 0
            seen: set[str] = set()
            for row in candidates:
                if (
                    count >= self.limits.max_dispatches
                    or len(seen) >= self.limits.max_stores
                    or len(active) >= self.limits.global_parallel_store_limit
                ):
                    break
                if (
                    row["store_id"] in active
                    or not set(row["dependencies"]) <= complete
                    or (row.get("next_eligible_at") and row["next_eligible_at"] > self.clock())
                ):
                    continue
                reserved = self.ledger.reserve(row, str(uuid.uuid4()), self.clock(), self.limits)
                event(
                    "installation_work_reserved",
                    store_id=row["store_id"],
                    plan_id=row["plan_id"],
                    work_unit_id=row["work_unit_id"],
                )
                try:
                    op = self.gateway.submit(reserved)
                    self.ledger.transition(
                        self.current(reserved), dispatch_operation_name=op, updated_at=self.clock()
                    )
                    event(
                        "installation_work_dispatched",
                        store_id=row["store_id"],
                        plan_id=row["plan_id"],
                        work_unit_id=row["work_unit_id"],
                    )
                except SafeError as exc:
                    if exc.code == "bigquery_write_outcome_unknown":
                        raise
                    self.ledger.transition(
                        self.current(reserved),
                        status="BLOCKED"
                        if exc.code == "installation_launch_rejected"
                        else "DISPATCH_UNKNOWN",
                        last_error_code=exc.code,
                        updated_at=self.clock(),
                    )
                    if self.auto_activate and exc.code != "installation_launch_rejected":
                        raise SafeError("work_dispatch_unknown") from None
                active.add(row["store_id"])
                seen.add(row["store_id"])
                count += 1
            return count
