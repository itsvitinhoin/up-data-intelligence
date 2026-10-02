# CHANGE #18.1 — MX Product Onboarding + Partial Coverage

## Objetivo / arquitetura

Estado de instalação somente leitura, derivado de metadata existente, separado da cobertura comercial certificada. Admin e Dashboard usam os componentes, tokens e bindings existentes. Base: `797dbbff09df0d8a5d93f3c24332c508b25d6012`; branch: `change-18-1-mx-product-onboarding`. Esta entrega não altera o runtime live associado a `7b6564f6ae9f2ec2207754d45ae9a8e0e70ba0fd`.

```text
Principal + grant tenant/store/B2B
→ GET /v1/stores/{store_id}/installation
→ InstallationReader → metadata operacional + HEAD/RECEIPT
→ envelope installation.v1 validado
→ bridge server-side com binding workspace → technical store
→ React Query → Admin → período certificado no Dashboard
```

A rota aceita somente tenant_id e operation; store técnico fica no path. Autorização ocorre antes das queries. O navegador envia workspace_operation_id; o bridge resolve o binding existente. `mx-fashion-b2b` e `mx-fashion` continuam identidades distintas. Company.status não representa instalação.

O envelope contém data, pagination=null e metadata (contract_version, store_id, snapshot_at, generation/policy_hash nullable, timezone e currency). data contém fontes, recursos, flags nullable, limites de Facts, janela disponível/recomendada, progresso e limitações. O parser rejeita campos desconhecidos, tipos inválidos e cobertura/percentuais inconsistentes. Sem publicação, existe metadata operacional válida com generation/hash/janela null.

## Queries / orçamento

Até quatro queries, usando uma sessão de orçamento por request:

1. installation_registry: projeção segura de `up_ops.store_runtime_config`, por @store; limite 2 detecta duplicidade. Estabelece o snapshot.
2. installation_sources: `up_core.source_connections`, por @store no snapshot; limite 101 detecta excesso.
3. installation_resources: `up_ops.sync_checkpoints` + `up_ops.sync_runs` + connections; joins por store/connection/source/resource/run, no mesmo snapshot; limite 501. Último checkpoint ordenado por updated_at e row_key; agregados identificam pendências/bloqueios, sem somar contadores históricos de replay.
4. head: `up_analytics.analytics_publications`, HEAD/RECEIPT completed na mesma store/policy/generation e snapshot, com a validação existente compartilhada sem mudar suas regras.

Não há leitura de payload RAW nem contagem comercial em CORE. Não há SQL com valores de usuário interpolados. A policy deve estar carregada no serviço e corresponder a timezone/currency/policy_version do Registry. Não escolhemos um hash arbitrário que a Read API não possa servir. Conexões UP Zero/Meta antigas/desabilitadas não são instalação corrente.

BigQueryReadSession mantém defaults: maximum_bytes_billed=1.073.741.824 por query; maximum_total_bytes_billed=8.589.934.592 por sessão; timeout=30s por query. Quatro queries podem reservar até 4 GiB, inclusive em falha. Não alteramos guards/retry. Logs existentes registram somente identificadores operacionais e métricas de query, sem SQL, payload ou PII.

Antes de uma validação live explicitamente autorizada, verificar leitura nessas tabelas e capacidade de executar jobs BigQuery. Preferir grants nas tabelas necessárias, sem writer/secretAccessor. Nenhum IAM é aplicado aqui.

## Installation semantics

| Estado | Evidência |
| --- | --- |
| INSTALLING | Sem janela Analytics servível, sem bloqueio confirmado. Fonte/configuração ausente fica PENDING. |
| PARTIAL | Janela publicada disponível; instalação/histórico completo ainda não comprovados. |
| READY | Janela disponível, fontes configuradas/ativas, recursos COMPLETE e Registry **e policy servível** confirmando history_complete/facts_complete. |
| BLOCKED | Registry pausado/inválido, conexão inativa/desconhecida, falha/checkpoint ativo exigindo revisão ou publicação inconsistente. |

