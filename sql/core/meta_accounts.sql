CREATE TABLE IF NOT EXISTS `${project_id}.up_core.meta_accounts` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `source_system` STRING,
  `raw_record_id` STRING,
  `run_id` STRING,
  `observed_at` TIMESTAMP,
  `source_updated_at` TIMESTAMP,
  `payload_hash` STRING,
  `version_id` STRING,
  `transform_version` STRING,
  `account_id` STRING,
  `api_version` STRING,
  `name` STRING,
  `status` STRING,
  `effective_status` STRING,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP,
  `account_status` INT64,
  `currency` STRING,
  `timezone_name` STRING
)
CLUSTER BY store_id, account_id;
