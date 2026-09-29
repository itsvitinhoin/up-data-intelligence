"""Analytics-specific guards; never modify the ingestion quality gate."""

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from src.analytics.schema import SCHEMAS
from src.utils.data import numeric

GRAINS = {
    "analytics_store_daily": ("order_date",),
    "analytics_customer_metrics": ("customer_id",),
    "analytics_customer_purchase_sequence": ("order_id",),
    "analytics_cohorts": ("cohort_month", "months_since_first_purchase"),
    "analytics_purchase_distribution": ("cohort_month", "purchase_bucket"),
    "analytics_products_daily": ("order_date", "product_key"),
    "analytics_funnel_daily": ("event_date",),
}
RULES = {
    "policy_missing": "blocking",
    "policy_hash_mismatch": "blocking",
    "history_coverage_unknown": "warning_if_incomplete_blocking_if_claimed_complete",
    "currency_missing": "warning_if_explicit_local_only_otherwise_blocking",
    "analytics_model_stale": "blocking",
    "analytics_materialization_duplicate_key": "blocking",
    "analytics_parity_failure": "blocking",
    "negative_revenue": "blocking",
    "paid_revenue_greater_than_generated": "blocking_if_no_overpayment_allowed",
    "order_without_customer": "warning",
    "duplicate_order": "blocking",
    "duplicate_customer": "blocking",
    "purchase_sequence_gap": "blocking",
    "cohort_negative_month": "blocking",
    "invalid_first_purchase": "blocking",
    "funnel_negative_counts": "blocking",
    "paid_orders_without_paid_revenue": "warning_when_payment_amount_unavailable",
    "customer_ltv_negative": "blocking",
    "analytics_duplicate_grain": "blocking",
}


def issue(rule: str, severity: str = "warning", count: int = 1) -> dict[str, Any]:
    # Aggregates only: no IDs, names, URLs, PII or credential content in diagnostics.
    return {"rule_id": rule, "severity": severity, "failed_count": count}


class AnalyticsQualityError(ValueError):
    pass


def unique(rows: list[dict[str, Any]], key: str, rule: str) -> None:
    values = [r.get(key) for r in rows]
    if any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(
        values
    ):
        raise AnalyticsQualityError(rule)


def validate_outputs(
    tables: dict[str, list[dict[str, Any]]], *, allow_overpayment: bool = False
) -> list[dict[str, Any]]:
    findings = []
    for table, rows in tables.items():
        counts = Counter(
            tuple(r.get(k) for k in ("store_id", "policy_hash", *GRAINS.get(table, ("row_key",))))
            for r in rows
        )
        if any(n > 1 for n in counts.values()):
            findings.append(issue("analytics_duplicate_grain", "blocking"))
        for row in rows:
            for name, value in row.items():
                if (
                    value is not None
                    and SCHEMAS[table].fields.get(name) == "NUMERIC"
                    and (name.startswith("revenue_") or name.startswith("ltv_"))
                ):
                    if Decimal(numeric(value) or "0") < 0:
                        findings.append(
                            issue(
                                "customer_ltv_negative"
                                if name.startswith("ltv_")
                                else "negative_revenue",
                                "blocking",
                            )
                        )
            paid, generated = row.get("revenue_paid"), row.get("revenue_generated")
            if paid is not None and generated is not None and not allow_overpayment:
                if Decimal(str(paid)) > Decimal(str(generated)):
                    findings.append(issue("paid_revenue_greater_than_generated", "blocking"))
            if row.get("orders_paid", 0) and paid is None:
                findings.append(issue("paid_orders_without_paid_revenue"))
            if row.get("months_since_first_purchase", 0) < 0:
                findings.append(issue("cohort_negative_month", "blocking"))
            if table == "analytics_funnel_daily" and any(
                row.get(k, 0) < 0
                for k in (
                    "sessions",
                    "product_views",
                    "add_to_cart",
                    "checkout_started",
                    "purchase",
                )
            ):
                findings.append(issue("funnel_negative_counts", "blocking"))
    sequences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tables.get("analytics_customer_purchase_sequence", []):
        sequences[row["store_id"] + ":" + row["customer_id"]].append(row)
    for rows in sequences.values():
        ordered = sorted(rows, key=lambda r: r["purchase_number"])
        if [r["purchase_number"] for r in ordered] != list(range(1, len(rows) + 1)):
            findings.append(issue("purchase_sequence_gap", "blocking"))
        if any(r["first_purchase_at"] != ordered[0]["order_at"] for r in rows):
            findings.append(issue("invalid_first_purchase", "blocking"))
    return findings
