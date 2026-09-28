# BigQuery — schema implementado da Fase 1

Fonte de verdade física: [catalog.py](../src/bigquery/catalog.py), JSON em [schemas Terraform](../infra/terraform/tables.json) e SQL gerado. OpenAPI de origem: [upzero-openapi.json](upzero-openapi.json). Nenhum dataset ou tabela foi criado em GCP nesta execução.

## Camadas
RAW contém JSON sanitizado por página, não BYTES originais. Campos: row_key/raw_record_id, store_id, source_system, resource, source_connection_id, run_id/request_id, ingested_at, position/next_position, request_filters, payload, payload_hash, bytes_read e versões do conector/spec/sanitização. Nenhum header de autenticação é persistido. Hash é calculado depois da sanitização.

CORE mantém colunas tipadas dos dados comerciais/identidade/tracking e metadados de proveniência. Dinheiro NUMERIC; IDs STRING; quantity de facts INT64, qty de item NUMERIC; timestamps UTC. source_updated_at só existe quando retornado pela fonte. raw_record_id liga qualquer versão ao RAW sanitizado. seller e snapshots são JSON com IDs conhecidos normalizados quando aplicável.

ANALYTICS existe somente no Terraform como dataset vazio. OPS armazena execuções, checkpoints, capacidades por loja e resultados de qualidade. Staging é parâmetro de consulta JSON, sem tabela auxiliar permanente.

## Tabelas e layout físico
| Dataset/tabela | Partição | Clustering |
|---|---|---|
| up_raw.upzero_customers | ingested_at | store_id, resource |
| up_raw.upzero_orders | ingested_at | store_id, resource |
| up_raw.upzero_analytics_facts | ingested_at | store_id, resource |
| up_core.customers | — | store_id, customer_id |
| up_core.customers_versions | observed_at | store_id, customer_id |
| up_core.orders | created_at | store_id, order_id |
| up_core.orders_versions | observed_at | store_id, order_id |
| up_core.order_items | order_created_at | store_id, order_id |
| up_core.order_items_versions | observed_at | store_id, order_id |
| up_core.analytics_events | occurred_at | store_id, fact_id |
| up_core.analytics_events_versions | observed_at | store_id, fact_id |
| up_core.touchpoints | occurred_at | store_id, session_id |
| up_core.identity_links | observed_at | store_id, source_fact_id |
| up_core.event_order_links | — | store_id, order_id |
| up_core.stores | — | store_id |
| up_core.source_connections | — | store_id |
| up_ops.sync_runs | started_at | store_id, resource |
| up_ops.sync_checkpoints | — | store_id |
| up_ops.quality_results | checked_at | store_id, rule_id |
| up_ops.source_capabilities | — | store_id |

## Chaves e histórico
row_key é hash determinístico que inclui store_id e chave de negócio; versões acrescentam raw_record_id, conteúdo e versão de transformação. Pedidos/itens têm relação pai-versão; item ausente de snapshot completo recebe present_in_latest_snapshot=false. Array omitido não equivale a vazio. Removed permanece como status da fonte, sem reinterpretação financeira.

Cada touchpoint referencia source_fact_id; parser extrai meta_campaign_id/meta_adset_id/meta_ad_id/meta_adset_name como STRING, com parser_version e parse_status. Identity links têm source_version_id e evidência de coocorrência; para estado atual, filtrar pela versão corrente do evento. event_order_links usa exclusivamente store_id+order_id observado e status matched/pending/missing_order_id.

## Escrita e limites
MERGE em transação por página, após deduplicar source row_key, com binds de dados e nomes de tabela de catálogo fechado. Payload transacional acima de 8 MB falha sem truncar; reduzir page_limit. CAST inválido não vira NULL silencioso. require_partition_filter=false permite localizar chaves antigas em correções temporais; custo precisa de medição no piloto.

O anexo é o contrato completo de origem, inclusive requests/endpoints fora de escopo e campos secretos redigidos. Ele não instrui copiar todo campo ao CORE.

## 7. Dicionário completo dos schemas da fonte

Inventário dos 97 schemas, inclusive requests, respostas e modelos Storefront. Request não comprova campo de resposta; schema Storefront não comprova endpoint disponível. `$ref` aponta à definição nomeada na fonte. required é local ao objeto, não implica que seu ancestral opcional exista. Este anexo descreve origem, não autoriza copiar todos os campos para CORE.

### AnalyticsMetricsResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.total` | integer | sim | Número de registros retornados. | — |
| `$.next_cursor` | string | não | Cursor para paginação incremental. | {"nullable": true} |
| `$.totals` | #/components/schemas/AnalyticsMetricsTotals | sim |  | {"$ref": "#/components/schemas/AnalyticsMetricsTotals"} |
| `$.meta` | #/components/schemas/AnalyticsMetricsMeta | sim |  | {"$ref": "#/components/schemas/AnalyticsMetricsMeta"} |
| `$.data` | array | sim |  | — |
| `$.data[]` | #/components/schemas/AnalyticsMetricItem | não |  | — |

### AnalyticsMetricsTotals

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.total_events` | integer | sim |  | {"format": "int64"} |
| `$.unique_users` | integer | sim |  | {"format": "int64"} |
| `$.unique_sessions` | integer | sim |  | {"format": "int64"} |
| `$.total_quantity` | integer | sim |  | {"format": "int64"} |
| `$.total_value` | number | sim |  | {"format": "double"} |

### AnalyticsMetricsMeta

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.from` | string | sim |  | {"format": "date-time"} |
| `$.to` | string | sim |  | {"format": "date-time"} |
| `$.limit` | integer | sim |  | {"format": "int64"} |
| `$.sort_by` | string | sim |  | {"enum": ["period_start", "total_events", "total_value"]} |
| `$.sort_dir` | string | sim |  | {"enum": ["asc", "desc"]} |

### AnalyticsFactsResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.total` | integer | sim | Número de registros retornados. | — |
| `$.next_cursor` | string | não | Cursor para paginação incremental. | {"nullable": true} |
| `$.data` | array | sim |  | — |
| `$.data[]` | #/components/schemas/AnalyticsFactItem | não |  | — |

### AnalyticsFactItem

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.occurred_at` | string | sim |  | {"format": "date-time"} |
| `$.event_id` | string | sim |  | — |
| `$.event_name` | string | sim |  | — |
| `$.user_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.anonymous_id` | string | não |  | {"nullable": true} |
| `$.session_id` | string | não |  | {"nullable": true} |
| `$.visitor_id` | string | não |  | {"nullable": true} |
| `$.fbclid` | string | não |  | {"nullable": true} |
| `$.fbc` | string | não |  | {"nullable": true} |
| `$.fbp` | string | não |  | {"nullable": true} |
| `$.gclid` | string | não |  | {"nullable": true} |
| `$.landing_url` | string | não |  | {"nullable": true} |
| `$.landing_host` | string | não |  | {"nullable": true} |
| `$.landing_path` | string | não |  | {"nullable": true} |
| `$.referrer` | string | não |  | {"nullable": true} |
| `$.referrer_host` | string | não |  | {"nullable": true} |
| `$.utm_source` | string | não |  | {"nullable": true} |
| `$.utm_medium` | string | não |  | {"nullable": true} |
| `$.utm_campaign` | string | não |  | {"nullable": true} |
| `$.utm_content` | string | não |  | {"nullable": true} |
| `$.utm_term` | string | não |  | {"nullable": true} |
| `$.source` | string | não |  | {"nullable": true} |
| `$.channel` | string | não |  | {"nullable": true} |
| `$.device_type` | string | não |  | {"nullable": true} |
| `$.product_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.product_variant_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.category_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.order_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.quantity` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.value` | number | não |  | {"format": "double", "nullable": true} |

### AnalyticsProductRef

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.name` | string | sim |  | — |
| `$.sku` | string | não |  | {"nullable": true} |

### AnalyticsCategoryRef

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.name` | string | sim |  | — |

### AnalyticsVariantRef

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.sku` | string | sim |  | — |

### AnalyticsUserRef

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.type` | string | sim | Tipo do cliente. | {"enum": ["WHOLESALE", "RETAIL"]} |
| `$.name` | string | não |  | {"nullable": true} |
| `$.cpf` | string | não |  | {"nullable": true} |
| `$.cnpj` | string | não |  | {"nullable": true} |
| `$.company_name` | string | não |  | {"nullable": true} |

### AnalyticsSellerRef

Vendedora atribuída pelo contexto do link `/v/{seller_slug}` quando a métrica
foi agregada com `seller_id` tipado.


| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim | ID da vendedora (`admins.id`). | {"format": "int64"} |
| `$.name` | string | não | Nome da vendedora. | {"nullable": true} |
| `$.seller_slug` | string | não | Slug usado no link (`/v/{seller_slug}`). | {"nullable": true} |

### AnalyticsMetricItem

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.period_start` | string | sim |  | {"format": "date-time"} |
| `$.period_type` | string | sim |  | {"enum": ["hour", "day", "week", "month"]} |
| `$.event_name` | string | sim |  | — |
| `$.product` | #/components/schemas/AnalyticsProductRef | não |  | {"$ref": "#/components/schemas/AnalyticsProductRef"} |
| `$.product_variant` | #/components/schemas/AnalyticsVariantRef | não |  | {"$ref": "#/components/schemas/AnalyticsVariantRef"} |
| `$.category` | #/components/schemas/AnalyticsCategoryRef | não |  | {"$ref": "#/components/schemas/AnalyticsCategoryRef"} |
| `$.user` | #/components/schemas/AnalyticsUserRef | não |  | {"$ref": "#/components/schemas/AnalyticsUserRef"} |
| `$.seller` | #/components/schemas/AnalyticsSellerRef | não |  | {"$ref": "#/components/schemas/AnalyticsSellerRef"} |
| `$.order_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.utm_source` | string | não |  | {"nullable": true} |
| `$.utm_medium` | string | não |  | {"nullable": true} |
| `$.utm_campaign` | string | não |  | {"nullable": true} |
| `$.source` | string | não |  | {"nullable": true} |
| `$.channel` | string | não |  | {"nullable": true} |
| `$.device_type` | string | não |  | {"nullable": true} |
| `$.total_events` | integer | sim |  | {"format": "int64"} |
| `$.unique_users` | integer | sim |  | {"format": "int64"} |
| `$.unique_sessions` | integer | sim |  | {"format": "int64"} |
| `$.total_quantity` | integer | sim |  | {"format": "int64"} |
| `$.total_value` | number | sim |  | {"format": "double"} |
| `$.updated_at` | string | sim |  | {"format": "date-time"} |

### StorefrontAssetCategory

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.name` | string | sim |  | — |
| `$.slug` | ['string', 'null'] | não |  | — |
| `$.status` | ['boolean', 'null'] | não |  | — |
| `$.parent_id` | ['integer', 'null'] | não |  | — |
| `$.store_id` | ['integer', 'null'] | não |  | — |

