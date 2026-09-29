-- PROPOSTA; NÃO EXECUTADA. Não incluída no Terraform ativo.
CREATE TABLE IF NOT EXISTS `${project_id}.up_analytics.analytics_customer_purchase_sequence` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `currency` STRING,
  `reporting_timezone` STRING,
  `policy_hash` STRING,
  `analytics_version` STRING,
  `calculated_at` TIMESTAMP,
  `history_complete` BOOL,
  `customer_id` STRING,
  `customer_type` STRING,
  `order_id` STRING,
  `source_order_version_id` STRING,
  `customer_classification` STRING,
  `order_at` TIMESTAMP,
  `first_purchase_at` TIMESTAMP,
  `order_date` DATE,
  `first_purchase_date` DATE,
  `purchase_number` INT64,
  `revenue_generated` NUMERIC,
  `revenue_fulfilled` NUMERIC,
  `revenue_paid` NUMERIC
)
PARTITION BY order_date
CLUSTER BY store_id, customer_id, policy_hash;
