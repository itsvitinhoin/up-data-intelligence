# CHANGE #03 — arquitetura operacional multi-store (proposta offline)

Status: desenho + modelos executáveis sintéticos, **não conectado ao runtime**.
Não há feature flag live para habilitar acidentalmente: `src/scale` não é importado
pelos entrypoints existentes. Defaults Settings/CLI, policy, schemas, Terraform
ativo, imagens, IAM e schedulers permanecem intactos. Nenhuma chamada cloud.

## 1. Auditoria rastreável do estado atual

| Evidência no código | Comportamento comprovado |
|---|---|
| `src/ingestion/planning.py:incremental` | Lê checkpoints `incremental/complete`, escolhe maior updated_at; Facts começam em max(initial_from, completed_to−72h), terminam em at. Sem checkpoint começa em initial_from. |
| `src/jobs/cli.py:main` | Retoma primeiro pending running/extracted usando filters salvos, depois chama incremental com refresh=True. Nenhum cursor é usado entre consultas distintas. |
| `src/ingestion/engine.py:run` | Chave de plano inclui store, connection, resource, filtros e mode. Sem refresh, plano complete retorna run salvo; refresh ignora checkpoint anterior e refaz consulta. |
| `src/connectors/upzero/client.py:pages` | Facts usam next_cursor; janela from/to fixa, sem OFFSET; cursor repetido/inválido falha. Limite app 1..1000 (default app1000). max_pages=10000, exceder falha, não é completude. |
| `engine.run/promote` | RAW+pending_raw_id+sync_run persistem antes do CORE. Promoção CORE e posição/checkpoint são transacionais. completed_to só no fim; erro de transformação deixa needs_review, não complete. extracted permite finalizar sem refetch. |
| `engine.run` RAW | request_id UUID novo por resposta recebida; raw_record_id=request_id. payload_hash não é usado para dedupe RAW. Payload passa por sanitization: RAW é evidência sanitizada, não cópia de secrets. |
| `engine.transform` | row_key=hash(store, entity ID); payload_hash e transform_version iguais pulam CORE/versões. Mudanças geram versões; proteção de observação obsoleta e updated_at quando disponível. |
| `src/bigquery/repository.py` + AtomicWriter | MERGEs transacionais por lote; transporte grande via session/temp tables. Número de jobs depende do tamanho e staging. Read/find usam store+keys; nem todos incluem filtro de partição temporal. |
| `cli` reconcile | Sem --from: initial_from até at, dividido em janelas diárias para Facts/Orders; customers varredura completa. **Não é somente 72h**. |
| `cli` sync orders | Janela de pedidos de 30 dias + revisita dias de criação dos pedidos abertos. Customers usam high_id, não atualização incremental garantida de perfis antigos. |
| `src/quality/service.py` | `reconcile()` ao fim de sync/backfill/reconcile/replay e em quality explícito. Nome não significa apenas ingestão histórica. Leitura de sync_runs por loja para freshness. |
| `sql/quality/reconcile.sql` | MERGE de todos os Facts da loja para links, UPDATE mesmo sem mudança; depois checks históricos de duplicatas, parser, purchases e pending. Sem filtro temporal. |
| `src/security/lease.py` | Um writer Foundation por store; GCS generation-precondition; não autoexpira. Outcome BigQuery incerto mantém lock; crash exige recuperação operacional. |
| `infra/terraform/main.tf` | Três Jobs/Schedulers para UMA pilot config; não existe dispatcher multi-store. Schedulers aprovados pausados. |

`tests/scale/test_current_audit.py` executa Engine real com SQLite e HTTP fixture:
repetir janela sem refresh não cria RAW; refresh idêntico dobra envelopes RAW,
mas não aumenta CORE nem versões. Retransmissão do pending RAW já salvo pode
reaproveitá-lo; **não é correto dizer que toda tentativa duplica RAW**. Re-fetch
HTTP/refresh novo cria nova observação. Historicamente RAW não será removido.

### Contrato UP Zero

