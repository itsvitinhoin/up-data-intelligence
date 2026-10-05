CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.installation_extension_plans` (
  `row_key` STRING NOT NULL,
  `plan_id` STRING NOT NULL,
  `onboarding_operation_id` STRING,
  `store_id` STRING NOT NULL,
  `status` STRING NOT NULL,
  `planner_version` STRING NOT NULL,
  `config_hash` STRING NOT NULL,
  `error_code` STRING,
  `revision` INT64 NOT NULL,
  `registry_revision` INT64 NOT NULL,
  `priority` INT64,
  `requested_from` TIMESTAMP NOT NULL,
  `target_as_of` TIMESTAMP NOT NULL,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP,
  `completed_at` TIMESTAMP,
  `adopted_coverage` JSON
)
CLUSTER BY store_id, status;
