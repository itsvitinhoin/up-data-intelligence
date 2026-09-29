-- READ ONLY; prepared, not executed. Aggregates only, no customer/order IDs.
WITH checks AS (
SELECT 'analytics_store_daily.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_store_daily.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,order_date FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` GROUP BY store_id,policy_hash,order_date HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_store_daily.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_store_daily.paid_must_be_null' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` WHERE average_order_value_paid IS NOT NULL OR first_party_revenue_paid_attributed IS NOT NULL OR revenue_paid IS NOT NULL OR roas_paid IS NOT NULL) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_store_daily.local_days' AS check_name, (SELECT COUNT(DISTINCT order_date) FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` WHERE store_id=@store AND policy_hash=@policy AND order_date>=DATE '2026-09-01' AND order_date<DATE '2026-09-28') AS actual, 27 AS expected
UNION ALL
SELECT 'analytics_store_daily.rows' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` WHERE store_id=@store AND policy_hash=@policy) AS actual, 27 AS expected
UNION ALL
SELECT 'analytics_store_daily.coverage_flag' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_store_daily` WHERE history_complete IS DISTINCT FROM FALSE OR observation_complete IS DISTINCT FROM FALSE) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_metrics.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_customer_metrics` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_metrics.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,customer_id FROM `up-data-intelligence-dev.up_analytics.analytics_customer_metrics` GROUP BY store_id,policy_hash,customer_id HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_metrics.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_customer_metrics` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_metrics.paid_must_be_null' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_customer_metrics` WHERE ltv_paid IS NOT NULL) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_purchase_sequence.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_customer_purchase_sequence` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_purchase_sequence.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,order_id FROM `up-data-intelligence-dev.up_analytics.analytics_customer_purchase_sequence` GROUP BY store_id,policy_hash,order_id HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_purchase_sequence.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_customer_purchase_sequence` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_customer_purchase_sequence.paid_must_be_null' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_customer_purchase_sequence` WHERE revenue_paid IS NOT NULL) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_cohorts.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_cohorts` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_cohorts.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,cohort_month,months_since_first_purchase FROM `up-data-intelligence-dev.up_analytics.analytics_cohorts` GROUP BY store_id,policy_hash,cohort_month,months_since_first_purchase HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_cohorts.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_cohorts` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_cohorts.paid_must_be_null' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_cohorts` WHERE revenue_paid IS NOT NULL) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_purchase_distribution.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_purchase_distribution` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_purchase_distribution.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,cohort_month,purchase_bucket FROM `up-data-intelligence-dev.up_analytics.analytics_purchase_distribution` GROUP BY store_id,policy_hash,cohort_month,purchase_bucket HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_purchase_distribution.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_purchase_distribution` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_products_daily.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_products_daily` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_products_daily.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,order_date,product_key FROM `up-data-intelligence-dev.up_analytics.analytics_products_daily` GROUP BY store_id,policy_hash,order_date,product_key HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_products_daily.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_products_daily` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_products_daily.paid_must_be_null' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_products_daily` WHERE revenue_paid IS NOT NULL) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_funnel_daily.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_funnel_daily` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM 'BRL') AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_funnel_daily.duplicate_grain' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,event_date FROM `up-data-intelligence-dev.up_analytics.analytics_funnel_daily` GROUP BY store_id,policy_hash,event_date HAVING COUNT(*)>1)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_funnel_daily.duplicate_row_key' AS check_name, (SELECT COUNT(*) FROM (SELECT store_id,policy_hash,row_key FROM `up-data-intelligence-dev.up_analytics.analytics_funnel_daily` GROUP BY store_id,policy_hash,row_key HAVING COUNT(*)>1 OR row_key IS NULL)) AS actual, 0 AS expected
UNION ALL
SELECT 'analytics_funnel_daily.local_days' AS check_name, (SELECT COUNT(DISTINCT event_date) FROM `up-data-intelligence-dev.up_analytics.analytics_funnel_daily` WHERE store_id=@store AND policy_hash=@policy AND event_date>=DATE '2026-09-01' AND event_date<DATE '2026-09-28') AS actual, 27 AS expected
UNION ALL
SELECT 'analytics_funnel_daily.rows' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_funnel_daily` WHERE store_id=@store AND policy_hash=@policy) AS actual, 27 AS expected
UNION ALL
SELECT 'analytics_funnel_daily.coverage_flag' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_funnel_daily` WHERE history_complete IS DISTINCT FROM FALSE OR observation_complete IS DISTINCT FROM TRUE) AS actual, 0 AS expected
UNION ALL
SELECT 'purchase_sequence.gaps' AS check_name, (SELECT COUNT(*) FROM (SELECT customer_id FROM `up-data-intelligence-dev.up_analytics.analytics_customer_purchase_sequence` WHERE store_id=@store AND policy_hash=@policy GROUP BY customer_id HAVING MIN(purchase_number)!=1 OR MAX(purchase_number)!=COUNT(*) OR COUNT(DISTINCT purchase_number)!=COUNT(*))) AS actual, 0 AS expected
UNION ALL
SELECT 'publications.head_count' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications` WHERE store_id=@store AND policy_hash=@policy AND record_kind='HEAD') AS actual, 1 AS expected
UNION ALL
SELECT 'publications.receipt_count' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications` WHERE store_id=@store AND policy_hash=@policy AND record_kind='RECEIPT') AS actual, 1 AS expected
UNION ALL
SELECT 'publications.head_generation' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications` WHERE store_id=@store AND policy_hash=@policy AND record_kind='HEAD' AND generation=1 AND status='completed') AS actual, 1 AS expected
UNION ALL
SELECT 'publications.receipt_completed' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications` WHERE store_id=@store AND policy_hash=@policy AND record_kind='RECEIPT' AND generation=1 AND status='completed' AND as_of=TIMESTAMP '2026-09-28T03:00:00Z' AND report_from=DATE '2026-09-01' AND report_to=DATE '2026-09-28') AS actual, 1 AS expected
UNION ALL
SELECT 'publications.wrong_scope' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications` WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR record_kind NOT IN ('HEAD','RECEIPT') OR record_kind IS NULL) AS actual, 0 AS expected
UNION ALL
SELECT 'publications.head_receipt_match' AS check_name, (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications` h JOIN `up-data-intelligence-dev.up_analytics.analytics_publications` r ON h.store_id=r.store_id AND h.policy_hash=r.policy_hash AND h.publication_id=r.publication_id AND h.source_watermark=r.source_watermark AND h.generation=r.generation WHERE h.store_id=@store AND h.policy_hash=@policy AND h.record_kind='HEAD' AND r.record_kind='RECEIPT') AS actual, 1 AS expected
)
SELECT check_name,actual,expected,actual=expected AS passed FROM checks ORDER BY check_name;
