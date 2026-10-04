"""One dynamically configured store, one lease and one cost envelope per execution."""

import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict, replace
from datetime import date, timedelta
from typing import Any

from src.analytics.cloud.reader import BigQueryAnalyticsReader, SourceGeneration
from src.analytics.cloud.runner import materialize as analytics_materialize
from src.analytics.cloud.transport import Transport
from src.analytics.cloud.writer import BigQueryAnalyticsWriter, Publication
from src.analytics.materialization import CoreSnapshot, plan_changes
from src.bigquery.repository import BigQueryRepository
from src.config.settings import Settings
from src.connectors.meta.config import Insights
from src.connectors.meta.live import MetaFoundationLiveConnector
from src.connectors.upzero.client import UpZeroConnector
from src.control_plane.model import StoreConfig, Window
from src.control_plane.preflight import Prerequisites
from src.control_plane.recovery_repository import BigQueryRecovery
from src.control_plane.recurring import certified_window, facts_coverage, monotonic
from src.control_plane.registry import Registry
from src.domain.models import SafeError
from src.ingestion.checkpoints import CHECKPOINT_RECOVERED, checkpoint_pending
from src.ingestion.engine import Engine, row_key
from src.ingestion.meta_live import MetaLiveEngine
from src.ingestion.planning import incremental, open_order_windows
from src.intelligence.live.cli import validated_secret_reference
from src.intelligence.live.runtime import materialize as intelligence_materialize
from src.observability.logging import event
from src.security.secrets import resolve_secret
from src.utils.data import digest, now


class StoreWorker:
    def __init__(
        self,
        registry: Registry,
        prerequisites: Callable[[StoreConfig, str, Window], None],
        lease: Callable[[str], AbstractContextManager[None]],
        action: Callable[[StoreConfig, str, Window], StoreConfig | None],
        metrics: Callable[[], dict[str, Any]],
    ):
        self.registry, self.prerequisites, self.lease, self.action, self.metrics = (
            registry,
            prerequisites,
            lease,
            action,
            metrics,
        )

    def execute(self, store: str, expected_revision: int, pipeline: str, window: Window) -> None:
        start = time.monotonic()
        status = "failed"
        try:
            with self.lease(store):
                config = self.registry.get(store)
                if (
                    config is None
                    or config.store_id != store
                    or config.revision != expected_revision
                ):
                    raise SafeError("store_registry_changed")
                if not config.eligible(pipeline):
                    raise SafeError("store_not_eligible")
                self.prerequisites(config, pipeline, window)
                updated = self.action(config, pipeline, window)
                if updated is not None and updated != config:
                    permitted = {
                        "facts_coverage_from",
                        "facts_coverage_to",
                        "facts_complete",
                        "revision",
                        "updated_at",
                    }
                    if (
                        pipeline != "upzero"
                        or updated.revision != config.revision + 1
                        or any(
                            value != asdict(updated)[key]
                            for key, value in asdict(config).items()
                            if key not in permitted
                        )
                    ):
                        raise SafeError("invalid_recurring_registry_update")
                    self.registry.save(updated, config.revision)
                status = "completed"
        finally:
            event(
                "store_worker_finished",
                store_id=store,
                pipeline=pipeline,
                duration_ms=int((time.monotonic() - start) * 1000),
                status=status,
                **self.metrics(),
            )


