CREATE TABLE IF NOT EXISTS `${project_id}.up_ops.onboarding_operations` (
  `row_key` STRING NOT NULL,
  `operation_id` STRING NOT NULL,
  `idempotency_key` STRING NOT NULL,
  `admin_subject_hash` STRING NOT NULL,
  `request_hash` STRING NOT NULL,
  `tenant_id` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `status` STRING NOT NULL,
  `current_step` STRING NOT NULL,
  `error_code` STRING,
  `secret_version_name` STRING,
  `revision` INT64 NOT NULL,
  `created_at` TIMESTAMP,
  `updated_at` TIMESTAMP,
  `completed_at` TIMESTAMP
)
CLUSTER BY admin_subject_hash, idempotency_key, store_id;