### StorefrontAssetSkuGroup

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.product_variant_id` | ['integer', 'null'] | não |  | — |
| `$.sku` | ['string', 'null'] | não |  | — |
| `$.image_key` | ['string', 'null'] | não |  | — |
| `$.combination_key` | ['string', 'null'] | não |  | — |
| `$.attribute_value_ids` | array | não |  | — |
| `$.images` | array | não |  | — |
| `$.images[].oneOf[1].image_url` | string | não |  | — |

### StorefrontAsset

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.product_id` | ['integer', 'null'] | não |  | — |
| `$.slug` | ['string', 'null'] | não |  | — |
| `$.title` | ['string', 'null'] | não |  | — |
| `$.code` | string | sim |  | — |
| `$.category_ids` | array | não |  | — |
| `$.meta` | object | não |  | {"additionalProperties": true} |
| `$.image_grouping_rule` | ['object', 'null'] | não |  | {"additionalProperties": true} |
| `$.sku_groups` | array | não |  | — |
| `$.sku_groups[]` | #/components/schemas/StorefrontAssetSkuGroup | não |  | — |

### StorefrontAssetListResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.oneOf[0][]` | #/components/schemas/StorefrontAsset | não |  | — |
| `$.oneOf[1].items` | array | não |  | — |
| `$.oneOf[1].items[]` | #/components/schemas/StorefrontAsset | não |  | — |

### StorefrontProductVariantSummary

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | não |  | {"format": "int64"} |
| `$.code` | ['string', 'null'] | não |  | — |
| `$.sku` | ['string', 'null'] | não |  | — |
| `$.price_cents` | ['integer', 'null'] | não |  | — |
| `$.active` | ['boolean', 'null'] | não |  | — |

### StorefrontProductSummary

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.store_id` | ['integer', 'null'] | não |  | — |
| `$.code` | ['string', 'null'] | não |  | — |
| `$.slug` | ['string', 'null'] | não |  | — |
| `$.name` | string | sim |  | — |
| `$.description` | ['string', 'null'] | não |  | — |
| `$.image_grouping_rule` | ['object', 'null'] | não |  | {"additionalProperties": true} |
| `$.tags` | array | não |  | — |
| `$.category_ids` | array | não |  | — |

### StorefrontProductListItem

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.product` | #/components/schemas/StorefrontProductSummary | não |  | {"$ref": "#/components/schemas/StorefrontProductSummary"} |
| `$.variants` | array | não |  | — |
| `$.variants[].variant` | #/components/schemas/StorefrontProductVariantSummary | não |  | {"$ref": "#/components/schemas/StorefrontProductVariantSummary"} |
| `$.variants[].images` | array | não |  | — |

### StorefrontProductListResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.oneOf[0][]` | #/components/schemas/StorefrontProductListItem | não |  | — |
| `$.oneOf[1].items` | array | não |  | — |
| `$.oneOf[1].items[]` | #/components/schemas/StorefrontProductListItem | não |  | — |

### StorefrontFilterAttributeValue

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.attribute_id` | integer | sim |  | {"format": "int64"} |
| `$.code` | string | sim |  | — |
| `$.name` | string | sim |  | — |
| `$.sort_order` | integer | sim |  | — |
| `$.meta` | ['object', 'null'] | não |  | {"additionalProperties": true} |

### StorefrontFilterAttribute

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.store_id` | ['integer', 'null'] | não |  | — |
| `$.code` | string | sim |  | — |
| `$.name` | string | sim |  | — |
| `$.sort_order` | integer | sim |  | — |
| `$.values` | array | sim |  | — |
| `$.values[]` | #/components/schemas/StorefrontFilterAttributeValue | não |  | — |

### StorefrontCartAttribute

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.attribute_code` | ['string', 'null'] | não |  | — |
| `$.attribute_name` | ['string', 'null'] | não |  | — |
| `$.value_name` | ['string', 'null'] | não |  | — |

### StorefrontCartItem

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.product_variant_id` | integer | sim |  | {"format": "int64"} |
| `$.asset_id` | ['integer', 'null'] | não |  | — |
| `$.asset_name` | ['string', 'null'] | não |  | — |
| `$.asset_image_url` | ['string', 'null'] | não |  | — |
| `$.quantity` | integer | sim |  | {"minimum": 1} |
| `$.price_cents_snapshot` | integer | sim |  | {"minimum": 0} |
| `$.product_name` | string | sim |  | — |
| `$.image_url` | ['string', 'null'] | não |  | — |
| `$.attributes` | array | não |  | — |
| `$.attributes[]` | #/components/schemas/StorefrontCartAttribute | não |  | — |

### StorefrontCart

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.items` | array | não |  | — |
| `$.items[]` | #/components/schemas/StorefrontCartItem | não |  | — |

### StorefrontCartAddItemRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.product_variant_id` | integer | sim |  | {"format": "int64"} |
| `$.quantity` | integer | sim |  | {"minimum": 1} |
| `$.asset_id` | integer | não |  | {"format": "int64"} |

### StorefrontCartUpdateItemRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.quantity` | integer | sim |  | {"minimum": 1} |

### StorefrontClient

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim |  | {"format": "int64"} |
| `$.name` | string | sim |  | — |
| `$.email` | string | sim |  | {"format": "email"} |
| `$.phone` | ['string', 'null'] | não |  | — |
| `$.cpf_cnpj` | ['string', 'null'] | não |  | — |
| `$.gender` | ['string', 'null'] | não |  | — |
| `$.birth_date` | ['string', 'null'] | não |  | — |
| `$.address_zip` | ['string', 'null'] | não |  | — |
| `$.address_street` | ['string', 'null'] | não |  | — |
| `$.address_number` | ['string', 'null'] | não |  | — |
| `$.address_complement` | ['string', 'null'] | não |  | — |
| `$.address_neighborhood` | ['string', 'null'] | não |  | — |
| `$.address_city` | ['string', 'null'] | não |  | — |
| `$.address_state` | ['string', 'null'] | não |  | — |
| `$.status` | string | sim |  | — |
| `$.created_at` | string | sim |  | — |

### StorefrontClientRegisterRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | sim |  | — |
| `$.email` | string | sim |  | {"format": "email"} |
| `$.phone` | string | não |  | — |
| `$.password` | string | sim |  | {"minLength": 6} |

### StorefrontClientLoginRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.email` | string | sim |  | {"format": "email"} |
| `$.password` | string | sim |  | {"minLength": 1} |

### StorefrontClientLoginResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | #/components/schemas/StorefrontClient | sim |  | {"$ref": "#/components/schemas/StorefrontClient"} |

### StorefrontClientUpdateRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | não |  | — |
| `$.email` | string | não |  | {"format": "email"} |
| `$.phone` | string | não |  | — |
| `$.password` | string | não |  | {"minLength": 6} |
| `$.cpf_cnpj` | string | não |  | — |
| `$.gender` | string | não |  | — |
| `$.birth_date` | string | não |  | — |
| `$.address_zip` | string | não |  | — |
| `$.address_street` | string | não |  | — |
| `$.address_number` | string | não |  | — |
| `$.address_complement` | string | não |  | — |
| `$.address_neighborhood` | string | não |  | — |
| `$.address_city` | string | não |  | — |
| `$.address_state` | string | não |  | — |

### StorefrontShippingQuote

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.method_id` | integer | sim |  | {"format": "int64"} |
| `$.method_name` | string | sim |  | — |
| `$.method_type` | string | sim |  | — |
| `$.price_cents` | integer | sim |  | {"minimum": 0} |
| `$.min_delivery_days` | ['integer', 'null'] | não |  | — |
| `$.max_delivery_days` | ['integer', 'null'] | não |  | — |
| `$.is_free` | boolean | sim |  | — |

### StorefrontShippingQuoteResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.quotes` | array | sim |  | — |
| `$.quotes[]` | #/components/schemas/StorefrontShippingQuote | não |  | — |
| `$.zip_code` | string | sim |  | — |

### ErrorResponse

Estrutura padrão para erros retornados pela API.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.error` | object | sim | Informações detalhadas do erro. | {"required": ["code", "message"]} |
| `$.error.code` | string | sim | Código estável para identificação do tipo de erro. | — |
| `$.error.message` | string | sim | Mensagem legível para diagnóstico do erro. | — |
| `$.error.details` | object | não | Metadados adicionais do erro (contexto, campos inválidos, etc.). | {"additionalProperties": true} |

### ExternalRef

Associação ERP -> plataforma por integração.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.integration` | string | sim | Nome da integração (bling/tiny/manse/custom_erp). | — |
| `$.external_id` | string | sim | ID do objeto no ERP. | — |

### VariantAttributeRef

Referência de atributo usada em payloads de variante.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | não | ID interno do atributo na plataforma. | — |
| `$.name` | string | sim | Nome do atributo exibido para humanos. | — |
| `$.code` | string | sim | Código canônico do atributo usado na integração. | — |

### VariantTermRef

Referência de termo selecionado para um atributo.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | sim | Nome do termo exibido para humanos. | — |
| `$.code` | string | sim | Código canônico do termo usado na integração. | — |

