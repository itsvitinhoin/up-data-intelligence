CREATE TABLE IF NOT EXISTS `${project_id}.up_core.catalog_products` (
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
  `product_id` STRING,
  `code` STRING,
  `name` STRING,
  `status` STRING,
  `category_ids` JSON,
  `category_names` JSON,
  `product_category_ids` JSON,
  `product_category_names` JSON,
  `external_ref` JSON,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
CLUSTER BY store_id, product_id;
