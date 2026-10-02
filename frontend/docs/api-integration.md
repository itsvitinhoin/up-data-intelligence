# Fronteira de integração

## Installation State — CHANGE #18.1

`createHttpApi().installation(scope)` consome o envelope estrito `installation.v1` de `GET /v1/stores/{store_id}/installation`, separado da metadata comercial que exige HEAD. O hook `useInstallation` usa o bridge server-side `/api/dashboard/installation`, binding existente de workspace para technical store, AbortSignal/no-store e polling de 30s somente em INSTALLING/PARTIAL. O modo demo/admin write e a autorização production não mudaram. [Semântica, limites e runbook offline](../../docs/CHANGE_18_MX_PRODUCT_ONBOARDING.md).

Esta entrega estabelece a interface `DataApi`, consumida exclusivamente pelos hooks. O modo demo é explícito e não liga um endpoint por variável de ambiente. Todas as futuras chamadas do transporte recebem `tenant_id` e `store_id`, sinal de cancelamento e credenciais de sessão via cookie. Não há token em storage, bundle ou configuração pública.

## Contratos de origem

- `../docs/DATA_INTELLIGENCE_API.md` e `../docs/openapi/data-intelligence.openapi.json`: contrato offline #11, `/v1/customers`, detalhe, timeline e pedidos influenciados.
- `../docs/CUSTOMER_API_CONTRACT.md` e `../config/contracts/customer-intelligence.v1.json`: contrato futuro #12, histórico paginado e metadata/cobertura.
- `../docs/PERFORMANCE_INTELLIGENCE.md`: modelos offline #14; não existe servidor HTTP de performance publicado.

Os caminhos acima são relativos à **raiz frontend**, não a este documento. Nenhum destes contratos foi modificado.

| UI / campo interno | Origem comercial pretendida | Condição de conexão |
| --- | --- | --- |
| Customer.name / city / state | profile.company_name/trade_name/city/state | Mapeamento explícito de nome; sem inferir localização ausente |
| Customer.requested / fulfilled | commercial.requested_revenue / fulfilled_revenue | Strings decimais e NULL preservados |
| Customer.orders | commercial.orders_count | Não substituir por purchase_count; frequência/recompra usam compras qualificantes |
| Customer.paid | paid_media_influenced_lifetime | Preservar true/false/unknown; não usar flag antiga de janela como lifetime |
| Customer360 orders | `/customers/{id}/orders` | Cursor e metadata coerentes; sem carregar histórico ilimitado |
| Timeline | `/customers/{id}/timeline` | Event key, evidência e ordenação originais; sem session/visitor/URLs/PII |
| Campanhas/performance | modelos #14 | Endpoint/projeção pendentes; cobertura de gasto/mídia e escopo obrigatórios |
| Overview, produtos, mapa, coortes | materializações aprovadas | Endpoint, grain, cobertura, paginação e projeção pendentes |
| Admin / integrations / users | futuro backend administrativo | Autenticação, RBAC, CSRF e gestão segura de credenciais pendentes |

CHANGE #15A: `services/api/http.ts` agora implementa o transporte separado da Dashboard Read API Analytics V1. Decodifica e valida `{data,pagination,metadata}`, store, geração, cobertura, `null` e decimais; oferece `customerCard` como projeção nullable. Os contratos offline #11/#12/#14 não foram promovidos nem lidos por essa API. O transporte não é compatível por cast com os modelos demo de campos obrigatórios: uma futura adaptação visual explícita deve preservar campos ausentes, sem preencher fixtures. `services/api/index.ts` continua `export const api = demoApi`.

O backend read-only está em `src/dashboard/`, com autenticação HTTP injetada e fail-closed, HEAD/RECEIPT e snapshot de leitura, budget por query e cursor. [Runbook DEV](../../docs/DASHBOARD_READ_API_DEV.md). A seleção opcional em `services/api/server.ts` usa somente ambiente privado do servidor (`DASHBOARD_DATA_MODE`, `DASHBOARD_READ_API_BASE_URL`); não faz cutover e não substitui uma sessão real por identidade demo. Não existem credenciais no bundle.

## Requisitos para ativação futura