### VariantAttributeAssignment

Associação entre atributo e termo para identificar uma opção de variante.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.attribute` | #/components/schemas/VariantAttributeRef | sim |  | {"$ref": "#/components/schemas/VariantAttributeRef"} |
| `$.term` | #/components/schemas/VariantTermRef | sim |  | {"$ref": "#/components/schemas/VariantTermRef"} |

### AttributeTermResponse

Termo de atributo cadastrado na loja.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do termo. | — |
| `$.attribute_id` | string | sim | ID interno do atributo pai. | — |
| `$.code` | string | sim | Código único do termo dentro do atributo. | — |
| `$.name` | string | sim | Nome do termo. | — |
| `$.sort_order` | integer | sim | Ordem de exibição do termo. | — |
| `$.rgb` | string | não | Cor opcional do termo lida de `meta.rgb`. | {"nullable": true} |

### AttributeResponse

Atributo da loja com sua lista de termos.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do atributo. | — |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.code` | string | sim | Código único do atributo na loja. | — |
| `$.name` | string | sim | Nome do atributo. | — |
| `$.sort_order` | integer | sim | Ordem de exibição do atributo. | — |
| `$.terms` | array | sim | Termos disponíveis para este atributo. | — |
| `$.terms[]` | #/components/schemas/AttributeTermResponse | não |  | — |

### AttributeCreateRequest

Payload para criação/atualização idempotente de atributo.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.code` | string | sim | Código único do atributo na loja. | — |
| `$.name` | string | sim | Nome do atributo. | — |
| `$.sort_order` | integer | não | Ordem de exibição do atributo. | — |

### AttributeTermCreateRequest

Payload para criação/atualização idempotente de termo de atributo.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.code` | string | sim | Código único do termo no atributo. | — |
| `$.name` | string | sim | Nome do termo. | — |
| `$.sort_order` | integer | não | Ordem de exibição do termo. | — |
| `$.rgb` | string | não | Cor opcional do termo; quando enviada, é persistida em `meta.rgb`. | — |
| `$.meta` | object | não | Metadados opcionais do termo. Quando `rgb` é enviado, ele é gravado em `meta.rgb`. | {"additionalProperties": true} |

### CategoryResponse

Categoria da loja.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | integer | sim | ID interno da categoria. | {"format": "int64"} |
| `$.name` | string | sim | Nome da categoria. | — |
| `$.status` | boolean | sim | Indica se a categoria está ativa. | — |
| `$.parent_id` | integer | não | ID da categoria pai (nulo para categoria raiz). | {"format": "int64", "nullable": true} |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.created_at` | string | sim | Data/hora de criação. | {"format": "date-time"} |
| `$.updated_at` | string | sim | Data/hora da última atualização. | {"format": "date-time"} |

### CategoryTreeResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.allOf[0]` | #/components/schemas/CategoryResponse | não |  | — |
| `$.allOf[1].children` | array | sim | Lista de subcategorias imediatas da categoria pai. | — |
| `$.allOf[1].children[]` | #/components/schemas/CategoryResponse | não |  | — |

### CategoryCreateRequest

Payload para criação de categoria.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | sim | Nome da categoria. | — |
| `$.status` | boolean | não | Define se a categoria será criada ativa. | {"default": true} |
| `$.parent_id` | integer | não | ID da categoria pai; nulo para categoria raiz. | {"format": "int64", "nullable": true} |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |

### CategoryUpdateRequest

Payload para atualização parcial de categoria.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | não | Novo nome da categoria. | — |
| `$.status` | boolean | não | Novo status (ativa/inativa). | — |
| `$.parent_id` | integer | não | Novo ID de categoria pai. | {"format": "int64", "nullable": true} |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |

### ProductCreateRequest

Payload para criação de produto via integração externa.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.code` | string | não | Código interno/ERP do produto. | — |
| `$.name` | string | sim | Nome do produto. | — |
| `$.description_html` | string | não | Descrição rica do produto em HTML. | — |
| `$.status` | string | não | Status de publicação do produto. | {"enum": ["active", "inactive", "archived"], "default": "active"} |
| `$.tags` | array | não | Marcadores livres do produto. | — |
| `$.category_ids` | array | não | IDs das categorias externas a serem associadas ao produto. | — |
| `$.product_category_ids` | array | não | IDs das categorias internas (ecommerce) a serem associadas ao produto. | — |
| `$.variants` | array | não | Lista inicial de variantes do produto. | — |
| `$.variants[]` | #/components/schemas/VariantUpsert | não |  | — |

### ProductUpdateRequest

Payload para atualização parcial de produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.code` | string | não | Novo código interno/ERP do produto. | — |
| `$.name` | string | não | Novo nome do produto. | — |
| `$.description_html` | string | não | Nova descrição rica em HTML. | — |
| `$.status` | string | não | Novo status de publicação. | {"enum": ["active", "inactive", "archived"]} |
| `$.tags` | array | não | Substitui as tags do produto. | — |
| `$.category_ids` | array | não | Substitui a lista de categorias externas associadas ao produto. | — |
| `$.product_category_ids` | array | não | Substitui a lista de categorias internas (ecommerce) associadas ao produto. | — |
| `$.variants` | array | não | Upsert de variantes associadas ao produto. | — |
| `$.variants[]` | #/components/schemas/VariantUpsert | não |  | — |

### ProductBatchRequest

Payload para criar ou atualizar produtos em lote.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.items` | array | sim | Lista de produtos a processar. Máximo 50 itens por batch. | {"minItems": 1, "maxItems": 50} |
| `$.items[]` | #/components/schemas/ProductBatchItemRequest | não |  | — |

### ProductBatchItemRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.allOf[0]` | #/components/schemas/ProductUpdateRequest | não |  | — |
| `$.allOf[1].id` | string | não | ID interno do produto. Alias aceito: product_id. Se enviado e não existir, o item falha. | — |
| `$.allOf[1].product_id` | string | não | Alias de id. | — |

### ProductBatchItemResult

Resultado individual de cada item do lote.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.item_index` | integer | sim | Índice do item original no array `items` (base 0). | — |
| `$.success` | boolean | sim | Indica se o item foi processado com sucesso. | — |
| `$.action` | string | não | Ação aplicada quando `success=true`. | {"nullable": true, "enum": ["created", "updated"]} |
| `$.product_id` | string | não | ID interno do produto quando `success=true`. | {"nullable": true} |
| `$.code` | string | não | Código interno do produto (ou o `code` enviado, em caso de falha). | {"nullable": true} |
| `$.error` | string | não | Mensagem de erro quando `success=false`. | {"nullable": true} |

### ProductBatchResponse

Resultado consolidado do processamento em lote.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.processed` | integer | sim | Total de itens processados. | — |
| `$.created` | integer | sim | Total de produtos criados. | — |
| `$.updated` | integer | sim | Total de produtos atualizados. | — |
| `$.failed` | integer | sim | Total de itens com falha. | — |
| `$.results` | array | sim |  | — |
| `$.results[]` | #/components/schemas/ProductBatchItemResult | não |  | — |

### ProductResponse

Representação completa do produto para API externa.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do produto (alias legado). | — |
| `$.product_id` | string | sim | ID interno do produto. | — |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.code` | string | sim | Código interno/ERP do produto. | — |
| `$.name` | string | sim | Nome do produto. | — |
| `$.description_html` | string | não | Descrição rica do produto em HTML. | — |
| `$.status` | string | sim | Status atual do produto. | {"enum": ["active", "inactive", "archived"]} |
| `$.tags` | array | não | Tags associadas ao produto. | — |
| `$.category_ids` | array | não | IDs das categorias externas/ERP associadas ao produto (tabela `external_categories`). | — |
| `$.category_names` | array | não | Nomes das categorias externas/ERP (mesma ordem de category_ids). | — |
| `$.product_category_ids` | array | não | IDs das categorias do ecommerce associadas ao produto (tabela `categories`). | — |
| `$.product_category_names` | array | não | Nomes das categorias do ecommerce (mesma ordem de product_category_ids). | — |
| `$.variants` | array | não | Variantes ativas/inativas do produto. | — |
| `$.variants[]` | #/components/schemas/VariantResponse | não |  | — |
| `$.created_at` | string | sim | Data/hora de criação. | {"format": "date-time"} |
| `$.updated_at` | string | sim | Data/hora da última atualização. | {"format": "date-time"} |

### ProductListResponse

Resposta paginada de listagem de produtos.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | sim | Itens da página atual. | — |
| `$.data[]` | #/components/schemas/ProductResponse | não |  | — |
| `$.next_cursor` | string | não | Cursor para próxima página; nulo quando não há mais itens. | {"nullable": true} |

### VariantUpsert

Variante para criação/atualização dentro do payload de produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | não | ID interno da variante (obrigatório para update de variante existente). | — |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.sku` | string | não | SKU da variante. | — |
| `$.barcode` | string | não | Código de barras da variante. | — |
| `$.price` | string | não | Preço de venda da variante (decimal string). | — |
| `$.promotional_price` | string | não | Preço promocional da variante (decimal string). | {"nullable": true} |
| `$.cost` | string | não | Custo unitário da variante (decimal string). | {"nullable": true} |
| `$.weight` | string | não | Peso da variante em gramas. Aceita string ou número (`"250"` ou `250`). Também aceita o alias `weight_grams`.<br> | {"nullable": true} |
| `$.attributes` | array | sim | Atributos da variante com o termo selecionado. | — |
| `$.attributes[]` | #/components/schemas/VariantAttributeAssignment | não |  | — |
| `$.active` | boolean | não | Indica se a variante está ativa para venda. | {"default": true} |

### ProductImageUpsert

