CREATE TABLE IF NOT EXISTS `${project_id}.up_raw.upzero_customers` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `source_system` STRING,
  `resource` STRING,
  `source_connection_id` STRING,
  `run_id` STRING,
  `request_id` STRING,
  `raw_record_id` STRING,
  `payload_hash` STRING,
  `connector_version` STRING,
  `spec_version` STRING,
  `spec_sha256` STRING,
  `sanitization_version` STRING,
  `ingested_at` TIMESTAMP,
  `position` JSON,
  `next_position` JSON,
  `request_filters` JSON,
  `payload` JSON,
  `bytes_read` INT64,
  `pagination_error` STRING
)
PARTITION BY DATE(ingested_at)
CLUSTER BY store_id, resource;