Fonte exclusiva: `docs/upzero-openapi.json`, GET /external/v1/analytics/facts:
from inclusivo requerido; to exclusivo (default servidor agora, mas cliente fixa);
limit default contrato200/max1000; cursor retornado na resposta anterior;
data/total/next_cursor, ID fact `id` e occurred_at. Não usar event_id como chave
substituta: é campo distinto e pode repetir. Auth existente sem novas keys.
O contrato não garante cursor global/CDC, snapshot estável entre páginas, SLA de
late arrival, tombstones, updated-since para Facts ou taxa de requests segura.
Não inferir ordenação imutável pelo exemplo de IDs. Alteração concorrente da fonte
pode afetar paginação; reconciliação e completude precisam de evidência independente.

## 2. Reprocessamento atual e limites da projeção

Para taxa uniforme estacionária, intervalo Δ=0,25h e lookback L=72h:
fast atual observa aproximadamente `1 + L/Δ = 289` vezes o volume único mensal.
Isso é observação, NÃO 289 versões CORE. Clipping por initial_from, falhas, pausas,
bursts e distribuição temporal mudam o resultado real.
Há ainda reconcile diário desde initial_from: com histórico fixo de referência H=30
dias, acrescenta `30×H/30=30` volumes mensais: **319× total Facts**. No primeiro mês
crescendo de zero, aproximação contínua ~15× adicional, e fast também sofre clipping;
319× não é medição do primeiro mês. Com histórico crescente, custo diário cresce.

Proposta fast sem overlap + reconcile72h: `1 + frequency×72/24` = **4×, 7×, 13×**
para 1/2/4x ao dia. A cobertura de atrasos >72h requer deep sweep/exception queue:
a estimativa dessas três opções não inclui um sweep extra de retenção inteira.
Escolha da frequência e cauda histórica fica pendente, não ativada.

## 3. Fast path e reconciliation separados

Fast usa `[last_completed_to, safe_end)`, safe_end=at−margem explicitamente aprovada.
Margem ZERO é cenário de simulação, não garantia de disponibilidade. Medir diferença
entre occurred_at e primeira observação, por loja/source; escolher margem via
quantis mais margem operacional após shadow. Sem watermark inicia em initial_from
num backfill explicitamente autorizado, nunca pula para agora.

Antes de consultar: reservar orçamento, fixar window e run ID, adquirir lock;
retomar o intervalo incompleto antes de criar outro. Cursor fica vinculado à mesma
query/filtros/connection; não reutilizar quando altera janela. RAW antes de CORE,
checkpoint só após persistência de todas as páginas e ausência de erro pendente.
Não reusar diretamente a busca atual de `incremental` checkpoints para o novo modo:
cutover exige watermark validado e namespace/modo separado. Janelas needs_review
não podem ser ignoradas para avançar por cima de um buraco.

Reconcile tem checkpoint independente, revisita intervalos fixos com cursor novo.
Não retrocede/avança fast completed_to. 1x/dia: menor custo, maior atraso para corrigir;
2x/dia: equilíbrio; 4x/dia: menor atraso, mais queries/evidências. Restatements do
mesmo fact_id seguem upsert/versionamento existente. Não presumir que ausência na
resposta significa delete. Cauda >lookback: sweep histórico rotativo, intervalo
solicitado ou feed fonte confiável; registrar coverage manifest e last_deep_scan.
Sem SLA da fonte não declarar ausência de late facts fora da janela: risco exposto
em freshness/completeness e exceções, nunca perda silenciosa declarada como sucesso.

## 4. RAW: nova observação versus payload idêntico

Proposta posterior, sem dedupe físico agora:
- payload blob imutável sanitizado com hash canônico, store/source/connection e
  versões de contrato/sanitização no namespace;
- observation envelope SEMPRE novo com run, request/window/cursor, observed_at,
  bytes/status/paginação e ponteiro para blob;
- hash idêntico só compartilha conteúdo, não apaga ocorrência/auditoria;
- next_cursor/token volátil pode tornar envelope diferente. Medir hash do conteúdo
  separado de metadados, mas preservar ambos; não ordenar data silenciosamente;
- payload hash não é source version. Sem versão garantida, rotular como observação;
- replay resolve envelope→blob e conserva lineage; blob só pode expirar depois de
  TODAS as referências elegíveis, considerando retenção/legal hold;
