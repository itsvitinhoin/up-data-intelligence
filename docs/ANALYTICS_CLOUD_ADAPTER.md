# BigQuery Analytics Cloud Adapter — offline readiness

Esta entrega contém código com cliente injetado, fakes, SQL/DML e Terraform proposto.
Nenhuma consulta, DDL, DML, migration, operação GCP, build, deploy, execução de Job,
Scheduler ou backfill foi realizada. Não foram alterados AnalyticsPolicy, policy_hash,
status, moeda, history_complete, LTV, cohorts, funnel ou grain de produto.

## Implementação

- `src/analytics/cloud/transport.py`: recebe cliente, nunca cria credenciais/client.
  Project/location explícitos, timeout, maximum_bytes_billed por consulta, cache
  explícito, limite de linhas por unidade (100 mil por padrão), métricas de bytes,
  duração e registros lidos. Unidade maior falha, não retorna resultado truncado.
- `reader.py`: quatro COREs com projeções mínimas do contrato SQL existente,
  store obrigatório, parâmetros tipados e `FOR SYSTEM_TIME AS OF @snapshot_at`.
  Partition pruning por range temporal em leituras por dias; histórico de cliente
  precisa consultar desde history_from, e tem custo distinto de ler um dia.
  BigQuery time travel fora da retenção falha; não substitui silenciosamente pela
  versão atual. Nenhuma coluna pessoal de perfil/email/telefone/documento é selecionada.
- `expand_dependencies`: reutiliza exatamente o planner aprovado sobre closures
  anterior/nova completas. Não usa um delta isolado como histórico de cliente.
  Reader recupera Orders por cliente/dias, Customers desses pedidos, Items pelos
  pedidos e Facts dos dias afetados, sempre no mesmo snapshot.
- `writer.py`: staging TEMP em sessão, INSERTs parametrizados por chunks de até
  500 KB de JSON por padrão (limite configurável 1 KB–1 MB), validação, transação
  única dos sete modelos e receipt/head. Linha individual acima do limite bloqueia.
- `runner.py`: composição reader → engine aprovado → findings → writer. Nenhuma
  lógica financeira é implementada no writer. Recebe plano/generation explícitos;
  não ativa detecção incremental autônoma nem cria recursos.
- `src.analytics.job`: entrypoint futuro. `--dry-run` significa **preparar SQL
  localmente**, não BigQuery dry-run. `--live` é sempre rejeitado nesta entrega,
  inclusive com project/store confirmados. Não existe factory live nem acesso a secrets.

Exemplo local com policy sintética (não cria SQLite, não acessa BigQuery):

```bash
python - <<'PY'
import json
from pathlib import Path
fixture = json.loads(Path('tests/fixtures/analytics_readiness/synthetic.json').read_text())
Path('/tmp/analytics-policy-synthetic.json').write_text(json.dumps(fixture['policy']))
PY
python -m src.analytics.job \
  --store synthetic-store --policy /tmp/analytics-policy-synthetic.json \
  --from 2026-03-01 --to 2026-03-03 --as-of 2026-04-02T12:00:00Z \
  --project up-data-intelligence-dev --location southamerica-east1 \
  --maximum-bytes-billed 1000000000 --timeout-seconds 300 \
  --dry-run --output /tmp/analytics-cloud-proposal
```

O CLI futuro deverá exigir `--live`, `--confirm-project` e `--confirm-store`
compatíveis, policy aprovada e geração verificada. Hoje nenhuma combinação habilita
live. Não executar manualmente os SQLs preparados nesta etapa.

## Auditoria de mudanças no CORE

Evidência: `src/bigquery/catalog.py` e `src/ingestion/engine.py`.

