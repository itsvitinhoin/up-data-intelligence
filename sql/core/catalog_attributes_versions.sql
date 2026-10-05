CREATE TABLE IF NOT EXISTS `${project_id}.up_core.catalog_attributes_versions` (
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
  `attribute_id` STRING,
  `code` STRING,
  `name` STRING,
  `terms` JSON
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, attribute_id;
