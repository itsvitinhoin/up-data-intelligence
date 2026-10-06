"""Official period metrics with independent completed source/checkpoint proof."""

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from src.connectors.meta.config import Account, Insights, configuration_key
from src.connectors.meta.period import PeriodInsights
from src.connectors.meta.purchase_reporting import PurchaseCertificate
from src.control_plane.recurring import meta_coverage
from src.dashboard.contracts import ReadError, decimal_string, integer
from src.dashboard.queries import Query
from src.dashboard.repository import Reader
from src.dashboard.service import _ratio
from src.domain.models import SafeError
from src.utils.data import digest, timestamp


class MetaPeriodReader:
    def __init__(
        self,
        project: str,
        reader: Reader,
        store: str,
        request: str,
        snapshot: str,
        certificates: tuple[PurchaseCertificate, ...],
    ):
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project):
            raise ValueError("invalid_project")
        self.project = project
        self.reader, self.store, self.request, self.snapshot, self.certificates = (
            reader,
            store,
            request,
            snapshot,
            certificates,
        )

    def read(self, start: str, end: str) -> dict[str, Any]:
        matches = [c for c in self.certificates if c.account.store_id == self.store]
        if len(matches) != 1:
            raise ReadError(424, "meta_period_definition_unavailable")
        certificate = matches[0]
        account = certificate.account

        def table(dataset: str, name: str) -> str:
            return f"`{self.project}.{dataset}.{name}`"

        daily = Insights(
            start,
            (date.fromisoformat(end) - timedelta(days=1)).isoformat(),
            certificate.action_report_time,
            certificate.attribution_windows,
            certificate.purchase_action_type,
        )
        daily_fields = [
            "spend",
            "impressions",
            "clicks",
            "link_clicks",
            "meta_reported_purchases",
            "meta_reported_purchase_value",
        ]
        daily_sums = ",".join(f"IF(COUNTIF({k} IS NULL)>0,NULL,SUM({k})) {k}" for k in daily_fields)
        fields = "store_id account_id connection_id api_version currency timezone level campaign_id adset_id ad_id configuration_hash date_start date_stop spend impressions reach frequency clicks link_clicks ctr cpc cpm meta_reported_purchases meta_reported_purchase_value purchase_action_type observed_at".split()
        sql = f"""SELECT
 ARRAY(SELECT AS STRUCT b.* FROM {table("up_core", "meta_account_bindings")} AS b FOR SYSTEM_TIME AS OF @read_at
 JOIN {table("up_ops", "store_runtime_config")} AS r FOR SYSTEM_TIME AS OF @read_at ON r.store_id=b.store_id AND r.meta_connection_id=b.connection_id AND r.meta_account_id=b.account_id AND r.meta_api_version=b.api_version AND r.currency=b.currency AND r.timezone=b.source_timezone
 JOIN {table("up_core", "source_connections")} AS s FOR SYSTEM_TIME AS OF @read_at ON s.store_id=b.store_id AND s.connection_id=b.connection_id AND s.source_system='meta'
 WHERE b.store_id=@store AND r.meta_enabled AND s.status='active' LIMIT 2) bindings,
 ARRAY(SELECT AS STRUCT TO_JSON_STRING(c) value FROM {table("up_ops", "sync_checkpoints")} AS c FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND resource IN ('meta_period_insights','meta_creative_insights_daily') ORDER BY plan_key LIMIT 1001) checkpoints,
 ARRAY(SELECT AS STRUCT TO_JSON_STRING(r) value FROM {table("up_ops", "sync_runs")} AS r FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND source='meta' AND resource IN ('meta_period_insights','meta_creative_insights_daily') ORDER BY run_id LIMIT 1001) runs,
 ARRAY(SELECT AS STRUCT {",".join("i.`" + k + "`" for k in fields)},
 (SELECT AS STRUCT COUNT(*) matches,ANY_VALUE(ad_name) name,ANY_VALUE(status) status,
 ANY_VALUE(creative_image_url) image_url,ANY_VALUE(creative_thumbnail_url) thumbnail_url,ANY_VALUE(creative_id) creative_id
 FROM {table("up_core", "meta_live_ads")} FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND account_id=@account AND ad_id=i.ad_id) ad,
 (SELECT AS STRUCT COUNT(*) matches,ANY_VALUE(campaign_name) name,ANY_VALUE(status) status FROM {table("up_core", "meta_live_campaigns")} FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND account_id=@account AND campaign_id=i.campaign_id) campaign,
 (SELECT AS STRUCT COUNT(*) matches,ANY_VALUE(adset_name) name,ANY_VALUE(status) status FROM {table("up_core", "meta_live_adsets")} FOR SYSTEM_TIME AS OF @read_at WHERE store_id=@store AND account_id=@account AND adset_id=i.adset_id) adset
 FROM {table("up_core", "meta_period_insights")} AS i FOR SYSTEM_TIME AS OF @read_at
 WHERE i.store_id=@store AND i.account_id=@account AND i.date_start=@from AND i.date_stop=@last AND i.purchase_action_type=@action
 ORDER BY i.level,i.campaign_id,i.adset_id,i.ad_id LIMIT 1001) metrics,
 ARRAY(SELECT AS STRUCT date_start date,{daily_sums},COUNT(*) row_count,COUNT(DISTINCT row_key) identities,
 COUNT(DISTINCT TO_JSON_STRING(STRUCT(ad_id,date_start))) grains,
 COUNTIF(level IS DISTINCT FROM 'ad' OR date_stop IS DISTINCT FROM date_start OR ad_id IS NULL OR campaign_id IS NULL OR adset_id IS NULL) invalid
 FROM {table("up_core", "meta_creative_insights_daily")} FOR SYSTEM_TIME AS OF @read_at
 WHERE store_id=@store AND account_id=@account AND configuration_hash=@daily_configuration AND date_start>=@from AND date_start<@to
 GROUP BY date_start ORDER BY date_start LIMIT 1001) daily"""
        rows = self.reader.query(
            Query(
                "meta_period",
                sql,
                {
                    "store": ("STRING", self.store),
                    "account": ("STRING", account.account_id),
                    "read_at": ("TIMESTAMP", self.snapshot),
                    "from": ("DATE", start),
                    "last": ("DATE", (date.fromisoformat(end) - timedelta(days=1)).isoformat()),
                    "action": ("STRING", certificate.purchase_action_type),
                    "daily_configuration": ("STRING", configuration_key(account, daily)),
                    "to": ("DATE", end),
                },
            ),
            request_id=self.request,
            store_id=self.store,
            generation=None,
        )
        if len(rows) != 1:
            raise ReadError(503, "meta_period_evidence_invalid")
        return self.project_rows(rows[0], account, certificate, start, end)

    @staticmethod
    def project_rows(
        evidence: dict[str, Any],
        account: Account,
        certificate: PurchaseCertificate,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        try:
            bindings = evidence["bindings"]
            if len(bindings) != 1 or any(
                bindings[0].get(k) != v
                for k, v in {
                    "store_id": account.store_id,
                    "account_id": account.account_id,
                    "connection_id": account.connection_id,
                    "api_version": account.api_version,
                    "source_timezone": account.timezone,
                    "currency": account.currency,
                }.items()
            ):
                raise ReadError(503, "meta_period_binding_invalid")
            arrays = [evidence[k] for k in ("checkpoints", "runs", "metrics")]
            if any(not isinstance(a, list) or len(a) > 1000 for a in arrays):
                raise ReadError(503, "meta_period_evidence_limit")
            cps = [json.loads(r["value"]) for r in arrays[0]]
            runs = [json.loads(r["value"]) for r in arrays[1]]
            data: dict[str, list[dict[str, Any]]] = {
                level: [] for level in ("account", "campaign", "adset", "ad")
            }
            configurations, completed = {}, {}
            for level in data:
                report = PeriodInsights(
                    start,
                    (date.fromisoformat(end) - timedelta(days=1)).isoformat(),
                    certificate.action_report_time,
                    certificate.attribution_windows,
                    certificate.purchase_action_type,
                    level=level,
                )
                spec = {"account": account.snapshot(), "insights": report.snapshot()}
                expected = [c for c in cps if c.get("filters") == spec]
                if not expected:
                    raise ReadError(424, "meta_period_coverage_unavailable")
                if len(expected) != 1:
                    raise ReadError(503, "meta_period_checkpoint_conflict")
                cp = expected[0]
                linked = [r for r in runs if r.get("run_id") == cp.get("run_id")]
                key = digest(["meta", "insights", spec, 100])
                if cp.get("status") != "complete" or cp.get("pending_raw_id") is not None:
                    raise ReadError(424, "meta_period_coverage_unavailable")
                if (
                    cp.get("store_id") != account.store_id
                    or cp.get("connection_id") != account.connection_id
                    or cp.get("resource") != "meta_period_insights"
                    or cp.get("plan_key") != key
                    or cp.get("mode") != "sync"
                    or len(linked) != 1
                    or any(
                        linked[0].get(k) != v
                        for k, v in {
                            "store_id": account.store_id,
                            "source": "meta",
                            "resource": "meta_period_insights",
                            "plan_key": key,
                            "status": "completed",
                            "core_records_failed": 0,
                            "mode": "sync",
                        }.items()
                    )
                ):
                    raise ReadError(503, "meta_period_checkpoint_invalid")
                run_start = timestamp(linked[0]["started_at"])
                run_end = timestamp(linked[0]["finished_at"])
                cp_end = timestamp(cp["updated_at"])
                if run_start > run_end or cp_end < run_end:
                    raise ReadError(503, "meta_period_checkpoint_invalid")
                completed[level] = (run_end, integer(linked[0]["core_records_processed"]))
                configurations[level] = digest({**account.snapshot(), **report.definition()})
            seen = set()
            for row in arrays[2]:
                level = row["level"]
                if level not in data or any(
                    row.get(k) != v
                    for k, v in {
                        "store_id": account.store_id,
                        "account_id": account.account_id,
                        "connection_id": account.connection_id,
                        "api_version": account.api_version,
                        "currency": account.currency,
                        "timezone": account.timezone,
                        "configuration_hash": configurations[level],
                        "purchase_action_type": certificate.purchase_action_type,
                    }.items()
                ):
                    raise ReadError(503, "meta_period_scope_mismatch")
                ids = tuple(row.get(k) for k in ("campaign_id", "adset_id", "ad_id"))
                identity = (level, *ids)
                present = {"account": 0, "campaign": 1, "adset": 2, "ad": 3}[level]
                if (
                    any(not isinstance(x, str) or not x.isdecimal() for x in ids[:present])
                    or any(x is not None for x in ids[present:])
                    or identity in seen
                ):
                    raise ReadError(503, "meta_period_grain_invalid")
                seen.add(identity)
                if str(row["date_start"]) != start or str(row["date_stop"]) != report.until:
                    raise ReadError(503, "meta_period_window_invalid")
                if timestamp(str(row["observed_at"])) > completed[level][0]:
                    raise ReadError(424, "meta_period_refresh_incomplete")
                safe = {"level": level, "campaign_id": ids[0], "adset_id": ids[1], "ad_id": ids[2]}
                for k in (
                    "spend",
                    "frequency",
                    "ctr",
                    "cpc",
                    "cpm",
                    "meta_reported_purchases",
                    "meta_reported_purchase_value",
                ):
                    safe[k] = decimal_string(row.get(k))
                for k in ("impressions", "reach", "clicks", "link_clicks"):
                    safe[k] = integer(row.get(k))
                safe["cpa"] = _ratio(safe["spend"], safe["meta_reported_purchases"])
                safe["roas"] = _ratio(safe["meta_reported_purchase_value"], safe["spend"])
                if any(
                    v is not None and (Decimal(str(v)) < 0)
                    for k, v in safe.items()
                    if k
                    in {
                        "spend",
                        "frequency",
                        "ctr",
                        "cpc",
                        "cpm",
                        "meta_reported_purchases",
                        "meta_reported_purchase_value",
                        "impressions",
                        "reach",
                        "clicks",
                        "link_clicks",
                    }
                ):
                    raise ReadError(503, "meta_period_metrics_invalid")
                for entity in ("campaign", "adset", "ad"):
                    catalog = row.get(entity, {})
                    if catalog.get("matches") not in {0, 1}:
                        raise ReadError(503, "meta_period_catalog_conflict")
                    safe[entity + "_name"] = catalog.get("name")
                    safe[entity + "_status"] = catalog.get("status")
                from src.normalization.meta_enrichment import media_url

                ad = row.get("ad", {})
                safe["preview_url"] = media_url(ad.get("image_url") or ad.get("thumbnail_url"))
                safe["creative_id"] = ad.get("creative_id")
                data[level].append(safe)
            if len(data["account"]) != 1:
                raise ReadError(424, "meta_period_account_unavailable")
            if any(completed[level][1] != len(rows) for level, rows in data.items()):
                raise ReadError(503, "meta_period_row_count_mismatch")
            daily_report = Insights(
                start,
                report.until,
                certificate.action_report_time,
                certificate.attribution_windows,
                certificate.purchase_action_type,
            )
            series = None
            try:
                meta_coverage(
                    account,
                    daily_report,
                    cps,
                    runs,
                    level="ad",
                    resource="meta_creative_insights_daily",
                )
            except SafeError as exc:
                if exc.code != "meta_complete_checkpoint_required":
                    raise
            else:
                daily_rows = evidence["daily"]
                if not isinstance(daily_rows, list) or len(daily_rows) > 1000:
                    raise ReadError(503, "meta_period_evidence_limit")
                series, dates = [], set()
                for daily_row in daily_rows:
                    day = str(daily_row["date"])
                    if (
                        day in dates
                        or not start <= day < end
                        or daily_row["row_count"] != daily_row["identities"]
                        or daily_row["row_count"] != daily_row["grains"]
                        or daily_row["invalid"] != 0
                    ):
                        raise ReadError(503, "meta_period_daily_invalid")
                    date.fromisoformat(day)
                    dates.add(day)
                    point: dict[str, str | None] = {"date": day}
                    point.update(
                        {
                            k: decimal_string(daily_row.get(k))
                            for k in (
                                "spend",
                                "meta_reported_purchases",
                                "meta_reported_purchase_value",
                            )
                        }
                    )
                    if any(
                        Decimal(v) < 0 for k, v in point.items() if k != "date" and v is not None
                    ):
                        raise ReadError(503, "meta_period_daily_invalid")
                    point["roas"] = _ratio(point["meta_reported_purchase_value"], point["spend"])
                    series.append(point)
            return {
                "series": series,
                "summary": data["account"][0],
                "campaigns": data["campaign"],
                "adsets": data["adset"],
                "ads": data["ad"],
                "basis": "official_meta_all_days",
                "report_from": start,
                "report_to": end,
                "purchase_action_type": certificate.purchase_action_type,
            }
        except ReadError:
            raise
        except (KeyError, TypeError, ValueError, SafeError):
            raise ReadError(503, "meta_period_evidence_invalid") from None
