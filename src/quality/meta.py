"""Meta-only quality policy; never fed into the deployed UP Zero resource gate."""

from collections import Counter
from typing import Any

from src.connectors.meta.config import CORE
from src.quality.rules import result
from src.utils.data import digest

DUPLICATE_RULES = {
    "accounts": "duplicate_meta_accounts",
    "campaigns": "duplicate_campaigns",
    "adsets": "duplicate_adsets",
    "ads": "duplicate_ads",
    "insights": "duplicate_meta_insights",
}
RULES = {
    **{rule: "warning_identical_blocking_conflict" for rule in DUPLICATE_RULES.values()},
    "fact_ad_id_without_meta_ad": "warning",
    "fact_adset_id_without_meta_adset": "warning",
    "fact_campaign_id_without_meta_campaign": "warning",
    "insights_without_ad": "warning",
    "invalid_meta_id": "blocking",
    "negative_spend": "blocking",
    "invalid_insights_date": "blocking",
}


def duplicate_current_rows(
    store: str, run: str, resource: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Audit physical current-table corruption. Caller supplies a bounded account slice.

    Unlike repeated source rows, duplicate persisted logical keys are always blocking.
    No external reads, state changes or global quality policy modifications here.
    """
    counts = Counter(r["row_key"] for r in rows if r["store_id"] == store)
    return [
        result(
            store,
            run,
            CORE[resource],
            DUPLICATE_RULES[resource],
            "alert",
            digest([resource, key]),
            failed=count - 1,
            checked=count,
        )
        for key, count in counts.items()
        if count > 1
    ]


def validate_foundation(resource: str, rows: list[dict[str, Any]], account: Any) -> None:
    """Strict proposed output contract; duplicates always block publication."""
    from datetime import date
    from decimal import Decimal

    from src.connectors.meta.config import meta_id
    from src.connectors.meta.foundation_schema import SCHEMAS
    from src.domain.models import SafeError
    from src.utils.data import numeric, timestamp

    schema = SCHEMAS.get(CORE.get(resource, ""))
    if schema is None:
        raise SafeError("invalid_meta_resource_configuration")
    seen = set()
    for row in rows:
        if set(row) != set(schema):
            raise SafeError("meta_foundation_schema_mismatch")
        if row["store_id"] != account.store_id or row["account_id"] != account.account_id:
            raise SafeError("meta_account_mismatch")
        if row["row_key"] in seen:
            raise SafeError("duplicate_meta_foundation_row")
        seen.add(row["row_key"])
        if any(
            not isinstance(row[k], str) or not row[k].strip()
            for k in ("row_key", "store_id", "account_id")
        ):
            raise SafeError("meta_foundation_schema_mismatch")
        required = {
            "accounts": ["meta_account_id"],
            "campaigns": ["campaign_id"],
            "adsets": ["campaign_id", "adset_id"],
            "ads": ["campaign_id", "adset_id", "ad_id"],
        }
        if resource == "insights":
            level = row["level"]
            if level not in {"campaign", "adset", "ad"}:
                raise SafeError("invalid_meta_level")
            mandatory = {
                "campaign": ["campaign_id"],
                "adset": ["campaign_id", "adset_id"],
                "ad": ["campaign_id", "adset_id", "ad_id"],
            }[level]
            if any(
                row[k] is not None
                for k in ("campaign_id", "adset_id", "ad_id")
                if k not in mandatory
            ):
                raise SafeError("meta_level_mismatch")
        else:
            mandatory = required[resource]
        for name in mandatory:
            meta_id(row[name])
        for field, typ in schema.items():
            value = row[field]
            if value is None:
                continue
            if typ == "STRING" and not isinstance(value, str):
                raise SafeError("meta_foundation_schema_mismatch")
            if field in {
                "account_id",
                "meta_account_id",
                "campaign_id",
                "adset_id",
                "ad_id",
                "creative_id",
            }:
                meta_id(value)
            if typ == "INT64" and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**63
            ):
                raise SafeError("invalid_meta_metric")
            if typ == "NUMERIC":
                if not isinstance(value, str) or numeric(value) is None or Decimal(value) < 0:
                    raise SafeError("invalid_meta_metric")
            if typ == "DATE" and (
                not isinstance(value, str) or date.fromisoformat(value).isoformat() != value
            ):
                raise SafeError("invalid_insights_date")
            if typ == "TIMESTAMP":
                timestamp(value)
            if typ == "JSON" and not isinstance(value, dict):
                raise SafeError("meta_foundation_schema_mismatch")
        if "currency" in row and row["currency"] != account.currency:
            raise SafeError("meta_currency_mismatch")
        if "timezone" in row and row["timezone"] != account.timezone:
            raise SafeError("meta_timezone_mismatch")
        if resource == "insights":
            if row["date_start"] != row["date_stop"] or row["spend"] is None:
                raise SafeError("invalid_insights_date_or_spend")
