# Analytics Materialization Readiness

Estado: preparação offline. Nenhuma consulta BigQuery, DDL, migration, build,
Cloud Run, Scheduler ou operação GCP foi executada nesta etapa. As sete tabelas
continuam em `infra/terraform/analytics_proposed`; não foram registradas no Terraform ativo.

## Auditoria da Foundation

| Situação | Constatação e ação |
|---|---|
| Existente | Catálogo de KPIs, sete schemas, referência Python Decimal, regras de qualidade, isolamento por loja e contratos de mídia. Preservados. |
| Lacuna técnica | Scripts SQL com múltiplos resultados não eram unidades completas de validação. Sete SELECTs parametrizados, com projeção completa do schema, foram preparados em `sql/analytics/models/`. |
| Lacuna técnica | `history_complete` não exigia evidência. Agora exige atestado explícito de origem, ausência de lacunas e cobertura até `as_of`. |
| Lacuna técnica | Sem publicação transacional nem plano incremental. Adapter SQLite e runner offline demonstram transação, recibo idempotente, isolamento e fechamento das dependências afetadas. Não são um writer BigQuery. |
| Lacuna técnica | Sem variante/SKU, itens do mesmo asset colapsavam. Agora a chave inclui order/item nesses casos; nenhum mapping é inferido. |
| Decisão comercial | Moeda, status qualificantes, cobertura histórica e de Facts, timezone, limites de atraso/custo e consumidor precisam ser aprovados por loja. Fixtures não são política DEV. |

Nenhum KPI financeiro foi redefinido. `total`, `fulfilled_total` e `payment_status`
não se tornam receita paga. O catálogo de KPIs e schemas existentes permanece vigente;
a atualização da chave de produto e o contrato de policy abaixo complementam a documentação anterior.

## AnalyticsPolicy

`src/analytics/config.py` exige store_id, policy_version, reporting_timezone,
currency, qualifying_order_statuses, history_complete, facts_complete, as_of,
report_from, report_to e history_from. Datas do relatório são locais, intervalo
semiaberto e dias fechados. `as_of` e history_from são instantes explícitos.
Não há default de loja, status ou moeda no contrato de materialização.

O hash semântico inclui versão do motor, policy_version, store, timezone, currency,
status ordenados/deduplicados e allow_unknown_currency_local. Não inclui janela,
as_of ou atestado de cobertura. Mudança de cobertura/history_from exige rebuild
explícito do mesmo store/policy; mudanças semânticas usam hash diferente.
A inclusão de policy_version e permissão de moeda ausente muda o hash em relação
à Foundation anterior. Como não há tabelas analytics materializadas, não há migration;
qualquer resultado offline antigo deve ser regenerado. Não misturar hashes antigos.

Os status CONFIRMED/SHIPPED na fixture são exemplos sintéticos, não decisão de
produção. Status afetam primeira compra, new/returning, LTV, sequência/frequência,
cohort, retenção e distribuição. CANCELED é proibido na lista qualificante, mas
continua em pedidos/receita gerados e cancelados conforme KPIs financeiros existentes.

`history_complete=true` exige HistoryCoverage com store, origin_at,
verified_through >= as_of, evidence_ref, confirmed_by, origin_confirmed=true e
gaps_checked=true. history_from não pode começar depois da origem atestada.
O código valida o contrato; a veracidade da evidência exige revisão humana.
Não registrar nomes de revisores/evidências em logs. Setembro completo, Customers
presentes ou backfill bem-sucedido não provam ausência de compras anteriores.
Com false: new_customers=NULL, classificação first_observed e limitações explícitas
nas métricas dependentes de origem. facts_complete é independente.

Moeda ausente bloqueia por padrão. `currency=null` só é aceito junto de
`allow_unknown_currency_local=true`: cálculo apenas na fonte local, currency NULL,
warning currency_missing, nenhum CAC/ROAS cross-source publicado. Moeda vazia não
é configuração válida. O contrato de mídia existente exige moeda explícita e
escopos compatíveis; divergência de moedas bloqueia junção. Não há FX.

## Runner e segurança da publicação

```bash
python -m src.analytics.offline \
  --fixture tests/fixtures/analytics_readiness/synthetic.json \
  --sqlite /tmp/up-analytics-synthetic.sqlite
```

Repita o comando para testar o recibo idempotente. Para outro snapshot sintético,
use `--previous-fixture CAMINHO_ANTERIOR`; `--full-refresh` é uma decisão explícita.
Este comando é local e não materializa BigQuery. Não fornecer exports de clientes
à fixture versionada. SQLite contém resultados e deve permanecer fora do Git.

