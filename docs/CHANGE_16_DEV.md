# CHANGE #16 — contrato live DEV, implementado e validado offline

Base: `968778ebdae6c336e784f34cdc8e847d1a3702ea`. Este documento substitui as propostas físicas conflitantes de #08–#14 para o piloto DEV; os artefatos offline continuam como referências históricas reproduzíveis. Nenhuma execução real, provisionamento ou imagem é evidenciada pela validação offline.

## Arquitetura e autoridade

CORE UP Zero + Meta live canônico → runner limitado por loja → três scopes Influence + Customer Intelligence + Performance → uma transação de publicação → Read API → bridge DEV server-side → UP Glass B2B. Cálculos não são executados nas requests do dashboard.

O contrato de entidades Meta é `normalize_foundation()` (#13). As tabelas antigas `meta_accounts`, `meta_campaigns`, `meta_adsets`, `meta_ads`, `meta_insights_daily` e suas versões permanecem **inativas**. Nomes físicos novos são `meta_live_accounts/campaigns/adsets/ads/insights_daily`, com uma tabela `_versions` para cada entidade. O catálogo canônico ganha apenas `version_id`, `payload_hash`, `source_system` para persistência/replay. O hash desconsidera o instante de observação; replay do mesmo RAW não cria versão duplicada. Insights usa **campaign/day, time_increment=1, sem breakdown**. A versão Graph é obrigatória e precisa de aprovação explícita; nenhum account ID ou API version é selecionado automaticamente.

Também são ativadas `meta_raw_accounts/campaigns/adsets/ads/insights` sanitizadas, mais `meta_account_bindings`. A binding é autoridade explícita; o runtime não a cria durante sync. Bind exige confirmação de loja/conta e validação read-only de currency/timezone, e usa lease da loja e lease global para evitar duas lojas vinculando a mesma conta simultaneamente. O listing `/me/adaccounts` nunca escolhe a primeira conta nem grava binding.

## Tabelas/grãos novos

São **29 adições** ao manifesto, sem mudar datasets, schemas existentes, Analytics V1, UP Zero, policy, digest DEV.4 ou schedulers:

| Família | Tabelas | Grão lógico |
|---|---|---|
| Meta RAW | 5 `meta_raw_*` | loja/conexão/página auditável sanitizada |
| Binding | `meta_account_bindings` | loja → conta explícita; conta não compartilhada entre lojas |
| Meta canônico | 5 `meta_live_*` + 5 `_versions` | loja/conta/entidade; insight conta/campanha/dia/configuração; versão imutável |
| Influence | `analytics_paid_touchpoints` | loja/generation/fact_id |
| Influence | `analytics_customer_paid_influence` | loja/generation/scope/customer_id |
| Influence | `analytics_order_paid_influence` | loja/generation/scope/order_id/campaign_id |
| Timeline | `analytics_customer_timeline` | loja/generation/customer_id/event_key |
| Customer Intelligence | `analytics_customer_360_profile`, `analytics_customer_journey_summary` | loja/generation/customer_id |
| Customer Intelligence | `analytics_customer_orders_summary`, `analytics_customer_products_summary` | loja/generation/cliente/pedido ou product_key |
| Performance | `analytics_campaign_performance_daily` | loja/generation/campanha/dia/scope |
| Performance | `analytics_campaign_customer_performance`, `analytics_campaign_order_performance` | loja/generation/campanha/cliente ou pedido/scope |
| Performance | `analytics_performance_summary` | loja/generation/scope |
| Publicação | `analytics_intelligence_publications` | HEAD por loja/policy; RECEIPT por publication_id |

Todos os novos Analytics usam `generation INT64`, com modo REQUIRED. As propostas antigas com generation textual são referências offline, não o contrato físico ativo. Schemas são gerados por `src.intelligence.live.schema`; `python -m src.bigquery.schema` gera manifesto/schemas/DDL canônico sem acesso externo. Snapshot de manifesto e hashes anteriores em `tests/fixtures/change16` verificam preservação integral dos schemas preexistentes.

## Evidência, finanças e cobertura

São materializados **LIFETIME, ACQUISITION e REPEAT_PURCHASE** juntos. Row keys de influência incluem scope. Um touch de aquisição não vira automaticamente influência de recompra. Reutilizamos o resolver determinístico existente; não há matching por nomes, CNPJ, CPF, email/telefone fuzzy ou `user_id == customer_id`.

Paid signal permanece campaign/adset/ad ID, fbclid/fbc/gclid. UTM ou fbp sozinhos não provam mídia paga. Touch sem caminho determinístico é preservado como unresolved. Não se inventa order_id para os Facts históricos afetados pelo bug UP Zero. Zero pedidos influenciados comprovados é válido. Pedido e FACT derivado são representações da mesma compra, sem duplicar frequência.

Requested ≠ fulfilled ≠ paid. Não existe Payment Ledger, revenue_paid, paid LTV, margem ou lucro nesta camada. Summary deduplica pedidos e clientes, incluindo participação comprovada sem campanha mapeada. Cada campanha pode contar sua participação no mesmo pedido; suas receitas **não são somáveis para obter receita da loja**. Spend conta campaign/day/config uma vez. A lista de campanhas agrega spend/cliques/impressões, recalcula CTR/CPC/CPM, e conta compradores distintos a partir da materialização por cliente, sem somar compradores diários.

`history_complete=false` mantém novos confirmados, CAC confirmado e LTV completo NULL. A primeira compra é observada. `product_id=NULL` permanece quando não há ID canônico; SKU/asset/variant não são convertidos em product_id. Health/segmentação continuam NULL/NOT_DEFINED. Flags verdadeiras comprovadas são preservadas; negativas sem cobertura suficiente viram NULL, inclusive no JSON de scopes. Unresolved/unmapped torna `influence_complete=false` e ROAS/CAC dependentes de mapping ficam NULL. Spend certificado exige checkpoint completo, sem pending RAW, run completed/zero failures, conta/currency/timezone/API/config e janela compatíveis. Ausência de linha só permite zero após cobertura comprovada.

## Publicação, retry e rollback

Analytics V1 HEAD/RECEIPT continua independente. Intelligence resolve e valida a base, fixa `FOR SYSTEM_TIME AS OF` nas fontes, calcula os 12 modelos, valida schemas/row counts/grãos, e faz staging em **TEMP tables de uma sessão BigQuery**. Só a transação final insere geração imutável, grava RECEIPT completed e move HEAD com compare-and-swap. A base V1 é revalidada dentro da transação. Não há DELETE, DROP, substituição de tabela ou limpeza de geração antiga.

O publication_id é determinístico para mesmos inputs, policy, Meta config, base, as_of e calculated_at controlado. A sequência física é INT64 e usa o máximo das RECEIPTs, não apenas HEAD: rollback de ponteiro não permite reutilizar uma geração antiga. O writer usa job_id único por tentativa com **job_retry=None**, reconciliando a RECEIPT em resposta perdida. Falha antes do commit deixa HEAD anterior. Se o resultado da transação permanecer incerto, erro `bigquery_write_outcome_unknown` mantém a lease; operador precisa reconciliar/cancelar o job antes de liberá-la. Não repetir blindamente.

Rollback futuro, sob aprovação e lease: selecionar uma RECEIPT completed anterior **da mesma loja/policy/base V1/as_of/janela**, validar todos os modelos/row counts e mover apenas HEAD em transação com compare-and-swap. Preservar row_key/record_kind da HEAD, copiar os demais campos da RECEIPT. Não alterar RECEIPT nem apagar linhas. Se a base V1 mudou, a Read API rejeita a antiga publicação; não forçar compatibilidade. O teste offline simula rollback de HEAD e publicação seguinte com sequência monotônica. Nenhum rollback real foi executado.

## APIs e frontend

Novas leituras materializadas:

- `/v1/customers/{id}/intelligence` (Customer 360 completo disponível), `/timeline`, `/products`;
- `/v1/customers/{id}` preserva summary V1 e acrescenta profile Intelligence quando certificado;
- `/v1/orders/influenced`, `/v1/customers/influenced`;
- `/v1/performance`;
- `/v1/campaigns`, `/v1/campaigns/{id}`, `/customers`, `/orders` por campanha.

Cada leitura valida principal/tenant/store/operation **antes** do BigQuery, resolve Intelligence HEAD+RECEIPT e compatibilidade V1. Entidades são store-scoped, não IDs globais. Falta publicação: 424. HEAD/RECEIPT duplicada/incompatível: falha explícita. As novas superfícies exigem a janela materializada exata; recorte diferente retorna 424, não aproximação sob HTTP.

Paginação keyset opaca, máximo 100, vinculada a principal/tenant/store/operation, ambas gerações, policy, recurso, filtros, entidade e tamanho. Dinheiro é texto decimal; SQL é parametrizado. Projeções excluem CPF/CNPJ completo, email, telefone, endereço, identity_path, session/visitor/user IDs, click IDs, tokens e payload RAW. Journey retorna evidência resumida, sem paths técnicos. Logs não contêm entidades, SQL com valores ou URLs com query.

Frontend mantém demoApi, UP Glass, navegação e B2C/marcas sem binding. Customer 360, Timeline, Marketing, produtos, Performance, Meta Campaigns e Media passam pelas mesmas bridges loopback server-side. Metadata distingue `publication_domain`, `analytics_generation` e `generation` Intelligence. Resolução de publicação é separada do cache imutável; keys incluem domínio/ambas gerações/policy/escopo/filtros/entidade/cursor. Listas filhas rejeitam mudança de geração, sem misturar a publicação do pai. Sem HEAD válida: unavailable-real; cobertura parcial: partial-real; nunca fallback demo. Geografia segue 424/mapa neutro. A busca global existente permanece explicitamente desabilitada no preview real, sem consultar clientes demo. As listas expõem somente uma chave opaca de registro para manter identidade estável de renderização.

## IAM, token e custos

Um token **global UP**, server-side. Terraform cria só container `up-intelligence-meta-global-token` com réplica regional, labels e proteção contra destruição, mais accessor da nova SA Meta. Não cria secret version/token. Para CLI, env `UP_META_DEV_TOKEN` só com `--allow-local-token-env` explícito, alternativa exclusiva ao `--secret-reference`.

Novas SAs Meta/Intelligence: BigQuery jobUser; writer via IAM por tabela usando o papel scoped existente; Intelligence reader só CORE/Meta/V1/ops necessários, writer só 13 tabelas Intelligence. Read service: variável opcional `change16_dashboard_reader_member` acrescenta Viewer somente às novas tabelas; permissões existentes em V1/CORE/jobUser precisam estar presentes no principal server-side, nunca no browser. IAM anterior não é editado. Foundation já tem permissões de dataset anteriores ao #16; reduzi-las exige change separado.

Jobs manuais são opcionais (`change16_runtime=null`): exigem imagem nova imutável, account/API version aprovadas e número de Secret Version. O materializer exige overrides de snapshot/calculated_at e aprovação de HEAD inicial. **Nenhum Scheduler novo**. Todos os anteriores permanecem pausados.

Dashboard: **1 GiB/query, 8 GiB/request, 30s**. Materializer: **1 GiB/query, 32 GiB/execution, 300s/job**, configuráveis explicitamente; reserva os ceilings mesmo em falhas e inclui a resolução base. Pilot: máximo 100.000 registros agregados e 32 MiB de fontes; exceder falha com pedido de particionamento, sem aumento silencioso. Staging usa chunks de até 500 KB. Uma execução grande pode consumir o orçamento reservado antes de publicar: HEAD permanece anterior. CLI Meta usa page_limit=100 configurável, 4 tentativas limitadas (429/5xx/transport), Retry-After≤300s, max_pages limitado, GET/HTTPS/host exato, Bearer header, sem redirects/paging.next. Medir custos/duração no piloto antes de schedules. 30s de expect live é teste funcional DEV, não SLO.

## Pré-requisitos e comandos futuros — não executados nesta tarefa

A conta Meta real e API version **ainda precisam ser aprovadas**. Exige ADC/operador com permissões BigQuery/Secret accessor/GCS lease e provisionamento DEV aprovado. Novo código exige imagem nova antes de Jobs; DEV.4 atual foi preservada. Cloud Run não é necessário para validar CLI local no Cloud Shell. Não há credenciais no Git.

O validator exige binding **já registrada**. Na primeira instalação, a tabela binding/container ainda não existirão: será necessário aprovar o provisionamento aditivo e adicionar a versão do token fora do Terraform, depois aprovar o bind explícito. Isso é um pré-requisito humano; o script não resolve esse ciclo escolhendo/gravando conta automaticamente. Se não houver binding, parar com `META_ACCOUNT_BINDING_REQUIRED`. Com binding preparada, ele faz uma única rodada completa com plan aditivo, confirmação separada de apply/publicação, sync, materialização, invariantes/parity e E2E live. Não foi executado.

```bash
# Executar somente após aprovação de operações DEV.
export META_ACCOUNT_ID='<CONTA_NUMERICA_APROVADA>'
export META_CONFIRM_ACCOUNT_ID="$META_ACCOUNT_ID"
export META_API_VERSION='<VERSAO_GRAPH_APROVADA>'
export META_TOKEN_SECRET_REFERENCE='projects/up-data-intelligence-dev/secrets/up-intelligence-meta-global-token/versions/<NUMERO>'

# Listing é read-only, não cria binding. Token não aparece na linha de comando.
.venv/bin/python -m src.intelligence.live.cli list-accounts \
  --live --project up-data-intelligence-dev --confirm-project up-data-intelligence-dev \
  --policy config/analytics/mx-fashion.dev.json --store-id mx-fashion --confirm-store mx-fashion \
  --api-version "$META_API_VERSION" --secret-reference "$META_TOKEN_SECRET_REFERENCE"

# Bind exige escolha/confirmação explícita, após tabelas aprovadas/provisionadas.
.venv/bin/python -m src.intelligence.live.cli bind-account \
  --live --project up-data-intelligence-dev --confirm-project up-data-intelligence-dev \
  --policy config/analytics/mx-fashion.dev.json --store-id mx-fashion --confirm-store mx-fashion \
  --account-id "$META_ACCOUNT_ID" --confirm-account-id "$META_CONFIRM_ACCOUNT_ID" \
  --connection-id '<CONNECTION_ID_APROVADA>' --api-version "$META_API_VERSION" \
  --secret-reference "$META_TOKEN_SECRET_REFERENCE" \
  --lease-bucket up-data-intelligence-dev-876521886531-leases

export CHANGE16_LIVE_CONFIRM=up-data-intelligence-dev
export CHANGE16_APPROVED_SHA='<SHA_COMPLETO_APROVADO_DE_MAIN>'
bash scripts/change16_dev_validate.sh
```

Não usar o script antes de aprovar conta/token/binding/provisionamento. A configuração Terraform padrão tem **29 novas tabelas e IAM/identidades/container adicionais**, não somente 29 recursos no plan. `change16_plan_guard.py` rejeita qualquer update/destroy/replacement, drift existente, Scheduler ou criação fora da allowlist #16. Não houve plan nesta tarefa; o total real depende das variáveis opcionais e state remoto.

Para replay Meta após falha, usar `meta-sync --resource <recurso> --replay-run <UUID>` com confirmações/binding/lease iguais, sem token/API externa. Para retomar checkpoint pendente, repetir sync sem `--refresh`; RAW persistido é promovido antes da próxima página. Refresh só depois do checkpoint complete. Para repetir materialização sem mudar identidade lógica, reutilizar os mesmos source_snapshot_at/calculated_at controlados registrados pela rodada. Não apagar RAW/CORE.

O validator preserva tabelas e dados DEV, encerra seus servidores e apaga planos/artefatos temporários locais. Não inicializa HEAD automaticamente sem confirmação `PUBLISH_CHANGE16_DEV`. Playwright integrado navega V1, cliente/Customer360/Timeline/Marketing/Produtos, Performance, campanhas/listas, Media e Geografia, retornando B2C demo; marca sem binding também é verificada ao final do percurso integrado. Não fixa spend/campanhas/influência/ROAS real. Se não houver campanhas, valida lista vazia; não fabrica campanha para abrir detalhe.

## Limitações a validar na única rodada futura

Sem Graph API/GCP nesta entrega, permanecem por comprovar permissões reais, compatibilidade da versão escolhida, certificação Meta, custo/duração, campos efetivamente presentes e SQL BigQuery executável. Testes usam MockTransport/readers/staging simulados e não equivalem a dry-run BigQuery live. História parcial e Facts sem order_id podem produzir zero influência e ROAS indisponível. Resolver ad/adset → campanha via hierarquia futura não é inventado nesta camada. Não há criativos completos, atribuição exclusiva, OAuth/Admin persistente, Payment Ledger, novo health score, auto-recorrência ou Geografia certificada.


## Validação offline desta entrega

- Python: 672 testes, incluindo 52 novos casos #16; ruff check/format e mypy aprovados.
- Frontend: 135 testes Vitest; lint, typecheck e format check aprovados.
- Playwright: quatro percursos offline aprovados com Chrome local e todas as respostas HTTP interceptadas; nenhuma API real utilizada.
- Terraform: fmt-check e validate aprovados; nenhuma execução de plan/apply. Manifesto anterior e hashes de todos os schemas existentes preservados por testes.
- Shell wrapper: bash -n aprovado; script live não executado. git diff --check aprovado.
- Docker, image files, navegação, policy e DEV tfvars não foram alterados. Nenhum build/deploy foi executado.

## MULTI-STORE CONTROL PLANE — CHANGE #16.1

Base: `628fa08a27fc5730a9743d78873e1800c43b6236`. Implementação e validação **offline**.
Não houve provisionamento, cadastro real, seed, inicialização de HEAD, consulta real,
Meta, build ou deploy nesta entrega.

**Adding a new store requires no Terraform resources.**

Nova store não cria dataset, tabela, job ou scheduler e não executa Terraform.
As quatro camadas continuam compartilhadas. O provisionamento inicial do control
plane é uma operação separada e ainda precisa de autorização; onboarding posterior
é configuração administrativa, não criação de infraestrutura Terraform.

### Registry e autoridade

`up_ops.store_runtime_config` é a única tabela adicionada ao manifesto ativo.
Grão: uma linha por `store_id`, sem particionamento, clustering `status,store_id`,
mesma proteção de exclusão das tabelas ativas. `row_key`, `store_id`, `status` e
`revision` são REQUIRED; os demais campos físicos são NULLABLE. A aplicação exige
booleans explícitos, defaults falsos, identidade válida e estados na allowlist
DRAFT/READY/ACTIVE/PAUSED/ERROR/DISABLED. Campos extras aos mínimos solicitados:

- `row_key` técnico e `revision` para compare-and-swap;
- `store_name`, `store_slug`, `upzero_store_identifier` e
  `purchase_order_id_effective_at` para compor Settings sem configuração do piloto;
- `qualifying_order_statuses`, sem default comercial e sem CANCELED;
- `history_coverage` com evidência explícita da policy existente;
- `facts_coverage_from/to` para impedir que `facts_complete=true` certifique uma
  janela diferente da evidência aprovada.

Não há tokens, chaves ou valores de secret no registry. A conexão UP Zero é resolvida
em `up_core.source_connections`, deve ser única/ativa/da própria store e apontar para
uma versão **numérica explícita** de secret UP Zero deste projeto. `latest` não é
aceito no novo caminho. `meta_account_bindings` continua autoridade da conta, conexão,
API version, currency e timezone. O token Meta é global UP, server-side, nunca por
store. Os fluxos anteriores de conexão/binding continuam separados: cadastrar uma
store não cria/conecta secret nem escolhe conta Meta.

`StoreAdmin` exige um principal ADMIN_UP confiável **antes de qualquer leitura**.
Nenhum parâmetro de browser vira autorização. A CLI é ferramenta interna DEV com
ADC/IAM e confirmação de project/store; não oferece endpoint público nem usa uma
flag `--role` para simular autorização. Futuro servidor administrativo deverá
construir esse principal a partir da autenticação real. UI administrativa permanece
inalterada; CLIENT_USER não recebe acesso ao registry.

Cadastro valida unicidade sob lease global de registro + lease da store. BigQuery
não impõe unicidade de chave; INSERT/UPDATE transacionais usam ASSERT e revision CAS.
Leitura/inventário duplicado falha explicitamente. Update sempre retorna DRAFT,
desabilita sync e exige revalidação. `validate-store` checa configuração/conexões e
promove READY; `activate-store` revalida e aceita apenas READY/PAUSED; `pause-store`
bloqueia o mesmo lease do worker e suspende novas execuções. READY valida a configuração,
**não certifica backfill**. Somente ACTIVE + sync_enabled + pipeline_enabled entra
no despacho. Stores com flags falsas continuam cadastradas sem execução.

Timezone usa ZoneInfo; currencies têm allowlist inicial explícita no modelo
(BRL/USD/EUR/GBP/CAD/AUD/MXN/ARS/CLP/COP/PEN/JPY/CNY/CHF/UYU/PYG/BOB/NZD).
Outras currencies exigem extensão revisada da allowlist, não aceitação silenciosa.
Ao menos uma operação B2B/B2C é obrigatória no cadastro. Meta/UP Zero podem ser
habilitados independentemente; Analytics/Intelligence usam **o contrato B2B atual**,
não inventam materialização B2C. Stores B2C/mistas podem cadastrar e usar fontes, mas
não ativam Analytics/Intelligence enquanto não existir contrato de seleção por operação;
esses modelos não têm discriminador de operação hoje. Histórico parcial permanece parcial.

### Dispatcher e workers compartilhados

`src/control_plane` separa modelo, registry/admin service, repository SQL, preflight,
REST gateway, dispatcher, worker/actions, budget e CLIs. SQL recebe store/datas como
parâmetros; nomes de tabelas/colunas/pipelines vêm de allowlists internas.

Fluxo: scheduler central → `up-store-dispatcher` → registry elegível → preflight
→ `jobs:run` com overrides → um worker para uma store/revision/janela explícita.
O worker adquire **o mesmo lease por store já usado pela Foundation/Meta** e relê
configuração/revision/eligibilidade/dependências antes de executar. Não há lote de
stores dentro de um materializador. Os quatro jobs são:

- `up-upzero-worker`;
- `up-meta-worker`;
- `up-analytics-worker`;
- `up-intelligence-worker`.

Sem store nos nomes, env ou args base. O dispatcher passa store/revision/cutoffs/budgets
em overrides; defaults incompletos dos jobs falham antes de ADC se lançados diretamente.
UP Zero reutiliza Engine/paginação/batching/idempotência, retoma checkpoints pendentes,
faz incremental/open-order reconcile e não sobrescreve conexões de outras integrações.
Pending UP Zero retoma os filtros/page-limit persistidos, sem recalcular seu plan_key.
Meta reutiliza o contrato canônico e retoma pending RAW inclusive de janela anterior
antes de refresh; mudança de binding/page-limit incompatível com pending exige recovery.
RAW continua antes de CORE. Nenhum checkpoint incompleto é tratado como source completa.

`max_parallel_stores=2` por padrão DEV (1..10 configurável). O pool espera **término da
execução remota**, não somente aceite do POST. Uma lease global `store-dispatch-global`
serializa dispatchers de todos os pipelines para que dois despachos não dobrem o limite.
Uma falha/bloqueio conhecido de store não impede outras; resposta de lançamento/poll
incerta interrompe novos lançamentos e mantém a lease global. POST não é repetido
automaticamente. A execução pode existir: reconciliar Cloud Run antes de liberar lease.
Crash/kill pode deixar lease persistente. Nunca há takeover por TTL, limpeza cega ou
retry ilimitado; limite de 24h do dispatcher/3900s de observação por worker é operacional,
não SLO. Confirmar terminalidade de TODAS as execuções pendentes antes de recuperação.

Janela é `--window-mode explicit` com todos os cinco campos, ou escolha explícita
`previous-closed-day`. Esta última calcula **por timezone da store** o dia local
anterior fechado, as_of no midnight final, snapshot/calculated_at capturados uma vez
pelo dispatcher. Não depende da janela de setembro nem da policy MX Fashion.
A flag facts_complete só vale dentro de facts_coverage_from/to; evidência ausente
ou fora do intervalo bloqueia a execução que declararia cobertura completa.

Preflight é repetido dentro do worker:

- UP Zero: conexão/versão de secret aprovada; não depende de Meta;
- Meta: binding explícita; não depende do materializador V1;
- Analytics V1: policy dinâmica + UP Zero completo. Clientes exigem scan incremental
  concluído após as_of; Orders/Facts exigem união **sem gaps** dos intervalos dos
  checkpoints desde history_from até as_of. Filtros/connection/run são conferidos;
  pending/status incompleto ou `core_records_failed` não zero bloqueia. `completed_to`
  sozinho não prova cobertura DATE; Orders considera o timezone da store;
- Intelligence: mesmas fontes UP Zero, Meta Insights com configuração/janela exata,
  catálogo Meta concluído sem pending, V1 HEAD/RECEIPT completed da janela e HEAD ainda
  igual após o snapshot. Sem DAG complexo; corrida/incompletude falha fechada e pode
  ser reavaliada no próximo despacho autorizado.

Analytics reutiliza Reader/Writer/runner V1, com refresh completo **apenas da store/policy**:
dias explícitos e grupos comerciais, transação CAS e receipts existentes. Não faz DROP,
DDL de tabela física nem DELETE de outra store/policy. O caminho compartilhado pode
inicializar singleton HEAD vazio **sob lease** para uma store ACTIVE aprovada; registro
ou validação não inicializam HEAD. HEAD>0 exige receipt compatível e generation máxima.
Retry com os mesmos store/revision/snapshot/janela reconcilia o mesmo publication_id.
V1 mantém o comportamento existente de substituição transacional de recortes; não se
promete retenção de gerações V1 inteiras fora do time travel. Intelligence reutiliza
publicação imutável/CAS do #16. A policy versionada do piloto e seu validator continuam
válidos como dev tooling, mas não entram nos workers compartilhados.

### Budgets, observabilidade e limites de escala

Ceiling proposto: **1 GiB/query**, envelope conservador **128 GiB/store execution**,
configuráveis em Terraform/CLI. Cada submissão reserva seu ceiling, inclusive erro;
exceder o envelope bloqueia, nunca aumenta automaticamente. `BoundedClient` cerca
inclusive queries da Repository legada e do reader V1 usado por Intelligence.
Todos os jobs, inclusive reads legadas, usam `job_retry=None` e submissão sem retry
SDK implícito: relançamentos invisíveis não podem escapar do envelope. O writer
continua seu retry explícito por job_id; reattach não cria query nova e custo conhecido
é contado uma vez por job_id. Rejeição local por budget antes de submissão é definitiva:
não inventa job pendente nem retém lease como escrita incerta. Se uma mutação já ficou
incerta, essa incerteza prevalece e exige recovery. Custo desconhecido continua NULL. O preflight do dispatcher
tem cliente/envelope independente por store, além do envelope do worker; não é gratuito.

Log de término inclui store_id/pipeline/duration_ms/query_count/bytes_processed/status,
sem customer/order IDs, payload, tokens ou SQL com valores. Budgets limitam custo, não
provam performance; os limites de snapshots/rows/payload existentes continuam valendo.
Facts V1 continua usando chunks/spool. Intelligence permanece com o limite revisado de
100k linhas/32 MiB; stores maiores falham explicitamente até a futura expansão do read
model/chunking. Isto prepara fan-out multi-store; não comprova SLO de 100 lojas em DEV.

### Terraform aditivo e segurança

`infra/terraform/control_plane.tf` contém inventário fixo de pipelines, não for_each
por store. Novas SAs por papel, grants de tabela e lease, jobUser, dispatcher permission
`run.jobs.runWithOverrides` **restrita aos quatro jobs** e leitura de operações são
separados. Scheduler SA só invoca o dispatcher. Writer custom role permite get/getData/
updateData; nenhuma tabela/data set recebe nova permissão de criação/exclusão do worker.
UP Zero accessor tem condition limitada ao namespace `up-intelligence-upzero-*` deste
projeto; Meta accessor cobre somente o container global já preparado no #16. Nenhuma
secret version é criada. Admin server member é opcional/null; só ganha registry writer,
leitura de conexões/binding, jobUser e lease, nunca credenciais via frontend.

Schedulers centrais `up-upzero-dispatch`, `up-meta-dispatch`, `up-analytics-dispatch`,
`up-intelligence-dispatch` são sempre **paused=true**. Os horários UTC são propostas;
recorrência só pode ser habilitada em change autorizado posterior. Dependências,
notas de filas e atrasos precisam de métricas antes disso.

`control_plane_image=null` mantém os cinco jobs/quatro schedulers ausentes até fornecer
uma **nova imagem imutável aprovada** que contenha estes módulos; não reutiliza DEV.4
ou altera digest/config atual. SAs/IAM/registry já estão descritos no Terraform. Uma
versão numérica global Meta também precisa de aprovação quando Meta for habilitado.
Nenhuma variável DEV existente foi modificada. `main.tf`, `analytics_runtime.tf` e
`change16.tf` ficam byte a byte preservados: recursos do piloto são legado mantido para
cumprir zero destroy/replacement, **não são o caminho de onboarding**. Sua retirada
futura exige mudança e aprovação separadas. IAM amplo legado existente não é revogado
neste change; novos workers só recebem os grants aqui descritos.

Fixtures `tests/fixtures/change161` guardam manifesto/hashes de schemas/Terraform da base.
Somente a tabela registry é acrescentada; todas as definições anteriores permanecem.
`scripts/control_plane_plan_guard.py` revisa **um JSON de plan futuro salvo offline** e
rejeita update/delete/replacement, dataset novo, tabela fora do registry, drift e scheduler
ativo. Isto é guarda adicional, não substitui revisão humana do plan. **Nenhum plan foi
executado**: não se afirma quantidade real de adds nem ausência de drift no GCP.
O guard específico de #16.1 pressupõe que a base aprovada já esteja provisionada.
Se #16 também estiver pendente, o plan conjunto conterá suas adições anteriores e
exigirá revisão explícita desse escopo; não ignorar uma rejeição do guard.

### Runbook futuro — NÃO executado nesta entrega

1. Revisar/provisionar uma vez a infraestrutura compartilhada após nova imagem aprovada,
   sob plan exclusivamente aditivo. Manter todos os schedulers pausados. Não adicionar
   store em tfvars/for_each. API/IAM/provider/REST ainda requerem validação DEV autorizada;
   Terraform validate não verifica permissões reais nem disponibilidade das fontes.
2. Usar principal interno ADMIN_UP com ADC/IAM, sem arquivos de credenciais no Git.
3. Cadastrar configuração não-secreta DRAFT (exemplo sintético abaixo). Conexões e
   bindings devem ser preparados por seu fluxo próprio explicitamente autorizado.
   Para UP Zero, inclusive Secret Manager fora deste registry: não há criação de
   secrets por cadastro. Meta utiliza o token global; nunca criar token por cliente.
4. Validar → READY; ativar → ACTIVE. Esta ativação **autoriza** o caminho compartilhado
   a inicializar seu HEAD e materializar quando as fontes estiverem completas. Nesta
   entrega nenhuma store foi cadastrada/ativada e nenhum HEAD foi inicializado.
5. Lançar dispatcher manual em janela explícita aprovada, com budgets. Só mais tarde,
   após métricas/revisão, considerar habilitar schedulers centrais.

Arquivo local não-secreto, valores comerciais próprios precisam de aprovação:

```json
{
  "store_id": "brand-example",
  "store_name": "Brand Example",
  "store_slug": "brand-example",
  "operation_b2b": true,
  "operation_b2c": false,
  "timezone": "America/Sao_Paulo",
  "currency": "BRL",
  "history_from": "2026-09-01T00:00:00Z",
  "history_complete": false,
  "facts_complete": false,
  "policy_version": "1.0.0",
  "qualifying_order_statuses": ["CONFIRMED", "SHIPPED"],
  "upzero_enabled": false,
  "meta_enabled": false,
  "analytics_enabled": false,
  "intelligence_enabled": false
}
```

Comandos futuros de registro, a partir da raiz do checkout no Cloud Shell. Eles fazem
DML registry e requerem autorização live posterior; não foram executados aqui:

```bash
UP_STORE_ID=brand-example
UP_ADMIN_ARGS=(
  --live --project up-data-intelligence-dev
  --confirm-project up-data-intelligence-dev
  --location southamerica-east1
  --lease-bucket up-data-intelligence-dev-876521886531-leases
  --store-id "$UP_STORE_ID" --confirm-store "$UP_STORE_ID"
)
.venv/bin/python -m src.control_plane.cli register-store "${UP_ADMIN_ARGS[@]}" --request /tmp/store-config.json
.venv/bin/python -m src.control_plane.cli read-store "${UP_ADMIN_ARGS[@]}"
# Depois das conexões autorizadas e update-store com flags/refs não-secretas:
.venv/bin/python -m src.control_plane.cli update-store "${UP_ADMIN_ARGS[@]}" --request /tmp/store-update.json
.venv/bin/python -m src.control_plane.cli validate-store "${UP_ADMIN_ARGS[@]}"
.venv/bin/python -m src.control_plane.cli activate-store "${UP_ADMIN_ARGS[@]}"
# Suspender novas execuções (esperar/cancelar worker existente antes, se necessário):
.venv/bin/python -m src.control_plane.cli pause-store "${UP_ADMIN_ARGS[@]}"
```

Não habilitar pipelines sem policy/statuses/coverage aprovados, versões numéricas de
secrets e fontes reais completas. O arquivo acima tem todas as flags falsas, portanto
READY/ACTIVE não lança nenhum pipeline. Não usar estes valores comerciais sintéticos
como policy de outra marca.

Exemplo de argumentos de **override** futuro do dispatcher no job `up-store-dispatcher`:

```bash
UP_DISPATCH_ARGS="--live,--project,up-data-intelligence-dev,--confirm-project,up-data-intelligence-dev,--location,southamerica-east1,--lease-bucket,up-data-intelligence-dev-876521886531-leases,--pipeline,analytics,--max-parallel-stores,2,--window-mode,explicit,--report-from,2026-09-01,--report-to,2026-09-02,--as-of,2026-09-02T03:00:00Z,--source-snapshot-at,<SNAPSHOT_UTC_APROVADO>,--calculated-at,<CALCULATED_AT_UTC_APROVADO>"
# SOMENTE após autorização live, fontes certificadas e substituir placeholders:
gcloud run jobs execute up-store-dispatcher \
  --project=up-data-intelligence-dev --region=southamerica-east1 \
  --args="$UP_DISPATCH_ARGS" --wait
```

O dispatcher só processa stores ACTIVE elegíveis; não usa um `store_id` padrão. Datas
acima são exemplos, não janela configurada em Terraform. O worker/scheduler gera ou
recebe janela explícita com os cutoffs aprovados. Primeira operação DEV deve revisar
registry/cobertura e binding, não simplesmente ativar recorrência.

Validação offline: suíte Python completa, testes novos de ciclo/admin/isolamento,
coverage/dependências, pending RAW, leases, fan-out real até terminalidade, envelopes,
gateway parametrizado/sem retry POST, schemas estáveis e plan guard; ruff, formatting,
mypy, Terraform fmt/validate e diff check. Frontend não mudou. O validator do piloto
`scripts/change16_dev_validate.sh` continua preservado.

Referências do protocolo consultadas sem operações cloud: [Cloud Run jobs.run/Overrides](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/run)
e [Execution metadata](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs.executions).
O gateway valida tanto project ID quanto seu número explicitamente configurado por
Terraform (`--project-number`), pois nomes retornados podem ser canônicos; nunca
segue operation/execution de outro projeto, região ou job. Não aplica retries ao POST.

Resultado desta entrega: **737 testes Python aprovados**, incluindo **65 testes novos**
do control plane; ruff lint/format, mypy (118 arquivos), Terraform fmt/validate e
git diff --check aprovados. Frontend não foi alterado e não foi executado.
