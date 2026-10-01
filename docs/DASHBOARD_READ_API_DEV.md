# Dashboard Read API — CHANGE #15A (DEV, não ativado)

Esta entrega prepara a leitura real da Analytics V1 sem executar BigQuery, GCP, deploy ou cutover. A composição visual continua `export const api = demoApi`. `createHttpApi` é um cliente HTTP separado, com envelope e DTOs validados; não aceita a sessão demonstrativa como autorização. O servidor HTTP ainda precisa de um autenticador real injetado antes de qualquer exposição de rede.

## Auditoria do HEAD

- O manifesto Terraform **ativo** contém `analytics_store_daily`, `analytics_customer_metrics`, `analytics_customer_purchase_sequence`, `analytics_cohorts`, `analytics_purchase_distribution`, `analytics_products_daily`, `analytics_funnel_daily` e `analytics_publications` em `up_analytics`. Os modelos de Influence, Customer 360 novo, Meta Live e Performance seguem em diretórios `*_proposed`; não são lidos.
- As sete tabelas de dados não contêm `generation`. O writer atual substitui as fatias afetadas e atualiza HEAD/RECEIPT em uma transação BigQuery. Cada request lê HEAD e RECEIPT juntos, exige um único par válido `completed` e captura `CURRENT_TIMESTAMP()` da leitura. Todas as queries seguintes usam `FOR SYSTEM_TIME AS OF @snapshot_at`. Assim, não leem estados de duas publicações dentro da mesma request. Se o snapshot não puder ser lido, falham; não recorrem ao estado corrente. [BigQuery permite parâmetro para `FOR SYSTEM_TIME AS OF` e restringe a janela de time travel](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/query-syntax#for_system_time_as_of).
- `config/analytics/mx-fashion.dev.json` é a policy versionada. O catálogo de policies é injetado por loja, sem `mx-fashion` fixo no serviço. HEAD deve coincidir com hash, período e `as_of` dessa policy. Para nova publicação/período, atualizar a policy aprovada antes de disponibilizar a leitura.
- Policy atual: `history_complete=false`, `facts_complete=true`, BRL, America/Sao_Paulo. Primeira compra é **observada**, não novo cliente definitivo. CAC/LTV completos e pagamento permanecem `null`.
- CORE `customers` contém `state/city` nullable e perfil comercial, mas não há evidência de cobertura geográfica suficiente nem dimensão histórica certificada da localização. `/v1/geography` falha 424 até auditoria de cobertura e regra comercial. Não usa inferência ou geocodificação.
- CORE `orders` e perfis podem mudar entre o snapshot de origem usado para materializar Analytics e a leitura HTTP. São lidos no snapshot da request e sinalizados `core_*_not_source_generation_pinned`. Não se afirma que o perfil/pedido CORE pertence à geração analítica. A consulta de pedidos usa `store_id`, `customer_id`, `source_system` e cutoff da policy.

## Camadas e contrato

`src/dashboard/queries.py` define SQL e colunas permitidas; `repository.py` executa com orçamento; `service.py` valida publicação, autorização, cobertura, DTOs e cursor; `http.py` fornece WSGI com autenticador injetado. Nenhum cliente GCP é criado implicitamente ao importar o serviço. `dev_probe.py` é diagnóstico local de leitura, **não** autenticação HTTP.

O autenticador do futuro servidor deve verificar identidade e produzir `Principal(subject, role, grants)` em servidor. Roles: `ADMIN_UP` e `CLIENT_USER`; ambos precisam de grants explícitos `(tenant_id,store_id,operation)`. Não existe bypass administrativo. Escopo recebido por query é apenas o recurso solicitado, não fonte de permissão. Ausência de autenticador/identidade retorna 401. Outra loja retorna 403 antes de query. Cliente de outra loja retorna 404 dentro da loja autorizada. Query params desconhecidos são rejeitados; filtros fuzzy, coleção, canal e mídia não são simulados.

Envelope em todas as respostas de sucesso: `{data,pagination,metadata}`. `metadata` traz `contract_version`, `store_id`, `generation`, `policy_hash`, `currency`, `reporting_timezone`, `as_of`, `report_from`, `report_to`, `history_complete`, `facts_complete`, `limitations`. Valores monetários/razões decimais via string ou `null`. Não há fallback de `null` para zero. `report_to` é exclusivo. A janela requisitada deve caber na publicação e ter no máximo 366 dias.

| Rota | Leituras após HEAD | Limites relevantes |
| --- | --- | --- |
| `GET /v1/stores/{store_id}/overview` | `analytics_store_daily`, `analytics_customer_purchase_sequence` | Datas locais fechadas; solicitado, atendido e cancelado separados. Leads, LTV completo, CAC, pago e mídia `null`/limitation. |
| `GET /v1/customers` | `analytics_customer_metrics` + projeção mínima `up_core.customers` | Só compradores observados; perfil opcional; cursor SHA/HMAC, até 100. Não expõe email, telefone, documentos ou endereço. |
| `GET /v1/customers/{customer_id}` | Mesmas + `analytics_customer_purchase_sequence` | Resumo observado, sem Customer 360/timeline offline. |
| `GET /v1/customers/{customer_id}/orders` | Existence check Analytics + `up_core.orders` | Cursor até 100; cancelados e status real preservados; solicitado ≠ atendido ≠ pago. |
| `GET /v1/retention` | `analytics_customer_purchase_sequence`, `analytics_purchase_distribution`, `analytics_cohorts` | Compradores/recompra observados; progressão 1→5+, médias/medianas observadas; coorte imatura fica `null`; 1000 células máximas. |
| `GET /v1/products` | `analytics_products_daily` | `product_id=null` se não resolvido; sem nome/estoque/variante inventados; compradores distintos entre dias `null`; cursor até 100. |
| `GET /v1/funnel` | `analytics_funnel_daily` | Estágios oficiais; `purchase` é evento, não pedido financeiro; exige `observation_complete=true` nos dias. |
| `GET /v1/geography` | Nenhuma enquanto a cobertura não for certificada | 424 `geography_coverage_not_certified`. UI demo permanece intacta. |

Clientes/pedidos/produtos usam ordenação estável com chave de cursor opaca assinada: hash de identidade ou timestamp + hash do pedido. Token vincula usuário, role, tenant, loja, operação, policy, geração, rota, filtros e tamanho. A chave HMAC deve vir de configuração secreta **server-side** no futuro, não do navegador/Git. O probe gera chave efêmera e não pagina. Cursor não substitui autorização. Troca de geração invalida o cursor.

O cliente HTTP TS valida envelope, metadata, escopo, paginação, decimais, `null` e projeções B2B. `customerCard` mostra o mapeamento para um view model **nullable**. O `DataApi` atual é demo e possui campos obrigatórios incompatíveis com ausência real. Por isso o adaptador real não é selecionado por `src/services/api/index.ts` e a UI não recebe mistura silenciosa de fixture com dado real. `frontend/src/services/api/server.ts` lê somente configuração privada `DASHBOARD_DATA_MODE=read-api` e `DASHBOARD_READ_API_BASE_URL`, sem variável `NEXT_PUBLIC`; ainda requer sessão/autenticação reais para uso. Não informar esses valores para a UI demo como se a sessão mock fosse válida.

## Custo, IAM e operação

`ReadBudget` propõe **1 GiB de `maximum_bytes_billed` por query**, **8 GiB reservados no máximo por request** e timeout de 30 s. HEAD consome uma reserva. O BigQuery também impõe o teto individual. Falha de orçamento retorna `query_budget_exceeded` (503); outras falhas retornam código genérico sem SQL/PII. Logs allowlisted registram `request_id`, `store_id`, recurso, geração, duração, bytes, linhas e status. Não registram payload, customer_id, query params, SQL nem exceção original.

IAM mínimo para a identidade **futura** da Read API: `roles/bigquery.jobUser` no projeto DEV; `roles/bigquery.dataViewer` nos datasets `up_analytics` e `up_core`. Sem writer/admin e sem permissões Meta. Para autenticação HTTP e segredo de cursor, escolher provedor de identidade e armazenamento server-side antes do deploy. Nenhum IAM foi alterado neste change. Restringir o acesso à API e desabilitar logs de URL/payload que exponham IDs de cliente.

Depois de revisar/aprovar uma primeira operação **read-only** em DEV, executar no Cloud Shell com ADC de operador que tenha as permissões acima:

```sh
cd ~/up-data-intelligence
python -m src.dashboard.dev_probe \
  --project up-data-intelligence-dev \
  --location southamerica-east1 \
  --policy config/analytics/mx-fashion.dev.json \
  --tenant-id operator-probe \
  --store-id mx-fashion \
  --from 2026-09-01 \
  --to 2026-09-02 \
  --allow-bq-read
```

`operator-probe` é apenas o marcador local da execução de diagnóstico, não um tenant autorizado do serviço HTTP; o BigQuery autentica o operador por ADC/IAM. Não usar `demo-up` como autorização real. Esse comando consulta HEAD/RECEIPT e somente um dia de Overview, imprime metadata/contagem sem PII/valores comerciais e não faz escrita. O servidor HTTP e o cutover do frontend só podem avançar depois de autorização/autenticação reais, teste de consulta DEV, cobertura geográfica, confirmação da policy/publicação e adequação dos view models nullable. O custo real depende dos bytes processados; os números acima são tetos, não previsão de gasto.

## Validação offline

```sh
.venv/bin/pytest -q tests/dashboard
.venv/bin/ruff check src/dashboard tests/dashboard
.venv/bin/ruff format --check src/dashboard tests/dashboard
.venv/bin/mypy src/dashboard
cd frontend && npm run lint && npm run typecheck && npm test
```

Nenhuma tabela, schema, policy, job, scheduler, IAM ou integração Meta é criada/alterada. Sem query, migração, backfill ou deploy nesta entrega.
