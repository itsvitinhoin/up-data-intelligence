CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.workspace_store_bindings` (
  `row_key` STRING NOT NULL,
  `tenant_id` STRING NOT NULL,
  `brand_id` STRING NOT NULL,
  `workspace_operation_id` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `operation` STRING NOT NULL,
  `status` STRING,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP
)
CLUSTER BY tenant_id, workspace_operation_id, store_id;