Fontes/recursos: PENDING, RUNNING, PARTIAL, COMPLETE, BLOCKED. Fonte com recursos concluídos e pendentes pode ser PARTIAL; processamento pendente tem prioridade RUNNING. Checkpoints complete/recovered sem RAW pendente são terminais. O run histórico failed/completed_with_errors de checkpoint recovered não volta a ser falha ativa; seu contador histórico permanece. Outros checkpoints ativos/needs_review continuam considerados mesmo que o último checkpoint esteja completo.

Conexão active é o status operacional armazenado, não uma nova verificação externa. Status desconhecido mantém active=null. Códigos expostos: source_not_configured, source_inactive, source_status_unknown, sync_requires_review. error_summary, cursor e pending_raw_id não são retornados; pending_raw é somente booleano.

## Coverage / período recomendado

A janela vem de `[report_from, report_to)` local de HEAD/RECEIPT válidos, conforme a policy servível. Não vem de data fixa, último timestamp ou MIN/MAX de checkpoints que esconderia lacunas. Um plano completo fornece somente sua própria janela; snapshot de clientes sem filtro temporal não recebe cobertura temporal inventada.

A janela V1 cobre Overview, Clientes, Pedidos, Retenção e Produtos. Não certifica automaticamente Funnel, Geography, Meta, Influence ou Intelligence; estes mantêm guards/publicações próprios. Limites de Facts ficam separados. Facts incompleto não elimina período comercial já publicado nem certifica o funil; não intersectamos fontes desnecessárias ao recurso.

Ver Dashboard requer recommended_preview_window na marca vinculada ao preview real. Ao abrir, filtros usam a janela publicada (fim exclusivo vira inclusivo apenas na UI). Sem binding real, a marca permanece explicitamente demo. Erro numa marca vinculada nunca vira fixture demo. Um bloqueio operacional com janela válida não apaga dados publicados: o acesso é baseado na janela certificada e a Read API comercial ainda valida sua própria publicação.

Nas páginas comerciais, ausência de janela/período fora da cobertura impede montar os componentes numéricos. O filtro bloqueia a aplicação do período inválido e informa **“Histórico deste período ainda está sendo processado.”** Default sem datas explícitas usa o intervalo publicado, sem transformar ausência em zero.

INSTALLING/PARTIAL mantém aviso: **“Histórico ainda está sendo processado. Os dados exibidos correspondem ao período atualmente certificado.”** Histórico parcial não vira completo.

## Progress / ETA

records_read/processed/failed vêm de source_records_read/core_records_processed/core_records_failed da última tentativa ligada a checkpoint por recurso, somente metrics_version=2. Métricas legadas ambíguas ficam null. Agregado só existe com todos os contadores necessários conhecidos: representa **últimas tentativas**, não registros únicos ou total histórico instalado.

Sem denominador real: total=null, percent=null, eta_seconds=null. UI mostra contagem observada ou “Calculando progresso...” e “Calculando tempo estimado...”. Tipos reservam RECORDS/TIME_COVERAGE/CHUNKS/UNKNOWN; percentual futuro exige total válido e aritmética coerente. Nesta entrega não é fabricado.

Cache por usuário/role/tenant/workspace/operação, AbortSignal e no-store. Polling de 30s apenas com observador montado em INSTALLING/PARTIAL; desligado em READY/BLOCKED, sem background polling/retry automático de erros.

## MX behavior

Não houve leitura live; o estado atual de MX não foi revalidado. Metadata Customers/Orders completos e Facts em andamento pode produzir COMPLETE/COMPLETE/RUNNING e overall PARTIAL se houver publicação servível. History incompleto continua declarado. Quatro checkpoints Customers recovered não são quatro falhas ativas.

Sem publicação: INSTALLING sem preview. Sem metadata/permissões válidas: erro explícito. Produto não hardcoda UUID, cursor, contagem ou data final MX. Fixtures são sintéticas e não contêm PII real.