Imagem enviada no payload de criação/atualização de produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.url` | string | não | URL pública da imagem. | {"format": "uri"} |
| `$.base64` | string | não | String base64 da imagem (aceita Data URL ou base64 puro). | — |
| `$.attributes` | array | não | Define agrupamento por variante. Quando vazio/ausente, a imagem é de produto. | — |
| `$.attributes[]` | #/components/schemas/VariantAttributeAssignment | não |  | — |
| `$.display_order` | integer | não | Ordem de exibição da imagem. | {"format": "int32"} |
| `$.is_primary` | boolean | não | Define a imagem principal. | — |

### ProductImageCreateRequest

Payload para adicionar imagem ao produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.allOf[0]` | #/components/schemas/ProductImageUpsert | não |  | — |

### ProductImageUpdateRequest

Payload para atualizar imagem existente do produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.allOf[0]` | #/components/schemas/ProductImageUpsert | não |  | — |

### ProductImageResponse

Representação de imagem do produto e seu vínculo com variantes.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno da imagem. | — |
| `$.product_id` | string | sim | ID interno do produto dono da imagem. | — |
| `$.image_url` | string | sim | URL final da imagem armazenada. | — |
| `$.combination_key` | string | não | Chave de combinação de atributos quando a imagem é vinculada a variante. | {"nullable": true} |
| `$.display_order` | integer | sim | Ordem de exibição da imagem na galeria. | {"format": "int32"} |
| `$.is_primary` | boolean | sim | Indica se é a imagem principal do produto. | — |
| `$.variant_ids` | array | sim | IDs das variantes associadas à imagem. | — |
| `$.created_at` | string | sim | Data/hora de criação. | {"format": "date-time"} |
| `$.updated_at` | string | sim | Data/hora da última atualização. | {"format": "date-time"} |

### ProductVideoUpsert

Vídeo enviado no payload de criação/atualização de produto.
Informe apenas um entre `url` e `base64`.


| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.url` | string | não | URL pública/original do vídeo. Mutuamente exclusivo com `base64`. | {"format": "uri", "nullable": true} |
| `$.base64` | string | não | Conteúdo do vídeo em base64. Aceita Data URL (ex.: `data:video/mp4;base64,...`)<br>ou base64 puro. Quando enviado, o backend faz upload no Bunny Stream e<br>salva as URLs resultantes no vídeo. Mutuamente exclusivo com `url`.<br> | {"nullable": true} |
| `$.name` | string | não | Nome do vídeo. | {"nullable": true} |
| `$.attributes` | array | não | Define agrupamento por variante. Quando vazio/ausente, usa variante padrão quando existir. | — |
| `$.attributes[]` | #/components/schemas/VariantAttributeAssignment | não |  | — |

### ProductVideoCreateRequest

Payload para adicionar vídeo ao produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.allOf[0]` | #/components/schemas/ProductVideoUpsert | não |  | — |

### ProductVideoUpdateRequest

Payload para atualizar vídeo existente do produto.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.allOf[0]` | #/components/schemas/ProductVideoUpsert | não |  | — |

### ProductVideoResponse

Representação de vídeo do produto e seu vínculo com variantes.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do vídeo. | — |
| `$.product_id` | string | sim | ID interno do produto dono do vídeo. | — |
| `$.url` | string | não | URL original do vídeo. | {"nullable": true} |
| `$.name` | string | não | Nome do vídeo. | {"nullable": true} |
| `$.variant_image_key` | string | sim | Chave de agrupamento do vídeo para mapeamento com variantes. | — |
| `$.variant_ids` | array | sim | IDs das variantes associadas ao vídeo. | — |
| `$.created_at` | string | sim | Data/hora de criação. | {"format": "date-time"} |
| `$.updated_at` | string | sim | Data/hora da última atualização. | {"format": "date-time"} |

### VariantCreateRequest

Payload para criação de variante.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.product_id` | string | sim | ID interno do produto pai. | — |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.sku` | string | não | SKU da variante. | — |
| `$.barcode` | string | não | Código de barras da variante. | — |
| `$.price` | string | sim | Preço de venda da variante (decimal string). | — |
| `$.promotional_price` | string | não | Preço promocional (decimal string). | {"nullable": true} |
| `$.weight` | string | não | Peso da variante em gramas. Aceita string ou número (`"250"` ou `250`). Também aceita o alias `weight_grams`.<br> | {"nullable": true} |
| `$.cost` | string | não | Custo unitário da variante. | {"nullable": true} |
| `$.attributes` | array | não | Atributos que definem a combinação da variante. | — |
| `$.attributes[]` | #/components/schemas/VariantAttributeAssignment | não |  | — |
| `$.active` | boolean | não | Indica se a variante inicia ativa. | {"default": true} |

### VariantUpdateRequest

Payload para atualização parcial de variante.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.sku` | string | não | Novo SKU da variante. | — |
| `$.barcode` | string | não | Novo código de barras da variante. | — |
| `$.price` | string | não | Novo preço de venda (decimal string). | — |
| `$.promotional_price` | string | não | Novo preço promocional (decimal string). | {"nullable": true} |
| `$.weight` | string | não | Novo peso da variante em gramas. Aceita string ou número (`"250"` ou `250`). Também aceita o alias `weight_grams`.<br> | {"nullable": true} |
| `$.cost` | string | não | Novo custo unitário da variante. | {"nullable": true} |
| `$.attributes` | array | não | Nova combinação de atributos/termos da variante. | — |
| `$.attributes[]` | #/components/schemas/VariantAttributeAssignment | não |  | — |
| `$.active` | boolean | não | Novo status de ativação da variante. | — |

### VariantResponse

Representação de variante para API externa.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno da variante. | — |
| `$.product_id` | string | sim | ID interno do produto pai. | — |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.sku` | string | não | SKU da variante. | — |
| `$.barcode` | string | não | Código de barras da variante. | — |
| `$.price` | string | sim | Preço de venda da variante. | — |
| `$.promotional_price` | string | não | Preço promocional da variante. | {"nullable": true} |
| `$.cost` | string | não | Custo unitário da variante. | — |
| `$.weight` | string | não | Peso da variante em gramas. | {"nullable": true} |
| `$.attributes` | array | não | Combinação de atributos/termos da variante. | — |
| `$.attributes[]` | #/components/schemas/VariantAttributeAssignment | não |  | — |
| `$.active` | boolean | sim | Indica se a variante está ativa. | — |
| `$.created_at` | string | sim | Data/hora de criação. | {"format": "date-time"} |
| `$.updated_at` | string | sim | Data/hora da última atualização. | {"format": "date-time"} |

### VariantListResponse

Resposta paginada de listagem de variantes.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | sim | Itens da página atual. | — |
| `$.data[]` | #/components/schemas/VariantResponse | não |  | — |
| `$.next_cursor` | string | não | Cursor para próxima página; nulo quando não há mais itens. | {"nullable": true} |

### InventoryAvailabilityResponse

Snapshot de disponibilidade de estoque para uma variante.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.variant_id` | string | sim | ID da variante consultada. | — |
| `$.warehouse_id` | string | não | Warehouse específico quando aplicável. | {"nullable": true} |
| `$.totals` | object | sim | Totais consolidados de estoque para a variante consultada. | {"required": ["qty_total", "qty_reserved", "qty_available"]} |
| `$.totals.qty_total` | number | sim | Quantidade total registrada. | — |
| `$.totals.qty_reserved` | number | sim | Quantidade reservada. | — |
| `$.totals.qty_available` | number | sim | Quantidade disponível para venda. | — |
| `$.breakdown` | array | não | Quebra opcional por warehouse/location/batch. | — |
| `$.breakdown[].warehouse_id` | string | não | Identificador do warehouse. | — |
| `$.breakdown[].location_id` | string | não | Identificador da localização física/lógica. | — |
| `$.breakdown[].location_type` | string | não | Tipo de localização do estoque. | {"enum": ["SELLABLE", "PICKING", "RECEIVING", "PACKING", "SHIPPING", "QUARANTINE", "DAMAGED"]} |
| `$.breakdown[].batch_id` | string | não | Identificador do lote, quando aplicável. | {"nullable": true} |
| `$.breakdown[].qty_total` | number | não | Quantidade total nesta quebra. | — |
| `$.breakdown[].qty_reserved` | number | não | Quantidade reservada nesta quebra. | — |
| `$.breakdown[].qty_available` | number | não | Quantidade disponível nesta quebra. | — |

### InventoryAdjustRequest

Payload para ajuste de estoque. Identifique a variante por `variant_id` **ou** `sku` (pelo menos um obrigatório).

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.movement_type` | string | sim | Tipo do movimento de estoque. | {"enum": ["IN", "OUT", "SET"]} |
| `$.variant_id` | string | não | ID da variante a ser ajustada. Opcional se `sku` for informado. | {"nullable": true} |
| `$.sku` | string | não | SKU da variante a ser ajustada. Opcional se `variant_id` for informado. | {"nullable": true} |
| `$.qty` | integer | sim | Sempre >= 0. Para `IN`/`OUT`, usa quantidade relativa. Para `SET`, define o valor absoluto do estoque disponível. | — |
| `$.price` | string | não | Novo preço de venda da variante (decimal string). | {"nullable": true} |
| `$.promotional_price` | string | não | Novo preço promocional da variante (decimal string). Envie "0" para remover promoção. | {"nullable": true} |
| `$.cost` | string | não | Custo unitário em decimal string (ex.: "21.50"). Quando informado, é salvo no item do movimento e também atualiza o custo da variante. Se omitido, o custo atual da variante não é alterado. Compatível com payload legado `unit_cost`. | {"nullable": true} |
| `$.reference` | object | não | Referência de origem do movimento. | — |
| `$.reference.reference_type` | string | não | Tipo da referência do movimento. | {"enum": ["ORDER", "ORDER_ITEM", "RETURN", "ADJUSTMENT", "PURCHASE", "MANUAL"]} |
| `$.reference.reference_id` | string | não | ID externo/interno da referência. | — |
| `$.note` | string | não | Observação livre do ajuste. | {"nullable": true} |

### InventoryAdjustResponse

