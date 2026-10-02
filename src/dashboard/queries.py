"""Allowlisted, parameterized BigQuery reads over active Analytics V1 and CORE."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    name: str
    sql: str
    parameters: dict[str, tuple[str, object]]


def table(project: str, dataset: str, name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project):
        raise ValueError("invalid_project")
    if dataset not in {"up_analytics", "up_core"} or name not in {
        "analytics_publications",
        "analytics_store_daily",
        "analytics_customer_metrics",
        "analytics_customer_purchase_sequence",
        "analytics_cohorts",
        "analytics_purchase_distribution",
        "analytics_products_daily",
        "analytics_funnel_daily",
        "customers",
        "orders",
    }:
        raise ValueError("dashboard_table_not_allowed")
    return f"`{project}.{dataset}.{name}`"


def build(project: str, name: str, **values: object) -> Query:
    """Only project/table identifiers are interpolated; caller values are parameters."""

    def a(model: str) -> str:
        return table(project, "up_analytics", model)

    def c(model: str) -> str:
        return table(project, "up_core", model)

    history = "FOR SYSTEM_TIME AS OF @snapshot_at"
    scope = "store_id=@store AND policy_hash=@policy"
    common = {
        "store": ("STRING", values.get("store")),
        "policy": ("STRING", values.get("policy")),
    }
    if name == "head":
        at = ""
        if values.get("snapshot_at") is not None:
            common["snapshot_at"] = ("TIMESTAMP", values["snapshot_at"])
            at = "FOR SYSTEM_TIME AS OF @snapshot_at"
        sql = f"""/* dashboard:head */
SELECT h.store_id,h.policy_hash,h.generation,h.publication_id,h.status,
 h.as_of,h.report_from,h.report_to,h.source_watermark,
 r.store_id AS receipt_store_id,r.policy_hash AS receipt_policy_hash,
 r.publication_id AS receipt_id,r.generation AS receipt_generation,
 r.status AS receipt_status,r.analytics_version AS receipt_version,
 r.source_watermark AS receipt_watermark,
 r.as_of AS receipt_as_of,r.report_from AS receipt_from,r.report_to AS receipt_to,
 CURRENT_TIMESTAMP() AS snapshot_at
FROM {a("analytics_publications")} AS h {at}
LEFT JOIN {a("analytics_publications")} AS r {at}
 ON r.record_kind='RECEIPT' AND r.store_id=h.store_id
 AND r.policy_hash=h.policy_hash AND r.publication_id=h.publication_id
WHERE h.record_kind='HEAD' AND h.store_id=@store AND h.policy_hash=@policy"""
        return Query(name, sql, common)
    params = {**common, "snapshot_at": ("TIMESTAMP", values.get("snapshot_at"))}
    if name in {"store_daily", "funnel_daily", "products", "cohorts"}:
        params.update(
            {"from": ("DATE", values.get("from_day")), "to": ("DATE", values.get("to_day"))}
        )
    if name == "store_daily":
        sql = f"""/* dashboard:store_daily */
SELECT order_date,currency,reporting_timezone,history_complete,observation_complete,
 orders_generated,orders_cancelled,approved_orders,new_customers,returning_customers,
 revenue_generated,revenue_fulfilled,revenue_cancelled,revenue_unfulfilled,
 average_order_value_generated,items_per_order_generated,items_per_order_fulfilled
FROM {a("analytics_store_daily")} {history}
WHERE {scope} AND order_date>=@from AND order_date<@to
ORDER BY order_date LIMIT 367"""
    elif name == "customer_period":
        params.update(
            {"from": ("DATE", values.get("from_day")), "to": ("DATE", values.get("to_day"))}
        )
        sql = f"""/* dashboard:customer_period */
SELECT COUNT(DISTINCT customer_id) AS buyers,
 COUNT(DISTINCT IF(purchase_number>=2,customer_id,NULL)) AS recurring_buyers,
 COUNT(*) AS qualifying_orders,
 COUNTIF(purchase_number>=2) AS recurring_orders,
 IF(COUNTIF(purchase_number>=2 AND revenue_fulfilled IS NULL)>0,NULL,
 SUM(IF(purchase_number>=2,revenue_fulfilled,0))) AS recurring_fulfilled
