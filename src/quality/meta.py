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
