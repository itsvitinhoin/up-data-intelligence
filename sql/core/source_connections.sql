CREATE TABLE IF NOT EXISTS `${project_id}.up_core.source_connections` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `connection_id` STRING,
  `source_system` STRING,
  `secret_resource_name` STRING,
  `status` STRING,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
CLUSTER BY store_id;
