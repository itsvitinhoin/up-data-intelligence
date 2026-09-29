# Meta — schemas propostos

16 tabelas novas; nenhum dataset novo, nenhuma mudança em colunas existentes.
Somente row_key e store_id são REQUIRED; todas as outras colunas são NULLABLE.
RAW e CORE são nomes lógicos nos datasets já existentes. Manifesto não ativado: `infra/terraform/meta_tables.proposed.json`.

## up_core.meta_account_bindings

Sem particionamento.

Clustering: `store_id`, `account_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| account_id | STRING | NULLABLE |
| connection_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| source_timezone | STRING | NULLABLE |
| currency | STRING | NULLABLE |
| configuration_hash | STRING | NULLABLE |
| configured_at | TIMESTAMP | NULLABLE |

## up_core.meta_accounts

Sem particionamento.

Clustering: `store_id`, `account_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| account_status | INT64 | NULLABLE |
| currency | STRING | NULLABLE |
| timezone_name | STRING | NULLABLE |

## up_core.meta_accounts_versions

Partição: `observed_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `account_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| account_status | INT64 | NULLABLE |
| currency | STRING | NULLABLE |
| timezone_name | STRING | NULLABLE |

## up_core.meta_ads

Sem particionamento.

Clustering: `store_id`, `account_id`, `ad_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| campaign_id | STRING | NULLABLE |
| adset_id | STRING | NULLABLE |
| ad_id | STRING | NULLABLE |

## up_core.meta_ads_versions

Partição: `observed_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `account_id`, `ad_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| campaign_id | STRING | NULLABLE |
| adset_id | STRING | NULLABLE |
| ad_id | STRING | NULLABLE |

## up_core.meta_adsets

Sem particionamento.

Clustering: `store_id`, `account_id`, `adset_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| campaign_id | STRING | NULLABLE |
| adset_id | STRING | NULLABLE |

## up_core.meta_adsets_versions

Partição: `observed_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `account_id`, `adset_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| campaign_id | STRING | NULLABLE |
| adset_id | STRING | NULLABLE |

## up_core.meta_campaigns

Sem particionamento.

Clustering: `store_id`, `account_id`, `campaign_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| campaign_id | STRING | NULLABLE |
| objective | STRING | NULLABLE |

## up_core.meta_campaigns_versions

Partição: `observed_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `account_id`, `campaign_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| name | STRING | NULLABLE |
| status | STRING | NULLABLE |
| effective_status | STRING | NULLABLE |
| created_at | TIMESTAMP | NULLABLE |
| updated_at | TIMESTAMP | NULLABLE |
| campaign_id | STRING | NULLABLE |
| objective | STRING | NULLABLE |

## up_core.meta_insights_daily

Partição: `date_start` (DATE) por dia.

Clustering: `store_id`, `account_id`, `ad_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| campaign_id | STRING | NULLABLE |
| adset_id | STRING | NULLABLE |
| ad_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| account_currency | STRING | NULLABLE |
| source_timezone | STRING | NULLABLE |
| configuration_hash | STRING | NULLABLE |
| purchase_action_type | STRING | NULLABLE |
| date_start | DATE | NULLABLE |
| date_stop | DATE | NULLABLE |
| spend | NUMERIC | NULLABLE |
| frequency | NUMERIC | NULLABLE |
| cpm | NUMERIC | NULLABLE |
| cpc | NUMERIC | NULLABLE |
| ctr | NUMERIC | NULLABLE |
| landing_page_views | NUMERIC | NULLABLE |
| meta_reported_purchases | NUMERIC | NULLABLE |
| meta_reported_purchase_value | NUMERIC | NULLABLE |
| impressions | INT64 | NULLABLE |
| reach | INT64 | NULLABLE |
| clicks | INT64 | NULLABLE |
| inline_link_clicks | INT64 | NULLABLE |
| actions | JSON | NULLABLE |
| action_values | JSON | NULLABLE |
| breakdown_values | JSON | NULLABLE |
| reporting_configuration | JSON | NULLABLE |

## up_core.meta_insights_daily_versions

