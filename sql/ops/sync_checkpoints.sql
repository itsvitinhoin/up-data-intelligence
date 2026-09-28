CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.sync_checkpoints` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `resource` STRING,
  `connection_id` STRING,
  `plan_key` STRING,
  `run_id` STRING,
  `status` STRING,
  `pending_raw_id` STRING,
  `mode` STRING,
  `filters` JSON,
  `position` JSON,
  `updated_at` TIMESTAMP,
  `completed_to` TIMESTAMP,
  `high_id` STRING
)
CLUSTER BY store_id;