| Fonte | Campos existentes úteis | Limitação |
|---|---|---|
| Todos os quatro COREs | observed_at, source_updated_at, version_id, raw_record_id, run_id, payload_hash, transform_version | observed_at é atribuído a raw.ingested_at; não é commit time. version_id é hash, não sequência temporal. |
| orders | created_at, updated_at | updated_at é da fonte; guarda contra versões antigas/conflitantes. Não cobre commits atrasados nem outras entidades. |
| customers | metadados comuns | Sem updated_at de domínio no schema CUSTOMER. Não inventar esse campo. |
| order_items | order_created_at, parent_order_version_id, present_in_latest_snapshot | Relação com snapshot pai; alterações/remoções não são detectáveis por order_created_at. |
| analytics_events | occurred_at + metadados comuns | occurred_at é tempo do evento, não chegada/alteração. |
| *_versions | mesmas entidades, partition observed_at | Retém versões; replay de payload idêntico pode ser ignorado. Não constitui log sequencial de commits/tombstones. |
| sync metadata | runs/checkpoints de ingestão | Não define snapshot transacional fechado e homogêneo dos quatro recursos para Analytics. |

`reader.candidates()` consulta versões pelo intervalo observado semiaberto e
snapshot fixo; retorna **candidatos**, não garantia de change capture completo.
Um RAW antigo promovido ao CORE depois do watermark pode ter observed_at anterior
à faixa seguinte. Time travel estabiliza leituras concorrentes, mas não resolve
essa lacuna do watermark. Nenhum código avança checkpoint de ingestão.

`SourceGeneration` exige snapshot_at explícito e hash opaco do manifesto da fonte.
Incrementalidade exige completeness_confirmed=true, uma atestação externa, não
uma conclusão inferida dos candidatos. Full refresh só com autorização explícita
pode operar sem essa atestação. Isso não altera history_complete: geração coerente
agora não comprova histórico comercial desde a origem.

Proposta futura, **não criada nem inserida no Terraform**: índice técnico de mudanças
CORE com commit generation, store, resource, entity key, previous/new version,
previous/new dependências, tombstone e estado do commit. IDs de entidades seriam
restritos nesse índice, nunca logs. O manifesto de geração seria publicado somente
após todos os lotes CORE associados estarem persistidos. É preciso decidir como
integrar essa publicação aos commits atuais de ingestão sem interromper o backfill.
Até lá: reconciliação explícita/snapshot completo autorizado ou geração certificada
externamente; sem promessa de CDC exactly-once a partir de observed_at sozinho.

## Dependências e limites

Order alterado expande dias financeiros antigos/novos, clientes antigos/novos,
histórico completo desses clientes, cohorts antiga/nova e **todos os membros** das
cohorts, sequência, distribuição e produtos. Fact tardio expande seu dia local e
session-day inteiro. Customer alterado expande pedidos/histórico dependentes.
O planner aprovado também considera maturidade de LTV e mudança de mês.

O provider de mudanças deve fornecer ambas as closures completas; `history_closure_confirmed`
é obrigatório. O adapter não descobre silenciosamente peers ausentes a partir de
um delta parcial. Esse provider/índice de dependências é bloqueio de ativação
incremental autônoma. Uma vez conhecido o conjunto completo, o reader lê apenas
clientes/dias/pedidos afetados e o writer publica apenas os recortes planejados.
Custos de lookup histórico continuam sujeitos ao teto por query. Limite por query
não é orçamento total de um job: várias queries/chunks somam custos.

Se uma unidade exceder 100 mil linhas, orçamento ou tamanho de parâmetro da API,
falha antes da publicação; o coordenador futuro deverá dividir por unidades com
closure completa, sem dividir arbitrariamente uma sequência/cohort. Não há
throughput de milhões de eventos comprovado por fakes. Essa validação faz parte
da ativação. Não há SELECT *, acesso RAW ou alteração CORE.

## Publicação e idempotência

Única tabela técnica adicional proposta: `up_analytics.analytics_publications`.
Dois tipos de registro:

- HEAD: singleton pré-provisionado por store/policy, generation corrente e último
  publication_id. Não se auto-inicializa no writer. Inicialização deve ocorrer sob
  exclusão externa/manual; BigQuery não impõe UNIQUE/PRIMARY KEY.
- RECEIPT: publication_id, store/policy, generation, as_of, janela, started_at,
  finished_at, status completed, analytics_version, source_watermark (hash), models,
  row_counts JSON e bytes_processed nullable. Nenhum customer/order ID ou PII.