- checkpoint + envelope + referência precisam de atomicidade e recuperação de
  órfãos. Reuso entre tenants proibido. Sem hash/canonicalização comprovada, guardar.

RAW histórico continua intacto. Reuso futuro demanda schema/migration e aprovação
separada. Estimador default raw_identical_fraction=0; reuso configurado é sensibilidade
hipotética, não economia comprovada. Com janelas/cursors diferentes, hit rate pode
ser baixo mesmo com maioria dos mesmos eventos.

## 5. Quality fast/deep e event_order_links

Fast recebe manifest de chaves alteradas e janelas afetadas, com peers históricos
necessários. Duplicate fact/order/customer: buscar TODOS peers das chaves afetadas,
não apenas linhas do dia. Duplicate event_id: fechamento por event_id, incluindo
NULL conforme regra atual. Parser/purchase checks no conjunto afetado; manter
severidade existente, capability effective_at e resource-scoped gate. Freshness
avalia watermarks separados de ingestão/reconcile/quality, não apenas last run.
Deep executa equivalentes integrais atuais por loja em cadência aprovada, detectando
corrupção/duplicatas fora do conjunto afetado. Fast aprovado não certifica histórico.

Links candidatos: união Facts alterados + Facts referenciando Orders alterados +
pending relevantes (IDs que chegaram ou buckets de retry vencidos). Carregar pedidos
necessários com store/source; recalcular matched/pending/missing_order_id com mesmas
regras. Atualizar apenas se status/order_id/source_version mudou; updated_at passa
a indicar mudança, e evidência de checagem fica no manifest separado. Deep periódico
reconstrói comparação completa, inclusive unmatched fora da janela. Não juntar por
nome, CNPJ inferido, sessão ou campos de tracking.

O modelo offline testa subset closure para duplicatas de Facts/parser e links;
**não é implementação de todos os checks SQL**. Migração exigirá parity de todos os
checks, inclusive duplicate_event_ids/Orders/Customers e severidades, com fixtures
adversariais e dry-runs autorizados. SQL ativo não mudou.

## 6. Orquestração recomendada (não provisionada)

| Opção | Isolamento/latência/falhas | Operação/custo/limite |
|---|---|---|
| A Jobs/Schedulers por loja | Simples, retry isolado; fácil diagnóstico | ~300 agendas/100lojas, configuração/IAM drift; aceita piloto, não preferida para100+ |
| B Dispatcher + workers por store | Fila justa, dispatch limitado, loja lenta não segura lote inteiro | Requer manifest/lease duráveis, dedupe de dispatch, orçamento e reconciliação de execução |
| C Job task_count/overrides | Fan-out por manifest imutável/index, concorrência do Job | Task retries e resultado agregado não substituem ack por store; evita array mutável. Batch lento complica acompanhamento |
| D Tasks/PubSub/Workflows | Fila e coordenação podem desacoplar execução | ACK/entrega repetida, custo e serviços adicionais; task HTTP não equivale a job longo concluído. Workflows útil para dependências, não um workflow por Fact |

Recomendação B: dispatcher pequeno consulta lojas devidas, round-robin persistente,
reservas atômicas e fila durável; workers Cloud Run Jobs por execução/store, imagem
compartilhada, runtime config validada, secrets resolvidos por connection. Scheduler
só acorda dispatcher, não 3×N agendas. Separar lanes fast/reconcile/deep/analytics;
reservar capacidade mínima fast sem starvation do reconcile (aging/deadlines).
Workers longos monitorados por execution status; dispatch aceite não é sucesso.
C é alternativa para lotes homogêneos, após teste de retries por task. Escolha do
backend de fila/coordenação é decisão humana pendente; modelo em memória não é
um lock distribuído. A identidade compartilhada amplia blast radius: opções pools
por grupo/tenant crítico e IAM mínimo precisam revisão antes de implantação.

## 7. Concorrência, rate limits, fairness

