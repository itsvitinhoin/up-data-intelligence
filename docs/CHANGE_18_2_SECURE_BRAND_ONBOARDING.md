# CHANGE #18.2 — Secure Brand Creation + Credentials

## Escopo e estado

Implementação offline sobre `4f13cd295f5cfcebb118e358bdd09d129a55ae5c`, na branch
`change-18-2-secure-brand-onboarding`. Nenhum recurso, secret, conexão, checkpoint,
publicação ou execução real foi criado. A Dashboard Read API permanece read-only.
MX Fashion existente não é migrada, resetada ou alterada; o registro duplicado é rejeitado.

```text
Browser — formulário existente, modo DEV explícito
↓
server bridge — loopback/same-origin, token privado
↓
ADMIN_UP Write API — authenticator confiável + grants de tenant
↓
Onboarding operation
↓
DRAFT Registry revision 1 + workspace binding (transaction)
↓
Secret Manager — container próprio + uma versão inicial numérica
↓
BQ atomic finalization — revision/CAS + ASSERTs
↓
INSTALLING — Registry DRAFT revision 2, pipelines desabilitados
```

## Composição e endpoints

`src/admin/contracts.py` define validação estrita, Principal, request e erros seguros.
`repository.py` contém SQL parametrizado e reconciliação. `secrets.py` recebe um SDK
Secret Manager injetado; não descobre credenciais/importa um client global. `service.py`
coordena a SAGA. `http.py` expõe WSGI com authenticator e service factory injetados.
Reutiliza StoreConfig, BigQueryRegistry, Transport, leases e validação de referências.
Não altera StoreWorker, Dispatcher, Engine UP Zero, Analytics ou Intelligence.

- `POST /v1/admin/onboarding`: obrigatório `Idempotency-Key` UUID canônico; JSON estrito;
  resposta 201 com metadata segura da operação. Nenhum query parameter permitido.
- `GET /v1/admin/onboarding/{operation_id}`: somente ADMIN_UP proprietário da operação
  e autorizado no tenant; 200 seguro ou 404 para operação alheia/inexistente.
- Erros usam somente `{ "error": { "code": "codigo_sanitizado" } }` e nunca mensagens SDK.
- Respostas não incluem credencial, referência Secret Manager, request/hash/subject ou token.
- HTTPS é obrigatório. A única exceção HTTP é a composição DEV explícita em loopback.

O backend não possui launcher automático live: o operador futuro deve compor
`OnboardingService(BigQueryOnboarding(Transport(...)), SecretManagerStore(...), lease,
subject_key)` e `create_wsgi_app(service_factory, authenticate)`.
Todos os métodos autorizam antes de lease/query/SDK. O authenticator precisa retornar
Principal verificado no servidor, com subject, role ADMIN_UP e tenants confiáveis;
nenhum header arbitrário do browser cria esse Principal.
`create_dev_admin_app(...)` é uma composição alternativa estritamente local, token
injetado de no mínimo 32 bytes e REMOTE_ADDR 127.0.0.1. Não é auth de produção.

## Request e limites

```json
{
  "tenant_id": "synthetic-tenant",
  "store": {
    "name": "Synthetic Brand",
    "slug": "synthetic-brand",
    "operation_b2b": true,
    "operation_b2c": false,
    "timezone": "America/Sao_Paulo",
    "currency": "BRL",
    "history_from": "2026-01-01"
  },
  "sources": {
    "upzero": { "enabled": false, "credential": null, "store_identifier": null },
    "meta": { "enabled": false, "account_id": null, "api_version": null }
  }
}
```

Esse exemplo não contém credencial. Quando UP Zero é habilitado, a credencial é
obrigatória exclusivamente no body; a mesma credencial deve ser reinserida no retry.
Meta exige account_id numérico e api_version no formato StoreConfig, sem campo de token.
Fontes desabilitadas exigem seus campos opcionais NULL. Chaves desconhecidas,
JSON duplicado, coercion de booleans e nenhum tipo de operação são rejeitados.

| Campo | Limite/regra |
|---|---|
| Body | 32.768 bytes; WSGI exige Content-Length; bridge limita stream mesmo sem header |
| Nome | 120 caracteres não vazios, sem controles/whitespace nas extremidades |
| Slug | 80 caracteres, regra StoreConfig; sem sufixo aleatório |
| Tenant | 100 caracteres, grant server-side obrigatório |
| Credential | 8.192 caracteres ASCII imprimíveis sem espaço; sem trim silencioso |
| store_identifier | 120 caracteres; opcional NULL |
| Idempotency-Key | UUID canônico de 36 caracteres |
| Timezone | 100 caracteres + validação ZoneInfo/StoreConfig |
| Currency | 3 caracteres + moedas suportadas pelo StoreConfig |
| history_from | data local ISO canônica de 10 caracteres |
| Account/API version | 32/16 caracteres + validação StoreConfig |

