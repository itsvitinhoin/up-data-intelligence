-- PROPOSTA; NÃO EXECUTADA. Não incluída no Terraform ativo.
CREATE TABLE IF NOT EXISTS `${project_id}.up_analytics.analytics_cohorts` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `currency` STRING,
  `reporting_timezone` STRING,
  `policy_hash` STRING,
  `analytics_version` STRING,
  `calculated_at` TIMESTAMP,
  `history_complete` BOOL,
  `cohort_month` DATE,
  `reporting_month` DATE,
  `months_since_first_purchase` INT64,
  `customers_in_cohort` INT64,
  `active_customers` INT64,
  `orders` INT64,
  `retention_rate` NUMERIC,
  `observed_retention_rate` NUMERIC,
  `revenue_generated` NUMERIC,
  `revenue_paid` NUMERIC,
  `period_complete` BOOL
)
PARTITION BY cohort_month
CLUSTER BY store_id, months_since_first_purchase, policy_hash;
