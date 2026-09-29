"""Compile seven single-SELECT BigQuery validation units from reviewed reference SQL.

No execution. Common CTEs replace TEMP scripts so each entire model can be dry-run.
Final projections are explicit and ordered exactly like the proposed table schemas.
"""

import re
from pathlib import Path
from typing import Any

from src.analytics.policy import LTV_DAYS, VERSION
from src.analytics.schema import SCHEMAS
from src.bigquery.catalog import TABLES

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FIELDS = {
    "orders": "store_id source_system order_id customer_id order_status payment_status requested_total fulfilled_total requested_items_qty fulfilled_items_qty created_at version_id".split(),
    "customers": "store_id source_system customer_id customer_type".split(),
    "order_items": "store_id source_system order_id item_id order_created_at asset_id variant_id sku original_qty qty unit_price status parent_order_version_id present_in_latest_snapshot".split(),
    "analytics_events": "store_id source_system fact_id session_id event_name occurred_at".split(),
}


def key(parts: str) -> str:
    return f"LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY({parts})))))"


def sources(project: str, fixtures: bool) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project):
        raise ValueError("invalid_project")
    parts = []
    for table, fields in SOURCE_FIELDS.items():
        if fixtures:
            expressions = []
            for field in fields:
                typ = TABLES[table].fields[field]
                value = f"JSON_VALUE(item,'$.{field}')"
                expressions.append(
                    (value if typ == "STRING" else f"CAST({value} AS {typ})") + f" AS `{field}`"
                )
            query = (
                "SELECT "
                + ",".join(expressions)
                + f" FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@fixture_{table}))) item"
            )
        else:
            query = (
                "SELECT "
                + ",".join(f"`{f}`" for f in fields)
                + f" FROM `{project}.up_core.{table}` WHERE store_id=@store AND source_system='upzero'"
            )
            if table == "orders":
                query += " AND created_at>=@history_from AND created_at<@as_of"
            elif table in {"order_items", "analytics_events"}:
                stamp = "order_created_at" if table == "order_items" else "occurred_at"
                query += f" AND {stamp}>=TIMESTAMP(@date_from,@timezone) AND {stamp}<TIMESTAMP(@date_to,@timezone)"
        parts.append(f"core_{table} AS ({query})")
    return ",\n".join(parts)


def temporary_cte(text: str, name: str) -> str:
    prefix = f"CREATE TEMP TABLE {name} AS\n"
    return text.split(prefix, 1)[1].split(";", 1)[0]


def section(text: str, marker: str) -> str:
    return text.split(marker, 1)[1].split(";", 1)[0].strip()


def replace_sources(sql: str) -> str:
    for table in SOURCE_FIELDS:
        sql = sql.replace("`${project_id}.up_core." + table + "`", "core_" + table)
    return sql


