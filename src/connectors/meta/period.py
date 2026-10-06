"""Non-additive official period Insights; separate from campaign/ad daily truth."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from src.connectors.meta.config import Account, Insights, meta_id
from src.connectors.meta.live import MetaFoundationLiveConnector
from src.connectors.meta.period_schema import FIELDS
from src.domain.models import Batch, SafeError
from src.ingestion.meta_live import MetaLiveEngine
from src.normalization.meta import count
from src.normalization.meta_enrichment import enrichment
from src.utils.data import digest, numeric, timestamp


@dataclass(frozen=True)
class PeriodInsights(Insights):
    level: str = "account"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.level not in {"account", "campaign", "adset", "ad"} or self.breakdowns:
            raise SafeError("meta_period_definition_invalid")

    def definition(self) -> dict[str, Any]:
        # A non-additive period has its own grain. It must never alias a daily row
        # or a different date range, including an overlapping monthly snapshot.
        return {
            **super().definition(),
            "level": self.level,
            "time_increment": "all_days",
            "since": self.since,
            "until": self.until,
        }


class MetaPeriodLiveConnector(MetaFoundationLiveConnector):
    def __init__(self, *args: Any, level: str, **kwargs: Any):
        if level not in {"account", "campaign", "adset", "ad"}:
            raise SafeError("meta_period_definition_invalid")
        super().__init__(*args, **kwargs)
        self.insights_level = level

    def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        if not path.endswith("/insights") or params.get("level") != self.insights_level:
            raise SafeError("meta_period_request_invalid")
        # Existing bounded transport owns retries, sanitized RAW and cursor safety.
        return super()._get(path, {**params, "time_increment": "all_days"})


class MetaPeriodEngine(MetaLiveEngine):
    core_names = {"insights": "meta_period_insights"}
    connector_version = "meta-period-1.0.0"

    def __init__(self, *args: Any, level: str, **kwargs: Any):
        if level not in {"account", "campaign", "adset", "ad"}:
            raise SafeError("meta_period_definition_invalid")
        self.insights_level = level
        super().__init__(*args, **kwargs)

    def run(self, resource: str, insights: Insights | None = None, **kwargs: Any) -> dict[str, Any]:
        if (
            resource != "insights"
            or not isinstance(insights, PeriodInsights)
            or insights.level != self.insights_level
        ):
            raise SafeError("meta_period_definition_invalid")
        return super().run(resource, insights, **kwargs)

    def _transform(self, raw: dict[str, Any]) -> Batch:
        filters = raw["request_filters"]
        if (
            raw["store_id"] != self.account.store_id
            or raw["source_connection_id"] != self.account.connection_id
            or filters.get("account") != self.account.snapshot()
        ):
            raise SafeError("meta_raw_scope_mismatch")
        spec = filters["insights"]
        if spec.get("time_increment") != "all_days" or spec.get("level") != self.insights_level:
            raise SafeError("meta_period_definition_invalid")
        report = PeriodInsights(**{k: v for k, v in spec.items() if k != "time_increment"})
        batch, seen = Batch(), set()
        for source in raw["payload"]["data"]:
            row = normalize_period(source, self.account, report, raw["ingested_at"])
            key = row["row_key"]
            if key in seen:
                raise SafeError("duplicate_meta_page_key")
            seen.add(key)
            payload_hash = digest({k: v for k, v in row.items() if k != "observed_at"})
            old = self.repo.read("meta_period_insights", self.account.store_id, [key])
            if len(old) > 1:
                raise SafeError("meta_period_identity_conflict")
            if old and old[0]["payload_hash"] == payload_hash:
                continue
            version = digest([key, raw["raw_record_id"], payload_hash, self.connector_version])
            row.update(payload_hash=payload_hash, version_id=version, source_system="meta")
            if set(row) != set(FIELDS):
                raise SafeError("meta_period_schema_mismatch")
            batch.add("meta_period_insights_versions", {**row, "row_key": version})
            if not old or timestamp(old[0]["observed_at"]) <= timestamp(row["observed_at"]):
                batch.add("meta_period_insights", row)
                batch.written += int(not old)
                batch.updated += int(bool(old))
        return batch


def normalize_period(
    source: dict[str, Any], account: Account, report: PeriodInsights, observed: str
) -> dict[str, Any]:
    if (
        meta_id(source.get("account_id")) != account.account_id
        or source.get("account_currency") != account.currency
        or source.get("date_start") != report.since
        or source.get("date_stop") != report.until
    ):
        raise SafeError("meta_period_source_mismatch")
    selected = {
        "account": (),
        "campaign": ("campaign_id",),
        "adset": ("campaign_id", "adset_id"),
        "ad": ("campaign_id", "adset_id", "ad_id"),
    }[report.level]
    ids = {
        k: meta_id(source.get(k)) if k in selected else None
        for k in ("campaign_id", "adset_id", "ad_id")
    }
    if any(source.get(k) is not None for k in ids if k not in selected):
        raise SafeError("meta_level_mismatch")
    spend = numeric(source.get("spend"))
    if spend is None or Decimal(spend) < 0:
        raise SafeError("invalid_meta_spend")
    counts = {
        k: count(source.get(k)) for k in ("impressions", "reach", "clicks", "inline_link_clicks")
    }

    def ratio(value: str | int | None, divisor: int | None, multiplier: int = 1) -> str | None:
        if value is None or divisor is None or divisor == 0:
            return None
        return numeric(Decimal(value) * multiplier / Decimal(divisor))

    extra = enrichment("insights", source, report)
    if any(
        Decimal(extra[k]) < 0
        for k in ("meta_reported_purchases", "meta_reported_purchase_value")
        if extra[k] is not None
    ):
        raise SafeError("invalid_meta_metric")
    definition = report.definition()
    configuration = digest({**account.snapshot(), **definition})
    return dict(
        row_key=digest([account.store_id, account.account_id, ids, configuration]),
        store_id=account.store_id,
        account_id=account.account_id,
        connection_id=account.connection_id,
        api_version=account.api_version,
        currency=account.currency,
        timezone=account.timezone,
        level=report.level,
        **ids,
        configuration_hash=configuration,
        reporting_configuration=definition,
        date_start=report.since,
        date_stop=report.until,
        spend=spend,
        impressions=counts["impressions"],
        reach=counts["reach"],
        clicks=counts["clicks"],
        link_clicks=counts["inline_link_clicks"],
        ctr=ratio(counts["clicks"], counts["impressions"], 100),
        cpc=ratio(spend, counts["clicks"]),
        cpm=ratio(spend, counts["impressions"], 1000),
        observed_at=timestamp(observed),
        **extra,
    )