Resultado do ajuste de estoque aplicado.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.movement_id` | string | sim | ID do movimento de estoque gerado. | — |
| `$.position` | object | sim | Posição consolidada após o ajuste. | {"required": ["position_id", "qty_total", "qty_reserved", "qty_available"]} |
| `$.position.position_id` | string | sim | Identificador lógico da posição de estoque. | — |
| `$.position.qty_total` | integer | sim | Quantidade total registrada. | — |
| `$.position.qty_reserved` | integer | sim | Quantidade reservada. | — |
| `$.position.qty_available` | integer | sim | Quantidade disponível para venda. | — |

### InventoryAdjustBatchItemRequest

Item de ajuste em lote. Envie `variant_id` ou `sku`.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.movement_type` | string | sim | Tipo do movimento de estoque. | {"enum": ["IN", "OUT", "SET"]} |
| `$.variant_id` | string | não | ID da variante. Tem prioridade quando enviado junto com `sku`. | {"nullable": true} |
| `$.sku` | string | não | SKU da variante. Usado quando `variant_id` não é enviado. | {"nullable": true} |
| `$.qty` | integer | sim | Sempre >= 0. Para `IN`/`OUT`, usa quantidade relativa. Para `SET`, define o valor absoluto do estoque disponível. | — |
| `$.price` | string | não | Novo preço de venda da variante (decimal string). | {"nullable": true} |
| `$.promotional_price` | string | não | Novo preço promocional da variante (decimal string). Envie "0" para remover promoção. | {"nullable": true} |
| `$.cost` | string | não | Custo unitário em decimal string (ex.: "21.50"). Quando informado, é salvo no item do movimento e também atualiza o custo da variante. Compatível com payload legado `unit_cost`. | {"nullable": true} |
| `$.reference` | object | não | Referência de origem do movimento. | — |
| `$.reference.reference_type` | string | não | Tipo da referência do movimento. | {"enum": ["ORDER", "ORDER_ITEM", "RETURN", "ADJUSTMENT", "PURCHASE", "MANUAL"]} |
| `$.reference.reference_id` | string | não | ID externo/interno da referência. | — |
| `$.note` | string | não | Observação livre do ajuste. | {"nullable": true} |

### InventoryAdjustBatchRequest

Payload para processar ajustes de estoque em lote.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.items` | array | sim | Lista de ajustes a processar. Máximo 100 itens por batch. | {"minItems": 1, "maxItems": 100} |
| `$.items[]` | #/components/schemas/InventoryAdjustBatchItemRequest | não |  | — |

### InventoryAdjustBatchItemResult

Resultado individual de cada item do lote.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.item_index` | integer | sim | Índice do item original no array `items` (base 0). | — |
| `$.success` | boolean | sim | Indica se o item foi processado com sucesso. | — |
| `$.variant_id` | string | não | ID da variante usada no processamento. | {"nullable": true} |
| `$.sku` | string | não | SKU informado no item, quando enviado. | {"nullable": true} |
| `$.movement_id` | string | não | ID do movimento gerado quando `success=true`. | {"nullable": true} |
| `$.position` | object | não | Posição consolidada quando `success=true`. | {"nullable": true} |
| `$.position.position_id` | string | não |  | — |
| `$.position.qty_total` | integer | não |  | — |
| `$.position.qty_reserved` | integer | não |  | — |
| `$.position.qty_available` | integer | não |  | — |
| `$.error` | string | não | Mensagem de erro quando `success=false`. | {"nullable": true} |

### InventoryAdjustBatchResponse

Resultado consolidado do processamento em lote.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.processed` | integer | sim | Total de itens processados. | — |
| `$.succeeded` | integer | sim | Total de itens com sucesso. | — |
| `$.failed` | integer | sim | Total de itens com falha. | — |
| `$.results` | array | sim |  | — |
| `$.results[]` | #/components/schemas/InventoryAdjustBatchItemResult | não |  | — |

### CustomerAddressPayload

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.zip` | string | não |  | {"nullable": true} |
| `$.street` | string | não |  | {"nullable": true} |
| `$.number` | string | não |  | {"nullable": true} |
| `$.complement` | string | não |  | {"nullable": true} |
| `$.neighborhood` | string | não |  | {"nullable": true} |
| `$.city` | string | não |  | {"nullable": true} |
| `$.state` | string | não |  | {"nullable": true} |

### CouponCreateRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | sim |  | — |
| `$.code` | string | sim |  | — |
| `$.status` | boolean | não |  | {"nullable": true} |
| `$.discount_type` | string | não |  | {"enum": ["percentage", "fixed"], "nullable": true} |
| `$.percentage` | number | não | Percentual em pontos (10 = 10%). Alternativa a percentage_bps. | {"nullable": true} |
| `$.percentage_bps` | integer | não |  | {"nullable": true, "minimum": 0, "maximum": 10000} |
| `$.value` | string | não | Valor fixo em reais (ex. "50.00"). Alternativa a value_cents. | {"nullable": true} |
| `$.value_cents` | integer | não |  | {"nullable": true} |
| `$.expiration_date` | string | não | YYYY-MM-DD | {"nullable": true} |
| `$.expiration_time` | string | não | HH:MM | {"nullable": true} |
| `$.free_shipping_active` | boolean | não |  | {"nullable": true} |
| `$.unique_per_user_active` | boolean | não |  | {"nullable": true} |
| `$.exclude_discounted_products_active` | boolean | não |  | {"nullable": true} |
| `$.only_discounted_products_active` | boolean | não |  | {"nullable": true} |
| `$.minimum_quantity_active` | boolean | não |  | {"nullable": true} |
| `$.minimum_quantity_value` | integer | não |  | {"nullable": true} |
| `$.email_rule_active` | boolean | não |  | {"nullable": true} |
| `$.email_list` | string | não | JSON array de emails. | {"nullable": true} |
| `$.minimum_purchase_value` | string | não |  | {"nullable": true} |
| `$.minimum_purchase_value_cents` | integer | não |  | {"nullable": true} |
| `$.minimum_purchase_value_active` | boolean | não |  | {"nullable": true} |
| `$.max_uses` | integer | não |  | {"nullable": true} |
| `$.max_uses_active` | boolean | não |  | {"nullable": true} |
| `$.maximum_purchase_value` | string | não |  | {"nullable": true} |
| `$.maximum_purchase_value_cents` | integer | não |  | {"nullable": true} |
| `$.maximum_purchase_value_active` | boolean | não |  | {"nullable": true} |
| `$.products_rule_active` | boolean | não |  | {"nullable": true} |
| `$.product_ids` | string | não | JSON array de product ids. | {"nullable": true} |
| `$.categories_rule_active` | boolean | não |  | {"nullable": true} |
| `$.category_ids` | string | não | JSON array de category ids. | {"nullable": true} |
| `$.external_ref` | composição | não |  | {"allOf": [{"$ref": "#/components/schemas/ExternalRef"}], "nullable": true} |
| `$.external_ref.allOf[0]` | #/components/schemas/ExternalRef | não |  | — |

### CouponResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | não |  | — |
| `$.name` | string | não |  | — |
| `$.code` | string | não |  | — |
| `$.status` | boolean | não |  | — |
| `$.discount_type` | string | não |  | — |
| `$.percentage_bps` | integer | não |  | {"nullable": true} |
| `$.value` | string | não |  | {"nullable": true} |
| `$.expiration_date` | string | não |  | {"nullable": true} |
| `$.expiration_time` | string | não |  | {"nullable": true} |
| `$.free_shipping_active` | boolean | não |  | — |
| `$.unique_per_user_active` | boolean | não |  | — |
| `$.exclude_discounted_products_active` | boolean | não |  | — |
| `$.only_discounted_products_active` | boolean | não |  | — |
| `$.minimum_quantity_active` | boolean | não |  | — |
| `$.minimum_quantity_value` | integer | não |  | {"nullable": true} |
| `$.email_rule_active` | boolean | não |  | — |
| `$.email_list` | string | não |  | {"nullable": true} |
| `$.minimum_purchase_value` | string | não |  | {"nullable": true} |
| `$.minimum_purchase_value_active` | boolean | não |  | — |
| `$.max_uses` | integer | não |  | {"nullable": true} |
| `$.max_uses_active` | boolean | não |  | — |
| `$.maximum_purchase_value` | string | não |  | {"nullable": true} |
| `$.maximum_purchase_value_active` | boolean | não |  | — |
| `$.products_rule_active` | boolean | não |  | — |
| `$.product_ids` | string | não |  | {"nullable": true} |
| `$.categories_rule_active` | boolean | não |  | — |
| `$.category_ids` | string | não |  | {"nullable": true} |
| `$.external_ref` | composição | não |  | {"allOf": [{"$ref": "#/components/schemas/ExternalRef"}], "nullable": true} |
| `$.external_ref.allOf[0]` | #/components/schemas/ExternalRef | não |  | — |
| `$.created_at` | string | não |  | {"nullable": true} |
| `$.updated_at` | string | não |  | {"nullable": true} |

### CouponListResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | não |  | — |
| `$.data[]` | #/components/schemas/CouponResponse | não |  | — |

### CustomerCreateRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | não |  | {"nullable": true} |
| `$.email` | string | sim |  | — |
| `$.phone` | string | não |  | {"nullable": true} |
| `$.password_hash` | string | não | Hash Argon2/bcrypt já persistido. Use para clonar o login entre lojas. Não envie a senha em texto. | {"nullable": true} |
| `$.cpf` | string | não | CPF (pontuado ou sem pontuação). Persistido com apenas dígitos. | {"nullable": true} |
| `$.cnpj` | string | não | CNPJ (pontuado ou sem pontuação). Persistido com apenas dígitos. | {"nullable": true} |
| `$.customer_type` | string | sim | Obrigatório. Tipo do cliente; não é inferido por CPF/CNPJ. | {"enum": ["RETAIL", "WHOLESALE"]} |
| `$.gender` | string | não | Gênero do cliente retail. Valores aceitos: female, male (também F/M/Feminino/Masculino). | {"nullable": true} |
| `$.birth_date` | string | não | Data de nascimento (YYYY-MM-DD). | {"nullable": true} |
| `$.created_at` | string | não | Data de cadastro original (ISO-8601/RFC3339). Se omitida, usa o timestamp atual. | {"format": "date-time", "nullable": true} |
| `$.external_ref` | composição | não | Referência externa (ex. Firebase user id) para vínculo em importações. | {"allOf": [{"$ref": "#/components/schemas/ExternalRef"}], "nullable": true} |
| `$.external_ref.allOf[0]` | #/components/schemas/ExternalRef | não |  | — |
| `$.address` | #/components/schemas/CustomerAddressPayload | não |  | {"$ref": "#/components/schemas/CustomerAddressPayload"} |
| `$.wholesale_profile` | #/components/schemas/CustomerWholesaleProfilePayload | não |  | {"$ref": "#/components/schemas/CustomerWholesaleProfilePayload"} |

