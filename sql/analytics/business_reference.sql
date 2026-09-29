-- BIGQUERY REFERENCE SCRIPT — PREPARADO, NÃO EXECUTADO.
-- Só TEMP TABLEs e SELECTs; não grava datasets. Nenhuma dependência de tabelas Meta.
-- Params: @store STRING, @timezone STRING, @currency STRING, @as_of TIMESTAMP,
-- @history_from TIMESTAMP, @date_from/@date_to DATE (to exclusivo, dias fechados),
-- @purchase_statuses ARRAY<STRING>, @history_complete BOOL, @facts_complete BOOL.
-- Requer snapshot CORE consistente e configuração/cobertura aprovadas.
-- Saídas de negócio; envelope/chaves propostos em src/analytics/schema.py.
-- Não há implantação automática ou promessa de validação remota deste SQL.

ASSERT @date_from < @date_to AND @date_to <= DATE(@as_of, @timezone)
  AS 'only_closed_reporting_days_supported';
ASSERT ARRAY_LENGTH(@purchase_statuses) > 0
  AND NOT EXISTS(SELECT 1 FROM UNNEST(@purchase_statuses) s
    WHERE s NOT IN ('RESERVED','CONFIRMED','PROCESSING','INVOICED','SHIPPED'))
  AS 'explicit_purchase_statuses_required';

CREATE TEMP TABLE source_orders AS
SELECT order_id, customer_id, order_status, payment_status, requested_total, fulfilled_total,
       requested_items_qty, fulfilled_items_qty, created_at, version_id
FROM `${project_id}.up_core.orders`
WHERE store_id = @store AND source_system = 'upzero'
  AND created_at >= @history_from AND created_at < @as_of;
CREATE TEMP TABLE source_customers AS
SELECT customer_id, customer_type FROM `${project_id}.up_core.customers`
WHERE store_id = @store AND source_system = 'upzero';
ASSERT NOT EXISTS(SELECT order_id FROM source_orders GROUP BY order_id HAVING COUNT(*) > 1)
  AS 'duplicate_order';
ASSERT NOT EXISTS(SELECT customer_id FROM source_customers GROUP BY customer_id HAVING COUNT(*) > 1)
  AS 'duplicate_customer';
ASSERT NOT EXISTS(SELECT 1 FROM source_orders WHERE requested_total < 0 OR fulfilled_total < 0)
  AS 'negative_revenue';
ASSERT NOT EXISTS(SELECT 1 FROM source_orders
  WHERE order_status NOT IN ('RESERVED','CONFIRMED','PROCESSING','INVOICED','SHIPPED','CANCELED')
    OR payment_status NOT IN ('paid','unpaid','canceled') OR order_status IS NULL OR payment_status IS NULL)
  AS 'unknown_commerce_status';

CREATE TEMP TABLE commerce AS
SELECT o.*, c.customer_id AS resolved_customer_id, c.customer_type,
       DATE(created_at, @timezone) AS order_date,
       order_status IN UNNEST(@purchase_statuses) AS is_purchase
FROM source_orders o LEFT JOIN source_customers c USING (customer_id);

CREATE TEMP TABLE purchase_sequence AS
SELECT @store AS store_id, resolved_customer_id AS customer_id, customer_type, order_id,
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
                          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);

-- analytics_customer_purchase_sequence: all observed history, not only report interval.
SELECT *, IF(purchase_number > 1, 'returning_customer',
             IF(@history_complete, 'new_customer', 'first_observed')) AS customer_classification
FROM purchase_sequence;

-- analytics_store_daily: strict NULL propagation, all created orders including cancelled.
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
 COALESCE(t.orders_generated,0) AS orders_generated, COALESCE(t.orders_paid,0) AS orders_paid,
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
FROM calendar LEFT JOIN totals t ON day=t.order_date LEFT JOIN customers c ON day=c.order_date;