`history_from` é convertido no servidor para início do dia na timezone informada,
em UTC. O relógio do browser não determina esse instante. Não há policy comercial
qualificante ou cobertura presumida. Lojas mistas conservam ambas as capacidades,
sem executar pipeline B2C ou B2B nesta etapa.

## Workspace e persistência

`store_id = slug`, `brand_id = brand-<slug>`; operações são `<slug>-b2b` e/ou `<slug>-b2c`.
Workspace operation ID nunca é o technical store ID. Um binding por operação real;
ASSERTs e lease global impedem colisões/cross-tenant, sem confiar em PK não enforced.
Readback valida tenant, brand, store, operação e IDs coerentes antes da projeção.

Somente duas tabelas novas no manifesto ativo, ambas em `up_ops`, sem particionamento
ou expiração e com deletion_protection herdada de `main.tf`:

- `workspace_store_bindings`: row_key, tenant_id, brand_id, workspace_operation_id,
  store_id, operation (REQUIRED STRING); status STRING; created_at/updated_at TIMESTAMP.
  Clustering tenant_id, workspace_operation_id, store_id.
- `onboarding_operations`: row_key, operation_id, idempotency_key, admin_subject_hash,
  request_hash, tenant_id, store_id, status, current_step (REQUIRED STRING);
  error_code/secret_version_name STRING; revision REQUIRED INT64;
  created_at/updated_at/completed_at TIMESTAMP. Clustering admin_subject_hash, idempotency_key, store_id.

`tenant_id` sustenta isolamento. `revision` permite CAS. `secret_version_name` é apenas
referência numérica necessária à recuperação, nunca secret_data/payload/credential.
O hash do subject é HMAC com chave de servidor estável, injetada, fora de Git;
rotacionar essa chave exige estratégia explícita de continuidade das operações antigas.
O hash estrutural do request exclui completamente a credencial e seu digest.
Ledger não guarda body, identidade plaintext do admin, CPF/CNPJ ou dados de cliente.

## Lifecycle, transactions e idempotência

1. Validar ADMIN_UP, tenant, request, UUID; adquirir os mesmos locks do StoreAdmin:
   `store-registry-registration-global` e store_id. Todos os escritores administrativos
   precisam respeitar esses locks. A unicidade global não é garantida apenas por BQ PK.
2. Reservar atomicamente ledger RESERVED, Registry DRAFT revision 1 e bindings DRAFT.
3. Persistir CONTAINER_INTENT antes do SDK; comprovar container próprio; persistir
   CONTAINER_READY. Persistir VERSION_INTENT antes de add; comprovar versão única;
   persistir SECRET_READY com referência numérica.
4. Persistir FINALIZING antes da transaction final. Ela cria source_connections,
   meta_account_bindings quando solicitado, atualiza Registry por CAS (revision 2),
   bindings coerentes e ledger INSTALLING/CONFIGURED no mesmo COMMIT.
5. Não acionar dispatcher/jobs/scheduler ou criar sync_run/checkpoint. Dashboard indisponível.

Mesmo subject autenticado + UUID gera a mesma operation_id determinística. Repetição
com request estrutural diferente retorna 409 idempotency_conflict. Com credencial
alterada retorna credential_retry_mismatch, comparando bytes em memória via
hmac.compare_digest contra a versão numérica já comprovada. Nunca grava seu digest,
cria versão adicional ou rebaixa uma operação INSTALLING previamente concluída.

SQL reside no repository, com parâmetros; somente nomes de tabelas/projeções do
catálogo confiável são montados. ASSERTs verificam ledger/revision, todos os campos
do Registry reservado, cardinalidade/exatidão de bindings, conexão globalmente única
e Meta account não vinculada a outra store. A transaction não grava nas tabelas de dados.
Job IDs determinísticos por operation/revision/step usam Transport e `job_retry=None`;
custo e timeout são obrigatórios no CloudConfig injetado, sem guard removido.
Para futura validação, propor 1 GiB/query, 32 GiB/operação, timeout 30s e resultado de
até 101 linhas por consulta de metadata; são limites de composição a aprovar, não
variáveis GCP aplicadas. Um Transport novo por request evita acumulação entre operações.

## Outcome unknown e recuperação

