CREATE TABLE IF NOT EXISTS `${project_id}.up_core.event_order_links` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `fact_id` STRING,
  `order_id` STRING,
  `source_version_id` STRING,
  `link_status` STRING,
  `updated_at` TIMESTAMP
)
CLUSTER BY store_id, order_id;
