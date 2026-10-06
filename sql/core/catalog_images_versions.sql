CREATE TABLE IF NOT EXISTS `${project_id}.up_core.catalog_images_versions` (
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
  `image_id` STRING,
  `product_id` STRING,
  `image_url` STRING,
  `combination_key` STRING,
  `display_order` INT64,
  `is_primary` BOOL,
  `variant_ids` JSON,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, image_id;