| Ponto | Evidência segura e comportamento |
|---|---|
| BQ reservation incerta | Ler ledger, Registry revision 1, bindings exatos, ausência de source/meta; aceitar somente estado completo esperado |
| BQ transição incerta | Ler ledger exato na próxima revision; sem segunda mutation |
| BQ finalization incerta | Ler ledger INSTALLING, Registry revision 2, bindings, source/meta exatos; recuperar somente prova completa |
| Create secret incerto | Ler metadata do nome determinístico e comprovar labels/replicação; não repetir create |
| Add version incerto/crash | Listar versões e acessar uma única ENABLED numérica; comparar bytes em memória; nunca segundo add cego |
| Falha definitiva do add | Marcar VERSION_RETRY_ALLOWED; próximo retry pode tentar add após verificar ausência de versão |
| Falha definitiva da transaction final | FINALIZATION_RETRY_ALLOWED; Registry reservado permanece revision 1; retry preserva secret |
| Secret estrangeiro/divergente | Colisão/mismatch; sem adoção, exclusão, overwrite ou rotação |

Se não há prova, retornar `secret_write_outcome_unknown` ou
`onboarding_write_outcome_unknown`, não interpretar ausência momentânea como rollback.
Zero versões após add incerto, múltiplas versões, versão desabilitada/destruída ou
leitura sem autorização não permitem novo add. Leitura pode retornar secret_read_failed;
o intent continua impedindo escrita cega. Não existe rotina automática de delete.

Uma intenção persistida também cobre crash antes/depois do SDK: sem prova, mantém
DRAFT/BLOCKED e exige análise administrativa futura. Falha definitivamente rejeitada
antes do create ainda pode exigir reconciliação manual, por escolha conservadora.
Resultados BigQuery SDK TIMESTAMP são normalizados para ISO antes da retomada/CAS.

O código preserva as leases global/store quando o outcome BigQuery permanece incerto,
usando o código já reconhecido pelo lease existente. Isso pode bloquear novas inscrições
administrativas até recuperação segura. Não liberar/remover lock enquanto um job incerto
puder continuar. Antes de nova mutation, confirmar término do job/transaction e estado
exato; APIs administrativas de recuperação/rearm/release não fazem parte desta change.
Não alterar manualmente valores do ledger sem um procedimento revisado de CAS.

## Secret Manager / UP Zero / Meta

Nome UP Zero `up-intelligence-upzero-<store_id>`, labels application=up-data-intelligence,
environment configurado e onboarding-operation=operation_id. Replicação user-managed
em uma única região injetada/aprovada, sem default para outra região. Secret já existente
precisa possuir labels e réplica exatas. Versões retornadas com project number são
canonicalizadas para project ID. Persistência exige `/versions/<N>` positivo; nunca latest.
SDK de mutation usa retry=None e timeout 10s. Reconciliation GET/list/access também
é limitada; listas com mais de uma versão falham de forma conservadora.

`source_connections` UP Zero guarda somente metadata e referência. Meta guarda conexão
`<store>-meta` com secret_resource_name=NULL, não cria nem acessa token por marca.
Token global Meta existente permanece intocado. Account binding conserva campos
consumidos por live.runtime::binding e Prerequisites.account; timezone/currency são
configuração declarada ainda não verificada na fonte. `configuration_hash=NULL` até
existir janela/definição Insights comprovada; não criar hash com semântica inventada.
Ambas as fontes ficam `status=pending`, sem chamada de verificação UP Zero/Meta.

## Installation State

`pending` → configured=true, active=NULL, state=PENDING. Sem recursos/publicação,
overall_state=INSTALLING e recommended_preview_window=NULL. O novo card nunca recebe
números demo como dados reais nem libera dashboard. `active` conserva avaliação dos
recursos; inactive/disabled/error e status arbitrários continuam BLOCKED.
Registro sem nenhuma integração não afirma coverage; o planner futuro precisará exigir
fontes aplicáveis antes de instalação. Nenhum binding de MX é migrado automaticamente.

## Frontend e fronteiras de segurança

O dialog Criar marca existente recebe a seção segura apenas com
`NODE_ENV=development` e `UP_ADMIN_ONBOARDING_DEV=1` privados. Default/produção continuam
fail-closed; o demo anterior funciona sem backend. Nenhum redesenho ou alteração de menus.
`Company`, demoApi e React Query não recebem a credencial.

Senha é input uncontrolled com autocomplete=new-password e spellcheck desabilitado.
FormData remove a chave e input é limpo antes de await. Submit usa fetch direto;
finally limpa payload/referência de body e componente aborta no unmount. Não há
localStorage, queryKey, mutation cache, telemetry ou export do valor. Strings JS/Python
não permitem zeroização garantida: coleta de lixo não substitui segurança do ambiente.
O card novo utiliza somente resposta validada: Instalando, fontes Pendente, Dashboard
desabilitado. A lista dessas respostas é memória de sessão, não cadastro production.