FROM {a("analytics_customer_purchase_sequence")} {history}
WHERE {scope} AND order_date>=@from AND order_date<@to"""
    elif name in {"customers", "customer"}:
        params.update(
            {
                "after": ("STRING", values.get("after", "")),
                "limit": ("INT64", values.get("limit", 2)),
            }
        )
        if name == "customer":
            params["customer"] = ("STRING", values.get("customer"))
        period_selector = ""
        if name == "customers" and values.get("from_day") is not None:
            params.update({"from": ("DATE", values["from_day"]), "to": ("DATE", values["to_day"])})
            period_selector = f"""AND EXISTS (
 SELECT 1 FROM {a("analytics_customer_purchase_sequence")} AS s {history}
 WHERE s.store_id=m.store_id AND s.policy_hash=@policy AND s.customer_id=m.customer_id
 AND s.order_date>=@from AND s.order_date<@to)"""
        selector = "m.customer_id=@customer" if name == "customer" else "cursor_key>@after"
        sql = f"""/* dashboard:{name} */
WITH metrics AS (
 SELECT *,LOWER(TO_HEX(SHA256(CONCAT(store_id,':',customer_id)))) AS cursor_key
 FROM {a("analytics_customer_metrics")} {history}
 WHERE {scope} AND customer_id IS NOT NULL
), profiles AS (
 SELECT customer_id,name,company_name,trade_name,state,city
 FROM {c("customers")} {history}
 WHERE store_id=@store AND source_system='upzero'
 QUALIFY COUNT(*) OVER(PARTITION BY customer_id)=1
)
SELECT m.customer_id,m.customer_type,m.purchases,m.first_purchase_at,
 m.first_purchase_date,m.ltv_lifetime_observed,m.ltv_paid,m.cursor_key,
 p.name,p.company_name,p.trade_name,p.state,p.city
FROM metrics m LEFT JOIN profiles p ON p.customer_id=m.customer_id
WHERE {selector} {period_selector} ORDER BY m.cursor_key LIMIT @limit"""
    elif name == "store_orders":
        params.update(
            {
                "from": ("DATE", values.get("from_day")),
                "to": ("DATE", values.get("to_day")),
                "timezone": ("STRING", values.get("timezone")),
                "status": ("STRING", values.get("status")),
                "after": ("STRING", values.get("after", "")),
                "limit": ("INT64", values.get("limit")),
                "as_of": ("TIMESTAMP", values.get("as_of")),
            }
        )
        sql = f"""/* dashboard:store_orders */
WITH selected AS (
 SELECT order_id,customer_id,created_at,order_status,payment_status,
 requested_total,fulfilled_total,requested_items_qty,fulfilled_items_qty,
 CONCAT(FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E6SZ',created_at),':',order_id) AS cursor_key
 FROM {c("orders")} {history}
 WHERE store_id=@store AND source_system='upzero'
 AND DATE(created_at,@timezone)>=@from AND DATE(created_at,@timezone)<@to
 AND created_at<@as_of AND (@status IS NULL OR order_status=@status)
)
SELECT * FROM selected WHERE cursor_key>@after ORDER BY created_at,order_id LIMIT @limit"""
        params.pop("policy")
    elif name == "acquisition_first":
        params.update(
            {"from": ("DATE", values.get("from_day")), "to": ("DATE", values.get("to_day"))}
        )
        sql = f"""/* dashboard:acquisition_first */
WITH first_orders AS (
 SELECT *,COUNT(*) OVER(PARTITION BY customer_id) AS customer_first_rows,
 COUNT(*) OVER(PARTITION BY order_id) AS order_first_rows
 FROM {a("analytics_customer_purchase_sequence")} {history}
 WHERE {scope} AND purchase_number=1
)
SELECT COUNT(DISTINCT customer_id) AS customers,COUNT(*) AS orders,
 COUNTIF(customer_first_rows!=1 OR order_first_rows!=1 OR customer_id IS NULL OR order_id IS NULL) AS invalid_first_orders,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,IF(COUNT(*)=0,NUMERIC '0',SUM(revenue_generated))) AS requested,
 IF(COUNTIF(revenue_fulfilled IS NULL)>0,NULL,IF(COUNT(*)=0,NUMERIC '0',SUM(revenue_fulfilled))) AS fulfilled
FROM first_orders WHERE order_date>=@from AND order_date<@to"""
    elif name == "orders":
        params.update(
            {
                "customer": ("STRING", values.get("customer")),
                "after": ("STRING", values.get("after", "")),
                "limit": ("INT64", values.get("limit")),
                "history_from": ("TIMESTAMP", values.get("history_from")),
                "as_of": ("TIMESTAMP", values.get("as_of")),
            }
        )
        sql = f"""/* dashboard:orders */
