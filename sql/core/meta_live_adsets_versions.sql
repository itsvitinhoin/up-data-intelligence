CREATE TABLE IF NOT EXISTS `${project_id}.up_core.meta_live_adsets_versions` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `account_id` STRING,
  `api_version` STRING,
  `contract_version` STRING,
  `observed_at` TIMESTAMP,
  `source_updated_at` TIMESTAMP,
  `adset_id` STRING,
  `campaign_id` STRING,
  `adset_name` STRING,
  `optimization_goal` STRING,
  `billing_event` STRING,
  `status` STRING,
  `effective_status` STRING,
  `targeting_summary` JSON,
  `version_id` STRING,
  `payload_hash` STRING,
  `source_system` STRING
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, account_id;