Entradas: somente snapshots CORE de Orders, Customers, Order Items e Analytics
Events. Sem RAW e sem mutação das entradas. Uma transação publica os sete recortes,
head e recibo. Uma falha intermediária reverte tudo. Falha após commit com perda
de resposta recupera o recibo sem duplicação. Compare-and-swap de geração rejeita
publicação concorrente baseada em estado antigo. Snapshot anterior deve corresponder
ao hash de revisão publicado. `as_of` regressivo é bloqueado.

O adapter mantém uma versão corrente por chave store/policy/model/row_key. Dois
hashes nunca sobrescrevem um ao outro. Recibo de execução antiga retorna o resultado
antigo, sem restaurar dados antigos sobre publicação posterior. Metadados as_of nas
linhas não afetadas continuam refletindo sua última recomputação; não representam
um snapshot global homogêneo. Consumidor deve observar freshness/manifest antes de
comparar resultados. O recibo/head local é simulação operacional, não proposta de
três novas tabelas BigQuery.

Limite atual: a referência aceita até 100 mil linhas por entrada; a detecção de
mudanças compara snapshots locais completos. Isso não é arquitetura de full scan
para milhões de Facts. O futuro reader precisa fornecer mudanças delimitadas mais
lookups de histórico/cohort completos, com watermark consistente. Não existe conexão
cloud nem writer de produção. A validação incremental prova a semântica dessas
unidades, não throughput de produção. Intervalos esparsos podem gerar dias
intermediários em memória antes da seleção final.

## Incrementalidade e contrato físico

Em todas as tabelas, physical key = store_id + policy_hash + business grain.
row_key = SHA256 do JSON canônico [store, policy_hash, discriminador, dimensões].
Sem upsert por cliente global, asset global ou dia global. O discriminador e as
dimensões exatas constam em engine.py/sql_models.py. A paridade BigQuery do hash
(inclusive serialização Unicode) permanece requisito de aceitação.

| Modelo (`analytics_`) | Business grain | Partition; clustering | Reprocessamento e publicação futura | Consumidor |
|---|---|---|---|---|
| store_daily | dia local | order_date; store_id, policy_hash | Substituir recortes dos dias afetados, mantendo outras lojas/policies. Status, valor, customer e primeira compra podem afetar dias antigos. | Receita/pedidos diários |
| customer_metrics | customer_id | sem partition; store_id, customer_id, policy_hash | MERGE por cliente com remoção restrita dos clientes afetados sem compra qualificante. Recalcular lifetime completo, inclusive vencimento de janelas LTV. | Customer 360/LTV observado |
| customer_purchase_sequence | order_id | order_date; store_id, customer_id, policy_hash | Substituir sequência completa dos clientes afetados; deletar somente linhas obsoletas desse conjunto. Compra antiga renumera compras posteriores. | Frequência e jornada de compras |
| cohorts | cohort_month + months_since_first_purchase | cohort_month; store_id, months_since_first_purchase, policy_hash | Substituir cohorts antiga e nova inteiras, com todos os membros e spine mensal. Tick mensal fecha/abre períodos. | Retenção/cohort |
| purchase_distribution | cohort_month + purchase_bucket | cohort_month; store_id, purchase_bucket, policy_hash | Substituir distribuição completa das cohorts afetadas, inclusive denominador original. | Recompra |
| products_daily | dia + product_key | order_date; store_id, product_key, policy_hash | Substituir dia afetado por alteração de pedido/item/snapshot; não somar novamente após retry. | Mix/volume bruto de itens |
| funnel_daily | dia local do evento | event_date; store_id, policy_hash | Substituir dia antigo/novo dos Facts alterados, lendo todos os eventos das sessões desse dia. | Funil observado por session-day |

MERGE futuro exige fonte deduplicada, staging validado e remoção dos ausentes
**restrita** ao conjunto afetado. MERGE apenas com INSERT/UPDATE deixa compras
canceladas e cohorts obsoletas. Nunca `CREATE OR REPLACE TABLE`, TRUNCATE global ou
DELETE sem store+policy+escopo. Alternativa: DELETE de recortes + INSERT dentro de
uma transação BigQuery. Validar atomicidade com staging/manifest e marcador de
publicação; leitores só devem consumir geração completa. Isso será implementação
separada, após dry-run/paridade e revisão de permissões. Nenhum DML foi preparado
para execução automática nesta etapa.

