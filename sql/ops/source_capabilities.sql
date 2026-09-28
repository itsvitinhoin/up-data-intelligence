CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.source_capabilities` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `connection_id` STRING,
  `purchase_order_id_effective_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
CLUSTER BY store_id;