1. Autenticar no servidor; validar vínculo empresa/marca/operação antes de acesso e cache. Não confiar nas roles ou IDs de sessão demonstrativos.
2. Adicionar DTOs de transporte validados em runtime. Expandir modelos internos para campos nullable (nome/localização/flags/valores), cobertura e motivos antes de ligar dados reais. O demo atual tem campos sintéticos completos onde o cenário os conhece.
3. Propagar metadata: contract_version, store_id, generation, policy_hash, moeda, timezone, as_of, history/facts coverage, período e limitations. Recusar store divergente e mistura de gerações.
4. Tornar tabelas remotas: page_size ≤100, cursor opaco, filtros compatíveis (texto exato no contrato atual), sorting suportado pelo servidor. Não traduzir busca fuzzy/coleção/canal demo automaticamente em filtros inexistentes.
5. Incluir geração e revisão de permissão no cache; limpar em 401/403/logout/troca. Reiniciar cursor na alteração de filtros ou geração. Não preencher uma nova operação com `placeholderData` da anterior.
6. Manter solicitado/atendido separados. Pagamentos, reativação, scores e CAC sem cobertura não recebem fallback numérico. Somar campanhas não produz total da loja.
7. Segredos serão recebidos por backend autorizado/Secret Manager. Campos API key/token ficam desabilitados no frontend desta etapa. Nenhuma integração simula OAuth ou valida uma credencial.

A demonstração não tenta certificar os contratos reais nem a segurança de produção. Sua separação permite conectar o adaptador correto sem transportar lógica de API ou dados sintéticos para componentes visuais.

CHANGE #15B.1: `/b2b` pode ser pré-visualizado com dados reais somente em desenvolvimento e com modo privado explícito `DASHBOARD_DATA_MODE=read-api-preview`. O browser chama apenas a rota same-origin `/api/dashboard/overview`, que resolve o workspace para a loja canônica no servidor e usa token efêmero para o servidor Python loopback. `api = demoApi` continua global; outras páginas permanecem demo. O Overview real valida envelope, mantém `NULL`, metadata/cobertura e mostra erro sem fallback. [Runbook do preview](../../docs/DASHBOARD_OVERVIEW_PREVIEW_DEV.md).

## Ajuste: plataforma operada pela UP

A permissão ADMIN neste frontend representa **Admin interno UP**. Usuários de marcas são VIEWER/MANAGER vinculados a uma única brand_id; a autorização é a interseção desse vínculo com tenant_id/store_id/operação. O catálogo administrativo e o inventário de contas Meta são globais da UP, nunca recursos expostos a clientes.

A futura credencial Meta é **global da UP, server-side**. Após validá-la no backend, listar contas disponíveis; cadastrar/vincular apenas meta_account_id, account_name, status e last_sync por marca. A referência demonstrativa impede a mesma conta de ser vinculada a duas marcas. Não implementar coleta de token por marca, token no browser, OAuth ou consulta real nesta etapa. Google Ads, TikTok, ERP e GA4 ficam reservados.

A autenticação mockada é uma seleção explícita de identidade; não há senha, convite ou usuário real provisionado. O cadastro e a edição de permissões são locais. Ativação real exige autenticação e autorização no servidor, revisão de acesso, revogação de sessão, gestão segura da senha e proteção das rotas globais de administração.

Agregações demonstrativas de influência usam união de order_id dentro do contexto autorizado, e somas em centavos. Nenhuma campanha recebe crédito exclusivo. As métricas reais continuarão vindo das materializações; não mover cálculos de domínio para componentes nem recalcular o histórico completo no browser. Coortes, novos clientes, reativação e dados financeiros indisponíveis nunca ganham número de fallback.

## CHANGE #15B.2 — Preview B2B Analytics V1

O modo DEV privado amplia a leitura same-origin para Pedidos, Aquisição observada, Retenção, Clientes/Summary/pedidos e Produtos. Geography mantém mapa neutro + 424; Performance aguarda materialização, sem fixtures. B2C e marcas não vinculadas seguem demo. `api = demoApi` continua global. Fonte/cobertura por página, cursor bounded, NULL e strings decimais preservados; nenhum cutover público nem camadas #08–#14 promovidas. [Runbook atual](../../docs/DASHBOARD_B2B_PREVIEW_DEV.md).

## CHANGE #16

`intelligence.ts` valida DTOs materializados; `http.ts` mantém demoApi separado e adiciona endpoints Customer360/Timeline/Produtos/Performance/Campaigns/Influence. Metadata leva ambos os domínios/gerações. Bridges continuam server-only/loopback, sem Meta token no browser. Nenhuma fixture é fallback na operação real vinculada. Consulte [CHANGE_16_DEV.md](../../docs/CHANGE_16_DEV.md); `npm test` e Playwright offline usam apenas fixtures sintéticas.
