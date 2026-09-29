# MX Fashion DEV — policy oficial e provisionamento de tabelas

Aprovação comercial recebida nesta etapa; dry-run e paridade Python/BigQuery 7/7
informados pelo responsável. Nenhuma operação GCP foi executada nesta preparação.

Policy não secreta: `config/analytics/mx-fashion.dev.json`.

```text
policy_hash = 3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c
```

Store mx-fashion, versão 1.0.0, timezone America/Sao_Paulo, moeda BRL.
Compras qualificantes: RESERVED, CONFIRMED, PROCESSING, INVOICED e SHIPPED.
CANCELED fica fora de primeira compra, sequência, frequência, recompra, LTV,
cohort, retenção e distribuição; permanece nos KPIs financeiros/cancelamento já
implementados. Nenhuma regra de cálculo foi modificada.

- history_complete=false: não existe evidência de histórico comercial desde a origem.
- history_from=2026-09-01T00:00:00Z, exatamente como aprovado.
- report_from=2026-09-01; report_to=2026-09-28 exclusivo.
- as_of=2026-09-28T03:00:00Z, meia-noite local no limite superior.
- facts_complete=true **somente para esse intervalo local fechado aprovado**.
- history_coverage=null e allow_unknown_currency_local=false.

Cobertura do relatório: 01/09 a 27/09 locais. Dia 28/09 não incluído: o término
informado do backfill, 2026-09-29T00:00:00Z, equivale a 28/09 às 21h locais.
Não estender facts_complete=true a novas janelas sem revisão de cobertura.
Setembro completo não comprova origem histórica; new_customers continua NULL e
classificação inicial continua first_observed conforme contrato existente.

## Promoção exclusivamente de tabelas

O gerador `python -m src.bigquery.schema` agora preserva a promoção dos oito
schemas revisados. `src.analytics.provisioning` copia os arquivos propostos byte a
byte para `infra/terraform/schemas/`, valida tipos/nomes/partições/clustering e
acrescenta suas definições ao manifesto ativo `infra/terraform/tables.json`.
O catálogo runtime de ingestão continua sem analytics. Meta permanece proposto.

| Tabela | Partition | Clustering |
|---|---|---|
| analytics_store_daily | order_date | store_id, policy_hash |
| analytics_customer_metrics | nenhuma | store_id, customer_id, policy_hash |
| analytics_customer_purchase_sequence | order_date | store_id, customer_id, policy_hash |
| analytics_cohorts | cohort_month | store_id, months_since_first_purchase, policy_hash |
| analytics_purchase_distribution | cohort_month | store_id, purchase_bucket, policy_hash |
| analytics_products_daily | order_date | store_id, product_key, policy_hash |
| analytics_funnel_daily | event_date | store_id, policy_hash |
| analytics_publications | nenhuma | store_id, policy_hash, record_kind |

Todas usam up_analytics existente. Tipos, modos NULLABLE/REQUIRED e grain foram
preservados. A proteção usa `google_bigquery_table.tables` já existente com
`deletion_protection=var.deletion_protection`, cujo default DEV é true.
Não foi alterado main.tf nem criado recurso de dataset adicional.

`analytics_publications` será somente tabela vazia: não inicializar HEAD, não
inserir receipt e não executar DML nesta fase.

O root `analytics_proposed/cloud.tf` não deve ser aplicado: continua contendo
propostas de Job/IAM e recursos de tabelas com endereços diferentes. As oito tabelas
agora pertencem exclusivamente aos endereços da raiz ativa abaixo; não criar um
segundo gerenciamento dessas tabelas pela raiz proposta.

## Expectativa para o futuro plan

```text
8 to add, 0 to change, 0 to destroy
```

Somente:

```text
google_bigquery_table.tables["analytics_store_daily"]
google_bigquery_table.tables["analytics_customer_metrics"]
google_bigquery_table.tables["analytics_customer_purchase_sequence"]
google_bigquery_table.tables["analytics_cohorts"]
google_bigquery_table.tables["analytics_purchase_distribution"]
google_bigquery_table.tables["analytics_products_daily"]
google_bigquery_table.tables["analytics_funnel_daily"]
google_bigquery_table.tables["analytics_publications"]
```

Comparação local contra a base: exatamente oito entradas adicionadas; nenhuma
entrada existente removida ou alterada, nenhum schema CORE/RAW/OPS alterado.
DEV.4 digest, configuração UP Zero MX Fashion, schedulers pausados, secrets,
datasets, IAM e Jobs existentes permanecem intactos. Policy JSON não é passada a
nenhum Job nesta fase. Não há nova conta, Scheduler, writer/reader IAM ou CDC.

**A expectativa não é resultado de plan.** State remoto/drift não foram consultados.
Se o futuro plan mostrar qualquer change/destroy/replacement ou recurso adicional,
parar e investigar; não considerar aceitável automaticamente e não aplicar.

Validações locais: policy.from_dict/reference/hash, schemas ativos iguais aos
propostos, regeneração idempotente, testes completos, lint/formatting Python,
mypy e diff-check. Terraform não está disponível no PATH deste ambiente;
fmt-check/validate não foram executados. Nenhum init/plan/apply foi executado.
A ausência dessas verificações Terraform permanece registrada, sem substituir
validate por testes Python.

Após revisão, autorizar separadamente o plan da raiz ativa. Apply, HEAD,
materialização, IAM, Job, Scheduler, build e deploy são etapas posteriores.