Três limites explícitos: global, por fonte e **1 writer por store**. Começar valores
somente após capacidade/rate limits contratados; simulação usa7global/5upzero, não
configuração aprovada. Ingestão, reconcile e link/quality writer da mesma loja
compartilham lock atual. Analytics depende de generation fechada e CAS próprio;
pode ler snapshot fechado, mas não abrir publicação sobre ingestão indefinida.

Budget diário e admission precisam compare-and-set/transação central; locks GCS
por store não implementam limite global. Lease de dispatch e lease de escrita têm
owners distintos; recovery deve verificar execução e jobs BigQuery antes de liberar.
Não introduzir TTL que permita writer zumbi; fencing token seria evolução separada.
HTTP429/retry-after aplica cooldown por connection e global source se indicado;
jitter/backoff bounded, retry budget. Nunca ocupar todos slots com loja em cooldown.
Cancelar/expirar uma tentativa não descarta intervalo: fila mantém pending ou
needs_review, com alerta e backoff. Uma loja lenta não bloqueia admission das outras.

## 8. Medição, labels e budgets

Proposta de ledger append-only por store_token, component, resource, run/job ID,
data UTC, interval, policy/transform version, status e motivo. Dimensões sem PII.
Medir API attempts/pages/records/bytes/retries, RAW envelope/payload bytes, CORE
processed/inserted/updated/failed, Analytics rows, elapsed execution seconds, CPU e
memória alocados, BigQuery bytes processed/billed e cache hit (NULL quando ausente).
Distinguir execução wall time de vCPU-seconds cobrados; métricas de alocação são
estimativas, não fatura. Não somar parent script e child jobs duas vezes.

`safe_job_labels()` prepara labels BigQuery allowlisted/hash store+run, sem PII.
Ainda não injeta labels nos clients ativos. Futura factory aplica a reads, writes,
quality e Analytics, sem omitir queries diretas de service.py. Date vem do job
creation time, não label de alta cardinalidade desnecessária; resolver hash→store
em registry restrito. Job IDs ficam no ledger, run label hash. Medição de bytes
sem stats completos permanece desconhecida, nunca custo zero.

Orçamentos distintos: bytes/dia/store (timezone explícita), bytes/run reconcile,
pages/run, execução wall timeout, tentativas/retries. Reserva conservadora antes
cada query/página; operações ambíguas não devolvem reserva. Guard compartilhado
atômico para stores/pools; reconciliar reservas a posteriori sem dupla contagem.
Per-query maximum_bytes_billed permanece, não substitui agregado. Exhaustion:
`deferred_budget`, checkpoint íntegro, intervalo persistido, alerta, retry_after e
política de aprovação/emergência para ingestão crítica. Não marcar completed nem
pular para próximo intervalo; orçamento insuficiente deve deteriorar SLO visivelmente.
A proposta Budget local testa o contrato, mas não grava ledger nem emite alerta real.

## 9. Analytics e Meta

Initial full refresh mantém guards MX Fashion e publicação única existentes.
Multi-store live NÃO foi habilitado. Evolução: CORE generation fechada por store
com manifest de runs/coverage/checkpoints sem necessidades de revisão, commit ack
conhecido e checks críticos aprovados → enqueue analytics(store,generation,policy).
Coalescer gerações pendentes; só publicar closure completa e manter receipt/CAS.
Não disparar por evento, nem usar observed_at como CDC confiável. Enquanto faltam
change index/old-new dependencies, incremental histórico não é autorizado; backfill
controlado/full refresh continua caminho válido dentro dos limites.

UP Zero fast, Meta Insights horário/diário com backfill de conversões/restatements
independente, Analytics após fontes requeridas pela policy. Meta atrasada não deve
fabricar spend zero nem bloquear modelos que não dependem dela. Nenhuma Meta API,
secret, schema ou cadência Meta foi ativada.

## 10. SLOs para decisão, não valores aprovados

| SLO | Opções | Trade-off / medida |
|---|---|---|
| Fast freshness | <15/<30/<60min | Mais runs versus latência; tempo desde safe_end persistido, não início do Job |
| Late-data reconciliation | <6/<12/<24h | 4/2/1x diário + duração/backlog; não garante cauda >lookback |
| Analytics freshness | <1/<4/<24h | Mais publicações/scans versus estabilidade; generation fechada até receipt |
| Fast quality | a cada run /30min | Escopo afetado versus atraso de alerta |
| Deep quality | diário/semanal | Custo histórico versus tempo de detecção fora do escopo |

