"""One resumable catalog snapshot, sharing a bounded budget across its resources."""

import time
from collections.abc import Callable
from typing import Any

from src.domain.models import SafeError
from src.ingestion.engine import Engine
from src.quality.catalog import certify_catalog_snapshot
from src.utils.data import digest, timestamp


class CatalogSnapshot:
    def __init__(self, engine: Engine, *, clock: Callable[[], float] = time.monotonic):
        self.engine, self.clock = engine, clock

    def evidence(
        self, resource: str, filters: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        key = digest(
            [
                self.engine.cfg.store_id,
                self.engine.cfg.connection_id,
                resource,
                filters,
                "incremental",
            ]
        )
        checkpoints = self.engine.repo.read("sync_checkpoints", self.engine.cfg.store_id, [key])
        if len(checkpoints) > 1:
            raise SafeError("catalog_snapshot_conflict")
        if not checkpoints:
            return {}, {}
        cp = checkpoints[0]
        runs = self.engine.repo.read("sync_runs", self.engine.cfg.store_id, [cp["run_id"]])
        if len(runs) != 1:
            raise SafeError("catalog_snapshot_run_mismatch")
        return cp, runs[0]

    def membership(self, resource: str, run: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self.engine.repo.iter_find(
            "catalog_observations", self.engine.cfg.store_id, "run_id", [run["run_id"]]
        ):
            if len(rows) >= 10000:
                raise SafeError("catalog_snapshot_too_large")
            rows.append(row)
        return rows

    def advance(
        self, cutoff: str, *, page_budget: int = 20, soft_time_budget_seconds: float = 600
    ) -> dict[str, Any]:
        cutoff = timestamp(cutoff)
        if (
            type(page_budget) is not int
            or not 1 <= page_budget <= 20
            or not 0 < soft_time_budget_seconds <= 600
        ):
            raise SafeError("invalid_slice_budget")
        started, remaining = self.clock(), page_budget
        records = pages = 0
        proofs = []
        variant_run: dict[str, Any] = {}
        for resource in ("products", "variants", "attributes", "inventory"):
            filters: dict[str, Any] = {"catalog_as_of": cutoff}
            if resource == "products":
                filters.update(limit=200, include_inactive=True)
            elif resource == "variants":
                filters["limit"] = 200
            elif resource == "inventory":
                # Exact membership of the already certified variant snapshot.
                # Freeze it in the checkpoint filters before any inventory fetch.
                filters["variant_ids"] = sorted(
                    row["entity_id"] for row in self.membership("variants", variant_run)
                )
            checkpoint, before = self.evidence(resource, filters)
            old_pages = before.get("pages", 0)
            time_left = soft_time_budget_seconds - (self.clock() - started)
            if checkpoint.get("status") != "complete":
                if remaining == 0 or time_left <= 0:
                    return {
                        "complete": False,
                        "yielded": True,
                        "records_processed": records,
                        "pages_processed": pages,
                    }
                current = self.engine.advance(
                    resource,
                    filters,
                    mode="incremental",
                    page_budget=remaining,
                    soft_time_budget_seconds=time_left,
                )
                remaining -= current["pages"] - old_pages
                checkpoint, current = self.evidence(resource, filters)
            else:
                current = before
            records += current["core_records_processed"]
            pages += current["core_pages_processed"]
            if checkpoint.get("status") != "complete":
                return {
                    "complete": False,
                    "yielded": True,
                    "records_processed": records,
                    "pages_processed": pages,
                }
            proof = certify_catalog_snapshot(
                self.engine.cfg.store_id,
                self.engine.cfg.connection_id,
                resource,
                cutoff,
                checkpoint,
                current,
                self.membership(resource, current),
            )
            proofs.append(proof)
            if resource == "variants":
                variant_run = current
        return {
            "complete": True,
            "yielded": False,
            "records_processed": records,
            "pages_processed": pages,
            "snapshots": proofs,
        }
