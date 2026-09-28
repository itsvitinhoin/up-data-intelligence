CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.quality_results` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `run_id` STRING,
  `resource` STRING,
  `rule_id` STRING,
  `severity` STRING,
  `record_id` STRING,
  `failed_count` INT64,
  `checked_count` INT64,
  `checked_at` TIMESTAMP
)
PARTITION BY DATE(checked_at)
CLUSTER BY store_id, rule_id;
