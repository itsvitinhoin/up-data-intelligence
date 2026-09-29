-- Prepared single SELECT; NOT validated on BigQuery.
WITH core_orders AS (SELECT `store_id`,`source_system`,`order_id`,`customer_id`,`order_status`,`payment_status`,`requested_total`,`fulfilled_total`,`requested_items_qty`,`fulfilled_items_qty`,`created_at`,`version_id` FROM `up-data-intelligence-dev.up_core.orders` WHERE store_id=@store AND source_system='upzero' AND created_at>=@history_from AND created_at<@as_of),
core_customers AS (SELECT `store_id`,`source_system`,`customer_id`,`customer_type` FROM `up-data-intelligence-dev.up_core.customers` WHERE store_id=@store AND source_system='upzero'),
core_order_items AS (SELECT `store_id`,`source_system`,`order_id`,`item_id`,`order_created_at`,`asset_id`,`variant_id`,`sku`,`original_qty`,`qty`,`unit_price`,`status`,`parent_order_version_id`,`present_in_latest_snapshot` FROM `up-data-intelligence-dev.up_core.order_items` WHERE store_id=@store AND source_system='upzero' AND order_created_at>=TIMESTAMP(@date_from,@timezone) AND order_created_at<TIMESTAMP(@date_to,@timezone)),
core_analytics_events AS (SELECT `store_id`,`source_system`,`fact_id`,`session_id`,`event_name`,`occurred_at` FROM `up-data-intelligence-dev.up_core.analytics_events` WHERE store_id=@store AND source_system='upzero' AND occurred_at>=TIMESTAMP(@date_from,@timezone) AND occurred_at<TIMESTAMP(@date_to,@timezone)),
source_orders AS (SELECT order_id, customer_id, order_status, payment_status, requested_total, fulfilled_total,
       requested_items_qty, fulfilled_items_qty, created_at, version_id
FROM core_orders
WHERE store_id = @store AND source_system = 'upzero'
  AND created_at >= @history_from AND created_at < @as_of),
source_customers AS (SELECT customer_id, customer_type FROM core_customers
WHERE store_id = @store AND source_system = 'upzero'),
commerce AS (SELECT o.*, c.customer_id AS resolved_customer_id, c.customer_type,
       DATE(created_at, @timezone) AS order_date,
       order_status IN UNNEST(@purchase_statuses) AS is_purchase
FROM source_orders o LEFT JOIN source_customers c USING (customer_id)),
purchase_sequence AS (SELECT @store AS store_id, resolved_customer_id AS customer_id, customer_type, order_id,
       version_id AS source_order_version_id, created_at AS order_at, order_date,
       ROW_NUMBER() OVER w AS purchase_number,
       FIRST_VALUE(created_at) OVER w AS first_purchase_at,
       FIRST_VALUE(order_date) OVER w AS first_purchase_date,
       requested_total AS revenue_generated, fulfilled_total AS revenue_fulfilled,
       CAST(NULL AS NUMERIC) AS revenue_paid
FROM commerce WHERE is_purchase AND resolved_customer_id IS NOT NULL
WINDOW w AS (PARTITION BY resolved_customer_id ORDER BY created_at, order_id
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)),
customer_metrics AS (SELECT customer_id, ANY_VALUE(customer_type) AS customer_type,
 MIN(first_purchase_at) AS first_purchase_at, MIN(first_purchase_date) AS first_purchase_date,
 MAX(IF(purchase_number=2,order_at,NULL)) AS second_purchase_at,
 MAX(IF(purchase_number=3,order_at,NULL)) AS third_purchase_at,
 MAX(IF(purchase_number=4,order_at,NULL)) AS fourth_purchase_at,
 COUNT(*) AS purchases,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,SUM(revenue_generated)) AS ltv_lifetime_observed,
 ARRAY_AGG(STRUCT(order_at,revenue_generated) ORDER BY order_at,order_id) AS observed_orders