-- analytics_customer_metrics. LTV origin is FIRST OBSERVED qualifying order.
-- Windows are exact elapsed 24h days [first, first+N); immature windows are NULL.
CREATE TEMP TABLE customer_metrics AS
SELECT customer_id, ANY_VALUE(customer_type) AS customer_type,
 MIN(first_purchase_at) AS first_purchase_at, MIN(first_purchase_date) AS first_purchase_date,
 MAX(IF(purchase_number=2,order_at,NULL)) AS second_purchase_at,
 MAX(IF(purchase_number=3,order_at,NULL)) AS third_purchase_at,
 MAX(IF(purchase_number=4,order_at,NULL)) AS fourth_purchase_at,
 COUNT(*) AS purchases,
 IF(COUNTIF(revenue_generated IS NULL)>0,NULL,SUM(revenue_generated)) AS ltv_lifetime_observed,
 ARRAY_AGG(STRUCT(order_at,revenue_generated) ORDER BY order_at,order_id) AS observed_orders
FROM purchase_sequence GROUP BY customer_id;
SELECT @store AS store_id, * EXCEPT(observed_orders),
 TIMESTAMP_DIFF(second_purchase_at,first_purchase_at,MICROSECOND)/86400000000.0 AS days_first_to_second,
 TIMESTAMP_DIFF(third_purchase_at,second_purchase_at,MICROSECOND)/86400000000.0 AS days_second_to_third,
 TIMESTAMP_DIFF(fourth_purchase_at,third_purchase_at,MICROSECOND)/86400000000.0 AS days_third_to_fourth,
 CAST(NULL AS NUMERIC) AS ltv_paid
FROM customer_metrics;
-- Long-form LTV projection, to pivot into proposed ltv_30d/... columns.
SELECT @store AS store_id, customer_id, days AS window_days,
 IF(TIMESTAMP_ADD(first_purchase_at, INTERVAL days DAY) <= @as_of,
   (SELECT IF(COUNTIF(o.revenue_generated IS NULL)>0,NULL,SUM(o.revenue_generated))
    FROM UNNEST(observed_orders) o WHERE o.order_at < TIMESTAMP_ADD(first_purchase_at,INTERVAL days DAY)),NULL) AS ltv,
 @history_complete AND TIMESTAMP_ADD(first_purchase_at,INTERVAL days DAY) <= @as_of AS window_complete
FROM customer_metrics CROSS JOIN UNNEST([30,60,90,180,365]) days;

-- analytics_cohorts: calendar month difference, bounded cohort x observed months.
CREATE TEMP TABLE cohort_population AS
SELECT DATE_TRUNC(first_purchase_date,MONTH) AS cohort_month, COUNT(*) AS customers_in_cohort
FROM customer_metrics GROUP BY cohort_month;
WITH activity AS (
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
FROM spine s LEFT JOIN activity a USING(cohort_month,reporting_month);

-- analytics_purchase_distribution: cumulative reached, buckets are NOT additive customers.
WITH ranked AS (
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
LEFT JOIN ranked r ON r.cohort_month=p.cohort_month AND r.bucket=b;

-- Period metrics: active customer population and previous equal-length LOCAL date interval.
WITH current_customers AS (
 SELECT DISTINCT customer_id FROM purchase_sequence WHERE order_date>=@date_from AND order_date<@date_to
), previous_customers AS (
 SELECT DISTINCT customer_id FROM purchase_sequence
 WHERE order_date>=DATE_SUB(@date_from,INTERVAL DATE_DIFF(@date_to,@date_from,DAY) DAY) AND order_date<@date_from
), repeat_customers AS (
 SELECT customer_id FROM purchase_sequence WHERE order_date<@date_to GROUP BY customer_id HAVING COUNT(*)>=2
)
SELECT SAFE_DIVIDE((SELECT COUNT(*) FROM purchase_sequence WHERE order_date>=@date_from AND order_date<@date_to),
                  (SELECT COUNT(*) FROM current_customers)) AS purchase_frequency,
 IF(@history_complete,SAFE_DIVIDE((SELECT COUNT(*) FROM current_customers JOIN repeat_customers USING(customer_id)),
                  (SELECT COUNT(*) FROM current_customers)),NULL) AS customer_repurchase_rate,
 IF(@history_complete,SAFE_DIVIDE((SELECT COUNT(*) FROM current_customers JOIN previous_customers USING(customer_id)),
                  (SELECT COUNT(*) FROM previous_customers)),NULL) AS customer_retention_rate;