WITH selected AS (
 SELECT order_id,customer_id,created_at,order_status,payment_status,
 requested_total,fulfilled_total,requested_items_qty,fulfilled_items_qty,
 CONCAT(FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E6SZ',created_at),':',
 LOWER(TO_HEX(SHA256(order_id)))) AS cursor_key
 FROM {c("orders")} {history}
 WHERE store_id=@store AND source_system='upzero' AND customer_id=@customer
 AND created_at>=@history_from AND created_at<@as_of
)
SELECT * FROM selected WHERE cursor_key>@after ORDER BY cursor_key LIMIT @limit"""
        params.pop("policy")
    elif name == "customer_summary":
        params["customer"] = ("STRING", values.get("customer"))
        sql = f"""/* dashboard:customer_summary */
SELECT COUNT(*) AS qualifying_orders,MIN(order_at) AS first_purchase_at,
 MAX(order_at) AS last_purchase_at,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,SUM(revenue_generated)) AS requested,
 IF(COUNTIF(revenue_fulfilled IS NULL)>0,NULL,SUM(revenue_fulfilled)) AS fulfilled
FROM {a("analytics_customer_purchase_sequence")} {history}
WHERE {scope} AND customer_id=@customer"""
    elif name == "retention_distribution":
        sql = f"""/* dashboard:retention_distribution */
SELECT cohort_month,purchase_bucket,customers,original_cohort_customers,
 percentage_of_original_cohort,revenue
FROM {a("analytics_purchase_distribution")} {history}
WHERE {scope} ORDER BY cohort_month,purchase_bucket LIMIT 1001"""
    elif name == "retention_cohorts":
        sql = f"""/* dashboard:retention_cohorts */
SELECT cohort_month,reporting_month,months_since_first_purchase,customers_in_cohort,
 active_customers,retention_rate,observed_retention_rate,period_complete
FROM {a("analytics_cohorts")} {history}
WHERE {scope} ORDER BY cohort_month,reporting_month LIMIT 1001"""
    elif name == "retention_gaps":
        sql = f"""/* dashboard:retention_gaps */
WITH numbered AS (
 SELECT customer_id,purchase_number,order_at,
 LAG(order_at) OVER(PARTITION BY customer_id ORDER BY purchase_number) AS previous_at
 FROM {a("analytics_customer_purchase_sequence")} {history}
 WHERE {scope}
), gaps AS (
 SELECT purchase_number AS stage,
 TIMESTAMP_DIFF(order_at,previous_at,MICROSECOND)/86400000000.0 AS gap_days
 FROM numbered WHERE purchase_number BETWEEN 2 AND 5 AND previous_at IS NOT NULL
)
SELECT stage,COUNT(*) AS transitions,AVG(gap_days) AS mean_days,
 ANY_VALUE(median_days) AS median_days
FROM (SELECT stage,gap_days,PERCENTILE_CONT(gap_days,0.5)
 OVER(PARTITION BY stage) AS median_days FROM gaps)
GROUP BY stage ORDER BY stage"""
    elif name == "products":
        params.update(
            {"after": ("STRING", values.get("after", "")), "limit": ("INT64", values.get("limit"))}
        )
        sql = f"""/* dashboard:products */
WITH grouped AS (
 SELECT product_key,product_id,sku,
 SUM(orders) AS orders,
 IF(COUNTIF(units_requested IS NULL)>0,NULL,SUM(units_requested)) AS units_requested,
 IF(COUNTIF(units_fulfilled IS NULL)>0,NULL,SUM(units_fulfilled)) AS units_fulfilled,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,SUM(revenue_generated)) AS requested,
 IF(COUNTIF(revenue_fulfilled IS NULL)>0,NULL,SUM(revenue_fulfilled)) AS fulfilled,
 LOWER(TO_HEX(SHA256(product_key))) AS cursor_key
 FROM {a("analytics_products_daily")} {history}
 WHERE {scope} AND order_date>=@from AND order_date<@to
 GROUP BY product_key,product_id,sku
)
SELECT * FROM grouped WHERE cursor_key>@after ORDER BY cursor_key LIMIT @limit"""
    elif name == "funnel_daily":
        sql = f"""/* dashboard:funnel_daily */
SELECT event_date,observation_complete,sessions,product_views,add_to_cart,
 checkout_started,purchase,sessions_with_cart,sessions_cart_then_checkout,
 sessions_cart_checkout_purchase,sessions_with_purchase,events_without_session
FROM {a("analytics_funnel_daily")} {history}
WHERE {scope} AND event_date>=@from AND event_date<@to
ORDER BY event_date LIMIT 367"""
    else:
        raise ValueError("dashboard_query_not_allowed")
    return Query(name, sql, params)