publication_id é hash de policy explícita, source generation/snapshot e affected
scope canônico. expected_generation não entra na identidade: retry/reconciliação
identifica a mesma publicação. O producer deve manter geração imutável; não reutilizar
o mesmo hash para fontes diferentes.

Staging é temporário e não visível ao consumidor. Chunks não são retomados isoladamente:
falha recria sessão/staging. Duplicate key é rejeitada, inclusive duplicata idêntica;
não existe deduplicação arbitrária de valores conflitantes. A validação exige schema
completo, key não vazia, grain único, store/policy/moeda coerentes, scope correto e
zero findings blocking. Casts tipados em staging também rejeitam tipos incompatíveis
antes do DML nos destinos. ASSERTs SQL repetem guardas de scope/chave/grain.

A transação verifica exatamente um HEAD e generation esperado, rejeita as_of
regressivo, substitui sete recortes, incrementa HEAD via compare-and-swap e insere
receipt. Conflito transacional ou geração antiga exige replanning; não há retry
cego do COMMIT. Uma falha no script reverte DML, e a sessão é encerrada (expiração
é fallback de limpeza). Falha depois do commit é reconciliada por receipt com
store/policy/publication_id exatos. Recibo já existente impede nova escrita.

Job IDs são únicos por tentativa; `job_retry=None` é explícito. Idempotência é do
receipt transacional, não do nome do job. Não se tenta reexecutar job falho com o
mesmo ID. Timeout ambíguo não significa rollback confirmado: retry primeiro procura
receipt; se necessário, conflito de geração/BigQuery impede dois commits concorrentes.

bytes_processed total ainda é desconhecido dentro do próprio COMMIT, portanto
permanece NULL no receipt. `bytes_processed_before_commit` registra medições já
conhecidas do transport writer; `commit_job_id` permite auditoria posterior do job.
Não somar esse campo como total completo nem incluir leituras do reader por suposição.
Métricas de job conhecidas ficam também nos eventos pós-commit; contador desconhecido
permanece NULL. started_at do receipt marca início da submissão do commit; logs
publication_started cobrem a fase de staging anterior. Falhas sem commit ficam em
logs, não geram receipt completed. As linhas HEAD não são receipts consumíveis.

## DML por modelo

| Modelo | Recorte substituído | Obsoletos removidos |
|---|---|---|
| store_daily | dias locais afetados | Linhas dos mesmos store/policy/dias |
| customer_metrics | clientes afetados | Cliente sem compra qualificante remanescente |
| customer_purchase_sequence | sequência inteira dos clientes afetados | Pedidos cancelados/reassociados |
| cohorts | cohorts afetadas completas | Cohort antiga/spine obsoleto |
| purchase_distribution | cohorts afetadas, todos os buckets | Distribuições antigas |
| products_daily | dias afetados, todos os product grains do dia | Variantes/linhas removidas do snapshot |
| funnel_daily | event_date afetado, session-day completo | Agregados antigos do dia |

Full refresh substitui a fatia completa store/policy dos modelos sem scope limitado;
modelos diários usam os dias explicitamente fornecidos. Incluir também dias já
publicados fora da janela quando a intenção for rebuild integral. O adapter não
apaga silenciosamente outras partições. Nunca TRUNCATE/global DELETE/CREATE OR
REPLACE de destino. DELETE + INSERT tem a semântica de rebuild dos contratos
aprovados; contadores distinguem inserção/alteração/remoção lógica, não apenas
linhas fisicamente reinseridas.

SQL versionado em `sql/analytics/cloud_proposed/`: staging, publicação e proposta
isolada de inicialização HEAD. Ainda não executado/validado no BigQuery. Os fakes
simulam a atomicidade esperada, não interpretam SQL nem provam comportamento real
de concorrência/transações do serviço.

## Terraform e IAM propostos

`infra/terraform/analytics_proposed/cloud.tf` é uma raiz independente, sem referência
no Terraform ativo. Propõe as sete tabelas existentes + publications (sem recriar
dataset), deletion protection/prevent_destroy, service account Analytics, leitura
nas quatro tabelas CORE e quatro versões, escrita nas oito tabelas analytics e
jobUser no projeto. Permissões de escrita são por tabela, sem dataEditor em CORE/RAW.
Não concede acesso a secrets Meta/UP Zero, Artifact Registry writer ou admin de projeto.