Watermark proposto: posição de alteração observada/persistida no CORE (timestamp
mais desempate estável), não apenas created_at. Capturar high-watermark fechado,
ler com sobreposição e deduplicar por entidade/versão; avançar somente após publicação.
O CORE atual e seu mecanismo de versões precisam ter o reader auditado antes dessa
integração: ausência de updated_at não pode ser substituída silenciosamente por
created_at. Deleções e reatribuições exigem versão anterior ou índice de dependências.

| Modelos | Watermark/lookback proposto |
|---|---|
| store_daily/products_daily | Alterações de Orders/Items/Customers + janela de sobreposição operacional; expandir dias original e novo e dependências de primeira compra. |
| customer_metrics/purchase_sequence | Mesmas alterações, lookup do histórico completo dos clientes afetados; nenhuma janela fixa limita lifetime. Acrescentar maturidade 30/60/90/180/365 dias. |
| cohorts/purchase_distribution | Cohorts antigas/novas dos clientes afetados e todos os seus membros; tick mensal. Nenhum lookback fixo elimina essa expansão. |
| funnel_daily | Alterações de Facts + sobreposição de chegada; ocorrido fora do lookback continua invalidando seu dia. Ler session-day completo. |

O número de dias de sobreposição é decisão operacional baseada no atraso medido,
não garantia de completude. Até existir feed confiável, reconciliação periódica
limitada/aprovada é necessária. Lookback de mídia será independente (restatements
Meta), sem conexão nem suposição de mesmo atraso da UP Zero.

## Produto e pagamento

Com variant_id/SKU disponíveis, a chave preserva asset/variant/SKU. Cores/tamanhos
não são inferidos por nome: variante distinta permanece distinta. Sem variant_id
e SKU, acrescenta order_id/item_id à chave e emite product_variant_unknown.
Isso prefere granularidade auditável a consolidar variantes desconhecidas. Sem
mapping explícito, nenhum asset vira product_id universal.

revenue_paid, average_order_value_paid, roas_paid e ltv_paid permanecem NULL.
Habilitação futura exige ledger com store, identificador estável de transação,
order_id, moeda, valores capturados/liquidados/estornados, tipo/status da operação,
datas efetivas e histórico de atualização; suportar pagamentos parciais, múltiplos,
reembolsos e chargebacks. Solicitar endpoint de transações/pagamentos e eventos de
estorno com paginação e incremental documentados à UP Zero. Não há endpoint novo
presumido aqui. Reconciliar ledger com pedidos antes de liberar métricas pagas.

## Paridade e comandos futuros — NÃO executados no GCP

A preparação local gera sete expected outputs Python, schemas, parâmetros e dois
requests por modelo. Os golden outputs versionados são exclusivamente sintéticos.
Checks locais verificam schema completo, comandos somente SELECT, duplicação,
resultados Python e contratos. Não interpretam SQL nem provam semântica BigQuery.

```bash
python -m src.analytics.parity prepare \
  --fixture tests/fixtures/analytics_readiness/synthetic.json \
  --output /tmp/up-analytics-readiness
```

No Cloud Shell, após autorização separada e instalação das dependências do projeto,
executar a lista exata abaixo. A fixture usa loja sintética e status ilustrativos;
valida schema, não custo representativo da MX Fashion. Para estimar custo real,
substituir policy por configuração aprovada e manter fixtures sem dados reais.

```bash
export ANALYTICS_FIXTURE=tests/fixtures/analytics_readiness/synthetic.json
export ANALYTICS_VALIDATION_DIR=/tmp/up-analytics-readiness
analytics_dry_run() {
  python -m src.analytics.parity dry-run \
    --fixture "$ANALYTICS_FIXTURE" --output "$ANALYTICS_VALIDATION_DIR" \
    --model "$1" --allow-gcp --confirm-project up-data-intelligence-dev \
    --maximum-bytes-billed 1000000000
}
analytics_dry_run analytics_store_daily
analytics_dry_run analytics_customer_metrics
analytics_dry_run analytics_customer_purchase_sequence
analytics_dry_run analytics_cohorts
analytics_dry_run analytics_purchase_distribution
analytics_dry_run analytics_products_daily
analytics_dry_run analytics_funnel_daily
```

