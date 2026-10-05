"""Canonical #13 durable projection on existing RAW/checkpoint/replay protocol."""

from typing import Any

from src.connectors.meta.config import CORE, Insights
from src.domain.models import Batch, SafeError
from src.ingestion.meta import MetaEngine
from src.normalization.meta import normalize_foundation
from src.normalization.meta_enrichment import enrichment
from src.utils.data import digest, timestamp


class MetaLiveEngine(MetaEngine):
    core_names = {k: v.replace("meta_", "meta_live_", 1) for k, v in CORE.items()}
    auto_binding = False
    connector_version = "meta-live-1.0.0"
    insights_level = "campaign"

    def _run(
        self,
        resource: str,
        insights: Insights | None,
        refresh: bool,
        page_budget: int | None = None,
        soft_time_budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        if insights is not None and self.connector.insights_level != self.insights_level:
            raise SafeError("meta_level_mismatch")
        matches = self.repo.read("meta_account_bindings", self.account.store_id)
        if len(matches) != 1 or any(
            matches[0].get(k) != v
            for k, v in {
                "account_id": self.account.account_id,
                "connection_id": self.account.connection_id,
                "api_version": self.account.api_version,
                "source_timezone": self.account.timezone,
                "currency": self.account.currency,
            }.items()
        ):
            raise SafeError("META_ACCOUNT_BINDING_REQUIRED")
        return super()._run(resource, insights, refresh, page_budget, soft_time_budget_seconds)

    def _configuration(self, insights: Insights | None) -> dict[str, Any]:
        return {
            "account": self.account.snapshot(),
            "insights": {**insights.snapshot(), "level": self.insights_level} if insights else None,
        }

    def _transform(self, raw: dict[str, Any]) -> Batch:
        if raw["request_filters"]["account"] != self.account.snapshot():
            raise SafeError("meta_binding_mismatch")
        resource = raw["resource"]
        spec = raw["request_filters"]["insights"]
        if (
            raw.get("store_id") != self.account.store_id
            or raw.get("source_connection_id") != self.account.connection_id
            or (spec is not None and spec.get("level") != self.insights_level)
        ):
            raise SafeError("meta_raw_scope_mismatch")
        insights = (
            Insights(**{k: v for k, v in spec.items() if k not in {"level", "time_increment"}})
            if spec
            else None
        )
        table = self.core_names[resource]
        batch = Batch()
        seen = set()
        for source in raw["payload"]["data"]:
            row = normalize_foundation(
                resource,
                source,
                self.account,
                insights,
                observed_at=raw["ingested_at"],
                level=self.insights_level,
            )
            row.update(enrichment(resource, source, insights))
            key = row["row_key"]
            if key in seen:
                raise SafeError("duplicate_meta_page_key")
            seen.add(key)
            payload_hash = digest({k: v for k, v in row.items() if k != "observed_at"})
            old = self.repo.read(table, self.account.store_id, [key])
            if resource != "ads" and old and old[0]["payload_hash"] == payload_hash:
                continue
            version = digest(
                [key, raw["raw_record_id"], payload_hash, "meta-live-enrichment-1.0.0"]
            )
            row.update(version_id=version, payload_hash=payload_hash, source_system="meta")
            batch.add(table + "_versions", {**row, "row_key": version})
            if not old or timestamp(old[0]["observed_at"]) <= timestamp(row["observed_at"]):
                batch.add(table, row)
                batch.written += int(not old)
                batch.updated += int(bool(old))
        return batch


class MetaCreativeEngine(MetaLiveEngine):
    """Ad/day extraction with separate CORE identity; campaign/day stays authoritative.

    Uses the same RAW-first, pending-page, checkpoint and bounded slice protocol.
    It is deliberately insights-only and must not overwrite campaign Insights.
    """

    core_names = {"insights": "meta_creative_insights_daily"}
    insights_level = "ad"
    connector_version = "meta-creative-1.0.0"

    def run(
        self,
        resource: str,
        insights: Insights | None = None,
        *,
        refresh: bool = False,
        _page_budget: int | None = None,
        _soft_time_budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        if resource != "insights" or insights is None or insights.breakdowns:
            raise SafeError("invalid_meta_creative_configuration")
        return super().run(
            resource,
            insights,
            refresh=refresh,
            _page_budget=_page_budget,
            _soft_time_budget_seconds=_soft_time_budget_seconds,
        )

    def replay(self, resource: str, original_run_id: str) -> dict[str, Any]:
        if resource != "insights":
            raise SafeError("invalid_meta_creative_configuration")
        return super().replay(resource, original_run_id)
