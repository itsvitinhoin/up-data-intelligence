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
