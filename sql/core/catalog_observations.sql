CREATE TABLE IF NOT EXISTS `${project_id}.up_core.catalog_observations` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `run_id` STRING,
  `resource` STRING,
  `entity_id` STRING,
  `entity_version_id` STRING,
  `raw_record_id` STRING,
  `payload_hash` STRING,
  `observed_at` TIMESTAMP
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, run_id, resource;
