"""Bounded recurring catalog/ad completion for installed stores, never auto-backfill."""

from datetime import date, timedelta

from src.admin.history import HistoryService
from src.analytics.cloud.transport import scalar
from src.domain.models import SafeError
from src.installation.model import Limits, config_hash
from src.utils.data import digest


class EnrichmentPrepare:
    def __init__(
        self,
        service: HistoryService,
        limits: Limits,
        *,
        images_enabled: bool = False,
        meta_period_enabled: bool = False,
    ):
        self.service, self.limits = service, limits
        self.images_enabled = images_enabled
        self.meta_period_enabled = meta_period_enabled

    def __call__(self, store: str | None = None) -> int:
        ledger = self.service.ledger
        params = [scalar("limit", "INT64", self.limits.max_stores)]
        where = "r.status='ACTIVE' AND r.sync_enabled AND r.operation_b2b AND r.analytics_enabled"
        if store:
            where += " AND r.store_id=@store"
            params.append(scalar("store", "STRING", store))
        rows, _ = ledger.transport.query(
            f"SELECT r.store_id FROM {ledger.sql.table('store_runtime_config')} r LEFT JOIN {ledger.sql.table('installation_plans')} p ON p.store_id=r.store_id AND p.status='COMPLETE' WHERE {where} GROUP BY r.store_id ORDER BY MAX(p.completed_at) ASC NULLS FIRST,r.store_id LIMIT @limit",
            params,
        )
        if len(rows) > self.limits.max_stores or len({r["store_id"] for r in rows}) != len(rows):
            raise SafeError("extension_store_inventory_limit")
        count = 0
        for row in rows:
            store_id = row["store_id"]
            try:
                existing = ledger.plans(store_id)
                if any(p["status"] != "COMPLETE" for p in existing):
                    continue  # Never replace/bypass pending or blocked evidence.
                c = ledger.config(store_id)
                publication = self.service.publication(c)
                end = publication["report_to"]
                purposes = [
                    (
                        "upzero",
                        "CATALOG_SNAPSHOT",
                        (date.fromisoformat(end) - timedelta(days=1)).isoformat(),
                    ),
                ]
                if self.images_enabled:
                    purposes.append(("upzero", "CATALOG_IMAGES", purposes[0][2]))
                purposes.append(("meta", "META_CREATIVE_COVERAGE", publication["report_from"]))
                if self.meta_period_enabled:
                    purposes.append(("meta", "META_PERIOD_REPORT", publication["report_from"]))
                for provider, purpose, start in purposes:
                    if not getattr(c, provider + "_enabled"):
                        continue
                    completed = [
                        p
                        for p in existing
                        if p["adopted_coverage"]["extension"]["purpose"] == purpose
                        and p["adopted_coverage"]["extension"]["publication"]["report_to"] == end
                        and p["config_hash"] == config_hash(c)
                    ]
                    if purpose == "META_CREATIVE_COVERAGE" and self.service.purchase_certificates:
                        certificates = [
                            x
                            for x in self.service.purchase_certificates
                            if x.account.store_id == store_id
                        ]
                        if len(certificates) != 1:
                            raise SafeError("extension_meta_definition_required")
                        action = certificates[0].purchase_action_type
                        completed = [
                            p
                            for p in completed
                            if all(
                                u["filters"].get("purchase_action_type") == action
                                for u in ledger.units(p["plan_id"])
                                if u["resource"] == "creative_insights"
                            )
                            and any(
                                u["resource"] == "creative_insights"
                                for u in ledger.units(p["plan_id"])
                            )
                        ]
                    if completed:
                        continue
                    self.service.prepare(
                        {"store_id": store_id},
                        provider,
                        start,
                        end,
                        purpose,
                        digest(["system-enrichment", "v1"]),
                    )
                    count += 1
                    break  # One admitted graph/store, next provider after completion.
            except SafeError as exc:
                if exc.code.endswith("outcome_unknown"):
                    raise
                from src.observability.logging import event

                event("installation_onboarding_blocked", store_id=store_id, code=exc.code)
        return count
