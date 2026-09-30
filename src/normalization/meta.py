"""Meta source normalization; exact decimal values, explicit provenance, no attribution."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.bigquery.repository import Repository
from src.connectors.meta.config import CORE, Account, Insights, configuration_key, meta_id
from src.domain.models import Batch, SafeError
from src.quality.meta import DUPLICATE_RULES
from src.quality.rules import result
from src.utils.data import digest, numeric, timestamp

VERSION = "1.0.0"


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SafeError("invalid_meta_field")
    return value.strip() or None


def count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SafeError("invalid_meta_metric")
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral() or not 0 <= number < 2**63:
        raise SafeError("invalid_meta_metric")
    return int(number)


def action_value(rows: Any, action: str | None) -> str | None:
    if rows is None or action is None:
        return None
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise SafeError("invalid_meta_actions")
    matches = [r for r in rows if r.get("action_type") == action]
    # Never add overlapping purchase categories or attribution windows together.
    if len(matches) > 1:
        raise SafeError("ambiguous_meta_action")
    return numeric(matches[0].get("value")) if matches else None


def normalize(
    resource: str, source: dict[str, Any], account: Account, insights: Insights | None
) -> tuple[str, dict[str, Any]]:
    if meta_id(source.get("account_id")) != account.account_id:
        raise SafeError("meta_account_mismatch")
    entity: dict[str, Any] = {"account_id": account.account_id, "api_version": account.api_version}
    if resource == "insights":
        if insights is None:
            raise SafeError("meta_insights_configuration_missing")
        for field in ("campaign_id", "adset_id", "ad_id"):
            entity[field] = meta_id(source.get(field))
        start, stop = source.get("date_start"), source.get("date_stop")
        try:
            if not isinstance(start, str) or not isinstance(stop, str):
                raise ValueError
            if (
                date.fromisoformat(start).isoformat() != start
                or start != stop
                or not insights.since <= start <= insights.until
            ):
                raise ValueError
        except ValueError:
            raise SafeError("invalid_insights_date") from None
        if source.get("account_currency") != account.currency:
            raise SafeError("meta_currency_mismatch")
        entity.update(
            date_start=start,
            date_stop=stop,
            account_currency=account.currency,
            source_timezone=account.timezone,
            configuration_hash=configuration_key(account, insights),
            purchase_action_type=insights.purchase_action_type,
            reporting_configuration=insights.definition(),
        )
        for field in ("spend", "frequency", "cpm", "cpc", "ctr"):
            entity[field] = numeric(source.get(field))
        if entity["spend"] is not None and Decimal(entity["spend"]) < 0:
            raise SafeError("negative_spend")
        for field in ("impressions", "reach", "clicks", "inline_link_clicks"):
            entity[field] = count(source.get(field))
        for field in ("actions", "action_values"):
            value = source.get(field)
            if value is not None and (
                not isinstance(value, list) or any(not isinstance(r, dict) for r in value)
            ):
                raise SafeError("invalid_meta_actions")
            entity[field] = value
        entity.update(
            landing_page_views=action_value(entity["actions"], "landing_page_view"),
            meta_reported_purchases=action_value(entity["actions"], insights.purchase_action_type),
            meta_reported_purchase_value=action_value(
                entity["action_values"], insights.purchase_action_type
            ),
        )
        dimensions = {key: source.get(key) for key in insights.breakdowns}
        if any(not isinstance(v, str) or not v for v in dimensions.values()):
            raise SafeError("missing_meta_breakdown")
        entity["breakdown_values"] = dimensions
        key = digest(
            [
                account.store_id,
                "meta",
                account.account_id,
                entity["ad_id"],
                start,
                stop,
                entity["configuration_hash"],
                dimensions,
            ]
        )
    else:
        for field in ("name", "status", "effective_status"):
            entity[field] = optional_text(source.get(field))
        for source_field, field in (("created_time", "created_at"), ("updated_time", "updated_at")):
            entity[field] = timestamp(source[source_field]) if source.get(source_field) else None
        if resource == "accounts":
            if source.get("id") != "act_" + account.account_id:
                raise SafeError("invalid_meta_id")
            if (
                source.get("timezone_name") != account.timezone
                or source.get("currency") != account.currency
            ):
                raise SafeError("meta_account_configuration_drift")
            entity.update(
                currency=account.currency,
                timezone_name=account.timezone,
                account_status=count(source.get("account_status")),
            )
            identity = account.account_id
        else:
            identity = meta_id(source.get("id"))
            entity[{"campaigns": "campaign_id", "adsets": "adset_id", "ads": "ad_id"}[resource]] = (
                identity
            )
            if resource in {"adsets", "ads"}:
                entity["campaign_id"] = meta_id(source.get("campaign_id"))
            if resource == "ads":
                entity["adset_id"] = meta_id(source.get("adset_id"))
            if resource == "campaigns":
                entity["objective"] = optional_text(source.get("objective"))
        key = digest([account.store_id, "meta", account.account_id, identity])
    return key, entity


def transform(raw: dict[str, Any], repo: Repository) -> Batch:
    config = raw["request_filters"]
    account = Account(**config["account"])
    insights_config = config.get("insights")
    insights = (
        Insights(
            **{k: v for k, v in insights_config.items() if k not in {"level", "time_increment"}}
        )
        if insights_config
        else None
    )
    resource, store, run = raw["resource"], raw["store_id"], raw["run_id"]
    if account.store_id != store or resource not in CORE:
        raise SafeError("meta_raw_scope_mismatch")
    batch, table = Batch(), CORE[resource]
    normalized = []
    for index, source in enumerate(raw["payload"]["data"]):
        try:
            if not isinstance(source, dict):
                raise SafeError("invalid_meta_record")
            key, entity = normalize(resource, source, account, insights)
            normalized.append((key, entity, digest(source)))
        except (SafeError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
            code = exc.code if isinstance(exc, SafeError) else "invalid_meta_field"
            batch.failed += 1
            batch.add(
                "quality_results",
                result(store, run, table, code, "alert", digest([raw["raw_record_id"], index])),
            )
    current = (
        {r["row_key"]: r for r in repo.read(table, store, [r[0] for r in normalized])}
        if normalized
        else {}
    )
    ad_ids = sorted({row[1]["ad_id"] for row in normalized}) if resource == "insights" else []
    available_ads = (
        {
            r["ad_id"]
            for r in repo.find("meta_ads", store, "ad_id", ad_ids)
            if r["account_id"] == account.account_id and r.get("source_system") == "meta"
        }
        if ad_ids
        else set()
    )
    seen: dict[str, str] = {}
    for key, entity, payload_hash in normalized:
        if key in seen:
            rule = DUPLICATE_RULES[resource]
            conflicting = seen[key] != payload_hash
            batch.add(
                "quality_results",
                result(store, run, table, rule, "alert" if conflicting else "warning", key),
            )
            batch.failed += int(conflicting)
            continue
        seen[key] = payload_hash
        if resource == "insights" and entity["ad_id"] not in available_ads:
            batch.add(
                "quality_results", result(store, run, table, "insights_without_ad", "warning", key)
            )
        old = current.get(key)
        if (
            old
            and old["payload_hash"] == payload_hash
            and old["transform_version"] == VERSION
            and old.get("api_version") == account.api_version
        ):
            continue
        if old and datetime.fromisoformat(timestamp(old["observed_at"])) > datetime.fromisoformat(
            timestamp(raw["ingested_at"])
        ):
            continue
        updated = entity.get("updated_at")
        if (
            old
            and updated
            and old.get("source_updated_at")
            and timestamp(updated) < timestamp(old["source_updated_at"])
        ):
            continue
        version = digest([key, raw["raw_record_id"], payload_hash, VERSION])
        row = {
            **entity,
            "row_key": key,
            "store_id": store,
            "source_system": "meta",
            "raw_record_id": raw["raw_record_id"],
            "run_id": run,
            "observed_at": raw["ingested_at"],
            "source_updated_at": updated,
            "payload_hash": payload_hash,
            "version_id": version,
            "transform_version": VERSION,
        }
        batch.add(table, row)
        batch.add(table + "_versions", {**row, "row_key": version})
        batch.written += int(old is None)
        batch.updated += int(old is not None)
    return batch


def normalize_foundation(
    resource: str,
    source: dict[str, Any],
    account: Account,
    insights: Insights | None,
    *,
    observed_at: str,
    level: str = "ad",
) -> dict[str, Any]:
    """CHANGE #13 pure projection into separate proposed schemas, no Repository IO."""
    from decimal import ROUND_HALF_EVEN, localcontext

    from src.connectors.meta.foundation_schema import SCHEMAS
    from src.quality.meta import validate_foundation

    if resource not in CORE or not isinstance(source, dict):
        raise SafeError("invalid_meta_resource_configuration")
    base: dict[str, Any] = {
        "store_id": account.store_id,
        "account_id": account.account_id,
        "api_version": account.api_version,
        "contract_version": "1.0.0",
        "observed_at": timestamp(observed_at),
        "source_updated_at": None,
    }
    if resource != "insights":
        key, entity = normalize(resource, source, account, None)
        base.update(row_key=key, source_updated_at=entity.get("updated_at"))
        if resource == "accounts":
            base.update(
                meta_account_id=account.account_id,
                account_name=entity["name"],
                currency=entity["currency"],
                timezone=entity["timezone_name"],
                status=str(entity["account_status"])
                if entity["account_status"] is not None
                else None,
                created_time=entity["created_at"],
                updated_time=entity["updated_at"],
            )
        elif resource == "campaigns":
            base.update(
                campaign_id=entity["campaign_id"],
                campaign_name=entity["name"],
                objective=entity["objective"],
                status=entity["status"],
                effective_status=entity["effective_status"],
                created_time=entity["created_at"],
                updated_time=entity["updated_at"],
            )
        elif resource == "adsets":
            targeting = source.get("targeting")
            if targeting is not None and not isinstance(targeting, dict):
                raise SafeError("invalid_meta_targeting")
            # Summary exposes only present field names, never audience IDs or location payloads.
            base.update(
                adset_id=entity["adset_id"],
                campaign_id=entity["campaign_id"],
                adset_name=entity["name"],
                optimization_goal=optional_text(source.get("optimization_goal")),
                billing_event=optional_text(source.get("billing_event")),
                targeting_summary={"fields_present": sorted(targeting)}
                if targeting is not None
                else None,
                status=entity["status"],
                effective_status=entity["effective_status"],
            )
        else:
            creative = source.get("creative")
            if creative is not None and not isinstance(creative, dict):
                raise SafeError("invalid_meta_creative")
            base.update(
                ad_id=entity["ad_id"],
                adset_id=entity["adset_id"],
                campaign_id=entity["campaign_id"],
                ad_name=entity["name"],
                creative_id=meta_id(creative["id"]) if creative is not None else None,
                status=entity["status"],
                effective_status=entity["effective_status"],
            )
    else:
        if insights is None or level not in {"campaign", "adset", "ad"}:
            raise SafeError("invalid_meta_resource_configuration")
        if meta_id(source.get("account_id")) != account.account_id:
            raise SafeError("meta_account_mismatch")
        if source.get("account_currency") != account.currency:
            raise SafeError("meta_currency_mismatch")
        start, stop = source.get("date_start"), source.get("date_stop")
        if (
            not isinstance(start, str)
            or not isinstance(stop, str)
            or date.fromisoformat(start).isoformat() != start
            or start != stop
            or not insights.since <= start <= insights.until
        ):
            raise SafeError("invalid_insights_date")
        selected = {
            "campaign": ("campaign_id",),
            "adset": ("campaign_id", "adset_id"),
            "ad": ("campaign_id", "adset_id", "ad_id"),
        }[level]
        ids = {
            field: meta_id(source.get(field)) if field in selected else None
            for field in ("campaign_id", "adset_id", "ad_id")
        }
        if any(source.get(field) is not None for field in ids if field not in selected):
            raise SafeError("meta_level_mismatch")
        dimensions = {field: source.get(field) for field in insights.breakdowns}
        if any(not isinstance(v, str) or not v.strip() for v in dimensions.values()):
            raise SafeError("missing_meta_breakdown")
        if any(
            field in source and field not in dimensions
            for field in ("age", "gender", "country", "publisher_platform", "platform_position")
        ):
            raise SafeError("unexpected_meta_breakdown")
        reporting = {**insights.definition(), "level": level}
        config = digest(
            {
                "api_version": account.api_version,
                "currency": account.currency,
                "timezone": account.timezone,
                **reporting,
            }
        )
        spend = numeric(source.get("spend"))
        if spend is None or Decimal(spend) < 0:
            raise SafeError("invalid_meta_spend")
        counts = {
            field: count(source.get(field))
            for field in ("impressions", "reach", "clicks", "inline_link_clicks")
        }
        lpv = action_value(source.get("actions"), "landing_page_view")
        if lpv is not None and Decimal(lpv) < 0:
            raise SafeError("invalid_meta_metric")

        def metric(
            numerator: str | int | None, denominator: int | None, multiplier: int = 1
        ) -> str | None:
            if numerator is None or denominator is None or denominator == 0:
                return None
            with localcontext() as ctx:
                ctx.prec = 78
                return numeric(
                    (Decimal(numerator) * multiplier / Decimal(denominator)).quantize(
                        Decimal("0.000000001"), rounding=ROUND_HALF_EVEN
                    )
                )

        base.update(
            **ids,
            level=level,
            date_start=start,
            date_stop=stop,
            spend=spend,
            currency=account.currency,
            timezone=account.timezone,
            configuration_hash=config,
            reporting_configuration=reporting,
            breakdown_values=dimensions,
            impressions=counts["impressions"],
            reach=counts["reach"],
            clicks=counts["clicks"],
            link_clicks=counts["inline_link_clicks"],
            landing_page_views=lpv,
            cpm=metric(spend, counts["impressions"], 1000),
            cpc=metric(spend, counts["clicks"]),
            ctr=metric(counts["clicks"], counts["impressions"], 100),
        )
        base["row_key"] = digest(
            [account.store_id, account.account_id, level, ids, start, config, dimensions]
        )
    if set(base) != set(SCHEMAS[CORE[resource]]):
        raise SafeError("meta_foundation_schema_mismatch")
    validate_foundation(resource, [base], account)
    return base
