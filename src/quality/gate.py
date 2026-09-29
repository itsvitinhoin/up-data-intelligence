"""Exit policy is separate from severity and from durable ingestion status."""

from typing import Any

RULE_RESOURCE = {
    "duplicate_customers": "customers",
    "duplicate_orders": "orders",
    "duplicate_facts": "analytics_facts",
    "duplicate_event_ids": "analytics_facts",
    "order_id_without_order": "analytics_facts",
    "invalid_meta_parser": "analytics_facts",
    **{
        event + "_without_order_id_" + period: "analytics_facts"
        for event in ("purchase", "purchase_item")
        for period in ("before_effective", "after_effective")
    },
}
# Persisted infrastructure alerts from an earlier failed attempt must not undo a
# successfully resumed run. Its terminal ingestion status is authoritative.
CHILD_BLOCKING_RULES = {
    "duplicate_order_items",
    "fact_without_technical_store",
    "conflicting_duplicate_in_page",
    "conflicting_source_version",
    "invalid_transformation_or_monetary_value",
}


def rule_resource(rule: str, resource: str) -> str:
    return RULE_RESOURCE.get(
        rule, "analytics_facts" if resource == "analytics_events" else resource
    )


def blocking(check: dict[str, Any], requested: str) -> bool:
    scope = rule_resource(check["rule_id"], check["resource"])
    return bool(
        check["failed_count"]
        and check["severity"] == "alert"
        and (requested == "all" or scope in {requested, "all"})
    )


def evaluate(
    requested: str,
    summaries: list[dict[str, Any]],
    global_checks: list[dict[str, Any]],
    child_checks: list[dict[str, Any]],
    *,
    quality_only: bool = False,
) -> dict[str, Any]:
    applicable = global_checks + [c for c in child_checks if c["rule_id"] in CHILD_BLOCKING_RULES]
    failed = [c for c in global_checks + child_checks if c["failed_count"]]
    blocked = any(blocking(c, requested) for c in applicable)
    ingestion_ok = bool(summaries) and all(s["status"] == "completed" for s in summaries)
    return {
        "ingestion_status": "not_requested"
        if quality_only
        else ("completed" if ingestion_ok else "failed"),
        "resource_quality_status": "fail" if blocked else "pass",
        "global_quality_status": "alert"
        if any(c["severity"] == "alert" for c in failed)
        else ("warning" if failed else "pass"),
        "blocking_for_requested_resource": blocked,
        "exit_code": int(blocked or (not quality_only and not ingestion_ok)),
    }
