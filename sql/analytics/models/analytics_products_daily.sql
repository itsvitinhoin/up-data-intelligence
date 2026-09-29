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
WITH lines AS(
 SELECT DATE(i.order_created_at,@timezone) AS order_date, i.order_id, i.item_id,
   IF((i.variant_id IS NULL OR i.variant_id='') AND (i.sku IS NULL OR i.sku=''),LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(i.asset_id,i.variant_id,i.sku,i.order_id,i.item_id))))),LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(i.asset_id,i.variant_id,i.sku)))))) AS product_key,i.asset_id,i.variant_id,i.sku,i.original_qty,i.qty,i.unit_price,i.status,c.customer_id
 FROM core_order_items i
 JOIN core_orders o ON o.store_id=i.store_id AND o.order_id=i.order_id
   AND o.version_id=i.parent_order_version_id
 LEFT JOIN core_customers c ON c.store_id=o.store_id AND c.customer_id=o.customer_id
   AND c.source_system='upzero'
 WHERE i.store_id=@store AND i.source_system='upzero' AND o.source_system='upzero'
   AND i.order_created_at>=TIMESTAMP(@date_from,@timezone) AND i.order_created_at<TIMESTAMP(@date_to,@timezone)
   AND o.created_at>=TIMESTAMP(@date_from,@timezone) AND o.created_at<TIMESTAMP(@date_to,@timezone)
   AND i.present_in_latest_snapshot AND i.status IN ('active','attended','removed')
), totals AS (
 SELECT order_date,product_key,asset_id,variant_id,sku,
   IF(COUNTIF(original_qty IS NULL)>0,NULL,SUM(original_qty)) AS units_requested,
   IF(COUNTIF(status!='removed' AND qty IS NULL)>0,NULL,SUM(IF(status='removed',0,qty))) AS units_fulfilled,
   IF(COUNTIF(original_qty IS NULL OR unit_price IS NULL)>0,NULL,SUM(original_qty*unit_price)) AS revenue_generated,
   IF(COUNTIF(status!='removed' AND (qty IS NULL OR unit_price IS NULL))>0,NULL,
      SUM(IF(status='removed',0,qty*unit_price))) AS revenue_fulfilled,
   IF(COUNTIF(status='removed' AND original_qty IS NULL)>0,NULL,SUM(IF(status='removed',original_qty,0))) AS removed_units,
   COUNT(DISTINCT order_id) AS orders,COUNT(DISTINCT customer_id) AS customers
 FROM lines GROUP BY order_date,product_key,asset_id,variant_id,sku
)
SELECT @store AS store_id, *,CAST(NULL AS STRING) AS product_id,CAST(NULL AS STRING) AS reference,
 CAST(NULL AS NUMERIC) AS revenue_paid, 'line_gross_at_current_unit_price' AS revenue_basis,
 SAFE_DIVIDE(revenue_fulfilled,units_fulfilled) AS average_selling_price,
 SAFE_DIVIDE(removed_units,units_requested) AS cancellation_rate,
 CAST(NULL AS NUMERIC) AS spend,CAST(NULL AS INT64) AS impressions,CAST(NULL AS INT64) AS clicks,
 CAST(NULL AS INT64) AS first_party_orders_attributed,CAST(NULL AS NUMERIC) AS first_party_revenue_attributed,
 CAST(NULL AS NUMERIC) AS roas
FROM totals
)
SELECT
 CAST(LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(@store,@policy_hash,'product',CAST(b.order_date AS STRING),b.product_key))))) AS STRING) AS `row_key`,
 CAST(@store AS STRING) AS `store_id`,
 CAST(@currency AS STRING) AS `currency`,
 CAST(@timezone AS STRING) AS `reporting_timezone`,
 CAST(@policy_hash AS STRING) AS `policy_hash`,
 CAST('1.0.0' AS STRING) AS `analytics_version`,
 CAST(@as_of AS TIMESTAMP) AS `calculated_at`,
 CAST(@history_complete AS BOOL) AS `history_complete`,
 CAST(b.order_date AS DATE) AS `order_date`,
 CAST(b.product_key AS STRING) AS `product_key`,
 CAST(b.product_id AS STRING) AS `product_id`,
 CAST(b.asset_id AS STRING) AS `asset_id`,
 CAST(b.variant_id AS STRING) AS `variant_id`,
 CAST(b.sku AS STRING) AS `sku`,
 CAST(b.reference AS STRING) AS `reference`,
 CAST(b.revenue_basis AS STRING) AS `revenue_basis`,
 CAST(b.orders AS INT64) AS `orders`,
 CAST(b.customers AS INT64) AS `customers`,
 CAST(b.impressions AS INT64) AS `impressions`,
 CAST(b.clicks AS INT64) AS `clicks`,
 CAST(b.first_party_orders_attributed AS INT64) AS `first_party_orders_attributed`,
 CAST(b.units_requested AS NUMERIC) AS `units_requested`,
 CAST(b.units_fulfilled AS NUMERIC) AS `units_fulfilled`,
 CAST(b.revenue_generated AS NUMERIC) AS `revenue_generated`,
 CAST(b.revenue_fulfilled AS NUMERIC) AS `revenue_fulfilled`,
 CAST(b.revenue_paid AS NUMERIC) AS `revenue_paid`,
 CAST(b.average_selling_price AS NUMERIC) AS `average_selling_price`,
 CAST(b.cancellation_rate AS NUMERIC) AS `cancellation_rate`,
 CAST(b.spend AS NUMERIC) AS `spend`,
 CAST(b.first_party_revenue_attributed AS NUMERIC) AS `first_party_revenue_attributed`,
 CAST(b.roas AS NUMERIC) AS `roas`
FROM business b
