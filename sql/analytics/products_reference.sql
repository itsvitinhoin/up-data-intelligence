-- BIGQUERY SELECT, NÃO EXECUTADO. @store, @timezone, @date_from/@date_to exclusivos.
-- Item grain stays variant/asset/SKU; product_id is NOT inferred from asset_id.
-- Validate duplicate item/order IDs and parent version consistency before materializing.
ASSERT NOT EXISTS(
 SELECT order_id FROM `${project_id}.up_core.orders`
 WHERE store_id=@store AND source_system='upzero'
   AND created_at>=TIMESTAMP(@date_from,@timezone) AND created_at<TIMESTAMP(@date_to,@timezone)
 GROUP BY order_id HAVING COUNT(*)>1) AS 'duplicate_order';
ASSERT NOT EXISTS(
 SELECT customer_id FROM `${project_id}.up_core.customers`
 WHERE store_id=@store AND source_system='upzero'
 GROUP BY customer_id HAVING COUNT(*)>1) AS 'duplicate_customer';
ASSERT NOT EXISTS(
 SELECT order_id,item_id FROM `${project_id}.up_core.order_items`
 WHERE store_id=@store AND source_system='upzero'
   AND order_created_at>=TIMESTAMP(@date_from,@timezone) AND order_created_at<TIMESTAMP(@date_to,@timezone)
 GROUP BY order_id,item_id HAVING COUNT(*)>1) AS 'duplicate_order_item';
ASSERT NOT EXISTS(
 SELECT 1 FROM `${project_id}.up_core.order_items`
 WHERE store_id=@store AND source_system='upzero'
   AND order_created_at>=TIMESTAMP(@date_from,@timezone) AND order_created_at<TIMESTAMP(@date_to,@timezone)
   AND (original_qty<0 OR qty<0 OR unit_price<0)) AS 'negative_revenue_or_quantity';
WITH lines AS (
 SELECT DATE(i.order_created_at,@timezone) AS order_date, i.order_id, i.item_id,
   i.asset_id,i.variant_id,i.sku,i.original_qty,i.qty,i.unit_price,i.status,c.customer_id
 FROM `${project_id}.up_core.order_items` i
 JOIN `${project_id}.up_core.orders` o ON o.store_id=i.store_id AND o.order_id=i.order_id
   AND o.version_id=i.parent_order_version_id
 LEFT JOIN `${project_id}.up_core.customers` c ON c.store_id=o.store_id AND c.customer_id=o.customer_id
   AND c.source_system='upzero'
 WHERE i.store_id=@store AND i.source_system='upzero' AND o.source_system='upzero'
   AND i.order_created_at>=TIMESTAMP(@date_from,@timezone) AND i.order_created_at<TIMESTAMP(@date_to,@timezone)
   AND o.created_at>=TIMESTAMP(@date_from,@timezone) AND o.created_at<TIMESTAMP(@date_to,@timezone)
   AND i.present_in_latest_snapshot AND i.status IN ('active','attended','removed')
), totals AS (
 SELECT order_date,asset_id,variant_id,sku,
   IF(COUNTIF(original_qty IS NULL)>0,NULL,SUM(original_qty)) AS units_requested,
   IF(COUNTIF(status!='removed' AND qty IS NULL)>0,NULL,SUM(IF(status='removed',0,qty))) AS units_fulfilled,
   IF(COUNTIF(original_qty IS NULL OR unit_price IS NULL)>0,NULL,SUM(original_qty*unit_price)) AS revenue_generated,
   IF(COUNTIF(status!='removed' AND (qty IS NULL OR unit_price IS NULL))>0,NULL,
      SUM(IF(status='removed',0,qty*unit_price))) AS revenue_fulfilled,
   IF(COUNTIF(status='removed' AND original_qty IS NULL)>0,NULL,SUM(IF(status='removed',original_qty,0))) AS removed_units,
   COUNT(DISTINCT order_id) AS orders,COUNT(DISTINCT customer_id) AS customers
 FROM lines GROUP BY order_date,asset_id,variant_id,sku
)
SELECT @store AS store_id, *,CAST(NULL AS STRING) AS product_id,CAST(NULL AS STRING) AS reference,
 CAST(NULL AS NUMERIC) AS revenue_paid, 'line_gross_at_current_unit_price' AS revenue_basis,
 SAFE_DIVIDE(revenue_fulfilled,units_fulfilled) AS average_selling_price,
 SAFE_DIVIDE(removed_units,units_requested) AS cancellation_rate,
 CAST(NULL AS NUMERIC) AS spend,CAST(NULL AS INT64) AS impressions,CAST(NULL AS INT64) AS clicks,
 CAST(NULL AS INT64) AS first_party_orders_attributed,CAST(NULL AS NUMERIC) AS first_party_revenue_attributed,
 CAST(NULL AS NUMERIC) AS roas
FROM totals;
