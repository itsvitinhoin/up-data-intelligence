"""Canonical checkpoint evidence; never reset or infer across gaps."""

from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.installation.model import Row, interval
from src.utils.data import digest


def prefix(start: str, end: str, intervals: list[tuple[str, str]]) -> str:
    cursor, stop = instant(start), instant(end)
    for a, b in sorted((instant(a), instant(b)) for a, b in intervals):
        if a > cursor:
            break
        if b > cursor:
            cursor = min(b, stop)
    return cursor.isoformat()


def inspect(config: StoreConfig, checkpoints: list[Row], runs: list[Row], target: str) -> Row:
    existing: dict[str, list[tuple[str, str]]] = {"orders": [], "analytics_facts": []}
    pending: list[Row] = []
    fresh = False
    for cp in checkpoints:
        if (
            cp.get("store_id") != config.store_id
            or cp.get("connection_id") != config.upzero_connection_id
        ):
            continue
        if cp.get("status") == "needs_review":
            raise SafeError("installation_checkpoint_needs_review")
        resource, filters, mode = cp["resource"], cp["filters"], cp["mode"]
        if resource in {"products", "variants", "attributes", "inventory"}:
            # Catalog checkpoints are current snapshots, never historical orders/facts
            # coverage or customer freshness. Still validate their ownership/identity.
            expected = digest(
                [config.store_id, config.upzero_connection_id, resource, filters, mode]
            )
            matching = [
                r
                for r in runs
                if r.get("run_id") == cp.get("run_id")
                and r.get("store_id") == config.store_id
                and r.get("resource") == resource
                and r.get("source") == "upzero"
                and r.get("plan_key") == expected
            ]
            if (
                mode != "incremental"
                or not isinstance(filters, dict)
                or not filters.get("catalog_as_of")
                or cp.get("plan_key") != expected
                or len(matching) != 1
            ):
                raise SafeError("work_checkpoint_mismatch")
            if cp.get("status") == "complete" and (
                cp.get("pending_raw_id") is not None
                or matching[0].get("status") != "completed"
                or matching[0].get("core_records_failed") != 0
            ):
                raise SafeError("installation_checkpoint_not_certified")
            continue
        if resource not in {"orders", "customers", "analytics_facts"} or mode not in {
            "backfill",
            "incremental",
            "reconcile",
        }:
            raise SafeError("work_checkpoint_mismatch")
        expected = digest([config.store_id, config.upzero_connection_id, resource, filters, mode])
        if cp.get("plan_key") != expected:
            raise SafeError("work_checkpoint_mismatch")
        matching = [
            r
            for r in runs
            if r.get("run_id") == cp.get("run_id")
            and r.get("store_id") == config.store_id
            and r.get("resource") == resource
            and r.get("source") == "upzero"
            and r.get("plan_key") == cp["plan_key"]
        ]
        if len(matching) != 1:
            raise SafeError("work_checkpoint_mismatch")
        run = matching[0]
        cp = {
            **cp,
            "records_processed": run.get("core_records_processed", run.get("records_read", 0)),
            "pages_processed": run.get("core_pages_processed", 0),
        }
        if cp.get("pending_raw_id") or cp.get("status") not in {"complete", "recovered"}:
            allowed = (
                {"limit", "after_id"}
                if resource == "customers"
                else {"from", "to", "limit"}
                if resource == "analytics_facts"
                else {"start_date", "end_date", "limit"}
            )
            if not set(filters) <= allowed:
                raise SafeError("work_checkpoint_mismatch")
            pending.append(cp)
            continue
        if cp["status"] == "recovered":
            continue  # historical recovery is never current snapshot freshness
        if (
            run.get("status") != "completed"
            or run.get("core_records_failed", run.get("records_failed", 0)) != 0
        ):
            raise SafeError("installation_checkpoint_not_certified")
        if resource == "customers":
            fresh |= bool(
                set(filters) <= {"limit"}
                and run.get("finished_at")
                and instant(run["finished_at"]) >= instant(target)
            )
        else:
            permitted = (
                {"from", "to", "limit"}
                if resource == "analytics_facts"
                else {"start_date", "end_date", "limit"}
            )
            covered = interval(resource, filters, config.timezone or "")
            if covered and set(filters) <= permitted:
                existing[resource].append(covered)
    return {"coverage": existing, "pending": pending, "customers_fresh": fresh}
