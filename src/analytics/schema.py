"""Reviewed analytics schemas. Terraform activation is separate from ingestion runtime."""

import json
from pathlib import Path

from src.bigquery.catalog import Table

BASE = {
    k: "STRING"
    for k in "row_key store_id currency reporting_timezone policy_hash analytics_version".split()
} | {"calculated_at": "TIMESTAMP", "history_complete": "BOOL"}


def fields(names: str, typ: str = "NUMERIC") -> dict[str, str]:
    return dict.fromkeys(names.split(), typ)


SCHEMAS = {
    "analytics_store_daily": Table(
        "up_analytics",
        BASE
        | fields("order_date payment_date", "DATE")
        | fields(
            "orders_generated orders_paid orders_cancelled approved_orders new_customers returning_customers purchasing_customers orders_without_customer meta_impressions meta_clicks first_party_new_customers_attributed first_party_orders_attributed",
            "INT64",
        )
        | fields(
            "revenue_generated revenue_fulfilled revenue_paid revenue_cancelled revenue_unfulfilled approval_rate average_order_value_generated average_order_value_paid items_per_order_generated items_per_order_fulfilled meta_spend meta_reported_purchases meta_reported_purchase_value first_party_revenue_generated_attributed first_party_revenue_paid_attributed new_customer_cac roas_generated roas_paid"
        )
        | {"observation_complete": "BOOL"},
        "order_date",
        ("store_id", "policy_hash"),
    ),
    "analytics_customer_metrics": Table(
        "up_analytics",
        BASE
        | fields("customer_id customer_type ltv_basis", "STRING")
        | {"first_purchase_date": "DATE", "purchases": "INT64"}
        | fields(
            "first_purchase_at second_purchase_at third_purchase_at fourth_purchase_at observed_through",
            "TIMESTAMP",
        )
        | fields(
            "ltv_lifetime_observed ltv_paid days_first_to_second days_second_to_third days_third_to_fourth ltv_30d ltv_60d ltv_90d ltv_180d ltv_365d"
        )
        | fields(
            "ltv_30d_complete ltv_60d_complete ltv_90d_complete ltv_180d_complete ltv_365d_complete",
            "BOOL",
        ),
        None,
        ("store_id", "customer_id", "policy_hash"),
    ),
    "analytics_customer_purchase_sequence": Table(
        "up_analytics",
        BASE
        | fields(
            "customer_id customer_type order_id source_order_version_id customer_classification",
            "STRING",
        )
        | fields("order_at first_purchase_at", "TIMESTAMP")
        | fields("order_date first_purchase_date", "DATE")
        | {"purchase_number": "INT64"}
        | fields("revenue_generated revenue_fulfilled revenue_paid"),
        "order_date",
        ("store_id", "customer_id", "policy_hash"),
    ),
    "analytics_cohorts": Table(
        "up_analytics",
        BASE
        | fields("cohort_month reporting_month", "DATE")
        | fields("months_since_first_purchase customers_in_cohort active_customers orders", "INT64")
        | fields("retention_rate observed_retention_rate revenue_generated revenue_paid")
        | {"period_complete": "BOOL"},
        "cohort_month",
        ("store_id", "months_since_first_purchase", "policy_hash"),
    ),
    "analytics_purchase_distribution": Table(
        "up_analytics",
        BASE
        | {"cohort_month": "DATE"}
        | fields("purchase_bucket revenue_basis", "STRING")
        | fields("customers original_cohort_customers", "INT64")
        | fields("percentage_of_original_cohort revenue"),
        "cohort_month",
        ("store_id", "purchase_bucket", "policy_hash"),
    ),
    "analytics_products_daily": Table(
        "up_analytics",
        BASE
        | {"order_date": "DATE"}
        | fields("product_key product_id asset_id variant_id sku reference revenue_basis", "STRING")
        | fields("orders customers impressions clicks first_party_orders_attributed", "INT64")
        | fields(
            "units_requested units_fulfilled revenue_generated revenue_fulfilled revenue_paid average_selling_price cancellation_rate spend first_party_revenue_attributed roas"
        ),
        "order_date",
        ("store_id", "product_key", "policy_hash"),
    ),
    "analytics_funnel_daily": Table(
        "up_analytics",
        BASE
        | {"event_date": "DATE"}
        | fields(
            "sessions product_views add_to_cart checkout_started purchase sessions_with_cart sessions_cart_then_checkout sessions_cart_checkout_purchase sessions_with_purchase events_without_session",
            "INT64",
        )
        | fields(
            "session_to_cart_rate cart_to_checkout_rate checkout_to_purchase_rate session_conversion_rate cost_per_session cost_per_add_to_cart cost_per_checkout"
        )
        | {"observation_complete": "BOOL"},
        "event_date",
        ("store_id", "policy_hash"),
    ),
}


def generate(root: Path = Path(".")) -> None:
    folder = root / "infra/terraform/analytics_proposed"
    (folder / "schemas").mkdir(parents=True, exist_ok=True)
    sql_folder = root / "sql/analytics/proposed_ddl"
    sql_folder.mkdir(parents=True, exist_ok=True)
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
        }
        sql = (
            "-- PROPOSTA; NÃO EXECUTADA. Não incluída no Terraform ativo.\nCREATE TABLE IF NOT EXISTS `${project_id}.up_analytics."
            + name
            + "` (\n"
        )
        sql += (
            ",\n".join(
                f"  `{k}` {t}" + (" NOT NULL" if k in {"store_id", "row_key"} else "")
                for k, t in spec.fields.items()
            )
            + "\n)"
        )
        if spec.partition:
            sql += "\nPARTITION BY " + spec.partition
        sql += "\nCLUSTER BY " + ", ".join(spec.cluster) + ";\n"
        (sql_folder / (name + ".sql")).write_text(sql)
    (folder / "tables.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    generate()
