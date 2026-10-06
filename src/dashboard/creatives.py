"""Ad/day rankings with independent completed source proof, never campaign metrics."""

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from src.connectors.meta.config import Account, Insights, configuration_key
from src.connectors.meta.purchase_reporting import PurchaseCertificate, selected_reporting
from src.control_plane.recurring import meta_coverage, meta_evidence_hash
from src.dashboard.contracts import ReadError, decimal_string, integer
from src.dashboard.queries import Query
from src.dashboard.repository import Reader
from src.domain.models import SafeError
from src.normalization.meta_enrichment import media_url
from src.utils.data import timestamp


class CreativeReader:
    def __init__(
        self,
        project: str,
        reader: Reader,
        store: str,
        request: str,
        snapshot: str,
        *,
        purchase_certificates: tuple[PurchaseCertificate, ...] = (),
    ):
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project):
            raise ValueError("invalid_project")
        self.project, self.reader, self.store, self.request, self.snapshot = (
            project,
            reader,
            store,
            request,
            snapshot,
        )
        self.purchase_certificates = purchase_certificates

    def table(self, dataset: str, name: str) -> str:
        allowed = {
            "up_ops": {"store_runtime_config", "sync_checkpoints", "sync_runs"},
            "up_core": {
                "meta_account_bindings",
                "source_connections",
                "meta_live_ads",
                "meta_creative_insights_daily",
            },
        }
        if name not in allowed.get(dataset, set()):
            raise ValueError("creative_table_not_allowed")
        return f"`{self.project}.{dataset}.{name}`"

    def query(
        self, name: str, sql: str, params: dict[str, tuple[str, object]]
    ) -> list[dict[str, Any]]:
        return self.reader.query(
            Query(
                name,
                sql,
                {
                    "store": ("STRING", self.store),
                    "read_at": ("TIMESTAMP", self.snapshot),
                    **params,
                },
            ),
            request_id=self.request,
            store_id=self.store,
            generation=None,
        )

    def read(self, start: str, end: str) -> list[dict[str, Any]]:
        """At most three rows per ranking; ranks computed over the complete selected period."""
        sources = self.query(
            "creative_source",
            f"""SELECT b.* FROM {self.table("up_core", "meta_account_bindings")} AS b FOR SYSTEM_TIME AS OF @read_at
 JOIN {self.table("up_ops", "store_runtime_config")} AS r FOR SYSTEM_TIME AS OF @read_at ON r.store_id=b.store_id AND r.meta_connection_id=b.connection_id AND r.meta_account_id=b.account_id AND r.meta_api_version=b.api_version AND r.timezone=b.source_timezone AND r.currency=b.currency
 JOIN {self.table("up_core", "source_connections")} AS s FOR SYSTEM_TIME AS OF @read_at ON s.store_id=b.store_id AND s.connection_id=b.connection_id AND s.source_system='meta'
 WHERE b.store_id=@store AND r.meta_enabled AND s.status='active' LIMIT 2""",
            {},
        )
        if not sources:
            raise ReadError(424, "creative_coverage_unavailable")
        if len(sources) != 1 or sources[0].get("store_id") != self.store:
            raise ReadError(503, "creative_source_ambiguous")
        try:
            b = sources[0]
            account = Account(
                self.store,
                b["account_id"],
                b["connection_id"],
                b["api_version"],
                b["source_timezone"],
                b["currency"],
            )
            evidence = self.query(
                "creative_evidence",
                f"""SELECT
 ARRAY(SELECT AS STRUCT TO_JSON_STRING(c) value FROM {self.table("up_ops", "sync_checkpoints")} AS c FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND connection_id=@connection AND resource IN ('meta_live_insights_daily','meta_creative_insights_daily','meta_live_ads') ORDER BY plan_key LIMIT 1001) checkpoints,
 ARRAY(SELECT AS STRUCT TO_JSON_STRING(r) value FROM {self.table("up_ops", "sync_runs")} AS r FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND source='meta' AND resource IN ('meta_live_insights_daily','meta_creative_insights_daily','meta_live_ads') ORDER BY run_id LIMIT 1001) runs""",
                {"connection": ("STRING", account.connection_id)},
            )
            if len(evidence) != 1:
                raise ReadError(503, "creative_evidence_invalid")
            cps = [json.loads(row["value"]) for row in evidence[0]["checkpoints"]]
            runs = [json.loads(row["value"]) for row in evidence[0]["runs"]]
            if len(cps) > 1000 or len(runs) > 1000:
                raise ReadError(503, "creative_evidence_limit")
            campaign = [
                c
                for c in cps
                if c.get("resource") == "meta_live_insights_daily"
                and (c.get("filters") or {}).get("account") == account.snapshot()
                and c.get("status") == "complete"
                and c.get("pending_raw_id") is None
            ]
            if not campaign:
                raise ReadError(424, "creative_definition_unavailable")
            latest = max(campaign, key=lambda c: timestamp(c["updated_at"]))
            spec = latest["filters"]["insights"]
            report = Insights(
                start,
                (date.fromisoformat(end) - timedelta(days=1)).isoformat(),
                spec["action_report_time"],
                tuple(spec["action_attribution_windows"]),
                spec.get("purchase_action_type"),
                tuple(spec["breakdowns"]),
            )
            if report.breakdowns:
                raise ReadError(424, "creative_definition_unavailable")
            report = selected_reporting(account, report, self.purchase_certificates)
            proof = meta_coverage(
                account, report, cps, runs, level="ad", resource="meta_creative_insights_daily"
            )
            if any(
                c.get("resource") == "meta_live_ads"
                and (c.get("filters") or {}).get("account") == account.snapshot()
                and (c.get("status") != "complete" or c.get("pending_raw_id"))
                for c in cps
            ):
                raise ReadError(424, "creative_catalog_refresh_incomplete")
            catalogs = [
                c
                for c in cps
                if c.get("resource") == "meta_live_ads"
                and c.get("status") == "complete"
                and c.get("pending_raw_id") is None
                and (c.get("filters") or {}).get("account") == account.snapshot()
            ]
            if not catalogs:
                raise ReadError(424, "creative_catalog_unavailable")
            catalog = max(catalogs, key=lambda c: timestamp(c["updated_at"]))
            linked = [r for r in runs if r.get("run_id") == catalog.get("run_id")]
            if len(linked) != 1 or any(
                linked[0].get(k) != v
                for k, v in {
                    "store_id": self.store,
                    "source": "meta",
                    "resource": "meta_live_ads",
                    "plan_key": catalog.get("plan_key"),
                    "status": "completed",
                    "core_records_failed": 0,
                }.items()
            ):
                raise ReadError(503, "creative_catalog_invalid")
        except ReadError:
            raise
        except (SafeError, KeyError, TypeError, ValueError):
            raise ReadError(424, "creative_coverage_unavailable") from None
        try:
            catalog_finished = timestamp(linked[0]["finished_at"])
        except (KeyError, TypeError, ValueError):
            raise ReadError(503, "creative_catalog_invalid") from None
        params: dict[str, tuple[str, object]] = {
            "account": ("STRING", account.account_id),
            "configuration": ("STRING", configuration_key(account, report)),
            "from": ("DATE", start),
            "to": ("DATE", end),
        }
        insights = f"{self.table('up_core', 'meta_creative_insights_daily')} FOR SYSTEM_TIME AS OF @read_at"
        where = "store_id=@store AND account_id=@account AND configuration_hash=@configuration AND date_start>=@from AND date_start<@to"
        # Physical duplicate identities/grains cannot compensate in aggregate totals.
        audit = self.query(
            "creative_grain",
            f"SELECT COUNT(*) row_count, COUNT(DISTINCT row_key) identities, COUNT(DISTINCT TO_JSON_STRING(STRUCT(ad_id,date_start))) grains, COUNTIF(level IS DISTINCT FROM 'ad' OR date_stop IS DISTINCT FROM date_start OR ad_id IS NULL OR campaign_id IS NULL OR adset_id IS NULL) invalid FROM {insights} WHERE {where}",
            params,
        )
        if (
            len(audit) != 1
            or audit[0].get("row_count") != audit[0].get("identities")
            or audit[0].get("row_count") != audit[0].get("grains")
            or audit[0].get("invalid") != 0
        ):
            raise ReadError(503, "creative_grain_invalid")
        fields = {
            key: f"IF(COUNTIF({key} IS NULL)>0,NULL,SUM({key})) {key}"
            for key in (
                "spend",
                "impressions",
                "clicks",
                "link_clicks",
                "meta_reported_purchases",
                "meta_reported_purchase_value",
            )
        }
        rows = self.query(
            "creative_rankings",
            f"""WITH totals AS (
 SELECT ad_id, ANY_VALUE(campaign_id) campaign_id,ANY_VALUE(adset_id) adset_id,COUNT(DISTINCT campaign_id) campaigns,COUNT(DISTINCT adset_id) adsets,{",".join(fields.values())}
 FROM {insights} WHERE {where} GROUP BY ad_id
), rates AS (
 SELECT *, SAFE_DIVIDE(clicks*100,impressions) ctr,SAFE_DIVIDE(spend,meta_reported_purchases) cpa FROM totals
), ranked AS (
 SELECT *,ROW_NUMBER() OVER(ORDER BY ctr DESC NULLS LAST,ad_id) ctr_rank,ROW_NUMBER() OVER(ORDER BY cpa ASC NULLS LAST,ad_id) cpa_rank,ROW_NUMBER() OVER(ORDER BY meta_reported_purchases DESC NULLS LAST,ad_id) purchases_rank FROM rates
), ads AS (
 SELECT ad_id,COUNT(*) catalog_matches,ANY_VALUE(ad_name) name,ANY_VALUE(status) status,ANY_VALUE(creative_id) creative_id,ANY_VALUE(creative_image_url) image_url,ANY_VALUE(creative_thumbnail_url) thumbnail_url,ANY_VALUE(creative_video_id) video_id,MAX(observed_at) preview_observed_at
 FROM {self.table("up_core", "meta_live_ads")} FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND account_id=@account GROUP BY ad_id
)
 SELECT r.*,a.* EXCEPT(ad_id) FROM ranked r LEFT JOIN ads a USING(ad_id)
 WHERE (ctr IS NOT NULL AND ctr_rank<=3) OR (cpa IS NOT NULL AND meta_reported_purchases>0 AND cpa_rank<=3) OR (meta_reported_purchases>0 AND purchases_rank<=3) ORDER BY r.ad_id LIMIT 10""",
            params,
        )
        if len(rows) > 9 or len({r.get("ad_id") for r in rows}) != len(rows):
            raise ReadError(503, "creative_rankings_invalid")
        result = []
        for row in rows:
            if (
                row.get("campaigns") != 1
                or row.get("adsets") != 1
                or row.get("catalog_matches") not in {None, 1}
            ):
                raise ReadError(503, "creative_identity_ambiguous")
            if (
                row.get("preview_observed_at")
                and timestamp(str(row["preview_observed_at"])) > catalog_finished
            ):
                raise ReadError(424, "creative_catalog_refresh_incomplete")
            if any(
                not isinstance(row.get(k), str) or not re.fullmatch(r"[0-9]+", row[k])
                for k in ("ad_id", "campaign_id", "adset_id")
            ):
                raise ReadError(503, "creative_identity_invalid")
            try:
                preview = media_url(row.get("image_url") or row.get("thumbnail_url"))
            except SafeError:
                preview = None  # Unsafe media is never a browser fetch target.
            data = {
                k: row.get(k)
                for k in (
                    "ad_id",
                    "campaign_id",
                    "adset_id",
                    "name",
                    "status",
                    "creative_id",
                    "video_id",
                )
            }
            data.update(
                {
                    k: decimal_string(row.get(k))
                    for k in (
                        "spend",
                        "ctr",
                        "cpa",
                        "meta_reported_purchases",
                        "meta_reported_purchase_value",
                    )
                }
            )
            data.update({k: integer(row.get(k)) for k in ("impressions", "clicks", "link_clicks")})
            if any(
                v is not None and v < 0
                for v in (data[k] for k in ("impressions", "clicks", "link_clicks"))
            ):
                raise ReadError(503, "creative_metrics_invalid")
            if any(
                Decimal(str(data[k])) < 0
                for k in (
                    "spend",
                    "ctr",
                    "cpa",
                    "meta_reported_purchases",
                    "meta_reported_purchase_value",
                )
                if data[k] is not None
            ):
                raise ReadError(503, "creative_metrics_invalid")
            data.update(
                store_id=self.store,
                preview_url=preview,
                preview_observed_at=timestamp(str(row["preview_observed_at"]))
                if row.get("preview_observed_at")
                else None,
                reporting_definition={**report.definition(), "level": "ad"},
                evidence_hash=meta_evidence_hash(proof),
                report_from=start,
                report_to=end,
                basis="meta_reported_ad_day",
                reach=None,
                frequency=None,
            )
            result.append(data)
        return result