def compile_model(model: str, *, project: str, fixtures: bool = False) -> str:
    if model not in SCHEMAS:
        raise ValueError("invalid_analytics_model")
    base = (ROOT / "sql/analytics/business_reference.sql").read_text()
    product = (ROOT / "sql/analytics/products_reference.sql").read_text()
    funnel = (ROOT / "sql/analytics/funnel_reference.sql").read_text()
    common = sources(project, fixtures)
    if model != "analytics_funnel_daily":
        for name in (
            "source_orders",
            "source_customers",
            "commerce",
            "purchase_sequence",
            "customer_metrics",
            "cohort_population",
        ):
            common += f",\n{name} AS (" + replace_sources(temporary_cte(base, name)) + ")"
    expressions: dict[str, str] = {}
    if model == "analytics_store_daily":
        query = section(
            base,
            "-- analytics_store_daily: strict NULL propagation, all created orders including cancelled.",
        )
        query = query.replace(
            "COALESCE(t.orders_generated,0) AS orders_generated,",
            "COALESCE(t.orders_generated,0) AS orders_generated, COALESCE(t.approved_orders,0) AS approved_orders,",
        )
        available = "order_date payment_date orders_generated orders_paid orders_cancelled approved_orders new_customers returning_customers purchasing_customers orders_without_customer revenue_generated revenue_fulfilled revenue_paid revenue_cancelled revenue_unfulfilled approval_rate average_order_value_generated average_order_value_paid items_per_order_generated items_per_order_fulfilled meta_spend new_customer_cac roas_generated roas_paid".split()
        expressions["observation_complete"] = "@history_complete"
        grain = "'daily',CAST(b.order_date AS STRING)"
    elif model == "analytics_customer_purchase_sequence":
        query = section(
            base,
            "-- analytics_customer_purchase_sequence: all observed history, not only report interval.",
        )
        available = [f for f in SCHEMAS[model].fields if f not in META_FIELDS]
        grain = "'sequence',b.order_id"
    elif model == "analytics_customer_metrics":
        query = "SELECT * FROM customer_metrics"
        available = "customer_id customer_type first_purchase_at first_purchase_date second_purchase_at third_purchase_at fourth_purchase_at purchases ltv_lifetime_observed".split()
        expressions.update(
            ltv_basis="'requested_total_of_qualifying_orders'", observed_through="@as_of"
        )
        for earlier, later in (("first", "second"), ("second", "third"), ("third", "fourth")):
            expressions[f"days_{earlier}_to_{later}"] = (
                f"SAFE_DIVIDE(CAST(TIMESTAMP_DIFF(b.{later}_purchase_at,b.{earlier}_purchase_at,MICROSECOND) AS NUMERIC),NUMERIC '86400000000')"
            )
        for days in LTV_DAYS:
            stop = f"TIMESTAMP_ADD(b.first_purchase_at,INTERVAL {days} DAY)"
            expressions[f"ltv_{days}d"] = (
                f"IF({stop}<=@as_of,(SELECT IF(COUNTIF(o.revenue_generated IS NULL)>0,NULL,SUM(o.revenue_generated)) FROM UNNEST(b.observed_orders) o WHERE o.order_at<{stop}),NULL)"
            )
            expressions[f"ltv_{days}d_complete"] = f"@history_complete AND {stop}<=@as_of"
        grain = "'customer',b.customer_id"
    elif model == "analytics_cohorts":
        query = section(base, "WITH activity AS")
        query = "WITH activity AS" + query
        available = "cohort_month reporting_month months_since_first_purchase customers_in_cohort active_customers orders revenue_generated revenue_paid observed_retention_rate retention_rate period_complete".split()
        grain = "'cohort',EXTRACT(YEAR FROM b.cohort_month)*12+EXTRACT(MONTH FROM b.cohort_month)-1,b.months_since_first_purchase"
    elif model == "analytics_purchase_distribution":
        query = "WITH ranked AS" + section(base, "WITH ranked AS")
        available = "cohort_month purchase_bucket customers original_cohort_customers percentage_of_original_cohort revenue".split()
        expressions["revenue_basis"] = "'generated_qualifying_orders'"
        grain = "'distribution',CAST(b.cohort_month AS STRING),IF(b.purchase_bucket='5+',5,CAST(b.purchase_bucket AS INT64))"
    elif model == "analytics_products_daily":
        query = "WITH lines AS" + section(product, "WITH lines AS")
        # Isolate unresolvable variants rather than collapsing an asset-only group.
        product_key = f"IF((i.variant_id IS NULL OR i.variant_id='') AND (i.sku IS NULL OR i.sku=''),{key('i.asset_id,i.variant_id,i.sku,i.order_id,i.item_id')},{key('i.asset_id,i.variant_id,i.sku')})"
        query = query.replace(
            "i.asset_id,i.variant_id,i.sku,i.original_qty",
            product_key + " AS product_key,i.asset_id,i.variant_id,i.sku,i.original_qty",
        )
        query = query.replace(
            "SELECT order_date,asset_id,variant_id,sku,",
            "SELECT order_date,product_key,asset_id,variant_id,sku,",
        )
        query = query.replace(
            "GROUP BY order_date,asset_id,variant_id,sku",
            "GROUP BY order_date,product_key,asset_id,variant_id,sku",
        )
        available = [f for f in SCHEMAS[model].fields if f not in META_FIELDS]
        grain = "'product',CAST(b.order_date AS STRING),b.product_key"
    else:
        for name in ("events", "ordered_events"):
            common += f",\n{name} AS (" + replace_sources(temporary_cte(funnel, name)) + ")"
        query = "WITH carts AS" + section(funnel, "WITH carts AS")
        query = query.replace(
            "COALESCE(c.sessions,0) AS sessions,",
            "COALESCE(c.sessions,0) AS sessions,"
            + ",".join(
                f"COALESCE(c.{f},0) AS {f}"
                for f in (
                    "sessions_with_cart",
                    "sessions_cart_then_checkout",
                    "sessions_cart_checkout_purchase",
                    "sessions_with_purchase",
                )
            )
            + ",",
        )
        available = [
            f for f in SCHEMAS[model].fields if f not in META_FIELDS and f != "observation_complete"
        ]
        expressions["observation_complete"] = "@facts_complete"
        grain = "'funnel',CAST(b.event_date AS STRING)"
    expressions = {**{f: "b." + f for f in available}, **expressions}
    expressions.update(
        row_key=key("@store,@policy_hash," + grain),
        store_id="@store",
        currency="@currency",
        reporting_timezone="@timezone",
        calculated_at="@as_of",
        policy_hash="@policy_hash",
        analytics_version=f"'{VERSION}'",
        history_complete="@history_complete",
    )
    # Missing projections must be explicit future/unsupported metrics, not silent gaps.
    nulls = {
        "meta_impressions",
        "meta_clicks",
        "meta_reported_purchases",
        "meta_reported_purchase_value",
        "first_party_new_customers_attributed",
        "first_party_orders_attributed",
        "first_party_revenue_generated_attributed",
        "first_party_revenue_paid_attributed",
        "ltv_paid",
    }
    missing = set(SCHEMAS[model].fields) - expressions.keys()
    if missing - nulls:
        raise ValueError("incomplete_sql_projection:" + ",".join(sorted(missing - nulls)))
    projection = [
        f"CAST({expressions.get(f, 'NULL')} AS {typ}) AS `{f}`"
        for f, typ in SCHEMAS[model].fields.items()
    ]
    return (
        "-- Prepared single SELECT; NOT validated on BigQuery.\nWITH "
        + common
        + ",\nbusiness AS (\n"
        + replace_sources(query)
        + "\n)\nSELECT\n "
        + ",\n ".join(projection)
        + "\nFROM business b\n"
    )


META_FIELDS = {
    "row_key",
    "store_id",
    "currency",
    "reporting_timezone",
    "calculated_at",
    "policy_hash",
    "analytics_version",
    "history_complete",
}


def generate(root: Path = ROOT) -> dict[str, Any]:
    folder = root / "sql/analytics/models"
    folder.mkdir(parents=True, exist_ok=True)
    for model in SCHEMAS:
        (folder / (model + ".sql")).write_text(
            compile_model(model, project="up-data-intelligence-dev")
        )
    return {"models": list(SCHEMAS), "executed": False}


if __name__ == "__main__":
    generate()
