CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.integration_operations` (
  `row_key` STRING NOT NULL,
  `operation_id` STRING NOT NULL,
  `tenant_id` STRING NOT NULL,
  `workspace_operation_id` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `provider` STRING NOT NULL,
  `action` STRING NOT NULL,
  `admin_subject_hash` STRING NOT NULL,
  `request_hash` STRING NOT NULL,
  `status` STRING NOT NULL,
  `current_step` STRING NOT NULL,
  `candidate_reference` STRING,
  `error_code` STRING,
  `registry_revision` INT64 NOT NULL,
  `revision` INT64 NOT NULL,
  `source_snapshot` JSON NOT NULL,
  `version_baseline` JSON,
  `created_at` TIMESTAMP NOT NULL,
  `updated_at` TIMESTAMP NOT NULL,
  `completed_at` TIMESTAMP
)
PARTITION BY DATE(created_at)
CLUSTER BY store_id, provider, status;
