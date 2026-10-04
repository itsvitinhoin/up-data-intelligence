"""Bounded new-onboarding preparation, isolated definite failures, no legacy adoption."""

from collections.abc import Callable
from contextlib import AbstractContextManager

from src.control_plane.model import StoreConfig, Window
from src.domain.models import SafeError
from src.installation.model import Limits, Row, require_creatable_plan
from src.installation.planner import Planner
from src.installation.repository import BigQueryLedger
from src.observability.logging import event
from src.utils.data import now


class AutoPrepare:
    def __init__(
        self,
        ledger: BigQueryLedger,
        source: Callable[[StoreConfig, str], Row],
        lease: Callable[[str], AbstractContextManager[None]],
        limits: Limits,
        clock: Callable[[], str] = now,
    ):
        self.ledger, self.source, self.lease, self.limits, self.clock = (
            ledger,
            source,
            lease,
            limits,
            clock,
        )

    def __call__(self, store: str | None) -> None:
        for operation in self.ledger.onboardings(self.limits.max_stores, store):
            current_store = operation["store_id"]
            try:
                with self.lease(current_store):
                    if self.ledger.plans(current_store):
                        continue
                    c = self.ledger.config(current_store)
                    if c.status != "DRAFT" or c.sync_enabled:
                        raise SafeError("installation_store_not_admissible")
                    for system in ("upzero", "meta"):
                        if getattr(c, system + "_enabled"):
                            self.source(c, system)
                    target = Window.previous_closed_day(c.timezone or "", self.clock()).as_of
                    cp, runs = self.ledger.evidence(current_store)
                    configured, plan, units = Planner(self.limits).calculate(
                        c, target, self.clock(), operation=operation, checkpoints=cp, runs=runs
                    )
                    require_creatable_plan(plan)
                    self.ledger.create(configured, plan, units)
            except SafeError as exc:
                if exc.code.endswith("outcome_unknown"):
                    raise
                if exc.code in {
                    "store_busy_or_lease_unavailable",
                    "store_busy",
                }:
                    continue
                # Persist a CAS failure receipt. Never silently loop on a broken brand.
                self.ledger.block_onboarding(operation, exc.code, self.clock())
                event("installation_onboarding_blocked", store_id=current_store, code=exc.code)
