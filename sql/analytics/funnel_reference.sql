-- BIGQUERY REFERENCE SCRIPT, NÃO EXECUTADO.
-- Params @store,@timezone,@date_from/@date_to (to exclusivo),@facts_complete BOOL.
-- Session grain = store + LOCAL event_date + session_id. Cross-midnight sessions are split.
CREATE TEMP TABLE events AS
SELECT fact_id,session_id,event_name,occurred_at,DATE(occurred_at,@timezone) AS event_date
FROM `${project_id}.up_core.analytics_events`
WHERE store_id=@store AND source_system='upzero'
 AND occurred_at>=TIMESTAMP(@date_from,@timezone) AND occurred_at<TIMESTAMP(@date_to,@timezone);
ASSERT NOT EXISTS(SELECT fact_id FROM events GROUP BY fact_id HAVING COUNT(*)>1) AS 'duplicate_fact';
CREATE TEMP TABLE ordered_events AS
SELECT *,ROW_NUMBER() OVER(PARTITION BY event_date,session_id ORDER BY occurred_at,fact_id) AS event_rank
FROM events WHERE session_id IS NOT NULL AND TRIM(session_id)!='';
WITH carts AS (
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
SELECT @store AS store_id,s.event_date,COALESCE(c.sessions,0) AS sessions,
 COALESCE(e.product_views,0) AS product_views,COALESCE(e.add_to_cart,0) AS add_to_cart,
 COALESCE(e.checkout_started,0) AS checkout_started,COALESCE(e.purchase,0) AS purchase,
 COALESCE(e.events_without_session,0) AS events_without_session,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_with_cart,c.sessions),NULL) AS session_to_cart_rate,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_cart_then_checkout,c.sessions_with_cart),NULL) AS cart_to_checkout_rate,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_cart_checkout_purchase,c.sessions_cart_then_checkout),NULL) AS checkout_to_purchase_rate,
 IF(@facts_complete,SAFE_DIVIDE(c.sessions_with_purchase,c.sessions),NULL) AS session_conversion_rate,
 CAST(NULL AS NUMERIC) AS cost_per_session,CAST(NULL AS NUMERIC) AS cost_per_add_to_cart,CAST(NULL AS NUMERIC) AS cost_per_checkout
FROM spine s LEFT JOIN session_counts c USING(event_date) LEFT JOIN event_counts e USING(event_date);
