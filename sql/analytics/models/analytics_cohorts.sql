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
       ROW_NUMBER() OVER purchase_order AS purchase_number,
       FIRST_VALUE(created_at) OVER purchase_first AS first_purchase_at,
       FIRST_VALUE(order_date) OVER purchase_first AS first_purchase_date,
       requested_total AS revenue_generated, fulfilled_total AS revenue_fulfilled,
       CAST(NULL AS NUMERIC) AS revenue_paid
FROM commerce WHERE is_purchase AND resolved_customer_id IS NOT NULL
-- Numbering functions cannot use a frame. Navigation retains its explicit frame.
WINDOW purchase_order AS (PARTITION BY resolved_customer_id ORDER BY created_at, order_id),
       purchase_first AS (PARTITION BY resolved_customer_id ORDER BY created_at, order_id
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
WITH activity AS(
 SELECT DATE_TRUNC(first_purchase_date,MONTH) AS cohort_month, DATE_TRUNC(order_date,MONTH) AS reporting_month,
 COUNT(DISTINCT customer_id) AS active_customers, COUNT(*) AS orders,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,SUM(revenue_generated)) AS revenue_generated
 FROM purchase_sequence GROUP BY cohort_month,reporting_month
), spine AS (
 SELECT p.*, month AS reporting_month FROM cohort_population p,
 UNNEST(GENERATE_DATE_ARRAY(cohort_month,DATE_TRUNC(DATE(@as_of,@timezone),MONTH),INTERVAL 1 MONTH)) month
)
SELECT @store AS store_id, s.cohort_month, s.reporting_month,
 DATE_DIFF(s.reporting_month,s.cohort_month,MONTH) AS months_since_first_purchase,
 s.customers_in_cohort, COALESCE(a.active_customers,0) AS active_customers, COALESCE(a.orders,0) AS orders,
 IF(a.orders IS NULL,0,a.revenue_generated) AS revenue_generated, CAST(NULL AS NUMERIC) AS revenue_paid,
 SAFE_DIVIDE(COALESCE(a.active_customers,0),s.customers_in_cohort) AS observed_retention_rate,
 IF(@history_complete AND DATE_ADD(s.reporting_month,INTERVAL 1 MONTH)<=DATE(@as_of,@timezone),
 SAFE_DIVIDE(COALESCE(a.active_customers,0),s.customers_in_cohort),NULL) AS retention_rate,
 DATE_ADD(s.reporting_month,INTERVAL 1 MONTH)<=DATE(@as_of,@timezone) AS period_complete
FROM spine s LEFT JOIN activity a USING(cohort_month,reporting_month)
)
SELECT
 CAST(LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(@store,@policy_hash,'cohort',EXTRACT(YEAR FROM b.cohort_month)*12+EXTRACT(MONTH FROM b.cohort_month)-1,b.months_since_first_purchase))))) AS STRING) AS `row_key`,
 CAST(@store AS STRING) AS `store_id`,
 CAST(@currency AS STRING) AS `currency`,
 CAST(@timezone AS STRING) AS `reporting_timezone`,
 CAST(@policy_hash AS STRING) AS `policy_hash`,
 CAST('1.0.0' AS STRING) AS `analytics_version`,
 CAST(@as_of AS TIMESTAMP) AS `calculated_at`,
 CAST(@history_complete AS BOOL) AS `history_complete`,
 CAST(b.cohort_month AS DATE) AS `cohort_month`,
 CAST(b.reporting_month AS DATE) AS `reporting_month`,
 CAST(b.months_since_first_purchase AS INT64) AS `months_since_first_purchase`,
 CAST(b.customers_in_cohort AS INT64) AS `customers_in_cohort`,
 CAST(b.active_customers AS INT64) AS `active_customers`,
 CAST(b.orders AS INT64) AS `orders`,
 CAST(b.retention_rate AS NUMERIC) AS `retention_rate`,
 CAST(b.observed_retention_rate AS NUMERIC) AS `observed_retention_rate`,
 CAST(b.revenue_generated AS NUMERIC) AS `revenue_generated`,
 CAST(b.revenue_paid AS NUMERIC) AS `revenue_paid`,
 CAST(b.period_complete AS BOOL) AS `period_complete`
FROM business b