### CustomerUpdateRequest

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.name` | string | não |  | {"nullable": true} |
| `$.email` | string | não |  | {"nullable": true} |
| `$.phone` | string | não |  | {"nullable": true} |
| `$.password_hash` | string | não | Hash Argon2/bcrypt já persistido. Use para clonar o login entre lojas. | {"nullable": true} |
| `$.cpf` | string | não |  | {"nullable": true} |
| `$.cnpj` | string | não |  | {"nullable": true} |
| `$.customer_type` | string | não |  | {"nullable": true, "enum": ["RETAIL", "WHOLESALE"]} |
| `$.gender` | string | não | Gênero do cliente retail. Valores aceitos: female, male. | {"nullable": true} |
| `$.birth_date` | string | não | Data de nascimento (YYYY-MM-DD). | {"nullable": true} |
| `$.created_at` | string | não | Corrige a data de cadastro (ISO-8601/RFC3339). | {"format": "date-time", "nullable": true} |
| `$.external_ref` | composição | não | Referência externa (ex. Firebase user id) para vínculo em importações. | {"allOf": [{"$ref": "#/components/schemas/ExternalRef"}], "nullable": true} |
| `$.external_ref.allOf[0]` | #/components/schemas/ExternalRef | não |  | — |
| `$.address` | #/components/schemas/CustomerAddressPayload | não |  | {"$ref": "#/components/schemas/CustomerAddressPayload"} |
| `$.wholesale_profile` | #/components/schemas/CustomerWholesaleProfilePayload | não |  | {"$ref": "#/components/schemas/CustomerWholesaleProfilePayload"} |

### CustomerWholesaleProfilePayload

Dados completos para perfil wholesale.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.contact_name` | string | não |  | {"nullable": true} |
| `$.company_name` | string | não |  | {"nullable": true} |
| `$.trade_name` | string | não |  | {"nullable": true} |
| `$.cnpj` | string | não | CNPJ com ou sem pontuação. | {"nullable": true} |
| `$.state_registration` | string | não |  | {"nullable": true} |
| `$.segment` | string | não |  | {"nullable": true} |
| `$.address_zip` | string | não |  | {"nullable": true} |
| `$.address_street` | string | não |  | {"nullable": true} |
| `$.address_number` | string | não |  | {"nullable": true} |
| `$.address_complement` | string | não |  | {"nullable": true} |
| `$.address_neighborhood` | string | não |  | {"nullable": true} |
| `$.address_city` | string | não |  | {"nullable": true} |
| `$.address_state` | string | não |  | {"nullable": true} |

### CustomerResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | não |  | {"nullable": true} |
| `$.name` | string | não |  | {"nullable": true} |
| `$.email` | string | não |  | {"nullable": true} |
| `$.phone` | string | não |  | {"nullable": true} |
| `$.password_hash` | string | não | Hash Argon2/bcrypt do login. Não é a senha em texto. | {"nullable": true} |
| `$.customer_type` | string | não |  | {"nullable": true, "enum": ["RETAIL", "WHOLESALE"]} |
| `$.status` | string | não | Status de aprovação do cadastro do cliente. | {"nullable": true, "enum": ["PENDING", "APPROVED", "REJECTED"]} |
| `$.external_ref` | composição | não | Referência externa persistida no cliente. | {"allOf": [{"$ref": "#/components/schemas/ExternalRef"}], "nullable": true} |
| `$.external_ref.allOf[0]` | #/components/schemas/ExternalRef | não |  | — |
| `$.retail_profile` | object | não |  | {"nullable": true} |
| `$.retail_profile.cpf` | string | não |  | {"nullable": true} |
| `$.retail_profile.gender` | string | não |  | {"nullable": true} |
| `$.retail_profile.birth_date` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_zip` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_street` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_number` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_complement` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_neighborhood` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_city` | string | não |  | {"nullable": true} |
| `$.retail_profile.address_state` | string | não |  | {"nullable": true} |
| `$.retail_profile.meta` | object | não | Dados extras do perfil varejo (campo livre JSON). | {"additionalProperties": true} |
| `$.wholesale_profile` | object | não |  | {"nullable": true} |
| `$.wholesale_profile.contact_name` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.company_name` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.trade_name` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.cnpj` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.state_registration` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.segment` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_zip` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_street` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_number` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_complement` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_neighborhood` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_city` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.address_state` | string | não |  | {"nullable": true} |
| `$.wholesale_profile.meta` | object | não | Dados extras do perfil atacado (campo livre JSON). | {"additionalProperties": true} |
| `$.seller` | object | não | Vendedora vinculada ao cliente. Presente apenas quando há uma vendedora atribuída. | {"nullable": true, "required": ["id", "name", "email"]} |
| `$.seller.id` | string | sim | ID interno da vendedora. | — |
| `$.seller.name` | string | sim | Nome da vendedora. | — |
| `$.seller.email` | string | sim | E-mail da vendedora. | — |

### CustomerListResponse

Sem descrição adicional.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | sim |  | — |
| `$.data[]` | #/components/schemas/CustomerResponse | não |  | — |

### OrderCreateRequest

Payload para criação de pedido externo.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.order_status` | string | não | Status inicial do pedido.<br>Ao criar via API ou ERP, apenas fluxos iniciais são permitidos: - `RESERVED`: Cria o pedido como aberto (pendente de pagamento). Reserva o estoque temporariamente se `reserve_stock: true`. - `CONFIRMED`: Cria o pedido já aprovado (pago). Também pode abater o estoque definitivamente logo na criação.<br> | {"enum": ["RESERVED", "CONFIRMED"], "default": "RESERVED"} |
| `$.payment_status` | string | não | Status inicial do pagamento. | {"enum": ["unpaid", "paid"], "default": "unpaid"} |
| `$.payment_method` | string | não | Forma de pagamento da loja. Aceita `pix`, `boleto`, `credit_card`/`cartao_externo`, `faturado` (e aliases). Resolve para o `payment_methods` correspondente; não cria método manual "Importado".<br> | {"nullable": true} |
| `$.installments` | integer | não | Número de parcelas do cartão (`1` = à vista). Só é aceito quando `payment_method` é `credit_card`. Se enviado sem `payment_method`, o pedido é criado como cartão. PIX, boleto e faturado devem omitir o campo.<br> | {"nullable": true, "minimum": 1, "maximum": 24} |
| `$.reserve_stock` | boolean | não | Define se deve reservar estoque ao criar o pedido. | {"default": true} |
| `$.created_at` | string | não | Data original do pedido (ISO-8601/RFC3339). Se omitida, usa o timestamp atual. Útil para importação histórica. | {"format": "date-time", "nullable": true} |
| `$.shipping_price` | string | não | Valor do frete em decimal (ex. "10.53"). Persistido em `shipping_price_cents`. | {"nullable": true} |
| `$.discount` | string | não | Desconto absoluto do pedido em decimal (ex. "69.60"). Distribuído proporcionalmente nos itens como `manual_discount_cents`.<br> | {"nullable": true} |
| `$.shipping_address` | composição | não | Endereço de entrega. Persistido nas colunas `shipping_*` e em `meta.checkout.address` / `meta.shipping_address` (usado pelo admin).<br> | {"allOf": [{"$ref": "#/components/schemas/CustomerAddressPayload"}]} |
| `$.shipping_address.allOf[0]` | #/components/schemas/CustomerAddressPayload | não |  | — |
| `$.customer_id` | string | sim | ID de cliente já cadastrado via `/external/v1/customers` (obrigatório). | — |
| `$.items` | array | sim | Itens do pedido. | — |
| `$.items[].external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.items[].variant_id` | string | não | ID interno da variante. Use `variant_id` **ou** `sku` — pelo menos um é obrigatório por item. Quando ambos são enviados, `variant_id` tem prioridade.<br> | — |
| `$.items[].sku` | string | não | SKU da variante. Alternativa a `variant_id` — pelo menos um é obrigatório por item. Se o SKU não existir na loja, retorna erro 400.<br> | — |
| `$.items[].qty` | number | sim | Quantidade solicitada. | — |
| `$.items[].unit_price` | string | não | Preço unitário no momento da venda. | — |

### OrderPatchRequest

Atualiza pagamento e/ou endereço de entrega de um pedido existente.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.payment_status` | string | não | Status do pagamento (também aceita valores do banco: PENDING, PAID, CANCELLED…). | {"enum": ["unpaid", "paid", "canceled"]} |
| `$.payment_method` | string | não | Forma de pagamento (`pix`, `boleto`, `credit_card`, `faturado`…). | {"nullable": true} |
| `$.installments` | integer | não | Número de parcelas do cartão (`1` = à vista). Só é aceito quando a forma de pagamento do pedido é `credit_card`.<br> | {"nullable": true, "minimum": 1, "maximum": 24} |
| `$.shipping_address` | composição | não | Endereço de entrega (colunas `shipping_*` + meta do admin). | {"allOf": [{"$ref": "#/components/schemas/CustomerAddressPayload"}]} |
| `$.shipping_address.allOf[0]` | #/components/schemas/CustomerAddressPayload | não |  | — |

### OrderResponse