FROM purchase_sequence GROUP BY customer_id),
cohort_population AS (SELECT DATE_TRUNC(first_purchase_date,MONTH) AS cohort_month, COUNT(*) AS customers_in_cohort
FROM customer_metrics GROUP BY cohort_month),
business AS (
WITH totals AS (
 SELECT order_date, COUNT(*) AS orders_generated, COUNTIF(payment_status='paid') AS orders_paid,
   COUNTIF(order_status='CANCELED') AS orders_cancelled, COUNTIF(is_purchase) AS approved_orders,
   IF(COUNTIF(requested_total IS NULL)>0,NULL,SUM(requested_total)) AS revenue_generated,
   IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,SUM(fulfilled_total)) AS revenue_fulfilled,
   IF(COUNTIF(order_status='CANCELED' AND requested_total IS NULL)>0,NULL,
      SUM(IF(order_status='CANCELED',requested_total,0))) AS revenue_cancelled,
   IF(COUNTIF(requested_items_qty IS NULL)>0,NULL,SUM(requested_items_qty)) AS requested_qty,
   IF(COUNTIF(fulfilled_items_qty IS NULL)>0,NULL,SUM(fulfilled_items_qty)) AS fulfilled_qty,
   COUNTIF(resolved_customer_id IS NULL) AS orders_without_customer
 FROM commerce WHERE order_date >= @date_from AND order_date < @date_to GROUP BY order_date
), customers AS (
 SELECT order_date, COUNT(DISTINCT customer_id) AS purchasing_customers,
   COUNT(DISTINCT IF(first_purchase_date=order_date,customer_id,NULL)) AS new_customers,
   COUNT(DISTINCT IF(first_purchase_date<order_date,customer_id,NULL)) AS returning_customers
 FROM purchase_sequence WHERE order_date >= @date_from AND order_date < @date_to GROUP BY order_date
), calendar AS (
 SELECT day FROM UNNEST(GENERATE_DATE_ARRAY(@date_from, DATE_SUB(@date_to, INTERVAL 1 DAY))) day
)
SELECT @store AS store_id, day AS order_date, @currency AS currency,
 COALESCE(t.orders_generated,0) AS orders_generated, COALESCE(t.approved_orders,0) AS approved_orders, COALESCE(t.orders_paid,0) AS orders_paid,
 COALESCE(t.orders_cancelled,0) AS orders_cancelled,
 IF(t.orders_generated IS NULL,0,t.revenue_generated) AS revenue_generated,
 IF(t.orders_generated IS NULL,0,t.revenue_fulfilled) AS revenue_fulfilled,
 CAST(NULL AS NUMERIC) AS revenue_paid, CAST(NULL AS DATE) AS payment_date,
 IF(t.orders_generated IS NULL,0,t.revenue_cancelled) AS revenue_cancelled,
 IF(t.orders_generated IS NULL,0,IF(t.revenue_generated >= t.revenue_fulfilled,t.revenue_generated-t.revenue_fulfilled,NULL)) AS revenue_unfulfilled,
 SAFE_DIVIDE(t.approved_orders,t.orders_generated) AS approval_rate,
 SAFE_DIVIDE(t.revenue_generated,t.orders_generated) AS average_order_value_generated,
 CAST(NULL AS NUMERIC) AS average_order_value_paid,
 SAFE_DIVIDE(t.requested_qty,t.orders_generated) AS items_per_order_generated,
 SAFE_DIVIDE(t.fulfilled_qty,t.orders_generated) AS items_per_order_fulfilled,
 IF(@history_complete,COALESCE(c.new_customers,0),NULL) AS new_customers,
 COALESCE(c.returning_customers,0) AS returning_customers,
 COALESCE(c.purchasing_customers,0) AS purchasing_customers,
 COALESCE(t.orders_without_customer,0) AS orders_without_customer,
 CAST(NULL AS NUMERIC) AS meta_spend, CAST(NULL AS NUMERIC) AS new_customer_cac,
 CAST(NULL AS NUMERIC) AS roas_generated, CAST(NULL AS NUMERIC) AS roas_paid
FROM calendar LEFT JOIN totals t ON day=t.order_date LEFT JOIN customers c ON day=c.order_date
)
SELECT
 CAST(LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(@store,@policy_hash,'daily',CAST(b.order_date AS STRING)))))) AS STRING) AS `row_key`,
 CAST(@store AS STRING) AS `store_id`,
 CAST(@currency AS STRING) AS `currency`,
 CAST(@timezone AS STRING) AS `reporting_timezone`,
 CAST(@policy_hash AS STRING) AS `policy_hash`,
 CAST('1.0.0' AS STRING) AS `analytics_version`,
 CAST(@as_of AS TIMESTAMP) AS `calculated_at`,
 CAST(@history_complete AS BOOL) AS `history_complete`,
 CAST(b.order_date AS DATE) AS `order_date`,
 CAST(b.payment_date AS DATE) AS `payment_date`,
 CAST(b.orders_generated AS INT64) AS `orders_generated`,
 CAST(b.orders_paid AS INT64) AS `orders_paid`,
 CAST(b.orders_cancelled AS INT64) AS `orders_cancelled`,
 CAST(b.approved_orders AS INT64) AS `approved_orders`,
 CAST(b.new_customers AS INT64) AS `new_customers`,
 CAST(b.returning_customers AS INT64) AS `returning_customers`,
 CAST(b.purchasing_customers AS INT64) AS `purchasing_customers`,
 CAST(b.orders_without_customer AS INT64) AS `orders_without_customer`,
 CAST(NULL AS INT64) AS `meta_impressions`,
 CAST(NULL AS INT64) AS `meta_clicks`,
 CAST(NULL AS INT64) AS `first_party_new_customers_attributed`,
 CAST(NULL AS INT64) AS `first_party_orders_attributed`,
 CAST(b.revenue_generated AS NUMERIC) AS `revenue_generated`,
 CAST(b.revenue_fulfilled AS NUMERIC) AS `revenue_fulfilled`,
 CAST(b.revenue_paid AS NUMERIC) AS `revenue_paid`,
 CAST(b.revenue_cancelled AS NUMERIC) AS `revenue_cancelled`,
 CAST(b.revenue_unfulfilled AS NUMERIC) AS `revenue_unfulfilled`,
 CAST(b.approval_rate AS NUMERIC) AS `approval_rate`,
 CAST(b.average_order_value_generated AS NUMERIC) AS `average_order_value_generated`,
 CAST(b.average_order_value_paid AS NUMERIC) AS `average_order_value_paid`,
 CAST(b.items_per_order_generated AS NUMERIC) AS `items_per_order_generated`,
 CAST(b.items_per_order_fulfilled AS NUMERIC) AS `items_per_order_fulfilled`,
 CAST(b.meta_spend AS NUMERIC) AS `meta_spend`,
 CAST(NULL AS NUMERIC) AS `meta_reported_purchases`,
 CAST(NULL AS NUMERIC) AS `meta_reported_purchase_value`,
 CAST(NULL AS NUMERIC) AS `first_party_revenue_generated_attributed`,
 CAST(NULL AS NUMERIC) AS `first_party_revenue_paid_attributed`,
 CAST(b.new_customer_cac AS NUMERIC) AS `new_customer_cac`,
 CAST(b.roas_generated AS NUMERIC) AS `roas_generated`,
 CAST(b.roas_paid AS NUMERIC) AS `roas_paid`,
 CAST(@history_complete AS BOOL) AS `observation_complete`
FROM business b
