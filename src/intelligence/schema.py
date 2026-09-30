"""Proposed Customer 360 schemas. No active Terraform registration."""

import json
from pathlib import Path

from src.bigquery.catalog import Table

BASE = dict.fromkeys("row_key store_id policy_hash generation currency".split(), "STRING") | {
    "calculated_at": "TIMESTAMP",
    "as_of": "TIMESTAMP",
}


def f(names: str, typ: str) -> dict[str, str]:
    return dict.fromkeys(names.split(), typ)


SCHEMAS = {
    "analytics_customer_360_profile": Table(
        "up_analytics",
        BASE
        | f("customer_id customer_type company_name trade_name state city ltv_basis", "STRING")
        | f("first_order_at last_purchase_at", "TIMESTAMP")
        | f(
            "first_purchase_requested_revenue first_purchase_fulfilled_revenue total_requested_revenue total_fulfilled_revenue total_requested_quantity total_fulfilled_quantity ltv_observed",
            "NUMERIC",
        )
        | f("total_orders purchase_count days_since_last_purchase", "INT64")
        | f(
            "has_repurchase paid_media_influenced acquisition_influenced repeat_purchase_influenced history_complete",
            "BOOL",
        ),
        None,
        ("store_id", "customer_id"),
    ),
    "analytics_customer_journey_summary": Table(
        "up_analytics",
        BASE
        | f("customer_id first_campaign_id last_campaign_id", "STRING")
        | f(
            "first_touch_at first_paid_touch_at last_paid_touch_at timeline_start timeline_end",
            "TIMESTAMP",
        )
        | f(
            "total_events total_sessions total_products_viewed total_cart_events total_checkout_events",
            "INT64",
        ),
        None,
        ("store_id", "customer_id"),
    ),
    "analytics_customer_orders_summary": Table(
        "up_analytics",
        BASE
        | f(
            "customer_id order_id order_status first_campaign_id last_campaign_id evidence_type influence_scope",
            "STRING",
        )
        | f("purchase_number campaign_count", "INT64")
        | {"created_at": "TIMESTAMP", "paid_media_influenced": "BOOL"}
        | f("requested_total fulfilled_total requested_items_qty fulfilled_items_qty", "NUMERIC")
        | f("identity_path campaigns influence_by_scope", "JSON"),
        "created_at",
        ("store_id", "customer_id", "order_id"),
    ),
    "analytics_customer_products_summary": Table(
        "up_analytics",
        BASE
        | f(
            "customer_id product_id product_key variant_id sku resolution_status revenue_basis",
            "STRING",
        )
        | {"orders_count": "INT64"}
        | f("requested_quantity fulfilled_quantity requested_revenue fulfilled_revenue", "NUMERIC")
        | f("first_purchase_at last_purchase_at", "TIMESTAMP"),
        None,
        ("store_id", "customer_id", "product_key"),
    ),
}


def generate(root: Path = Path(".")) -> None:
    path = root / "infra/terraform/customer_intelligence_proposed"
    (path / "schemas").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in SCHEMAS.items():
        schema = [
            {
                "name": k,
                "type": typ,
                "mode": "REQUIRED" if k in {"row_key", "store_id"} else "NULLABLE",
            }
            for k, typ in spec.fields.items()
        ]
        (path / "schemas" / f"{name}.json").write_text(json.dumps(schema, indent=2) + "\n")
        manifest[name] = {
            "dataset": spec.dataset,
            "partition": spec.partition,
            "cluster": list(spec.cluster),
            "deletion_protection": True,
        }
    (path / "tables.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    generate()