Bridge `/api/admin/onboarding` e GET individual exigem modo explícito, URL de acesso
loopback, same-origin, métodos/content-type/body limitados. Upstream exclusivamente
`http://127.0.0.1:<porta>`; token privado `UP_ADMIN_DEV_TOKEN` >=32 e
`UP_ADMIN_API_BASE_URL` somente server-side. Não repassa Authorization/Cookie do browser,
apenas Content-Type, Idempotency-Key e seu próprio X-UP-Admin-Preview-Token.
Respostas HTTP/SDK inesperadas são sanitizadas e parseadas por allowlist; extra fields
incluindo credential/reference são rejeitados. Cache-Control private,no-store.
Não habilitado por NEXT_PUBLIC. Host/same-origin são controles de preview, não identidade
production nem sandbox contra processos locais maliciosos. Sessão demo não autoriza GCP.

O handler não loga payload/SQL/credential. Ledger é a auditoria persistente de etapas.
Composição live futura deve desabilitar debug SDK, captura de request bodies e headers
em proxies/observabilidade; usar logging safe existente. Não serializar Request para logs.

## Terraform / IAM — código offline

Somente as duas tabelas novas são promovidas. `onboarding.tf` dá table-level writer
nas quatro tabelas adicionais ao trusted control_plane_admin_member; grant existente
store_runtime_config permanece. Total de cinco tabelas administrativas, não dataset editor.
Grant existente de jobUser/lease/read é reutilizado. Nenhum IAM por store.
UP Zero control-plane worker exclui as duas tabelas novas da sua seleção automática;
seu namespace de Secret Manager permanece inalterado. Foundation legado já tem acesso
wide em up_ops: não foi ampliado/reorganizado nesta tarefa; as tabelas novas herdam
esse acesso antigo. Reduzir essa permissão exige revisão separada.