Partição: `observed_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `account_id`, `ad_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| observed_at | TIMESTAMP | NULLABLE |
| source_updated_at | TIMESTAMP | NULLABLE |
| payload_hash | STRING | NULLABLE |
| version_id | STRING | NULLABLE |
| transform_version | STRING | NULLABLE |
| account_id | STRING | NULLABLE |
| campaign_id | STRING | NULLABLE |
| adset_id | STRING | NULLABLE |
| ad_id | STRING | NULLABLE |
| api_version | STRING | NULLABLE |
| account_currency | STRING | NULLABLE |
| source_timezone | STRING | NULLABLE |
| configuration_hash | STRING | NULLABLE |
| purchase_action_type | STRING | NULLABLE |
| date_start | DATE | NULLABLE |
| date_stop | DATE | NULLABLE |
| spend | NUMERIC | NULLABLE |
| frequency | NUMERIC | NULLABLE |
| cpm | NUMERIC | NULLABLE |
| cpc | NUMERIC | NULLABLE |
| ctr | NUMERIC | NULLABLE |
| landing_page_views | NUMERIC | NULLABLE |
| meta_reported_purchases | NUMERIC | NULLABLE |
| meta_reported_purchase_value | NUMERIC | NULLABLE |
| impressions | INT64 | NULLABLE |
| reach | INT64 | NULLABLE |
| clicks | INT64 | NULLABLE |
| inline_link_clicks | INT64 | NULLABLE |
| actions | JSON | NULLABLE |
| action_values | JSON | NULLABLE |
| breakdown_values | JSON | NULLABLE |
| reporting_configuration | JSON | NULLABLE |

## up_raw.meta_raw_accounts

Partição: `ingested_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `source_connection_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| resource | STRING | NULLABLE |
| source_connection_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| request_id | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| payload_hash | STRING | NULLABLE |
| connector_version | STRING | NULLABLE |
| spec_version | STRING | NULLABLE |
| spec_sha256 | STRING | NULLABLE |
| sanitization_version | STRING | NULLABLE |
| ingested_at | TIMESTAMP | NULLABLE |
| position | JSON | NULLABLE |
| next_position | JSON | NULLABLE |
| request_filters | JSON | NULLABLE |
| payload | JSON | NULLABLE |
| bytes_read | INT64 | NULLABLE |
| pagination_error | STRING | NULLABLE |

## up_raw.meta_raw_ads

Partição: `ingested_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `source_connection_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| resource | STRING | NULLABLE |
| source_connection_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| request_id | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| payload_hash | STRING | NULLABLE |
| connector_version | STRING | NULLABLE |
| spec_version | STRING | NULLABLE |
| spec_sha256 | STRING | NULLABLE |
| sanitization_version | STRING | NULLABLE |
| ingested_at | TIMESTAMP | NULLABLE |
| position | JSON | NULLABLE |
| next_position | JSON | NULLABLE |
| request_filters | JSON | NULLABLE |
| payload | JSON | NULLABLE |
| bytes_read | INT64 | NULLABLE |
| pagination_error | STRING | NULLABLE |

## up_raw.meta_raw_adsets

Partição: `ingested_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `source_connection_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| resource | STRING | NULLABLE |
| source_connection_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| request_id | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| payload_hash | STRING | NULLABLE |
| connector_version | STRING | NULLABLE |
| spec_version | STRING | NULLABLE |
| spec_sha256 | STRING | NULLABLE |
| sanitization_version | STRING | NULLABLE |
| ingested_at | TIMESTAMP | NULLABLE |
| position | JSON | NULLABLE |
| next_position | JSON | NULLABLE |
| request_filters | JSON | NULLABLE |
| payload | JSON | NULLABLE |
| bytes_read | INT64 | NULLABLE |
| pagination_error | STRING | NULLABLE |

## up_raw.meta_raw_campaigns

Partição: `ingested_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `source_connection_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| resource | STRING | NULLABLE |
| source_connection_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| request_id | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| payload_hash | STRING | NULLABLE |
| connector_version | STRING | NULLABLE |
| spec_version | STRING | NULLABLE |
| spec_sha256 | STRING | NULLABLE |
| sanitization_version | STRING | NULLABLE |
| ingested_at | TIMESTAMP | NULLABLE |
| position | JSON | NULLABLE |
| next_position | JSON | NULLABLE |
| request_filters | JSON | NULLABLE |
| payload | JSON | NULLABLE |
| bytes_read | INT64 | NULLABLE |
| pagination_error | STRING | NULLABLE |

## up_raw.meta_raw_insights

Partição: `ingested_at` (TIMESTAMP) por dia.

Clustering: `store_id`, `source_connection_id`.

| Coluna | Tipo | Modo |
|---|---|---|
| row_key | STRING | REQUIRED |
| store_id | STRING | REQUIRED |
| source_system | STRING | NULLABLE |
| resource | STRING | NULLABLE |
| source_connection_id | STRING | NULLABLE |
| run_id | STRING | NULLABLE |
| request_id | STRING | NULLABLE |
| raw_record_id | STRING | NULLABLE |
| payload_hash | STRING | NULLABLE |
| connector_version | STRING | NULLABLE |
| spec_version | STRING | NULLABLE |
| spec_sha256 | STRING | NULLABLE |
| sanitization_version | STRING | NULLABLE |
| ingested_at | TIMESTAMP | NULLABLE |
| position | JSON | NULLABLE |
| next_position | JSON | NULLABLE |
| request_filters | JSON | NULLABLE |
| payload | JSON | NULLABLE |
| bytes_read | INT64 | NULLABLE |
| pagination_error | STRING | NULLABLE |