## Security / limitations / próxima Change

Principal e grant B2B são obrigatórios. Store apenas B2C é bloqueada; marca mista não habilita query B2C. Bridge continua DEV/loopback, same-origin, GET, allowlist de parâmetros e token privado server-side. Sessão demo não vira auth production. Não há secrets/PII no contrato ou bundle.

Admin saveBrand continua demo em memória, credenciais desabilitadas. Resumo de integrações demonstrativas está identificado como configuração demo; o estado operacional vinculado vem do servidor, sem interpretar credential digitada como conectada. Fontes/recursos genéricos permitem conectores futuros sem alegar integração existente.

Não implementados: Orchestrator V2, chunk queue, mutações, novas tabelas, migrations, Terraform, auth production, total/ETA comprováveis, instalação automática ou prova de histórico desde a origem. Próxima Change: API administrativa com ADMIN_UP real, grants e auditoria para `Create Store → credentials → Secret Manager → Source Connection → Registry → Installation Plan`. Orchestrator V2 deverá fornecer plano/chunks/denominador/throughput verificáveis e execução idempotente.

## Validação offline

Na raiz:

```sh
.venv/bin/pytest -q tests/dashboard
.venv/bin/pytest -q
.venv/bin/ruff check
.venv/bin/ruff format --check
.venv/bin/mypy
git diff --check
```

Em frontend:

```sh
npm test
npm run lint
npm run typecheck
npm run format:check
DASHBOARD_E2E_LIVE=0 PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./node_modules/.bin/playwright test --config=playwright.b2b-preview.config.ts
npm run build
```

E2Es interceptam todas as chamadas Dashboard com envelopes sintéticos; não iniciam Python/BigQuery nem consultam GCP. Teste live permanece separado. Chrome é detalhe deste ambiente, podendo ser substituído pelo Chromium do Playwright. Arquivos Next gerados para .next-offline não pertencem ao change.

Resultados finais: 1.902 testes Python passaram (103,29s); suíte dashboard com 121 testes passou (0,37s); Ruff check/format e mypy passaram (130 arquivos de código). Frontend: 196 testes unitários passaram, lint/typecheck/format passaram, sete E2Es offline passaram (11,5s) e build Next.js de produção local passou. git diff --check passou. A revisão do diff e do bundle não encontrou credenciais; arquivos gerados/cache/state/plan não entram no commit. O único aviso do E2E é NO_COLOR ignorado por FORCE_COLOR, sem impacto funcional. Nenhum teste live foi executado.

## Files changed

Backend:
- src/dashboard/installation.py
- src/dashboard/installation_queries.py
- src/dashboard/service.py
- src/dashboard/queries.py
- src/dashboard/http.py
- src/dashboard/dev_preview_server.py
- tests/dashboard/test_installation.py

Frontend:
- frontend/src/types/installation.ts
- frontend/src/services/api/installation.ts
- frontend/src/services/api/installation-bridge.server.ts
- frontend/src/services/api/http.ts
- frontend/src/app/api/dashboard/installation/route.ts
- frontend/src/hooks/use-installation.ts
- frontend/src/components/installation-state.tsx
- frontend/src/components/period-filter.tsx
- frontend/src/components/shell.tsx
- frontend/src/features/brand-integrations.tsx
- frontend/src/features/providers.tsx
- frontend/src/app/globals.css
- frontend/tests/installation.test.ts
- frontend/tests/fixtures/installation.ts
- frontend/tests/overview-source-state.test.ts
- frontend/tests/e2e/installation.spec.ts
- frontend/tests/e2e/b2b-real-preview.spec.ts
- frontend/playwright.b2b-preview.config.ts
- frontend/README.md
- frontend/docs/api-integration.md

Documentação:
- docs/CHANGE_18_MX_PRODUCT_ONBOARDING.md

Nenhum push/deploy/operação live. Commit local na branch separada, sem modificar main.
