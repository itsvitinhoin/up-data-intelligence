CREATE TABLE IF NOT EXISTS `${project_id}.up_core.meta_account_bindings` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `account_id` STRING,
  `connection_id` STRING,
  `api_version` STRING,
  `source_timezone` STRING,
  `currency` STRING,
  `configuration_hash` STRING,
  `configured_at` TIMESTAMP
)
CLUSTER BY store_id, account_id;
