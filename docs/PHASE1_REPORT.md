# Relatório de entrega — Fase 1 Data Foundation

Implementação local concluída em 2026-09-28. Nenhum deploy, terraform plan/apply, secret real, recurso GCP ou requisição UP Zero de produção foi executado. Não houve commit/push no GitHub. O OpenAPI original foi preservado integralmente.

## Implementado

- Python 3.13; conector UpZeroConnector READ-ONLY com somente customers, orders e analytics/facts; X-API-Key, timeout, retry/backoff/Retry-After, erro estruturado e paginação por contrato.
- Sanitização pré-RAW testável, preservando campos comerciais/tracking e redigindo autenticação inclusive em estruturas aninhadas e URLs.
- Store registry e source_connection separados; Secret Manager por referência, sem secret/version criada no Terraform.
- RAW por página com proveniência, hashes e versões; transação de checkpoint antes de normalização.
- CORE tipado com versões de clientes/pedidos/itens/facts; preservação de requested/fulfilled, removed, snapshots e eventos anônimos.
- Parser de landing_url e colunas meta_campaign_id/meta_adset_id/meta_ad_id/meta_adset_name STRING; nenhuma conexão Meta.
- Touchpoints por Fact; event_order_links somente por order_id e loja; identity_links somente por coocorrência observada, sem user_id=customer_id.
- Jobs CLI sync/backfill/reconcile/quality/replay; Cloud Run Jobs sync/reconcile/quality declarados, Scheduler pausado por default.
- Exclusão mútua por loja: flock local e bucket GCS técnico com escrita condicional; sem dados da UP Zero no bucket. Acréscimo necessário para single-writer distribuído.
- Adaptador SQLite offline e BigQuery com MERGEs parametrizados em transação. Replay streaming não carrega run inteiro na memória.
- Terraform para datasets/tabelas, service accounts, IAM restrito, referências de secret, locks e jobs, com variáveis por ambiente/projeto/região/localização.
- README e seis documentos arquiteturais atualizados para RAW sanitizado e escopo efetivamente implementado.

## Testes e verificações

| Verificação | Resultado |
|---|---|
| pytest, suíte completa | **90 testes passando**, zero falhas |
| Cobertura de linhas | **86,82%**, 889/1024 linhas; não é cobertura de branches |
| Ruff check e format | Aprovados |
| mypy strict | Aprovado, 33 arquivos de src |
| Terraform fmt / validate | Aprovados com provider Google 8.4.0 e Terraform 1.16.4 |
| Backfill CLI offline | Executado com fixtures sintéticas, sem rede |
| Auditoria runtime | 33 pacotes, zero vulnerabilidades conhecidas |
| Auditoria ambiente completo | 66 pacotes, zero vulnerabilidades conhecidas; nenhum pacote ignorado |
| Scan de padrões de segredo | Zero correspondências nos arquivos de entrega; revisão de fixtures/config/IaC |
| OpenAPI | SHA-256 inalterado: 47e863d1942ba4074faaace1398e97fb25f3a1c25e3ab65bed01cafe33b21043 |

A rede é bloqueada nos testes. Integração local usa SQLite/MockTransport; testes BigQuery/Secret Manager/GCS usam mocks. Terraform validate não equivale a provisionamento nem valida IAM em um projeto real. Nenhuma execução SQL real, teste UP Zero live ou build/deploy de imagem foi realizado. Auditoria de vulnerabilidade/padrões não é garantia absoluta de ausência de vulnerabilidades/segredos.

Coberturas importantes: paginação completa, loops e falta de progresso; timeout/429/5xx; headers/erros sem secrets; replay/retomada após RAW; isolamento A/B com mesmos IDs; removed e solicitado/atendido; atualização/correção e impedimento de regressão por replay antigo; números JSON canônicos e precisão NUMERIC; encoding/placeholders/duplicidade de parâmetros Meta; vigência configurável de purchase/purchase_item.

## Segurança

Política 1.0.0: campos de autenticação são redigidos antes de qualquer RAW. URL sem segredo permanece igual; parâmetro secreto/userinfo é redigido; recovery_url é bloqueada explicitamente. Não há cópia do corpo original. Hash se refere ao payload sanitizado e números JSON equivalentes são canonicalizados para estabilidade de replay.

Logs contêm apenas metadados allowlisted e códigos de erro. CPF/CNPJ, identificadores e tracking necessários permanecem restritos por IAM; não são classificados como anonimizados. Runtime não concede acesso a BI ou up_analytics. Retenção RAW é variável obrigatória; governança de PII/CORE deve ser definida antes do piloto real. Exclusão/LGPD completa não foi implementada como produto adicional.

## BigQuery

4 datasets em Terraform: up_raw, up_core, up_ops e up_analytics. **20 tabelas**; up_analytics permanece vazio. Nenhum recurso existe por efeito desta entrega.

