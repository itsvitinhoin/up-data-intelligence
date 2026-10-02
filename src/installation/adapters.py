"""Server-only source adapters; no client construction or IO on import."""

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from typing import Protocol

from src.config.settings import Settings
from src.connectors.meta.config import Insights
from src.connectors.upzero.client import UpZeroConnector
from src.control_plane.model import StoreConfig, Window
from src.control_plane.worker import Actions
from src.domain.models import SafeError
from src.ingestion.engine import Engine, row_key
from src.ingestion.meta_live import MetaLiveEngine
from src.installation.model import Limits, Row
from src.security.secrets import resolve_secret
from src.utils.data import digest, now


class SourceVerifier(Protocol):
    def verify(self, config: StoreConfig, row: Row) -> Row: ...


class ProbeVerifier:
    """Injected one-page probes return no source payload, keys, identifiers or PII."""

    def __init__(self, probes: dict[str, Callable[[StoreConfig, Row], None]]):
        self.probes = probes

    def verify(self, config: StoreConfig, row: Row) -> Row:
        probe = self.probes.get(row["source"])
        if probe is None:
            raise SafeError("source_verification_unavailable")
        probe(config, row)
        return {
            "verified": True,
            "source": row["source"],
            "connection_id": row["connection_id"],
            "capabilities": ["customers"] if row["source"] == "upzero" else ["accounts"],
            "verified_at": now(),
            "safe_error": None,
        }


