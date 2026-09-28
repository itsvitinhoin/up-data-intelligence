CREATE TABLE IF NOT EXISTS `${project_id}.up_core.order_items` (
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
  `order_id` STRING,
  `item_id` STRING,
  `variant_id` STRING,
  `asset_id` STRING,
  `asset_name` STRING,
  `asset_image_url` STRING,
  `image_url` STRING,
  `sku` STRING,
  `status` STRING,
  `parent_order_version_id` STRING,
  `qty` NUMERIC,
  `original_qty` INT64,
  `unit_price` NUMERIC,
  `order_created_at` TIMESTAMP,
  `present_in_latest_snapshot` BOOL
)
PARTITION BY DATE(order_created_at)
CLUSTER BY store_id, order_id;
