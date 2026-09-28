CREATE TABLE IF NOT EXISTS `${project_id}.up_core.customers_versions` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `source_system` STRING,
  `raw_record_id` STRING,
  `run_id` STRING,
  `observed_at` TIMESTAMP,
  `source_updated_at` TIMESTAMP,
  `payload_hash` STRING,
  `version_id` STRING,
  `transform_version` STRING,
  `customer_id` STRING,
  `customer_type` STRING,
  `status` STRING,
  `name` STRING,
  `email` STRING,
  `phone` STRING,
  `cpf` STRING,
  `cnpj` STRING,
  `company_name` STRING,
  `trade_name` STRING,
  `seller` JSON,
  `retail_profile` JSON,
  `wholesale_profile` JSON
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, customer_id;