Representação de pedido para API externa. Inclui valor solicitado (`requested_total`, `requested_items_qty`) e valor atendido (`fulfilled_total`, `fulfilled_items_qty`). Itens `removed` (soft delete) entram no solicitado, não entram no atendido e permanecem em `items`.


| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do pedido. | — |
| `$.external_ref` | #/components/schemas/ExternalRef | não |  | {"$ref": "#/components/schemas/ExternalRef"} |
| `$.order_status` | string | sim | Status atual do pedido.<br>Valores possíveis e seus significados: - **RESERVED**: Pedido recém-criado/aberto, aguardando pagamento ou processamento. Status inicial padrão ao criar via API. - **CONFIRMED**: Pedido aprovado ou com pagamento validado, pronto para faturamento/separação. - **PROCESSING**: Pedido em processamento/separação interno. - **INVOICED**: Nota fiscal emitida (NF-e autorizada ou em processamento pela SEFAZ). - **SHIPPED**: Pedido despachado/entregue ao cliente. - **CANCELED**: Pedido cancelado.<br> | {"enum": ["RESERVED", "CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED", "CANCELED"]} |
| `$.payment_status` | string | sim | Status atual do pagamento. | {"enum": ["unpaid", "paid", "canceled"]} |
| `$.payment_method` | string | não | Forma de pagamento do pedido. Mesmos valores aceitos na criação: `pix`, `boleto`, `credit_card`, `faturado`. `null` quando o pedido ainda não tem método associado.<br> | {"nullable": true} |
| `$.payment_method_name` | string | não | Nome de exibição da forma de pagamento cadastrada na loja. | {"nullable": true} |
| `$.installments` | integer | não | Número de parcelas. Preenchido quando a forma de pagamento é cartão (`credit_card`). `1` = à vista. `null` para PIX, boleto, faturado ou quando o parcelamento não foi informado.<br> | {"nullable": true, "minimum": 1} |
| `$.invoice` | composição | não | Dados da invoice/NF-e vinculada ao pedido, quando existir. | {"allOf": [{"$ref": "#/components/schemas/OrderInvoiceResponse"}], "nullable": true} |
| `$.invoice.allOf[0]` | #/components/schemas/OrderInvoiceResponse | não |  | — |
| `$.label` | composição | não | Dados da etiqueta de envio vinculada ao pedido, quando existir. | {"allOf": [{"$ref": "#/components/schemas/OrderLabelResponse"}], "nullable": true} |
| `$.label.allOf[0]` | #/components/schemas/OrderLabelResponse | não |  | — |
| `$.customer` | object | não | Dados do cliente associados ao pedido. | {"nullable": true} |
| `$.customer.id` | string | não | ID interno do cliente. | {"nullable": true} |
| `$.customer.name` | string | não | Nome do cliente. | {"nullable": true} |
| `$.customer.email` | string | não | E-mail do cliente. | {"nullable": true} |
| `$.customer.phone` | string | não | Telefone do cliente. | {"nullable": true} |
| `$.customer.customer_type` | string | não | Tipo de cliente vinculado ao pedido. | {"nullable": true, "enum": ["RETAIL", "WHOLESALE"]} |
| `$.customer.retail_profile` | object | não | Dados do perfil varejo, quando disponíveis. | {"nullable": true} |
| `$.customer.retail_profile.cpf` | string | não | CPF do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.gender` | string | não | Gênero informado no perfil varejo. | {"nullable": true} |
| `$.customer.retail_profile.birth_date` | string | não | Data de nascimento do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_zip` | string | não | CEP do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_street` | string | não | Logradouro do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_number` | string | não | Número do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_complement` | string | não | Complemento do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_neighborhood` | string | não | Bairro do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_city` | string | não | Cidade do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.address_state` | string | não | Estado do endereço do cliente varejo. | {"nullable": true} |
| `$.customer.retail_profile.meta` | object | não | Dados extras do perfil varejo (campo livre JSON). | {"additionalProperties": true} |
| `$.customer.wholesale_profile` | object | não | Dados do perfil atacado, quando disponíveis. | {"nullable": true} |
| `$.customer.wholesale_profile.contact_name` | string | não | Nome do contato comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.company_name` | string | não | Razão social. | {"nullable": true} |
| `$.customer.wholesale_profile.trade_name` | string | não | Nome fantasia. | {"nullable": true} |
| `$.customer.wholesale_profile.cnpj` | string | não | CNPJ da empresa. | {"nullable": true} |
| `$.customer.wholesale_profile.state_registration` | string | não | Inscrição estadual. | {"nullable": true} |
| `$.customer.wholesale_profile.segment` | string | não | Segmento de atuação da empresa. | {"nullable": true} |
| `$.customer.wholesale_profile.address_zip` | string | não | CEP do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.address_street` | string | não | Logradouro do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.address_number` | string | não | Número do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.address_complement` | string | não | Complemento do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.address_neighborhood` | string | não | Bairro do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.address_city` | string | não | Cidade do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.address_state` | string | não | UF do endereço comercial. | {"nullable": true} |
| `$.customer.wholesale_profile.meta` | object | não | Dados extras do perfil atacado (campo livre JSON). | {"additionalProperties": true} |
| `$.shipping_address` | object | não | Endereço de entrega do pedido; quando ausente no pedido, usa fallback do endereço do perfil do cliente. | {"nullable": true, "additionalProperties": true} |
| `$.subtotal` | string | sim | Subtotal atual do pedido em decimal (itens `active` e `attended`), antes dos descontos e frete. | — |
| `$.discount` | string | sim | Soma dos descontos do pedido em decimal (cupom, faixa, forma de pagamento, manual e composição).<br> | — |
| `$.shipping` | string | sim | Valor do frete do pedido em decimal. | — |
| `$.total` | string | sim | Total atual do pedido em decimal (itens `active` e `attended`, após descontos e frete). | — |
| `$.total_items_qty` | integer | sim | Soma das quantidades atuais (`qty`) dos itens `active` e `attended`. | — |
| `$.requested_total` | string | sim | Valor solicitado do pedido em decimal (`original_qty` de todos os itens, inclusive `removed`, após descontos e frete).<br> | — |
| `$.requested_items_qty` | integer | sim | Soma das quantidades solicitadas (`original_qty`) de todos os itens, inclusive `removed`. | — |
| `$.fulfilled_total` | string | sim | Valor atendido do pedido em decimal (`qty` dos itens `active` e `attended`, após descontos e frete). Itens `removed` não entram. Se nenhum item foi atendido/ativo, retorna `"0.00"` (sem somar frete).<br> | — |
| `$.fulfilled_items_qty` | integer | sim | Soma das quantidades atuais (`qty`) dos itens `active` e `attended`. | — |
| `$.items_count` | integer | sim | Quantidade de linhas de itens do pedido, incluindo itens `removed` (soft delete). | — |
| `$.items` | array | não | Itens do pedido, incluindo `removed` (soft delete). Itens removidos entram no solicitado e não entram no atendido.<br> | — |
| `$.items[].id` | string | sim | ID interno do item de pedido. | — |
| `$.items[].variant_id` | string | não | ID da variante associada ao item. | {"nullable": true} |
| `$.items[].asset_id` | string | não | ID do asset vinculado ao item (quando houver). | {"nullable": true} |
| `$.items[].asset_name` | string | não | Nome do asset vinculado ao item. | {"nullable": true} |
| `$.items[].asset_image_url` | string | não | URL da imagem do asset (prioritária quando existir). | {"nullable": true} |
| `$.items[].image_url` | string | não | URL fallback da imagem do produto/variante. | {"nullable": true} |
| `$.items[].sku` | string | não | SKU do item. | {"nullable": true} |
| `$.items[].qty` | number | sim | Quantidade atual do item (atendida). Para `removed`, em geral 0. | — |
| `$.items[].original_qty` | integer | sim | Quantidade solicitada original do item. | — |
| `$.items[].unit_price` | string | não | Preço unitário do item. | {"nullable": true} |
| `$.items[].status` | string | sim | Estado atual do item no pedido. `removed` é o soft delete (permanece no array e no valor solicitado).<br> | {"enum": ["active", "attended", "removed"]} |
| `$.allocations` | array | não | Reservas por posição/lote (se reserve_stock=true). | — |
| `$.allocations[].id` | string | não | ID interno da alocação de estoque. | — |
| `$.allocations[].order_item_id` | string | não | ID do item de pedido relacionado à alocação. | — |
| `$.allocations[].variant_id` | string | não | ID da variante alocada. | — |
| `$.allocations[].warehouse_id` | string | não | ID do warehouse reservado. | — |
| `$.allocations[].location_id` | string | não | ID da localização reservada. | — |
| `$.allocations[].batch_id` | string | não | ID do lote reservado, quando aplicável. | {"nullable": true} |
| `$.allocations[].qty` | number | não | Quantidade alocada. | — |
| `$.allocations[].status` | string | não | Estado atual da alocação. | {"enum": ["reserved", "committed", "released"]} |
| `$.created_at` | string | sim | Data/hora de criação do pedido. | {"format": "date-time"} |
| `$.updated_at` | string | sim | Data/hora da última atualização do pedido. | {"format": "date-time"} |

### OrderListResponse

Resposta paginada de listagem de pedidos.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | sim | Itens da página atual. | — |
| `$.data[]` | #/components/schemas/OrderResponse | não |  | — |
| `$.page` | integer | sim | Número da página atual. | — |
| `$.total_pages` | integer | sim | Total de páginas disponíveis com os filtros aplicados. | — |
| `$.total` | integer | sim | Total de pedidos encontrados com os filtros aplicados. | — |

### Webhook

Webhook registrado para eventos da loja.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do webhook. | — |
| `$.url` | string | sim | URL de destino para entrega de eventos. | {"format": "uri"} |
| `$.events` | array | sim | Lista de eventos que disparam o webhook. | — |
| `$.secret` | string | não | Usado para assinatura HMAC (somente no create/rotate; pode ser omitido no GET). | {"nullable": true} |
| `$.is_active` | boolean | sim | Indica se o webhook está ativo. | {"default": true} |
| `$.created_at` | string | sim | Data/hora de criação do webhook. | {"format": "date-time"} |

### WebhookCreateRequest

Payload para criação de webhook.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.url` | string | sim | URL que receberá os eventos. | {"format": "uri"} |
| `$.events` | array | sim | Eventos que devem ser assinados neste webhook. | — |
| `$.secret` | string | não | Segredo HMAC para validar requests (se não enviar, a plataforma gera). | — |
| `$.is_active` | boolean | não | Define se o webhook inicia ativo. | {"default": true} |

