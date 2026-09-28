-- PREPARED ONLY. Run in DEV only after reviewing additive schema migration.
-- No UPDATE/DELETE of existing data; historical columns remain nullable.
-- Do not deploy the metrics-v2 writer before these columns exist.
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `metrics_version` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `source_records_read` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `source_bytes_read` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `raw_pages_written` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `raw_payload_bytes` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `core_records_processed` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `core_records_inserted` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `core_records_updated` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `core_records_failed` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `core_pages_processed` INT64;
ALTER TABLE `up-data-intelligence-dev.up_ops.sync_runs` ADD COLUMN IF NOT EXISTS `replay_records_read` INT64;