| Tabela | Partição | Clustering |
|---|---|---|
| up_raw.upzero_customers | ingested_at | store_id, resource |
| up_raw.upzero_orders | ingested_at | store_id, resource |
| up_raw.upzero_analytics_facts | ingested_at | store_id, resource |
| up_core.customers | sem partição | store_id, customer_id |
| up_core.customers_versions | observed_at | store_id, customer_id |
| up_core.orders | created_at | store_id, order_id |
| up_core.orders_versions | observed_at | store_id, order_id |
| up_core.order_items | order_created_at | store_id, order_id |
| up_core.order_items_versions | observed_at | store_id, order_id |
| up_core.analytics_events | occurred_at | store_id, fact_id |
| up_core.analytics_events_versions | observed_at | store_id, fact_id |
| up_core.touchpoints | occurred_at | store_id, session_id |
| up_core.identity_links | observed_at | store_id, source_fact_id |
| up_core.event_order_links | sem partição | store_id, order_id |
| up_core.stores | sem partição | store_id |
| up_core.source_connections | sem partição | store_id |
| up_ops.sync_runs | started_at | store_id, resource |
| up_ops.sync_checkpoints | sem partição | store_id |
| up_ops.quality_results | checked_at | store_id, rule_id |
| up_ops.source_capabilities | sem partição | store_id |

Os schemas físicos estão em src/bigquery/catalog.py, SQL e JSON Terraform sincronizados. RAW=3 tabelas; CORE=13; OPS=4. Não há tabelas de fontes/endpoints adicionais. Capacidade Meta no registry é apenas meta_ad_account_id nullable, sem integração.

## Ingestion

- **Customers:** ID descendente, after_id pelo menor ID, página vazia encerra; incremental atravessa maior ID anterior. Reconcile percorre todo o cadastro para alterações antigas.
- **Orders:** page/total_pages, criação com datas inclusivas na timezone configurada. Lookback de criação, reconsulta por datas dos pedidos abertos e backfill histórico; nunca MAX(updated_at) como cursor de API.
- **Analytics facts:** janela fixa [from,to), cursor, lookback e backfill. Fact corrigido conserva chave por loja+fact_id e cria versão. IDs Meta continuam strings. Nenhum anônimo é descartado por falta de user_id/order_id.

RAW + checkpoint pending antecedem CORE. Query transactions asseguram promoção conjunta de estado, histórico e OPS. Lotes iguais não duplicam corrente. Erro monetário/transformação preserva RAW e resulta em needs_review. Erro de paginação bloqueia progresso e mantém a página problemática. Dados são parâmetros SQL, não interpolação.

## Gaps e limites

1. Sem updated_since, snapshot transacional, retenção e quotas documentados: sincronização incremental depende de reconciliação, sem prometer CDC completo.
2. Correção de purchase/purchase_item.order_id precisa de data por loja, confirmação de backfill e estabilidade de IDs. Até lá, NULL é preservado e mensurado.
3. user_id=customer_id, item de pedido em facts e IDs de conta de mídia não têm evidência suficiente. Nenhum vínculo foi inventado.
4. SQL cloud, permissões IAM, região, disponibilidade da imagem e comportamento real de paginação precisam do teste dev autorizado. Não foram declarados como verificados.
5. Uma transação tem limite preventivo de 8 MB; excesso exige reduzir page_limit. Um registro individual maior que o limite exige estratégia adicional aprovada, sem truncamento automático.
6. Lock cloud não expira sozinho: após crash/timeout, operador confirma ausência de job ativo antes de remover o objeto da loja. Evita dois escritores, mas exige recuperação operacional.
7. Alertas são linhas de qualidade e logs estruturados; não foi configurado canal externo de notificação. Nenhum email/Slack foi enviado.
8. Custos/quotas e throughput de milhões de eventos não foram medidos. SQL de qualidade global e correções podem ler várias partições; piloto deve medir antes de ampliar para 100+ lojas.
9. Retenção CORE/histórico, consentimento e procedimentos de direitos/exclusão exigem governança antes de dados reais. Testes de isolamento não substituem RLS para futuros consumidores multi-tenant.
10. Fact/cliente sem source_updated_at depende da ordem observada; não existe garantia de histórico anterior à coleta. Payloads iguais não produzem cópias de versão desnecessárias.

## Próximo passo — primeiro teste real de uma PILOT_STORE

Fornecer **referências/configuração, nunca a chave no chat/repositório**:

1. Projeto GCP dev autorizado, região Cloud Run e localização BigQuery/GCS, backend Terraform e identidade do operador.
2. store_id, nome/slug, timezone efetiva UP Zero, connection_id e confirmação externa de que a credencial corresponde à loja correta.
3. Nome completo de um secret existente contendo a API Key; conceder acesso à identidade apropriada. A criação/carregamento do secret deve ocorrer por procedimento seguro separado.
4. Imagem construída/revisada por digest e bucket técnico/configuração IAM revisados; aprovação explícita de provisionamento em dev, que não faz parte da execução realizada.
5. Retenção RAW/CORE aprovada, limites de tráfego conhecidos e período pequeno (por exemplo uma hora de facts), além de volume aproximado.
6. Data da correção purchase/purchase_item, se confirmada; senão null. Definir lookback, stale_after_minutes e page_limit conservadores.

