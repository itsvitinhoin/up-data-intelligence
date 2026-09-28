CREATE TABLE IF NOT EXISTS `${project_id}.up_core.stores` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `store_name` STRING,
  `store_slug` STRING,
  `status` STRING,
  `upzero_store_identifier` STRING,
  `timezone` STRING,
  `meta_ad_account_id` STRING,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
CLUSTER BY store_id;