### WebhookListResponse

Resposta de listagem de webhooks.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | sim | Webhooks cadastrados na loja. | — |
| `$.data[]` | #/components/schemas/Webhook | não |  | — |

### CartAbandonedWebhookEnvelope

Envelope enviado ao destino para o evento `cart_abandoned`.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.event` | string | sim |  | — |
| `$.store_id` | integer | sim |  | {"format": "int64"} |
| `$.timestamp` | string | sim |  | {"format": "date-time"} |
| `$.data` | object | sim | Dados do carrinho com contexto de recuperação. | {"required": ["id", "status", "recovery_token", "recovery_url"]} |
| `$.data.id` | integer | sim |  | {"format": "int64"} |
| `$.data.client_id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.data.phone` | ['string', 'null'] | não | Telefone do cliente resolvido para o carrinho. | — |
| `$.data.customer_phone` | ['string', 'null'] | não | Alias de `phone`. | — |
| `$.data.customer_name` | ['string', 'null'] | não |  | — |
| `$.data.contact_name` | ['string', 'null'] | não |  | — |
| `$.data.customer` | object | não | Dados resumidos do cliente vinculado ao carrinho. | — |
| `$.data.customer.id` | integer | não |  | {"format": "int64", "nullable": true} |
| `$.data.customer.phone` | ['string', 'null'] | não |  | — |
| `$.data.customer.name` | ['string', 'null'] | não |  | — |
| `$.data.customer.contact_name` | ['string', 'null'] | não |  | — |
| `$.data.status` | string | sim |  | — |
| `$.data.recovery_token` | string | sim | Token bruto para recuperar o carrinho. | — |
| `$.data.recovery_url` | string | sim | URL pronta para recuperação do carrinho. | — |
| `$.data.recovery_expires_at` | string | não |  | {"format": "date-time"} |
| `$.data.recovery_max_uses` | integer | não |  | — |

### WebhookLog

Registro de tentativa de entrega de um webhook.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.id` | string | sim | ID interno do log. | — |
| `$.webhook_id` | string | sim | ID interno do webhook. | — |
| `$.event` | string | sim | Evento enviado. | — |
| `$.url` | string | sim | URL de destino chamada. | {"format": "uri"} |
| `$.response_status` | integer | não | HTTP status retornado pelo destino. | {"nullable": true} |
| `$.response_body` | string | não | Trecho do corpo de resposta do destino. | {"nullable": true} |
| `$.duration_ms` | integer | não | Duração da tentativa em milissegundos. | {"nullable": true} |
| `$.success` | boolean | sim | Se a entrega foi bem-sucedida. | — |
| `$.error_message` | string | não | Mensagem de erro quando a tentativa falha. | {"nullable": true} |
| `$.created_at` | string | sim | Data/hora de criação do log. | {"format": "date-time"} |

### WebhookLogListResponse

Resposta da listagem de logs de webhook.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.data` | array | sim |  | — |
| `$.data[]` | #/components/schemas/WebhookLog | não |  | — |

### OrderInvoiceUpsertRequest

Payload para registrar/atualizar dados de NF-e de um pedido via integração fiscal.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.order_id` | string | sim | ID interno do pedido (numérico como string). | — |
| `$.status` | string | não | Status da nota fiscal emitida.<br>- `AUTHORIZED`: NF-e autorizada pela SEFAZ. **Transiciona o pedido para INVOICED.**<br>- `PENDING`: Em processamento. **Transiciona o pedido para INVOICED.**<br>- `PROCESSING`: Em processamento. **Transiciona o pedido para INVOICED.**<br>- `REJECTED`: Rejeitada pela SEFAZ. Não altera status do pedido.<br>- `CANCELLED`: Cancelada. Não altera status do pedido.<br>- `ERROR`: Erro no processamento. Não altera status do pedido.<br> | {"enum": ["PENDING", "PROCESSING", "AUTHORIZED", "REJECTED", "CANCELLED", "ERROR"], "default": "AUTHORIZED"} |
| `$.nf_number` | string | não | Número da nota fiscal. | {"nullable": true} |
| `$.pdf_url` | string | não | URL pública do PDF da NF-e. Tem prioridade sobre `pdf_base64` quando ambos enviados. | {"format": "uri", "nullable": true} |
| `$.pdf_base64` | string | não | Conteúdo do PDF da NF-e em base64. Aceita Data URL (`data:application/pdf;base64,...`)<br>ou base64 puro. Quando enviado, o backend faz upload e salva a URL resultante.<br> | {"nullable": true} |
| `$.xml_url` | string | não | URL pública do XML da NF-e. Tem prioridade sobre `xml_base64` quando ambos enviados. | {"format": "uri", "nullable": true} |
| `$.xml_base64` | string | não | Conteúdo do XML da NF-e em base64. Aceita Data URL (`data:application/xml;base64,...`)<br>ou base64 puro. Quando enviado, o backend faz upload e salva a URL resultante.<br> | {"nullable": true} |
| `$.access_key` | string | não | Chave de acesso da NF-e (44 dígitos). | {"nullable": true} |
| `$.integration_name` | string | não | Identificador do sistema fiscal emissor. | {"nullable": true} |
| `$.integration_reference_id` | string | não | ID do documento no sistema fiscal externo. | {"nullable": true} |

### OrderInvoiceResponse

Dados da invoice registrada para o pedido.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.order_id` | string | sim | ID interno do pedido. | — |
| `$.status` | string | sim | Status atual da invoice. | {"enum": ["PENDING", "PROCESSING", "AUTHORIZED", "REJECTED", "CANCELLED", "ERROR"]} |
| `$.nf_number` | string | não | Número da nota fiscal. | {"nullable": true} |
| `$.pdf_url` | string | não | URL pública do PDF da NF-e (pode ter sido gerada via upload de base64). | {"format": "uri", "nullable": true} |
| `$.xml_url` | string | não | URL pública do XML da NF-e (pode ter sido gerada via upload de base64). | {"format": "uri", "nullable": true} |
| `$.access_key` | string | não | Chave de acesso da NF-e (44 dígitos). | {"nullable": true} |
| `$.integration_name` | string | não | Identificador do sistema fiscal emissor. | {"nullable": true} |
| `$.integration_reference_id` | string | não | ID do documento no sistema fiscal externo. | {"nullable": true} |
| `$.updated_at` | string | sim | Data/hora da última atualização da invoice. | {"format": "date-time"} |

### OrderLabelUpsertRequest

Payload para registrar/atualizar etiqueta de envio de um pedido.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.order_id` | string | sim | ID interno do pedido (numérico como string). | — |
| `$.status` | string | não | Status da etiqueta de envio.<br>- `ISSUED`: Etiqueta gerada com sucesso. **Transiciona o pedido para SHIPPED.**<br>- `ERROR`: Erro ao gerar etiqueta. Não altera o status do pedido.<br> | {"enum": ["ISSUED", "ERROR"], "default": "ISSUED"} |
| `$.tracking_code` | string | não | Código de rastreamento da transportadora. | {"nullable": true} |
| `$.carrier` | string | não | Nome/código da transportadora. | {"nullable": true} |
| `$.pdf_url` | string | não | URL pública do PDF da etiqueta. Tem prioridade sobre `pdf_base64` quando ambos enviados. | {"format": "uri", "nullable": true} |
| `$.pdf_base64` | string | não | Conteúdo do PDF da etiqueta em base64. Aceita Data URL (`data:application/pdf;base64,...`)<br>ou base64 puro. Quando enviado, o backend faz upload e salva a URL resultante.<br> | {"nullable": true} |
| `$.error_message` | string | não | Mensagem de erro quando `status = ERROR`. | {"nullable": true} |
| `$.issued_at` | string | não | Data/hora de emissão da etiqueta no formato RFC 3339. | {"format": "date-time", "nullable": true} |
| `$.integration_name` | string | não | Identificador do sistema de logística emissor. | {"nullable": true} |
| `$.integration_reference_id` | string | não | ID da etiqueta no sistema externo. | {"nullable": true} |
| `$.payload` | object | não | Dados brutos retornados pelo sistema de logística (armazenados como JSONB). | {"nullable": true} |
| `$.meta` | object | não | Metadados livres para uso interno da integração. | {"nullable": true} |

### OrderLabelResponse

Dados da etiqueta de envio registrada para o pedido.

| Campo / caminho | Tipo ou referência | Required local | Descrição | Restrições adicionais |
|---|---|---|---|---|
| `$.order_id` | string | sim | ID interno do pedido. | — |
| `$.status` | string | sim | Status atual da etiqueta. | {"enum": ["ISSUED", "ERROR"]} |
| `$.tracking_code` | string | não | Código de rastreamento da transportadora. | {"nullable": true} |
| `$.carrier` | string | não | Nome/código da transportadora. | {"nullable": true} |
| `$.pdf_url` | string | não | URL pública do PDF da etiqueta. | {"format": "uri", "nullable": true} |
| `$.integration_name` | string | não | Identificador do sistema de logística emissor. | {"nullable": true} |
| `$.integration_reference_id` | string | não | ID da etiqueta no sistema externo. | {"nullable": true} |
| `$.error_message` | string | não | Mensagem de erro quando status = ERROR. | {"nullable": true} |
| `$.issued_at` | string | não | Data/hora de emissão da etiqueta. | {"format": "date-time", "nullable": true} |
| `$.updated_at` | string | sim | Data/hora da última atualização. | {"format": "date-time"} |
