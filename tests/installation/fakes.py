"""Synthetic CAS oracle. No SDK client, credentials or external IO."""

from copy import deepcopy

from src.domain.models import SafeError
from src.installation.model import ACTIVE


class MemoryLedger:
    def __init__(self, config, plan, units):
        self.c = config
        self.p = {plan["plan_id"]: deepcopy(plan)}
        self.u = {r["work_unit_id"]: deepcopy(r) for r in units}
        self.sources = {}

    def plans(self, store=None):
        return deepcopy([p for p in self.p.values() if store is None or p["store_id"] == store])

    def units(self, plan=None):
        return deepcopy([r for r in self.u.values() if plan is None or r["plan_id"] == plan])

    def config(self, store):
        assert store == self.c.store_id
        return self.c

    def create(self, config, plan, units):
        if self.p and plan["plan_id"] not in self.p:
            raise SafeError("installation_plan_conflict")
        self.p.setdefault(plan["plan_id"], deepcopy(plan))
        for row in units:
            self.u.setdefault(row["work_unit_id"], deepcopy(row))

    def transition(self, old, **changes):
        saved = self.u[old["work_unit_id"]]
        if saved != old:
            raise SafeError("installation_work_conflict")
        new = {**old, **changes, "revision": old["revision"] + 1}
        self.u[old["work_unit_id"]] = deepcopy(new)
        return new

    def reserve(self, old, token, at, limits):
        if (
            old["status"] not in {"PENDING", "DEFERRED"}
            or any(
                r["store_id"] == old["store_id"] and r["status"] in ACTIVE for r in self.u.values()
            )
            or len({r["store_id"] for r in self.u.values() if r["status"] in ACTIVE})
            >= limits.global_parallel_store_limit
        ):
            raise SafeError("installation_work_conflict")
        return self.transition(
            old,
            status="DISPATCHING",
            dispatch_token=token,
            reservation_revision=old["revision"] + 1,
            attempt_count=old["attempt_count"] + 1,
            dispatch_operation_name=None,
            execution_name=None,
            updated_at=at,
        )

    def update_plan(self, old, config=None, **changes):
        if self.p[old["plan_id"]] != old:
            raise SafeError("installation_plan_conflict")
        new = {**old, **changes, "revision": old["revision"] + 1}
        if config:
            self.c = config
            new["registry_revision"] = config.revision
        self.p[old["plan_id"]] = deepcopy(new)
        return new

    def verified(self, old, source, at, *, success=True):
        self.sources[source["connection_id"]] = {
            **source,
            "status": "active" if success else "error",
        }
        return self.transition(old, status="COMPLETE" if success else "BLOCKED", finished_at=at)
