# Schemas Analytics propostos

Sete tabelas em up_analytics já previsto. Não registradas no catálogo runtime ou no Terraform ativo.

Chave lógica: store_id + policy_hash + grão da tabela. row_key é hash determinístico, sem as_of ou intervalo de extração. Somente row_key/store_id são REQUIRED; demais campos NULLABLE.

## analytics_store_daily

Grão: store_id, policy_hash, order_date.

Partição: order_date. Clustering: store_id, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| order_date | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| payment_date | DATE | NULL: evidência inexistente no CORE atual usado |
| orders_generated | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| orders_paid | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| orders_cancelled | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| approved_orders | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| new_customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| returning_customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| purchasing_customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| orders_without_customer | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| meta_impressions | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| meta_clicks | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| first_party_new_customers_attributed | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| first_party_orders_attributed | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| revenue_generated | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_fulfilled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_paid | NUMERIC | NULL: evidência inexistente no CORE atual usado |
| revenue_cancelled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_unfulfilled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| approval_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| average_order_value_generated | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| average_order_value_paid | NUMERIC | NULL: evidência inexistente no CORE atual usado |
| items_per_order_generated | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| items_per_order_fulfilled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| meta_spend | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| meta_reported_purchases | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| meta_reported_purchase_value | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| first_party_revenue_generated_attributed | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| first_party_revenue_paid_attributed | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| new_customer_cac | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| roas_generated | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| roas_paid | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| observation_complete | BOOL | Configuração/cobertura explícita, não inferida da API |

## analytics_customer_metrics

Grão: store_id, policy_hash, customer_id.

Partição: nenhuma. Clustering: store_id, customer_id, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| customer_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| customer_type | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| ltv_basis | STRING | TRANSFORMED: regra explícita documentada |
| first_purchase_date | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| purchases | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| first_purchase_at | TIMESTAMP | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| second_purchase_at | TIMESTAMP | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| third_purchase_at | TIMESTAMP | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| fourth_purchase_at | TIMESTAMP | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| observed_through | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| ltv_lifetime_observed | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_paid | NUMERIC | NULL: evidência inexistente no CORE atual usado |
| days_first_to_second | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| days_second_to_third | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| days_third_to_fourth | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_30d | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_60d | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_90d | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_180d | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_365d | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_30d_complete | BOOL | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_60d_complete | BOOL | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_90d_complete | BOOL | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_180d_complete | BOOL | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| ltv_365d_complete | BOOL | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |

## analytics_customer_purchase_sequence

Grão: store_id, policy_hash, order_id.

Partição: order_date. Clustering: store_id, customer_id, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| customer_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| customer_type | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| order_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| source_order_version_id | STRING | OBSERVED: orders.version_id |
| customer_classification | STRING | TRANSFORMED: regra explícita documentada |
| order_at | TIMESTAMP | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| first_purchase_at | TIMESTAMP | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| order_date | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| first_purchase_date | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| purchase_number | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_generated | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_fulfilled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_paid | NUMERIC | NULL: evidência inexistente no CORE atual usado |

## analytics_cohorts

Grão: store_id, policy_hash, cohort_month, months_since_first_purchase.

Partição: cohort_month. Clustering: store_id, months_since_first_purchase, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| cohort_month | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| reporting_month | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| months_since_first_purchase | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| customers_in_cohort | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| active_customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| orders | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| retention_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| observed_retention_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_generated | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_paid | NUMERIC | NULL: evidência inexistente no CORE atual usado |
| period_complete | BOOL | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |

## analytics_purchase_distribution

Grão: store_id, policy_hash, cohort_month, purchase_bucket.

Partição: cohort_month. Clustering: store_id, purchase_bucket, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| cohort_month | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| purchase_bucket | STRING | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_basis | STRING | TRANSFORMED: regra explícita documentada |
| customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| original_cohort_customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| percentage_of_original_cohort | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |

## analytics_products_daily

Grão: store_id, policy_hash, order_date, product_key.

Partição: order_date. Clustering: store_id, product_key, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| order_date | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| product_key | STRING | TRANSFORMED: regra explícita documentada |
| product_id | STRING | NULL: evidência inexistente no CORE atual usado |
| asset_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| variant_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| sku | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| reference | STRING | NULL: evidência inexistente no CORE atual usado |
| revenue_basis | STRING | TRANSFORMED: regra explícita documentada |
| orders | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| customers | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| impressions | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| clicks | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| first_party_orders_attributed | INT64 | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| units_requested | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| units_fulfilled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_generated | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_fulfilled | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| revenue_paid | NUMERIC | NULL: evidência inexistente no CORE atual usado |
| average_selling_price | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| cancellation_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| spend | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| first_party_revenue_attributed | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| roas | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |

## analytics_funnel_daily

Grão: store_id, policy_hash, event_date.

Partição: event_date. Clustering: store_id, policy_hash.

| Coluna | Tipo | Fonte/classificação |
|---|---|---|
| row_key | STRING | TRANSFORMED: política/chave/versão analítica |
| store_id | STRING | OBSERVED: identificador/dimensão CORE; customer exige relação exata na loja |
| currency | STRING | Configuração/cobertura explícita, não inferida da API |
| reporting_timezone | STRING | Configuração/cobertura explícita, não inferida da API |
| policy_hash | STRING | TRANSFORMED: política/chave/versão analítica |
| analytics_version | STRING | TRANSFORMED: política/chave/versão analítica |
| calculated_at | TIMESTAMP | Configuração/cobertura explícita, não inferida da API |
| history_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
| event_date | DATE | TRANSFORMED: timestamp UTC → calendário local; ver definição do modelo |
| sessions | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| product_views | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| add_to_cart | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| checkout_started | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| purchase | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| sessions_with_cart | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| sessions_cart_then_checkout | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| sessions_cart_checkout_purchase | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| sessions_with_purchase | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| events_without_session | INT64 | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| session_to_cart_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| cart_to_checkout_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| checkout_to_purchase_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| session_conversion_rate | NUMERIC | CALCULATED: fórmula e denominador em ANALYTICS_FOUNDATION.md / analytics_kpi_catalog.json |
| cost_per_session | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| cost_per_add_to_cart | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| cost_per_checkout | NUMERIC | Contrato futuro Meta/ATTRIBUTED; NULL no build atual |
| observation_complete | BOOL | Configuração/cobertura explícita, não inferida da API |
