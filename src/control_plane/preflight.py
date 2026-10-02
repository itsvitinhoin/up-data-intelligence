"""Fail closed on source ownership, unresolved batches or unproven coverage."""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.analytics.cloud.transport import Transport, scalar
from src.connectors.meta.config import Account
from src.control_plane.model import StoreConfig, Window, instant
from src.control_plane.recovery_repository import BigQueryRecovery
from src.control_plane.repository import decoded
from src.domain.models import SafeError
from src.ingestion.checkpoints import CHECKPOINT_RECOVERED, checkpoint_pending
from src.intelligence.live.runtime import binding, reporting


class Prerequisites:
    def __init__(self, transport: Transport):
        self.transport = transport

    def rows(
        self, store: str, table: str, columns: str = "*", snapshot: str | None = None
    ) -> list[dict[str, Any]]:
        # table/columns are INTERNAL constants; every store and instant is parameterized.
        clauses = " FOR SYSTEM_TIME AS OF @snapshot" if snapshot else ""
        rows, _ = self.transport.query(
            f"SELECT {columns} FROM `{self.transport.config.project}.{table}`{clauses} WHERE store_id=@store",
            [scalar("store", "STRING", store), scalar("snapshot", "TIMESTAMP", snapshot)],
        )
        return [decoded(row) for row in rows]

    def source(self, c: StoreConfig) -> dict[str, Any]:
        rows = self.rows(
            c.store_id,
            "up_core.source_connections",
            "connection_id,source_system,status,secret_resource_name",
        )
        found = [r for r in rows if r["source_system"] == "upzero" and r["status"] == "active"]
        if len(found) != 1 or found[0]["connection_id"] != c.upzero_connection_id:
            raise SafeError("upzero_connection_not_ready")
        reference = found[0].get("secret_resource_name", "")
        if not isinstance(reference, str) or not re.fullmatch(
            r"projects/"
            + re.escape(self.transport.config.project)
            + r"/secrets/up-intelligence-upzero-[a-z0-9-]+/versions/[1-9][0-9]*",
            reference,
        ):
            raise SafeError("approved_upzero_secret_version_required")
        return found[0]

    def account(self, c: StoreConfig) -> Account:
        account = binding(self.transport, c.store_id, c.meta_account_id or "")
        if (account.connection_id, account.api_version, account.timezone, account.currency) != (
            c.meta_connection_id,
            c.meta_api_version,
            c.timezone,
            c.currency,
        ):
            raise SafeError("registry_meta_binding_mismatch")
        return account

    def configuration(self, c: StoreConfig) -> None:
        c.ready()
        if c.upzero_enabled:
            self.source(c)
        if c.meta_enabled:
            self.account(c)

    def check(self, c: StoreConfig, pipeline: str, window: Window) -> None:
        if not c.eligible(pipeline):
            raise SafeError("store_not_eligible")
        c.ready()
        if pipeline in {"upzero", "analytics", "intelligence"}:
            self.source(c)
        if pipeline in {"meta", "intelligence"}:
            self.account(c)
        if pipeline in {"analytics", "intelligence"}:
            c.policy(window).reference()
            self.upzero_complete(c, window)
        if pipeline == "intelligence":
            self.meta_complete(c, window)
            self.analytics_complete(c, window)

    def upzero_complete(self, c: StoreConfig, window: Window) -> None:
        checkpoints = self.rows(
            c.store_id, "up_ops.sync_checkpoints", snapshot=window.source_snapshot_at
        )
        runs = self.rows(
            c.store_id,
            "up_ops.sync_runs",
            "run_id,status,finished_at,core_records_failed,source,mode",
            window.source_snapshot_at,
        )
        run_map = {r["run_id"]: r for r in runs}
        if len(run_map) != len(runs):
            raise SafeError("duplicate_source_runs")
        for resource in ("customers", "orders", "analytics_facts"):
            selected = [
                r
                for r in checkpoints
                if r.get("resource") == resource
                and r.get("connection_id") == c.upzero_connection_id
            ]
            if any(checkpoint_pending(r) for r in selected):
                raise SafeError("upzero_source_not_complete")
            good = []
            for checkpoint in selected:
                if checkpoint.get("status") == CHECKPOINT_RECOVERED:
                    # Recovered Customers no longer block, but NEVER prove fresh collection.
                    # Other resources remain fail-closed until interval recovery is reviewed.
                    if resource != "customers":
                        raise SafeError("upzero_recovered_resource_not_supported")
                    BigQueryRecovery(self.transport).recovered(
                        checkpoint, c.store_id, snapshot=window.source_snapshot_at
                    )
                    continue
                run = run_map.get(checkpoint.get("run_id"))
                if (
                    run
                    and run["status"] == "completed"
                    and run["core_records_failed"] == 0
                    and run.get("source") == "upzero"
                    and run.get("mode") in {"backfill", "incremental", "reconcile"}
                ):
                    good.append((checkpoint, run))
            if not good:
                raise SafeError("upzero_complete_checkpoint_required")
            if resource == "customers":
                # An unfiltered incremental scan reaches source exhaustion (not a date window).
                if not any(
                    r["finished_at"]
                    and instant(str(r["finished_at"])) >= instant(window.as_of)
                    and set(cp["filters"]) <= {"limit"}
                    for cp, r in good
                ):
                    raise SafeError("customers_complete_scan_required")
                continue
            intervals = []
            for cp, _ in good:
                filters = cp["filters"]
                try:
                    if resource == "orders" and set(filters) <= {"start_date", "end_date", "limit"}:
                        zone = ZoneInfo(c.timezone or "")
                        start = datetime.combine(
                            date.fromisoformat(filters["start_date"]), time(), zone
                        ).astimezone(UTC)
                        end = datetime.combine(
                            date.fromisoformat(filters["end_date"]) + timedelta(days=1),
                            time(),
                            zone,
                        ).astimezone(UTC)
                    elif resource == "analytics_facts" and set(filters) <= {"from", "to", "limit"}:
                        start, end = instant(filters["from"]), instant(filters["to"])
                    else:
                        continue
                    intervals.append((start, end))
                except (KeyError, ValueError):
                    continue
            covered = instant(c.history_from or "")
            for start, end in sorted(intervals):
                if start <= covered:
                    covered = max(covered, end)
            if covered < instant(window.as_of):
                raise SafeError("upzero_history_window_not_covered")

    def meta_complete(self, c: StoreConfig, window: Window) -> None:
        account = self.account(c)
        report = reporting(account, c.policy(window))
        checkpoints = self.rows(
            c.store_id, "up_ops.sync_checkpoints", snapshot=window.source_snapshot_at
        )
        expected = {
            "account": account.snapshot(),
            "insights": {**report.snapshot(), "level": "campaign"},
        }
        found = [
            r
            for r in checkpoints
            if r["resource"] == "meta_live_insights_daily"
            and r["status"] == "complete"
            and not r.get("pending_raw_id")
            and r["filters"] == expected
        ]
        if len(found) != 1:
            raise SafeError("meta_complete_checkpoint_required")
        runs = self.rows(
            c.store_id,
            "up_ops.sync_runs",
            "run_id,status,finished_at,core_records_failed",
            window.source_snapshot_at,
        )
        run = [r for r in runs if r["run_id"] == found[0]["run_id"]]
        if len(run) != 1 or run[0]["status"] != "completed" or run[0]["core_records_failed"] != 0:
            raise SafeError("meta_source_not_complete")
        # Catalog snapshots are also dependencies; old Insights do not prove a failed
        # campaigns/adsets/ads extraction was complete.
        for resource in ("accounts", "campaigns", "adsets", "ads"):
            selected = [
                r
                for r in checkpoints
                if r["resource"] == "meta_live_" + resource
                and r["connection_id"] == c.meta_connection_id
                and r["filters"].get("account") == account.snapshot()
            ]
            if not selected or any(
                r["status"] != "complete" or r.get("pending_raw_id") for r in selected
            ):
                raise SafeError("meta_catalog_not_complete")
            ids = {r["run_id"] for r in selected}
            completed = [
                r
                for r in runs
                if r["run_id"] in ids
                and r["status"] == "completed"
                and r["core_records_failed"] == 0
                and r.get("finished_at")
                and instant(str(r["finished_at"])) >= instant(window.as_of)
            ]
            if not completed:
                raise SafeError("meta_catalog_completed_run_required")

    def analytics_complete(self, c: StoreConfig, window: Window) -> None:
        policy = c.policy(window)
        rows = self.rows(
            c.store_id, "up_analytics.analytics_publications", snapshot=window.source_snapshot_at
        )
        rows = [r for r in rows if r["policy_hash"] == policy.policy_hash]
        heads = [r for r in rows if r["record_kind"] == "HEAD"]
        if len(heads) != 1 or heads[0]["status"] != "completed":
            raise SafeError("analytics_completed_head_required")
        receipts = [
            r
            for r in rows
            if r["record_kind"] == "RECEIPT"
            and r["generation"] == heads[0]["generation"]
            and r["publication_id"] == heads[0]["publication_id"]
            and r["status"] == "completed"
        ]
        if (
            len(receipts) != 1
            or str(receipts[0]["report_from"]) != policy.report_from
            or str(receipts[0]["report_to"]) != policy.report_to
            or instant(str(receipts[0]["as_of"])) != instant(policy.as_of)
        ):
            raise SafeError("analytics_window_receipt_required")

        current = self.rows(
            c.store_id,
            "up_analytics.analytics_publications",
            "record_kind,policy_hash,generation,publication_id,status",
        )
        current_heads = [
            r
            for r in current
            if r["record_kind"] == "HEAD" and r["policy_hash"] == policy.policy_hash
        ]
        if len(current_heads) != 1 or any(
            current_heads[0].get(k) != heads[0].get(k)
            for k in ("generation", "publication_id", "status")
        ):
            raise SafeError("analytics_publication_changed_after_snapshot")
