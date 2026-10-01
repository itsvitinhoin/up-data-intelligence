CREATE TABLE IF NOT EXISTS `${project_id}.up_core.meta_live_accounts` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `account_id` STRING,
  `api_version` STRING,
  `contract_version` STRING,
  `observed_at` TIMESTAMP,
  `source_updated_at` TIMESTAMP,
  `meta_account_id` STRING,
  `account_name` STRING,
  `currency` STRING,
  `timezone` STRING,
  `status` STRING,
  `created_time` TIMESTAMP,
  `updated_time` TIMESTAMP,
  `version_id` STRING,
  `payload_hash` STRING,
  `source_system` STRING
)
CLUSTER BY store_id, account_id;