class InstallationActions:
    def __init__(
        self,
        actions: Actions,
        source: Callable[[StoreConfig, str], Row],
        certify: Callable[[StoreConfig, Row], None],
    ):
        self.actions, self.source, self.certify = actions, source, certify
        self.verifier = ProbeVerifier({"upzero": self.probe_upzero, "meta": self.probe_meta})

    def upzero(self, c: StoreConfig, *, active: bool) -> tuple[Settings, UpZeroConnector]:
        from src.admin.secrets import pinned_reference

        source = self.source(c, "upzero")
        if active and source.get("status") != "active":
            raise SafeError("source_verification_required")
        if source.get("status") == "active":
            # Existing stores can have an explicitly approved legacy secret name.
            # Reuse the existing project/namespace/numeric-version ownership guard.
            approved = self.actions.prerequisites.source(c)
            reference = approved["secret_resource_name"]
            if approved["connection_id"] != source["connection_id"] or reference != source.get(
                "secret_resource_name"
            ):
                raise SafeError("source_verification_outcome_unknown")
        else:
            reference = pinned_reference(
                source.get("secret_resource_name"),
                c.store_id,
                project=self.actions.transport.config.project,
            )
        cfg = Settings(
            c.store_id,
            c.store_name or c.store_id,
            c.store_slug or c.store_id,
            c.timezone or "",
            c.upzero_connection_id or "",
            c.history_from or "",
            purchase_order_id_effective_at=c.purchase_order_id_effective_at,
            upzero_store_identifier=c.upzero_store_identifier,
            page_limit=None,
        )
        return cfg, UpZeroConnector(resolve_secret(reference))

    def probe_upzero(self, c: StoreConfig, row: Row) -> None:
        _, connector = self.upzero(c, active=False)
        try:
            page = next(connector.pages("customers", {"limit": 1}))
            if page.pagination_error:
                raise SafeError("source_verification_failed")
        finally:
            connector.close()

    def meta(self, c: StoreConfig) -> tuple[MetaLiveEngine, Callable[[], None]]:
        from src.connectors.meta.live import MetaFoundationLiveConnector
        from src.intelligence.live.cli import validated_secret_reference

        account = self.actions.prerequisites.account(c)
        connector = MetaFoundationLiveConnector(
            account,
            project=self.actions.transport.config.project,
            live=True,
            confirm_store=c.store_id,
            confirm_account=account.account_id,
            token=resolve_secret(validated_secret_reference(self.actions.meta_reference or "")),
            page_limit=100,
        )
        return MetaLiveEngine(
            self.actions.repository(), connector, accounts=(account,), lease=lambda: nullcontext()
        ), connector.close

    def probe_meta(self, c: StoreConfig, row: Row) -> None:
        engine, close = self.meta(c)
        try:
            page = next(engine.connector.pages("accounts", None, {}))
            if page.pagination_error:
                raise SafeError("source_verification_failed")
        finally:
            close()

    def __call__(self, c: StoreConfig, row: Row, limits: Limits) -> Row:
        try:
            return self.execute(c, row, limits)
        except Exception:
            client = self.actions.transport.client
            # Uncertain writes take precedence over a later budget/error wrapper.
            if getattr(client, "mutation_outcome_unknown", False) is True:
                raise SafeError("bigquery_write_outcome_unknown") from None
            if getattr(client, "budget_exhausted", False) is True:
                raise SafeError("store_execution_budget_exhausted") from None
            raise

    def execute(self, c: StoreConfig, row: Row, limits: Limits) -> Row:
        if row["unit_kind"] == "VERIFY_SOURCE":
            captured = self.source(c, row["source"])
            self.verifier.verify(c, row)
            if self.source(c, row["source"]) != captured:
                raise SafeError("source_verification_outcome_unknown")
            return {"complete": True, "verified_source": captured}
        if row["source"] == "upzero":
            cfg, connector = self.upzero(c, active=True)
            try:
                repo = self.actions.repository()
                expected = digest(
                    [
                        c.store_id,
                        c.upzero_connection_id,
                        row["resource"],
                        row["filters"],
                        row["mode"],
                    ]
                )
                if row["checkpoint_plan_key"] != expected:
                    raise SafeError("work_checkpoint_mismatch")
                if row["unit_kind"] == "LEGACY_RESUME":
                    cp = repo.read("sync_checkpoints", c.store_id, [expected])
                    if (
                        len(cp) != 1
                        or cp[0]["run_id"] != row["run_id"]
                        or cp[0]["filters"] != row["filters"]
                        or cp[0]["mode"] != row["mode"]
                    ):
                        raise SafeError("work_checkpoint_mismatch")
                cp = repo.read("sync_checkpoints", c.store_id, [expected])
                refresh = (
                    row["unit_kind"] == "SYNC_SNAPSHOT"
                    and row.get("run_id") is None
                    and bool(cp)
                    and cp[0]["status"] in {"complete", "recovered"}
                    and not cp[0].get("pending_raw_id")
                )
                if refresh and cp[0]["status"] == "recovered":
                    from src.control_plane.recovery_repository import BigQueryRecovery

                    BigQueryRecovery(self.actions.transport).recovered(cp[0], c.store_id)
                self.seed(c, cfg)
                result = Engine(cfg, repo, connector).advance(
                    row["resource"],
                    row["filters"],
                    mode=row["mode"],
                    refresh=refresh,
                    page_budget=limits.page_budget,
                    soft_time_budget_seconds=limits.soft_time_budget_seconds,
                )
            finally:
                connector.close()
        elif row["source"] == "meta":
            if self.source(c, "meta").get("status") != "active":
                raise SafeError("source_verification_required")
            engine, close = self.meta(c)
            try:
                filters = row["filters"]
                report = (
                    Insights(filters["since"], filters["until"], "impression", ("7d_click",), None)
                    if row["resource"] == "insights"
                    else None
                )
                result = engine.advance(
                    row["resource"],
                    report,
                    page_budget=limits.page_budget,
                    soft_time_budget_seconds=limits.soft_time_budget_seconds,
                )
            finally:
                close()
        elif row["unit_kind"] == "PUBLISH_ANALYTICS":
            self.certify(c, row)
            at = now()
            f = row["filters"]
            # Publication owns its cutoff flags, not global requested-range completeness.
            scoped = replace(
                c,
                facts_complete=f["facts_complete"],
                facts_coverage_from=c.history_from,
                facts_coverage_to=f["as_of"],
            )
            w = Window(f["report_from"], f["report_to"], f["as_of"], at, at)
            self.actions.prerequisites.upzero_complete(scoped, w)
            self.actions.analytics(scoped, w)
            return {"complete": True}
        else:
            raise SafeError("installation_adapter_unavailable")
        return {
            "complete": result.get("complete", False),
            "yielded": result.get("yielded", False),
            "run_id": result["run_id"],
            "checkpoint_plan_key": result["plan_key"],
            "records_processed": result["core_records_processed"],
            "pages_processed": result["core_pages_processed"],
        }

    def seed(self, c: StoreConfig, cfg: Settings) -> None:
        """Reuse Foundation metadata without overwriting verified source_connections."""
        repo = self.actions.repository()
        store_key, capability_key = (
            row_key(c.store_id, "store"),
            row_key(c.store_id, cfg.connection_id),
        )
        stores = repo.read("stores", c.store_id, [store_key])
        capabilities = repo.read("source_capabilities", c.store_id, [capability_key])
        if len(stores) > 1 or len(capabilities) > 1:
            raise SafeError("installation_metadata_invalid")
        store = {
            "row_key": store_key,
            "store_id": c.store_id,
            "store_name": cfg.store_name,
            "store_slug": cfg.store_slug,
            "timezone": cfg.timezone,
            "status": "active",
            "upzero_store_identifier": cfg.upzero_store_identifier,
            "meta_ad_account_id": c.meta_account_id,
            "created_at": stores[0]["created_at"] if stores else now(),
            "updated_at": now(),
        }
        capability = {
            "row_key": capability_key,
            "store_id": c.store_id,
            "connection_id": cfg.connection_id,
            "purchase_order_id_effective_at": cfg.purchase_order_id_effective_at,
            "updated_at": now(),
        }
        changes = {}
        for table, previous, row in [
            ("stores", stores, store),
            ("source_capabilities", capabilities, capability),
        ]:
            if not previous or any(
                previous[0].get(k) != v for k, v in row.items() if k != "updated_at"
            ):
                changes[table] = [row]
        if changes:
            repo.write(changes)
