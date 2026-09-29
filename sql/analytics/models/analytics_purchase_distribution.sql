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
WITH ranked AS(
 SELECT DATE_TRUNC(first_purchase_date,MONTH) AS cohort_month, LEAST(purchase_number,5) AS bucket,
 COUNT(DISTINCT customer_id) AS customers,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,SUM(revenue_generated)) AS revenue
 FROM purchase_sequence GROUP BY cohort_month,bucket
)
SELECT @store AS store_id,p.cohort_month,IF(b=5,'5+',CAST(b AS STRING)) AS purchase_bucket,
 COALESCE(r.customers,0) AS customers,p.customers_in_cohort AS original_cohort_customers,
 SAFE_DIVIDE(COALESCE(r.customers,0),p.customers_in_cohort) AS percentage_of_original_cohort,
 IF(r.customers IS NULL,0,r.revenue) AS revenue
FROM cohort_population p CROSS JOIN UNNEST([1,2,3,4,5]) b
LEFT JOIN ranked r ON r.cohort_month=p.cohort_month AND r.bucket=b
)
SELECT
 CAST(LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(@store,@policy_hash,'distribution',CAST(b.cohort_month AS STRING),IF(b.purchase_bucket='5+',5,CAST(b.purchase_bucket AS INT64))))))) AS STRING) AS `row_key`,
 CAST(@store AS STRING) AS `store_id`,
 CAST(@currency AS STRING) AS `currency`,
 CAST(@timezone AS STRING) AS `reporting_timezone`,
 CAST(@policy_hash AS STRING) AS `policy_hash`,
 CAST('1.0.0' AS STRING) AS `analytics_version`,
 CAST(@as_of AS TIMESTAMP) AS `calculated_at`,
 CAST(@history_complete AS BOOL) AS `history_complete`,
 CAST(b.cohort_month AS DATE) AS `cohort_month`,
 CAST(b.purchase_bucket AS STRING) AS `purchase_bucket`,
 CAST('generated_qualifying_orders' AS STRING) AS `revenue_basis`,
 CAST(b.customers AS INT64) AS `customers`,
 CAST(b.original_cohort_customers AS INT64) AS `original_cohort_customers`,
 CAST(b.percentage_of_original_cohort AS NUMERIC) AS `percentage_of_original_cohort`,
 CAST(b.revenue AS NUMERIC) AS `revenue`
FROM business b
