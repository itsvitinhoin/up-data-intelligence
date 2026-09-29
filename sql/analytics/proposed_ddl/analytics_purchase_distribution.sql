-- PROPOSTA; NÃO EXECUTADA. Não incluída no Terraform ativo.
CREATE TABLE IF NOT EXISTS `${project_id}.up_analytics.analytics_purchase_distribution` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `currency` STRING,
  `reporting_timezone` STRING,
  `policy_hash` STRING,
  `analytics_version` STRING,
  `calculated_at` TIMESTAMP,
  `history_complete` BOOL,
  `cohort_month` DATE,
  `purchase_bucket` STRING,
  `revenue_basis` STRING,
  `customers` INT64,
  `original_cohort_customers` INT64,
  `percentage_of_original_cohort` NUMERIC,
  `revenue` NUMERIC
)
PARTITION BY cohort_month
CLUSTER BY store_id, purchase_bucket, policy_hash;