Custom roles separadas: create container (`secretmanager.secrets.create`) no projeto;
get metadata/add/list/access (`secretmanager.secrets.get`, `secretmanager.versions.add`,
`secretmanager.versions.list`, `secretmanager.versions.access`) condicionado a resource.name
no namespace projects/<project-number>/secrets/up-intelligence-upzero-.
A nomenclatura das permissões foi conferida na [referência oficial Google](https://docs.cloud.google.com/iam/docs/roles-permissions/secretmanager).
Create é autorizado no projeto e não oferece restrição perfeita por nome: aplicação
valida namespace determinístico, ownership e região. Leitura de namespace pode acessar
credenciais UP Zero existentes: trusted admin e princípio de mínimo privilégio são
obrigatórios. Não há permissão delete/secretmanager.admin/Owner/Editor, token global Meta,
SecretVersion Terraform ou recurso por marca. Roles/grants só existem quando o member
é configurado. `terraform fmt` também alinhou três atributos no arquivo offline
analytics_proposed/cloud.tf; sem mudança funcional ou promoção desse módulo.

## Validação e runbook offline

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
cd frontend
npm test -- --run
npm run lint
npm run typecheck
npm run format:check
npm run build
PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./node_modules/.bin/playwright test --config=playwright.onboarding.config.ts
DASHBOARD_E2E_LIVE=0 PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./node_modules/.bin/playwright test --config=playwright.b2b-preview.config.ts
cd ..
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform validate
git diff --check
```

Playwright usa portas offline separadas, fixtures synthetic-only, interceptação HTTP,
URLs/tokens backend vazios e sem Python/GCP. Não iniciar simultaneamente os dois E2Es,
pois compartilham .next-offline. Build não habilita onboarding em produção.
Validação Terraform usa provider local instalado; não faz init/plan/apply nem migra state.

Para testar a Write API agora, usar Memory/Fake SDK da suíte — sem montar clientes GCP.
A ativação DEV com SDK exige autorização separada, authenticator/grants confiáveis,
chave HMAC estável, service factory/servidor WSGI explícitos, budgets, leases e recursos
já provisionados. Não publicar uma request contendo credencial em scripts, shell history,
curl inline, snapshots/trace/test output ou documentação. Inserir via input protegido.

## Limitações e #18.3

SQL/SDK foram testados com fakes e validação estrutural, não executados em BigQuery/Secret
Manager. IAM conditions e transações precisam de validação DEV autorizada separadamente.
Readback/ledger são duráveis; descoberta/listagem de marcas e bindings dinâmicos no
frontend/Read API continuam trabalho futuro, não usar login demo como autorização.
Não existe autenticação production, persistência administrativa production do frontend,
logo upload real, secret rotation, cancelamento ou recuperação manual automatizada.
As versões e secrets parciais são retidos, sem delete. O registro DRAFT bloqueia pipelines.

#18.3 deverá, com autorização própria, validar fontes e contas, descobrir capacidades,
gerar plano de instalação, executar chunks/checkpoints idempotentes, medir progresso/ETA
e publicar coverage consistente antes de permitir PARTIAL/READY e liberar dashboard:

```text
INSTALLING → source verification → discovery → work planning → chunks
→ progress → ETA → PARTIAL → READY
```

Deve integrar grants/workspace bindings persistidos com o resolver, preservar MX,
falhar fechado sem cobertura e só ativar workers sob revisão. Não basta mudar status
ou flags para simular instalação concluída.

## Arquivos alterados — lista completa

- `README.md`
- `docs/CHANGE_18_2_SECURE_BRAND_ONBOARDING.md`
- `frontend/README.md`
- `frontend/docs/api-integration.md`
- `frontend/playwright.onboarding.config.ts`
- `frontend/src/app/api/admin/onboarding/[operationId]/route.ts`
- `frontend/src/app/api/admin/onboarding/route.ts`
- `frontend/src/app/layout.tsx`
- `frontend/src/features/admin.tsx`
- `frontend/src/features/brand-integrations.tsx`
- `frontend/src/features/providers.tsx`
- `frontend/src/features/secure-onboarding.tsx`
- `frontend/src/services/api/onboarding-bridge.server.ts`
- `frontend/src/services/api/onboarding.ts`
- `frontend/src/types/onboarding.ts`
- `frontend/tests/e2e/onboarding.spec.ts`
- `frontend/tests/fixtures/onboarding.ts`
- `frontend/tests/onboarding.test.ts`
- `infra/terraform/analytics_proposed/cloud.tf`
- `infra/terraform/control_plane.tf`
- `infra/terraform/onboarding.tf`
- `infra/terraform/schemas/onboarding_operations.json`
- `infra/terraform/schemas/workspace_store_bindings.json`
- `infra/terraform/tables.json`
- `sql/ops/onboarding_operations.sql`
- `sql/ops/workspace_store_bindings.sql`
- `src/admin/__init__.py`
- `src/admin/contracts.py`
- `src/admin/http.py`
- `src/admin/repository.py`
- `src/admin/schema.py`
- `src/admin/secrets.py`
- `src/admin/service.py`
- `src/bigquery/catalog.py`
- `src/bigquery/schema.py`
- `src/dashboard/installation.py`
- `src/security/secrets.py`
- `tests/admin/test_onboarding.py`
- `tests/change16/test_stack.py`
- `tests/control_plane/test_control_plane.py`
- `tests/dashboard/test_installation.py`

## Resultado local desta entrega

- pytest completo: **1.963 passed** (105,49s); 51 casos do domínio admin.
- Ruff check: All checks passed; Ruff format: 241 files already formatted.
- mypy: Success, no issues found in 137 source files.
- Frontend: 214 testes, 20 arquivos; lint/typecheck/format:check aprovados.
- Next build: compilação/TypeScript/45 páginas estáticas concluídos; sem deploy.
- Playwright onboarding: 1 passed; B2B/Installation offline: 7 passed.
- Agent-browser local: conteúdo/elementos presentes, sem overlay/erros; screenshot
  temporário fora do repositório, sem credencial. Servidor temporário encerrado.
- Terraform fmt -check -recursive e validate: aprovados. Validate precisou executar
  o provider local fora do sandbox após falha de handshake; nenhum plan/apply/init.
- git diff --check: aprovado. Manifesto existente e schemas anteriores preservados;
  somente duas tabelas novas. Busca local nas 41 alterações não encontrou material
  de chave privada, token real ou credential JSON. Nenhum artefato sensível staged.
- Bundle cliente de produção não contém UP_ADMIN_DEV_TOKEN, UP_ADMIN_API_BASE_URL
  nem os valores sintéticos usados pelos testes.
- Warning NO_COLOR/FORCE_COLOR nos E2Es é apenas configuração de terminal.
- Next alterou tsconfig ao gerar .next-offline; a alteração transitória foi removida,
  restaurando a configuração versionada, e format/typecheck foram repetidos com sucesso.

```text
GCP live: NO
Secret real: NO
Meta live: NO
UP Zero live: NO
Cloud Run: NO
Terraform plan: NO
Terraform apply: NO
Schedulers: NO CHANGE
MX live: NO CHANGE
```