class Actions:
    def __init__(
        self,
        transport: Transport,
        prerequisites: Prerequisites,
        *,
        lease_bucket: str,
        meta_secret_reference: str | None = None,
        page_limit: int = 1000,
    ):
        if not 1 <= page_limit <= 1000:
            raise SafeError("invalid_page_limit")
        self.transport, self.prerequisites, self.bucket = transport, prerequisites, lease_bucket
        self.meta_reference, self.page_limit = meta_secret_reference, page_limit

    def repository(self) -> BigQueryRepository:
        # The client is injected and already bounded; do not discover another credential/client.
        repo = BigQueryRepository.__new__(BigQueryRepository)
        repo.client = self.transport.client
        repo.project, repo.location = self.transport.config.project, self.transport.config.location
        return repo

    def __call__(self, c: StoreConfig, pipeline: str, w: Window) -> StoreConfig | None:
        try:
            if pipeline == "upzero":
                self.upzero(c, w)
                repo = self.repository()
                return facts_coverage(
                    c,
                    repo.read("sync_checkpoints", c.store_id),
                    repo.read("sync_runs", c.store_id),
                    w.as_of,
                    now(),
                )
            elif pipeline == "meta":
                self.meta(c, w)
            elif pipeline == "analytics":
                self.analytics(c, w)
            elif pipeline == "intelligence":
                intelligence_materialize(
                    self.transport,
                    c.policy(w),
                    self.prerequisites.account(c),
                    tenant="internal-control-plane",
                    snapshot_at=w.source_snapshot_at,
                    calculated_at=w.calculated_at,
                    initialize_head=True,
                )
            else:
                raise SafeError("invalid_pipeline")
        except Exception:
            if getattr(self.transport.client, "mutation_outcome_unknown", False) is True:
                raise SafeError("bigquery_write_outcome_unknown") from None
            if getattr(self.transport.client, "budget_exhausted", False) is True:
                raise SafeError("store_execution_budget_exhausted") from None
            raise
        return None

    def upzero(self, c: StoreConfig, w: Window) -> None:
        source = self.prerequisites.source(c)
        cfg = Settings(
            c.store_id,
            c.store_name or c.store_id,
            c.store_slug or c.store_id,
            c.timezone or "",
            c.upzero_connection_id or "",
            c.history_from or "",
            secret_resource_name=source["secret_resource_name"],
            upzero_store_identifier=c.upzero_store_identifier,
            project_id=self.transport.config.project,
            location=self.transport.config.location,
            lease_bucket=self.bucket,
            purchase_order_id_effective_at=c.purchase_order_id_effective_at,
            page_limit=self.page_limit,
        )
        repo = self.repository()
        client = UpZeroConnector(resolve_secret(cfg.secret_resource_name), max_pages=cfg.max_pages)
        try:
            engine = Engine(cfg, repo, client)
            # Do not overwrite source_connections or confuse other integrations with UP Zero.
            old = repo.read("stores", c.store_id, [row_key(c.store_id, "store")])
            repo.write(
                {
                    "stores": [
                        {
                            "row_key": row_key(c.store_id, "store"),
                            "store_id": c.store_id,
                            "store_name": cfg.store_name,
                            "store_slug": cfg.store_slug,
                            "timezone": cfg.timezone,
                            "status": "active",
                            "upzero_store_identifier": cfg.upzero_store_identifier,
                            "meta_ad_account_id": c.meta_account_id,
                            "created_at": old[0]["created_at"] if old else now(),
                            "updated_at": now(),
                        }
                    ],
                    "source_capabilities": [
                        {
                            "row_key": row_key(c.store_id, cfg.connection_id),
                            "store_id": c.store_id,
                            "connection_id": cfg.connection_id,
                            "purchase_order_id_effective_at": cfg.purchase_order_id_effective_at,
                            "updated_at": now(),
                        }
                    ],
                }
            )
            for resource in ("customers", "orders", "analytics_facts"):
                selected = [
                    r
                    for r in repo.read("sync_checkpoints", c.store_id)
                    if r["resource"] == resource and r["connection_id"] == cfg.connection_id
                ]
                for checkpoint in selected:
                    if checkpoint.get("status") == CHECKPOINT_RECOVERED and not checkpoint_pending(
                        checkpoint
                    ):
                        BigQueryRecovery(self.transport).recovered(checkpoint, c.store_id)
                pending = [r for r in selected if checkpoint_pending(r)]
                for checkpoint in sorted(pending, key=lambda r: r["updated_at"]):
                    resume_engine = Engine(replace(cfg, page_limit=None), repo, client)
                    if checkpoint["plan_key"] != digest(
                        [
                            c.store_id,
                            cfg.connection_id,
                            resource,
                            checkpoint["filters"],
                            checkpoint["mode"],
                        ]
                    ):
                        raise SafeError("upzero_pending_configuration_requires_recovery")
                    summary = resume_engine.run(
                        resource, checkpoint["filters"], mode=checkpoint["mode"]
                    )
                    self.completed(summary)
                filters, stop = incremental(repo, cfg, resource, w.as_of)
                self.completed(
                    engine.run(resource, filters, mode="incremental", refresh=True, stop_at_id=stop)
                )
                if resource == "orders":
                    for filters in open_order_windows(repo, cfg):
                        self.completed(
                            engine.run("orders", filters, mode="reconcile", refresh=True)
                        )
        finally:
            client.close()

    @staticmethod
    def completed(summary: dict[str, Any]) -> None:
        if summary["status"] != "completed" or summary.get("core_records_failed") != 0:
            raise SafeError("source_sync_incomplete")

    def meta(self, c: StoreConfig, w: Window) -> None:
        account = self.prerequisites.account(c)
        report = Insights(
            w.report_from,
            (date.fromisoformat(w.report_to) - timedelta(days=1)).isoformat(),
            "impression",
            ("7d_click",),
            None,
        )
        token = resolve_secret(validated_secret_reference(self.meta_reference or ""))
        connector = MetaFoundationLiveConnector(
            account,
            project=self.transport.config.project,
            live=True,
            confirm_store=c.store_id,
            confirm_account=account.account_id,
            token=token,
            page_limit=min(self.page_limit, 100),
        )
        try:
            # Outer StoreWorker owns the single shared lease, including binding recheck.
            engine = MetaLiveEngine(
                self.repository(), connector, accounts=(account,), lease=lambda: nullcontext()
            )
            # Resume all unfinished pages first, even a previous reporting window.
            checkpoints = self.repository().read("sync_checkpoints", c.store_id)
            for resource in ("accounts", "campaigns", "adsets", "ads", "insights"):
                pending = [
                    cp
                    for cp in checkpoints
                    if cp["resource"] == engine.core_names[resource]
                    and cp["connection_id"] == c.meta_connection_id
                    and (cp["status"] != "complete" or cp.get("pending_raw_id"))
                ]
                for cp in pending:
                    spec = cp["filters"]["insights"]
                    if cp["filters"]["account"] != account.snapshot() or cp["plan_key"] != digest(
                        ["meta", resource, cp["filters"], connector.page_limit]
                    ):
                        raise SafeError("meta_pending_configuration_requires_recovery")
                    previous: Insights | None = None
                    if spec:
                        previous_spec: dict[str, Any] = {
                            k: v for k, v in spec.items() if k not in {"level", "time_increment"}
                        }
                        for field in ("breakdowns", "action_attribution_windows"):
                            if field in previous_spec:
                                previous_spec[field] = tuple(previous_spec[field])
                        previous = Insights(**previous_spec)
                    self.completed(engine.run(resource, previous))
                self.completed(
                    engine.run(resource, report if resource == "insights" else None, refresh=True)
                )
        finally:
            connector.close()

    def analytics(self, c: StoreConfig, w: Window) -> None:
        policy = c.policy(w)
        heads = self.prerequisites.publication(c, w)
        current = certified_window(c, heads, w.source_snapshot_at)
        monotonic(current, w)
        source = SourceGeneration(
            w.source_snapshot_at, digest([c.store_id, c.revision, w.source_snapshot_at]), True
        )
        plan = plan_changes(policy, CoreSnapshot([], [], [], []), None, None)
        publication = Publication(
            policy, source, plan, heads[0]["generation"], full_refresh_authorized=True
        )
        analytics_materialize(
            BigQueryAnalyticsReader(self.transport, policy),
            BigQueryAnalyticsWriter(self.transport),
            publication,
        )


def main() -> int:
    from src.control_plane.cli import worker_main

    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
