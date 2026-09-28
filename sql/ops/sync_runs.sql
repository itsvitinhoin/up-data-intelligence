CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.sync_runs` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `run_id` STRING,
  `source` STRING,
  `resource` STRING,
  `status` STRING,
  `error_summary` STRING,
  `plan_key` STRING,
  `mode` STRING,
  `started_at` TIMESTAMP,
  `finished_at` TIMESTAMP,
  `records_read` INT64,
  `records_written` INT64,
  `records_updated` INT64,
  `records_failed` INT64,
  `pages` INT64,
  `retries` INT64,
  `bytes` INT64
)
PARTITION BY DATE(started_at)
CLUSTER BY store_id, resource;