O cliente usa explicitamente project=up-data-intelligence-dev,
location=southamerica-east1, standard SQL, cache desabilitado e dry_run=True.
Cada saída informa model, mode, bytes_processed estimados e schema se retornado.
Erros de campo/tipo/parâmetro terminam o comando com erro. Schema ausente no retorno
não é prova de schema correto. Dry-run não materializa, nem prova resultados ou
validações de dados. Se bytes estimados forem zero pela loja sintética, não concluir
custo zero de produção. IAM futuro: bigquery.jobs.create no projeto e leitura
restrita dos quatro COREs usados; não é necessário conceder escrita analytics para
estes SELECTs. Nenhuma permissão foi alterada.

Parâmetros: store STRING, timezone STRING, currency STRING nullable, policy_hash
STRING, purchase_statuses ARRAY<STRING>, history_from/as_of TIMESTAMP,
date_from/date_to DATE, history_complete/facts_complete BOOL. Todos são derivados
da policy explícita. Requests ficam em /tmp, não contêm credentials.

Depois dos sete dry-runs, a comparação efetiva usa quatro parâmetros JSON sintéticos
(fixture_orders/customers/order_items/analytics_events) em vez de ler CORE:

```bash
for model in analytics_store_daily analytics_customer_metrics analytics_customer_purchase_sequence analytics_cohorts analytics_purchase_distribution analytics_products_daily analytics_funnel_daily; do
  python -m src.analytics.parity parity \
    --fixture "$ANALYTICS_FIXTURE" --output "$ANALYTICS_VALIDATION_DIR" \
    --model "$model" --allow-gcp --confirm-project up-data-intelligence-dev \
    --maximum-bytes-billed 1000000000 || break
done
```

Este último comando EXECUTA SELECT no BigQuery, podendo gerar cobrança; requer
nova autorização. Não cria tabelas persistentes. Compara todas as colunas/chaves,
NULL, Decimal, datas e instantes; divergência gera analytics_parity_failure sem
imprimir linhas/PII. Resultado verde de Python contra golden não substitui este passo.
O manifest de preparação sempre mantém bigquery_validated=false; guardar evidência
dos sete resultados remotos com commit/hash da fixture para aprovação posterior.

## Observabilidade e qualidade

Eventos analytics_execution_started, analytics_model_started,
analytics_model_finished, analytics_quality, analytics_execution_finished.
Policy hash, janela e as_of acompanham os eventos. rows_read é a soma dos registros
selecionados dos quatro COREs para cálculo da execução; não é bytes escaneados nem
soma das leituras repetidas por modelo. Por modelo: rows_generated/inserted/updated/
deleted/failed. Contadores de publicação só saem após commit. bytes_processed=NULL
no adapter local, nunca zero inventado. Falha de sistema com quantidade desconhecida
usa rows_failed=NULL. Recibo idempotente retorna o relatório original sem nova escrita.
Logs não contêm registros, customer/order IDs, reviewer, URLs, valores de credenciais
ou conteúdo de fixtures. Futuro reader deverá informar bytes reais do job.

| Regra | Severidade |
|---|---|
| policy_missing / policy_hash_mismatch | blocking |
| history_coverage_unknown | warning quando false; blocking para alegação complete sem evidência |
| currency_missing | warning com permissão local explícita; blocking nos demais casos |
| analytics_model_stale | blocking para as_of regressivo; SLA de atraso permanece decisão operacional |
| analytics_materialization_duplicate_key | blocking |
| analytics_parity_failure | blocking para aprovação da materialização |

As regras existentes e o quality gate da ingestão permanecem preservados.

## Checklist antes de materializar DEV

1. Aprovar policy real por loja: moeda, timezone, status, versão, janelas, as_of,
   origem/evidência ou history_complete=false e cobertura de Facts.
2. Aprovar fonte do watermark, tratamento de deleção e limite/SLA de atraso;
   definir orçamento e tamanho de unidades de processamento.
3. Executar suite local, lint, formatting, mypy e diff-check no commit publicado.
4. Autorizar separadamente e executar os sete dry-runs; revisar schema e estimativas.
5. Autorizar e executar sete SELECTs sintéticos; exigir paridade integral. Ampliar
   matriz com cenários de timezone, NULL, cancelamento e atraso antes de produção.
6. Implementar/revisar reader incremental e writer BigQuery transacional com staging,
   commit marker, retry/CAS e métricas, sem alterar ingestão em andamento.
7. Revisar Terraform/schema propostos e IAM em plan separado. Sem remover/recriar CORE.
8. Aprovar criação das tabelas e execução inicial analytics em etapa independente.
9. Só então autorizar migration/build/deploy/materialização; verificar freshness,
   isolamento por store/policy, custos e reconciliação. Meta e métricas pagas permanecem
   bloqueadas até suas próprias evidências/contratos.
