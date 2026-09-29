-- Prepared single SELECT; NOT validated on BigQuery.
WITH core_orders AS (SELECT `store_id`,`source_system`,`order_id`,`customer_id`,`order_status`,`payment_status`,`requested_total`,`fulfilled_total`,`requested_items_qty`,`fulfilled_items_qty`,`created_at`,`version_id` FROM `up-data-intelligence-dev.up_core.orders` WHERE store_id=@store AND source_system='upzero' AND created_at>=@history_from AND created_at<@as_of),
core_customers AS (SELECT `store_id`,`source_system`,`customer_id`,`customer_type` FROM `up-data-intelligence-dev.up_core.customers` WHERE store_id=@store AND source_system='upzero'),
core_order_items AS (SELECT `store_id`,`source_system`,`order_id`,`item_id`,`order_created_at`,`asset_id`,`variant_id`,`sku`,`original_qty`,`qty`,`unit_price`,`status`,`parent_order_version_id`,`present_in_latest_snapshot` FROM `up-data-intelligence-dev.up_core.order_items` WHERE store_id=@store AND source_system='upzero' AND order_created_at>=TIMESTAMP(@date_from,@timezone) AND order_created_at<TIMESTAMP(@date_to,@timezone)),
core_analytics_events AS (SELECT `store_id`,`source_system`,`fact_id`,`session_id`,`event_name`,`occurred_at` FROM `up-data-intelligence-dev.up_core.analytics_events` WHERE store_id=@store AND source_system='upzero' AND occurred_at>=TIMESTAMP(@date_from,@timezone) AND occurred_at<TIMESTAMP(@date_to,@timezone)),
events AS (SELECT fact_id,session_id,event_name,occurred_at,DATE(occurred_at,@timezone) AS event_date
FROM core_analytics_events
WHERE store_id=@store AND source_system='upzero'
 AND occurred_at>=TIMESTAMP(@date_from,@timezone) AND occurred_at<TIMESTAMP(@date_to,@timezone)),
ordered_events AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_date,session_id ORDER BY occurred_at,fact_id) AS event_rank
FROM events WHERE session_id IS NOT NULL AND TRIM(session_id)!=''),
business AS (
WITH carts AS(
 SELECT event_date,session_id,MIN(IF(event_name='add_to_cart',event_rank,NULL)) AS cart_rank,
 COUNTIF(event_name='purchase')>0 AS any_purchase FROM ordered_events GROUP BY event_date,session_id
), checkouts AS (
 SELECT c.*,MIN(IF(e.event_name='checkout_started' AND e.event_rank>=c.cart_rank,e.event_rank,NULL)) AS checkout_rank
 FROM carts c LEFT JOIN ordered_events e USING(event_date,session_id)
 GROUP BY c.event_date,c.session_id,c.cart_rank,c.any_purchase
), chains AS (
 SELECT c.*,COUNTIF(e.event_name='purchase' AND e.event_rank>=c.checkout_rank)>0 AS chained_purchase
 FROM checkouts c LEFT JOIN ordered_events e USING(event_date,session_id)
 GROUP BY c.event_date,c.session_id,c.cart_rank,c.any_purchase,c.checkout_rank
), session_counts AS (
 SELECT event_date,COUNT(*) AS sessions,COUNTIF(cart_rank IS NOT NULL) AS sessions_with_cart,
 COUNTIF(checkout_rank IS NOT NULL) AS sessions_cart_then_checkout,
 COUNTIF(chained_purchase) AS sessions_cart_checkout_purchase,COUNTIF(any_purchase) AS sessions_with_purchase
 FROM chains GROUP BY event_date
), event_counts AS (
 SELECT event_date,COUNTIF(event_name='product_view') AS product_views,COUNTIF(event_name='add_to_cart') AS add_to_cart,
 COUNTIF(event_name='checkout_started') AS checkout_started,COUNTIF(event_name='purchase') AS purchase,
 COUNTIF(session_id IS NULL OR TRIM(session_id)='') AS events_without_session FROM events GROUP BY event_date
), spine AS (
 SELECT day AS event_date FROM UNNEST(GENERATE_DATE_ARRAY(@date_from,DATE_SUB(@date_to,INTERVAL 1 DAY))) day
)
SELECT @store AS store_id,s.event_date,COALESCE(c.sessions,0) AS sessions,COALESCE(c.sessions_with_cart,0) AS sessions_with_cart,COALESCE(c.sessions_cart_then_checkout,0) AS sessions_cart_then_checkout,COALESCE(c.sessions_cart_checkout_purchase,0) AS sessions_cart_checkout_purchase,COALESCE(c.sessions_with_purchase,0) AS sessions_with_purchase,
 COALESCE(e.product_views,0) AS product_views,COALESCE(e.add_to_cart,0) AS add_to_cart,
 COALESCE(e.checkout_started,0) AS checkout_started,COALESCE(e.purchase,0) AS purchase,
 COALESCE(e.events_without_session,0) AS events_without_session,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_with_cart,c.sessions),NULL) AS session_to_cart_rate,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_cart_then_checkout,c.sessions_with_cart),NULL) AS cart_to_checkout_rate,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_cart_checkout_purchase,c.sessions_cart_then_checkout),NULL) AS checkout_to_purchase_rate,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_with_purchase,c.sessions),NULL) AS session_conversion_rate,
 CAST(NULL AS NUMERIC) AS cost_per_session,CAST(NULL AS NUMERIC) AS cost_per_add_to_cart,CAST(NULL AS NUMERIC) AS cost_per_checkout
