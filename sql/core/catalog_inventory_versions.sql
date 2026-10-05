CREATE TABLE IF NOT EXISTS `${project_id}.up_core.catalog_inventory_versions` (
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
  `warehouse_id` STRING,
  `qty_total` NUMERIC,
  `qty_reserved` NUMERIC,
  `qty_available` NUMERIC,
  `breakdown` JSON
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, variant_id;
