"""Installed-store work uses V2 adapters, without initial-install lifecycle writes."""

from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from src.analytics.cloud.reader import BigQueryAnalyticsReader, SourceGeneration
from src.analytics.cloud.runner import materialize
from src.analytics.cloud.writer import BigQueryAnalyticsWriter, Publication
from src.analytics.materialization import CoreSnapshot, plan_changes
from src.connectors.meta.config import Insights
from src.control_plane.model import StoreConfig, Window, instant
from src.control_plane.recurring import certified_window
from src.domain.models import SafeError
from src.ingestion.meta_live import MetaCreativeEngine
from src.installation.adapters import InstallationActions
from src.installation.model import Limits, Row
from src.utils.data import digest, now


class ExtensionActions(InstallationActions):
    def execute(self, c: StoreConfig, row: Row, limits: Limits) -> Row:
        if row["unit_kind"] == "VERIFY_SOURCE" or row["unit_kind"] == "LEGACY_RESUME":
            raise SafeError("extension_work_contract_invalid")
        if row["source"] == "meta":
            if row["unit_kind"] == "META_CATALOG" and row["resource"] in {
                "accounts",
                "campaigns",
                "adsets",
                "ads",
            }:
                return super().execute(c, row, limits)
            if row["resource"] not in {"insights", "creative_insights", "period_insights"}:
                raise SafeError("extension_work_contract_invalid")
            if self.source(c, "meta")["status"] != "active":
                raise SafeError("source_verification_required")
            period = row["resource"] == "period_insights"
            engine, close = self.meta(
                c,
                creative=row["resource"] == "creative_insights",
                period_level=row["filters"].get("level") if period else None,
            )
            try:
                f = row["filters"]
                from src.connectors.meta.period import MetaPeriodEngine, PeriodInsights

                report_type = PeriodInsights if period else Insights
                report = report_type(
                    f["since"],
                    f["until"],
                    f["action_report_time"],
                    tuple(f["action_attribution_windows"]),
                    f["purchase_action_type"],
                    tuple(f.get("breakdowns", ())),
                    **({"level": f["level"]} if period else {}),
                )
                if period:
                    if f.get("time_increment") != "all_days":
                        raise SafeError("meta_period_definition_invalid")
                    engine = MetaPeriodEngine(
                        engine.repo,
                        engine.connector,
                        accounts=(engine.account,),
                        lease=lambda: nullcontext(),
                        level=f["level"],
                    )
                if row["resource"] == "creative_insights":
                    engine = MetaCreativeEngine(
                        engine.repo,
                        engine.connector,
                        accounts=(engine.account,),
                        lease=lambda: nullcontext(),
                    )
                result = engine.advance(
                    "insights",
                    report,
                    page_budget=limits.page_budget,
                    soft_time_budget_seconds=limits.soft_time_budget_seconds,
                )
            finally:
                close()
            return dict(
                complete=result.get("complete", False),
                yielded=result.get("yielded", False),
                run_id=result["run_id"],
                checkpoint_plan_key=result["plan_key"],
                records_processed=result["core_records_processed"],
                pages_processed=result["core_pages_processed"],
            )
        if row["unit_kind"] != "PUBLISH_ANALYTICS":
            return super().execute(c, row, limits)
        self.certify(c, row)
        at = now()
        # Re-read HEAD under the store lease: daily processing may have advanced
        # since the request. Historical publishing must retain that entire window.
        daily = Window.previous_closed_day(c.timezone or "", at)
        heads = self.actions.prerequisites.publication(c, daily)
        current = certified_window(c, heads, at)
        start = min(current.report_from, row["filters"]["report_from"])
        boundary = (
            datetime.combine(date.fromisoformat(start), time(), ZoneInfo(c.timezone or ""))
            .astimezone(UTC)
            .isoformat()
        )
        scoped = replace(
            c,
            facts_coverage_from=min(
                instant(c.history_from or boundary), instant(boundary)
            ).isoformat(),
            facts_coverage_to=current.as_of,
            facts_complete=True,
        )
        window = Window(start, current.report_to, current.as_of, at, at)
        # Complete same-store checkpoints/runs, including fresh Customers, prove
        # the extended prefix before any publication write. Intent is not coverage.
        self.actions.prerequisites.upzero_complete(scoped, window)
        policy = scoped.policy(window)
        source = SourceGeneration(at, digest([c.store_id, row["work_unit_id"], at]), True)
        change = plan_changes(policy, CoreSnapshot([], [], [], []), None, None)
        publication = Publication(
            policy, source, change, heads[0]["generation"], full_refresh_authorized=True
        )
        materialize(
            BigQueryAnalyticsReader(self.actions.transport, policy),
            BigQueryAnalyticsWriter(self.actions.transport),
            publication,
        )
        # CAS only the range proven from COMPLETE checkpoints, still under the
        # worker's store lease. Unknown CAS retains that lease and stops dispatch.
        from src.control_plane.repository import BigQueryRegistry

        updated = replace(
            c,
            facts_coverage_from=scoped.facts_coverage_from,
            facts_coverage_to=max(
                instant(c.facts_coverage_to or current.as_of), instant(current.as_of)
            ).isoformat(),
            facts_complete=True,
        )
        if updated != c:
            BigQueryRegistry(self.actions.transport).save(
                replace(updated, revision=c.revision + 1, updated_at=now()), c.revision
            )
        return {"complete": True}
