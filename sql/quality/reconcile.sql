-- Tenant scope is a bound parameter, never interpolated from CLI input.
MERGE `${project_id}.up_core.event_order_links` L
USING (
  SELECT E.row_key, E.store_id, E.fact_id, E.order_id, E.version_id,
    CASE WHEN E.order_id IS NULL THEN 'missing_order_id'
         WHEN O.order_id IS NOT NULL THEN 'matched' ELSE 'pending' END link_status
  FROM `${project_id}.up_core.analytics_events` E
  LEFT JOIN `${project_id}.up_core.orders` O
    ON E.store_id=O.store_id AND E.order_id=O.order_id
  WHERE E.store_id=@store
) S ON L.store_id=S.store_id AND L.row_key=S.row_key
WHEN MATCHED THEN UPDATE SET order_id=S.order_id, source_version_id=S.version_id,
 link_status=S.link_status, updated_at=CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (row_key,store_id,fact_id,order_id,source_version_id,link_status,updated_at)
 VALUES(S.row_key,S.store_id,S.fact_id,S.order_id,S.version_id,S.link_status,CURRENT_TIMESTAMP());
SELECT 'order_id_without_order' rule_id, COUNTIF(link_status='pending') failed_count,
 COUNTIF(order_id IS NOT NULL) checked_count FROM `${project_id}.up_core.event_order_links` WHERE store_id=@store
UNION ALL
SELECT 'duplicate_facts', COUNT(*)-COUNT(DISTINCT fact_id), COUNT(*) FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store
UNION ALL
SELECT 'duplicate_orders', COUNT(*)-COUNT(DISTINCT order_id), COUNT(*) FROM `${project_id}.up_core.orders` WHERE store_id=@store
UNION ALL
SELECT 'duplicate_customers', COUNT(*)-COUNT(DISTINCT customer_id), COUNT(*) FROM `${project_id}.up_core.customers` WHERE store_id=@store
UNION ALL
SELECT 'purchase_without_order_id_before_effective', COUNTIF(order_id IS NULL), COUNT(*) FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store AND event_name='purchase' AND (@effective IS NULL OR occurred_at < @effective)
UNION ALL
SELECT 'purchase_without_order_id_after_effective', COUNTIF(order_id IS NULL), COUNT(*) FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store AND event_name='purchase' AND (@effective IS NOT NULL AND occurred_at >= @effective)
UNION ALL
SELECT 'purchase_item_without_order_id_before_effective', COUNTIF(order_id IS NULL), COUNT(*) FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store AND event_name='purchase_item' AND (@effective IS NULL OR occurred_at < @effective)
UNION ALL
SELECT 'purchase_item_without_order_id_after_effective', COUNTIF(order_id IS NULL), COUNT(*) FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store AND event_name='purchase_item' AND (@effective IS NOT NULL AND occurred_at >= @effective)
UNION ALL
SELECT 'invalid_meta_parser', COUNTIF(parse_status IN ('invalid_url','invalid_id','placeholder','conflict')), COUNT(*) FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store
UNION ALL
SELECT 'duplicate_event_ids', COALESCE(SUM(n-1),0), COALESCE(SUM(n),0) FROM (SELECT COUNT(*) n FROM `${project_id}.up_core.analytics_events` WHERE store_id=@store GROUP BY event_id HAVING COUNT(*)>1);