Job e Scheduler dependem de enable_job_proposal=false por padrão. Scheduler pausado;
Job contém somente `--help`, portanto não é um deployment funcional pronto para
ativar. Imagem é variável obrigatória; não altera digest DEV existente. Invocador
do Scheduler tem somente run.invoker nesse Job. Nenhum recurso proposto foi criado.
Provider 8.4.0/Terraform ~>1.16.0 acompanham a raiz atual; validação Terraform desta
proposta depende da ferramenta/provider e está pendente (Terraform não disponível
no PATH nesta etapa). Não houve init/plan/apply.

**Limite de segurança:** dataViewer por tabela permite ler todas as colunas dessa
tabela, embora o reader selecione somente as necessárias. IAM BigQuery comum não
implementa allowlist de colunas por SELECT. Se for requisito de autorização estrito,
aprovar authorized routines/views ou policy tags/dataset de exposição separado,
com leitura consistente por snapshot. Não colocar authorized views editáveis pela
mesma conta writer: isso permitiria ampliar a projeção. A proposta IAM atual NÃO
é prova de isolamento de colunas e essa decisão bloqueia ativação sob tal requisito.
Nenhuma mudança IAM existente foi feita.

## Observabilidade e testes

Preservados execution_started/model_started/model_finished/quality/execution_finished.
Adicionados publication_started/publication_committed/publication_reconciled.
Campos permitidos incluem publication_id, store, policy, model, affected_scope_count,
rows_read/generated/failed, bytes/duration. row_counts do receipt contém inserted,
updated e deleted por modelo; métricas de linhas já existentes não são inferidas do
número de INSERTs do script. Clientes/pedidos, URLs, payloads e secrets não são logs.
Failures desconhecidas usam rows_failed=NULL. Relatórios de fakes só usam fixtures
sintéticas versionadas; nenhum export real foi incorporado.

Testes cobrem parâmetros/projeção/pruning, store/policy, teto de bytes, falha de
leitura, staging inválido, transação/rollback/retry, perda de resposta, geração
obsoleta, remoção de linhas, sequência, mudança de cohort, variante, Fact tardio,
full refresh explícito, bloqueio live e ausência de DML CORE/RAW/global DELETE.
Os testes anteriores preservam semântica de negócio. Paridade BigQuery e execução
real concorrente continuam pendentes, conforme `ANALYTICS_MATERIALIZATION_READINESS.md`.

## Checklist de ativação — ordem futura

1. Autorizar e validar dry-run dos sete SELECTs Analytics; orçamento/location/schema.
2. Autorizar e validar Python ↔ BigQuery parity sintética; validar staging/DML em
   tabelas isoladas, rollback, conflito concorrente e lost acknowledgement.
3. Aprovar AnalyticsPolicy MX Fashion (status/moeda/cobertura/as_of), estratégia de
   generation/closure, orçamento e limite de unidade. Resolver segurança por coluna.
4. Revisar plan e ativar os schemas analytics no Terraform, sem recreação CORE.
   Provisionar HEADs uma única vez sob exclusão; não inicializar durante concorrência.
5. Criar IAM Analytics mínimo aprovado. Validar leitura restrita e negações de write
   CORE/RAW e secrets; revisar requisitos de time travel e dados protegidos.
6. Após autorização, build da imagem com adapter/CLI live revisado e guards explícitos.
7. Deploy do Job Analytics com imagem imutável, policy e confirmações aprovadas.
8. Materialização sintética isolada; testar retries, receipts, contagens e orçamento.
9. Materialização DEV real delimitada, geração fechada e backfill preservado.
10. Quality/reconciliação, freshness, custos e observabilidade antes de liberar consumo.
11. Somente após aprovação separada habilitar Scheduler; neste código permanece pausado.

Parado antes de qualquer GCP/build/deploy/migration. Commit/push publica somente
código e propostas; não é autorização de ativação.
