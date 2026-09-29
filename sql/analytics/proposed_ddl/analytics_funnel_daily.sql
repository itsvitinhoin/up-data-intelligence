-- PROPOSTA; NÃO EXECUTADA. Não incluída no Terraform ativo.
CREATE TABLE IF NOT EXISTS `${project_id}.up_analytics.analytics_funnel_daily` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `currency` STRING,
  `reporting_timezone` STRING,
  `policy_hash` STRING,
  `analytics_version` STRING,
  `calculated_at` TIMESTAMP,
  `history_complete` BOOL,
  `event_date` DATE,
  `sessions` INT64,
  `product_views` INT64,
  `add_to_cart` INT64,
  `checkout_started` INT64,
  `purchase` INT64,
  `sessions_with_cart` INT64,
  `sessions_cart_then_checkout` INT64,
  `sessions_cart_checkout_purchase` INT64,
  `sessions_with_purchase` INT64,
  `events_without_session` INT64,
  `session_to_cart_rate` NUMERIC,
  `cart_to_checkout_rate` NUMERIC,
  `checkout_to_purchase_rate` NUMERIC,
  `session_conversion_rate` NUMERIC,
  `cost_per_session` NUMERIC,
  `cost_per_add_to_cart` NUMERIC,
  `cost_per_checkout` NUMERIC,
  `observation_complete` BOOL
)
PARTITION BY event_date
CLUSTER BY store_id, policy_hash;
