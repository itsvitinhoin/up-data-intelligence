-- PREPARED ONLY: additive scope approved; execution requires separate authorization.
-- Never executed by the application. All 31 columns are NULLABLE (no NOT NULL).
-- Additive nullable metadata only. No backfill, replacement, snapshot removal or IAM changes.
-- Apply/reconcile schema before running transformation 1.1.0. See docs/IDENTITY_MIGRATION_PLAN.md.
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `email_normalized` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `phone_normalized` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `phone_e164` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `cnpj_digits` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `cpf_digits` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `seller_id` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `state` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `city` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `identity_normalization_version` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `external_ref` JSON;
ALTER TABLE `up-data-intelligence-dev.up_core.customers` ADD COLUMN IF NOT EXISTS `identity_normalization_issues` JSON;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `email_normalized` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `phone_normalized` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `phone_e164` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `cnpj_digits` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `cpf_digits` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `seller_id` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `state` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `city` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `identity_normalization_version` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `external_ref` JSON;
ALTER TABLE `up-data-intelligence-dev.up_core.customers_versions` ADD COLUMN IF NOT EXISTS `identity_normalization_issues` JSON;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `source_entity_type` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `source_entity_id` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `identifier_type_from` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `identifier_value_from` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `identifier_type_to` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `identifier_value_to` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `confidence_type` STRING;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `first_seen_at` TIMESTAMP;
ALTER TABLE `up-data-intelligence-dev.up_core.identity_links` ADD COLUMN IF NOT EXISTS `last_seen_at` TIMESTAMP;
