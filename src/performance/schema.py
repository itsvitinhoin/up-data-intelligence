"""CHANGE #14 proposals, outside active Terraform/catalog."""

import json
from pathlib import Path


def f(names: str, typ: str) -> dict[str, str]:
    return dict.fromkeys(names.split(), typ)


BASE = (
    f(
        "row_key store_id account_id policy_hash generation currency timezone influence_scope",
        "STRING",
    )
    | f("period_start period_end", "DATE")
    | f("as_of calculated_at", "TIMESTAMP")
    | f("history_complete facts_complete spend_complete influence_complete", "BOOL")
)
NEW = (
    f("is_new_customer previous_purchase_exists", "BOOL")
    | f("first_purchase_at", "TIMESTAMP")
    | f("first_qualified_order_id classification_order_id", "STRING")
    | f("historical_purchase_count_before_first_purchase", "INT64")
)
COMMERCE = f(
    "requested_revenue_influenced fulfilled_revenue_influenced requested_quantity_influenced fulfilled_quantity_influenced",
    "NUMERIC",
)
EFFICIENCY = f("roas_requested roas_fulfilled cac_new_customer fulfillment_rate", "NUMERIC")
COUNTS = f("influenced_customers influenced_orders new_customers_influenced", "INT64")
SCHEMAS = {
    "analytics_campaign_performance_daily": BASE
    | {"date": "DATE"}
    | f("campaign_id campaign_name adset_id ad_id", "STRING")
    | f("spend observed_spend ctr cpc cpm", "NUMERIC")
    | f("impressions clicks", "INT64")
    | COUNTS
    | COMMERCE
    | EFFICIENCY,
    "analytics_campaign_customer_performance": BASE
    | f("campaign_id customer_id", "STRING")
    | {"paid_media_influenced": "BOOL"}
    | f("first_paid_touch_at last_paid_touch_at", "TIMESTAMP")
    | {"orders_influenced": "INT64"}
    | f("requested_revenue fulfilled_revenue requested_quantity fulfilled_quantity", "NUMERIC")
    | NEW,
    "analytics_campaign_order_performance": BASE
    | f("campaign_id order_id customer_id evidence_type", "STRING")
    | f("purchase_number touch_count", "INT64")
    | f("first_paid_touch_at last_paid_touch_at", "TIMESTAMP")
    | {"identity_path": "JSON"}
    | f("requested_total fulfilled_total requested_items_qty fulfilled_items_qty", "NUMERIC")
    | NEW,
    "analytics_performance_summary": BASE
    | f("meta_spend observed_meta_spend", "NUMERIC")
    | COUNTS
    | COMMERCE
    | EFFICIENCY,
}


def generate(root: Path = Path(".")) -> None:
    path = root / "infra/terraform/performance_proposed"
    (path / "schemas").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, fields in SCHEMAS.items():
        (path / "schemas" / (name + ".json")).write_text(
            json.dumps(
                [
                    {
                        "name": k,
                        "type": v,
                        "mode": "REQUIRED" if k in {"row_key", "store_id"} else "NULLABLE",
                    }
                    for k, v in fields.items()
                ],
                indent=2,
            )
            + "\n"
        )
        manifest[name] = {
            "dataset": "up_analytics",
            "partition": "date" if name.endswith("daily") else "period_start",
            "cluster": ["store_id", "account_id"],
            "deletion_protection": True,
        }
    (path / "tables.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    generate()
