# Fronteira de integração

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

`services/api/http.ts` demonstra a fronteira de transporte para **view models**, inclusive paginação ainda local ao demo. Ele NÃO decodifica nem consome diretamente os DTOs #11/#12. As rotas desse esqueleto são candidatas, não um novo contrato aprovado. Ao conectar, substituir essa implementação por adaptador que valide responses e traduza apenas campos autorizados. Nunca fazer cast de um envelope `{data,pagination,metadata}` para uma lista.

## Requisitos para ativação futura

1. Autenticar no servidor; validar vínculo empresa/marca/operação antes de acesso e cache. Não confiar nas roles ou IDs de sessão demonstrativos.
2. Adicionar DTOs de transporte validados em runtime. Expandir modelos internos para campos nullable (nome/localização/flags/valores), cobertura e motivos antes de ligar dados reais. O demo atual tem campos sintéticos completos onde o cenário os conhece.
3. Propagar metadata: contract_version, store_id, generation, policy_hash, moeda, timezone, as_of, history/facts coverage, período e limitations. Recusar store divergente e mistura de gerações.
4. Tornar tabelas remotas: page_size ≤100, cursor opaco, filtros compatíveis (texto exato no contrato atual), sorting suportado pelo servidor. Não traduzir busca fuzzy/coleção/canal demo automaticamente em filtros inexistentes.
5. Incluir geração e revisão de permissão no cache; limpar em 401/403/logout/troca. Reiniciar cursor na alteração de filtros ou geração. Não preencher uma nova operação com `placeholderData` da anterior.
6. Manter solicitado/atendido separados. Pagamentos, reativação, scores e CAC sem cobertura não recebem fallback numérico. Somar campanhas não produz total da loja.
7. Segredos serão recebidos por backend autorizado/Secret Manager. Campos API key/token ficam desabilitados no frontend desta etapa. Nenhuma integração simula OAuth ou valida uma credencial.

A demonstração não tenta certificar os contratos reais nem a segurança de produção. Sua separação permite conectar o adaptador correto sem transportar lógica de API ou dados sintéticos para componentes visuais.

## Ajuste: plataforma operada pela UP

A permissão ADMIN neste frontend representa **Admin interno UP**. Usuários de marcas são VIEWER/MANAGER vinculados a uma única brand_id; a autorização é a interseção desse vínculo com tenant_id/store_id/operação. O catálogo administrativo e o inventário de contas Meta são globais da UP, nunca recursos expostos a clientes.

A futura credencial Meta é **global da UP, server-side**. Após validá-la no backend, listar contas disponíveis; cadastrar/vincular apenas meta_account_id, account_name, status e last_sync por marca. A referência demonstrativa impede a mesma conta de ser vinculada a duas marcas. Não implementar coleta de token por marca, token no browser, OAuth ou consulta real nesta etapa. Google Ads, TikTok, ERP e GA4 ficam reservados.

A autenticação mockada é uma seleção explícita de identidade; não há senha, convite ou usuário real provisionado. O cadastro e a edição de permissões são locais. Ativação real exige autenticação e autorização no servidor, revisão de acesso, revogação de sessão, gestão segura da senha e proteção das rotas globais de administração.

Agregações demonstrativas de influência usam união de order_id dentro do contexto autorizado, e somas em centavos. Nenhuma campanha recebe crédito exclusivo. As métricas reais continuarão vindo das materializações; não mover cálculos de domínio para componentes nem recalcular o histórico completo no browser. Coortes, novos clientes, reativação e dados financeiros indisponíveis nunca ganham número de fallback.
