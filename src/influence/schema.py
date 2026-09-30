"""Four additive proposed tables; never added to active Analytics V1 manifests."""

import json
from pathlib import Path

from src.bigquery.catalog import Table

BASE = {k: "STRING" for k in "row_key store_id policy_hash currency".split()} | {
    "calculated_at": "TIMESTAMP",
    "as_of": "TIMESTAMP",
    "history_complete": "BOOL",
    "facts_complete": "BOOL",
}


def fields(names: str, typ: str) -> dict[str, str]:
    return dict.fromkeys(names.split(), typ)


SCHEMAS = {
    "analytics_paid_touchpoints": Table(
        "up_analytics",
        BASE
        | fields(
            "fact_id event_id session_id visitor_id user_id campaign_id adset_id ad_id utm_source utm_medium utm_campaign touch_type evidence_type",
            "STRING",
        )
        | {"occurred_at": "TIMESTAMP", "identity_path": "JSON", "paid_signal_types": "JSON"},
        "occurred_at",
        ("store_id", "campaign_id", "fact_id"),
    ),
    "analytics_customer_paid_influence": Table(
        "up_analytics",
        BASE
        | fields(
            "customer_id first_campaign_id last_campaign_id evidence_type influence_scope", "STRING"
        )
        | {"paid_media_influenced": "BOOL", "identity_path": "JSON"}
        | fields("first_paid_touch_at last_paid_touch_at", "TIMESTAMP")
        | fields("paid_touch_count campaign_count adset_count ad_count influenced_orders", "INT64")
        | fields(
            "requested_revenue_influenced fulfilled_revenue_influenced requested_quantity_influenced fulfilled_quantity_influenced",
            "NUMERIC",
        ),
        None,
        ("store_id", "customer_id"),
    ),
    "analytics_order_paid_influence": Table(
        "up_analytics",
        BASE
        | fields(
            "order_id customer_id campaign_id adset_id ad_id evidence_type influence_scope",
            "STRING",
        )
        | fields("purchase_number touch_count", "INT64")
        | fields("first_paid_touch_at last_paid_touch_at", "TIMESTAMP")
        | fields(
            "requested_total fulfilled_total requested_items_qty fulfilled_items_qty", "NUMERIC"
        )
        | fields("identity_path participating_ads", "JSON"),
        None,
        ("store_id", "customer_id", "order_id", "campaign_id"),
    ),
    "analytics_customer_timeline": Table(
        "up_analytics",
        BASE
        | fields(
            "customer_id event_id fact_id event_name session_id visitor_id user_id campaign_id adset_id ad_id utm_source utm_medium utm_campaign product_id variant_id order_id channel source device_type confidence_type record_type order_status",
            "STRING",
        )
        | {"occurred_at": "TIMESTAMP", "identity_path": "JSON"}
        | fields(
            "value quantity requested_total fulfilled_total requested_items_qty fulfilled_items_qty",
            "NUMERIC",
        ),
        "occurred_at",
        ("store_id", "customer_id", "order_id"),
    ),
}


def generate(root: Path = Path(".")) -> None:
    folder = root / "infra/terraform/paid_influence_proposed"
    (folder / "schemas").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in SCHEMAS.items():
        schema = [
            {
                "name": k,
                "type": t,
                "mode": "REQUIRED" if k in {"row_key", "store_id"} else "NULLABLE",
            }
            for k, t in spec.fields.items()
        ]
        (folder / "schemas" / (name + ".json")).write_text(json.dumps(schema, indent=2) + "\n")
        manifest[name] = {
            "dataset": spec.dataset,
            "partition": spec.partition,
            "cluster": list(spec.cluster),
            "deletion_protection": True,
        }
    (folder / "tables.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    generate()
