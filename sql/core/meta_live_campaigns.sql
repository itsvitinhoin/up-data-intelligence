CREATE TABLE IF NOT EXISTS `${project_id}.up_core.meta_live_campaigns` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `account_id` STRING,
  `api_version` STRING,
  `contract_version` STRING,
  `observed_at` TIMESTAMP,
  `source_updated_at` TIMESTAMP,
  `campaign_id` STRING,
  `campaign_name` STRING,
  `objective` STRING,
  `status` STRING,
  `effective_status` STRING,
  `created_time` TIMESTAMP,
  `updated_time` TIMESTAMP,
  `version_id` STRING,
  `payload_hash` STRING,
  `source_system` STRING
)
CLUSTER BY store_id, account_id;