FROM spine s LEFT JOIN session_counts c USING(event_date) LEFT JOIN event_counts e USING(event_date)
)
SELECT
 CAST(LOWER(TO_HEX(SHA256(TO_JSON_STRING(JSON_ARRAY(@store,@policy_hash,'funnel',CAST(b.event_date AS STRING)))))) AS STRING) AS `row_key`,
 CAST(@store AS STRING) AS `store_id`,
 CAST(@currency AS STRING) AS `currency`,
 CAST(@timezone AS STRING) AS `reporting_timezone`,
 CAST(@policy_hash AS STRING) AS `policy_hash`,
 CAST('1.0.0' AS STRING) AS `analytics_version`,
 CAST(@as_of AS TIMESTAMP) AS `calculated_at`,
 CAST(@history_complete AS BOOL) AS `history_complete`,
 CAST(b.event_date AS DATE) AS `event_date`,
 CAST(b.sessions AS INT64) AS `sessions`,
 CAST(b.product_views AS INT64) AS `product_views`,
 CAST(b.add_to_cart AS INT64) AS `add_to_cart`,
 CAST(b.checkout_started AS INT64) AS `checkout_started`,
 CAST(b.purchase AS INT64) AS `purchase`,
 CAST(b.sessions_with_cart AS INT64) AS `sessions_with_cart`,
 CAST(b.sessions_cart_then_checkout AS INT64) AS `sessions_cart_then_checkout`,
 CAST(b.sessions_cart_checkout_purchase AS INT64) AS `sessions_cart_checkout_purchase`,
 CAST(b.sessions_with_purchase AS INT64) AS `sessions_with_purchase`,
 CAST(b.events_without_session AS INT64) AS `events_without_session`,
 CAST(b.session_to_cart_rate AS NUMERIC) AS `session_to_cart_rate`,
 CAST(b.cart_to_checkout_rate AS NUMERIC) AS `cart_to_checkout_rate`,
 CAST(b.checkout_to_purchase_rate AS NUMERIC) AS `checkout_to_purchase_rate`,
 CAST(b.session_conversion_rate AS NUMERIC) AS `session_conversion_rate`,
 CAST(b.cost_per_session AS NUMERIC) AS `cost_per_session`,
 CAST(b.cost_per_add_to_cart AS NUMERIC) AS `cost_per_add_to_cart`,
 CAST(b.cost_per_checkout AS NUMERIC) AS `cost_per_checkout`,
 CAST(@facts_complete AS BOOL) AS `observation_complete`
FROM business b
