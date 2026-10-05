CREATE TABLE IF NOT EXISTS `${project_id}.up_core.catalog_variants_versions` (
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
  `variant_id` STRING,
  `product_id` STRING,
  `sku` STRING,
  `price` NUMERIC,
  `promotional_price` NUMERIC,
  `attributes` JSON,
  `active` BOOL,
  `color` STRING,
  `color_code` STRING,
  `size` STRING,
  `size_code` STRING,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, variant_id;
