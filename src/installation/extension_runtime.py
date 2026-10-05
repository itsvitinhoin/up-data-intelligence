"""Reuse the V2 claim, CAS, launch and bounded worker protocol for extensions."""

from collections.abc import Callable
from typing import Any

from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.installation.extensions import validate_extension
from src.installation.model import Row
from src.installation.orchestrator import Orchestrator
from src.installation.progress import plan_state
from src.installation.worker import Worker


class ExtensionWorker(Worker):
    def __init__(self, *args: Any, source: Callable[[Row], Row], **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.extension_source = source

    def configuration_valid(self, plan: Row, config: StoreConfig) -> bool:
        if plan.get("status") not in {"RUNNING", "PARTIAL"}:
            return False
        try:
            validate_extension(plan, config, self.extension_source(plan))
            return True
        except SafeError:
            return False


class ExtensionOrchestrator(Orchestrator):
    def __init__(self, *args: Any, source: Callable[[Row], Row], **kwargs: Any):
        if kwargs.get("auto_activate") or kwargs.get("activation"):
            raise SafeError("extension_activation_forbidden")
        super().__init__(*args, **kwargs)
        self.extension_source = source

    def dispatch(self, store: str | None = None) -> int:
        # Normal Dispatcher holds this lease until its workers terminate. Once
        # reserved, durable extension admission blocks normal workers on this store.
        with self.lease("store-dispatch-global"):
            return super().dispatch(store)

    def dispatch_plans(self) -> list[Row]:
        # Daily snapshots accumulate. Completed graphs must neither starve new
        # work nor be invalidated retrospectively by a later credential rotation.
        return [p for p in self.ledger.plans() if p["status"] != "COMPLETE"]

    def refresh(self, plan: Row) -> Row:
        try:
            validate_extension(
                plan, self.ledger.config(plan["store_id"]), self.extension_source(plan)
            )
        except SafeError as exc:
            return self.ledger.update_plan(
                plan, status="BLOCKED", error_code=exc.code, updated_at=self.clock()
            )
        rows = self.ledger.units(plan["plan_id"])
        published, final = self.publication(plan, rows)
        state = plan_state(rows, publication_valid=published, final_valid=final)
        if state == plan["status"]:
            return plan
        # No config argument: Registry status/sync/coverage are never replaced with
        # installation DRAFT/partial intent, even while historical work runs.
        return self.ledger.update_plan(
            plan,
            status=state,
            updated_at=self.clock(),
            completed_at=self.clock() if state == "COMPLETE" else None,
        )