Separar atrasos de fonte, fila, orçamento, execução e erro; definir percentil e janela
de avaliação com responsável. Coverage=false/needs_review não pode cumprir SLO de
completude apenas porque latency está baixa.

## 11. Terraform FUTURO, rollout e rollback

Não criar módulo aplicável agora nem alterar Terraform ativo. Futuro desenho requer:
dispatcher Job/serviço e agenda, backend durável de queue/leases/budget ledger,
workers parametrizados, SA/roles mínimos, monitoramento/alertas/DLQ, limites por pool,
registry de cadence por store e config versionada. Sem role admin ampla nem secrets
em manifest. Dedupe RAW e ledger/change index físicos demandam proposta de schemas
aditiva separada. Custos/quotas de fila/backend não estão incluídos no simulador.

1. MX Fashion shadow metrics: instrumentação aprovada separadamente, sem trocar
   planner; medir payload/hash hits, scans, duration, late arrivals e custo por query.
   Gate: métricas completas, baseline comparável, nenhum writer adicional.
2. MX Fashion nova agenda: aprovação explícita; pausar antiga, drenar/verificar
   leases/jobs, seed watermark sem gaps com audit; habilitar feature/config de uma
   loja. Gate: igualdade de conjuntos/chaves e checks por intervalo fechado, late
   recovery testado, zero skip de budget, custo dentro do aprovado.
3. 5 lojas: isolar quotas, tenants e falhas; gate zero cross-store e fairness.
4. 20 lojas: injetar loja lenta/429/budget/erro; gate sem starvation/duplicação,
   recuperação de leases/outcomes ambíguos e SLOs aprovados.
5. 100 lojas: ramp gradual por cohort com limites globais, observação suficiente
   para pelo menos um ciclo deep e cauda late escolhida; sem promoção automática.

Rollback em cada fase: suspender novos dispatches, drenar ou reconciliar jobs
ambíguos, manter todos RAW/checkpoints/receipts, reverter config/imagem operacional
aprovada, voltar planner antigo a partir do último limite contíguo seguro com overlap.
Não executar ambos writers simultaneamente. Preservar fila pendente para recuperação;
nenhum DROP, reset HEAD, remoção de evidência ou rewind destrutivo de CORE.

Decisões humanas: margem/safe_end, SLA fonte/limites/cursor stability; cadência1/2/4,
lookback e cobertura de cauda; budgets/alertas/exceção crítica; fila backend/pools/IAM;
SLO percentis; retenção e reuso RAW; profiles comerciais; CPU/memória; janelas de
rollout e responsáveis. Nenhuma decisão comercial Analytics mudou.

## 12. Entregáveis e validação

- `src/scale/proposal.py`: modelos offline de janela, admission/lock, orçamento,
  labels, seleção de links, qualidade de escopo e transação sintética.
- `scripts/estimate_scale_cost.py`: CLI com presets/parâmetros, sem preços/cloud.
- `docs/scale/ESTIMATES.md` e `estimates.json`: comparações 1/10/100 e storage200.
- `tests/scale`: 11 testes novos, incluindo Engine real em SQLite comprovando RAW
  adicional com refresh e estabilidade CORE/versions; modelos100stores, concorrência
  global/source/store, falha reconcile sem bloquear fast de outras lojas, budgets,
  late arrival/restatement, idempotência, isolamento, quality subset e links.

Validação final: **399 testes** (incluindo os anteriores), ruff lint/format, mypy
(71 arquivos, incluindo simulador), git diff --check e CLI preset100/compare passaram.
Rede proibida pela fixture global nos testes. Os modelos não comprovam locks
multi-processo, paridade completa BigQuery, taxa API, fila durável ou alertas reais:
esses gates permanecem necessários antes de ativação. Não houve mudança Terraform;
fmt/validate não foram necessários nesta entrega. Nenhum plan/apply/GCP/build/deploy.