Após revisão/provisionamento autorizado, manter Scheduler pausado e executar uma única CLI live com confirmação exata de PILOT_STORE, seguindo o README. Conferir registros sanitizados, contagens, vínculos, qualidade e consumo antes de agendar. Não conectar Meta nem iniciar produção como próximo passo automático.

## Arquivos

[README](../README.md) documenta setup, comandos, configuração e recuperação. Manifesto abaixo lista os arquivos de fonte/configuração/documentação da entrega, excluindo virtualenv, caches, banco local, terraform state/provider e credenciais.

- `.dockerignore`
- `.env.example`
- `.gitignore`
- `Dockerfile`
- `README.md`
- `config.example.json`
- `docs/ARCHITECTURE_PLAN.md`
- `docs/BIGQUERY_SCHEMA.md`
- `docs/DATA_MODEL.md`
- `docs/DATA_QUALITY.md`
- `docs/INGESTION_STRATEGY.md`
- `docs/PHASE1_REPORT.md`
- `docs/SECURITY.md`
- `docs/upzero-openapi.json`
- `infra/terraform/.terraform.lock.hcl`
- `infra/terraform/environments/dev.tfvars.example`
- `infra/terraform/environments/prod.tfvars.example`
- `infra/terraform/environments/staging.tfvars.example`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/schemas/analytics_events.json`
- `infra/terraform/schemas/analytics_events_versions.json`
- `infra/terraform/schemas/customers.json`
- `infra/terraform/schemas/customers_versions.json`
- `infra/terraform/schemas/event_order_links.json`
- `infra/terraform/schemas/identity_links.json`
- `infra/terraform/schemas/order_items.json`
- `infra/terraform/schemas/order_items_versions.json`
- `infra/terraform/schemas/orders.json`
- `infra/terraform/schemas/orders_versions.json`
- `infra/terraform/schemas/quality_results.json`
- `infra/terraform/schemas/source_capabilities.json`
- `infra/terraform/schemas/source_connections.json`
- `infra/terraform/schemas/stores.json`
- `infra/terraform/schemas/sync_checkpoints.json`
- `infra/terraform/schemas/sync_runs.json`
- `infra/terraform/schemas/touchpoints.json`
- `infra/terraform/schemas/upzero_analytics_facts.json`
- `infra/terraform/schemas/upzero_customers.json`
- `infra/terraform/schemas/upzero_orders.json`
- `infra/terraform/tables.json`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `pyproject.toml`
- `requirements.lock`
- `sql/core/analytics_events.sql`
- `sql/core/analytics_events_versions.sql`
- `sql/core/customers.sql`
- `sql/core/customers_versions.sql`
- `sql/core/event_order_links.sql`
- `sql/core/identity_links.sql`
- `sql/core/order_items.sql`
- `sql/core/order_items_versions.sql`
- `sql/core/orders.sql`
- `sql/core/orders_versions.sql`
- `sql/core/source_connections.sql`
- `sql/core/stores.sql`
- `sql/core/touchpoints.sql`
- `sql/ops/quality_results.sql`
- `sql/ops/source_capabilities.sql`
- `sql/ops/sync_checkpoints.sql`
- `sql/ops/sync_runs.sql`
- `sql/quality/reconcile.sql`
- `sql/raw/upzero_analytics_facts.sql`
- `sql/raw/upzero_customers.sql`
- `sql/raw/upzero_orders.sql`
- `src/__init__.py`
- `src/bigquery/__init__.py`
- `src/bigquery/catalog.py`
- `src/bigquery/repository.py`
- `src/bigquery/schema.py`
- `src/config/__init__.py`
- `src/config/settings.py`
- `src/connectors/__init__.py`
- `src/connectors/upzero/__init__.py`
- `src/connectors/upzero/client.py`
- `src/connectors/upzero/fixtures.py`
- `src/domain/__init__.py`
- `src/domain/models.py`
- `src/ingestion/__init__.py`
- `src/ingestion/engine.py`
- `src/ingestion/planning.py`
- `src/jobs/__init__.py`
- `src/jobs/backfill.py`
- `src/jobs/cli.py`
- `src/normalization/__init__.py`
- `src/normalization/entities.py`
- `src/normalization/meta_url.py`
- `src/observability/__init__.py`
- `src/observability/logging.py`
- `src/quality/__init__.py`
- `src/quality/rules.py`
- `src/quality/service.py`
- `src/security/__init__.py`
- `src/security/lease.py`
- `src/security/sanitization.py`
- `src/security/secrets.py`
- `src/utils/__init__.py`
- `src/utils/data.py`
- `tests/conftest.py`
- `tests/fixtures/pilot.json`
- `tests/integration/test_engine.py`
- `tests/unit/test_bigquery_contract.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_cloud_adapters.py`
- `tests/unit/test_connector_security.py`
- `tests/unit/test_parser.py`
- `tests/unit/test_planning_quality.py`
- `uv.lock`
