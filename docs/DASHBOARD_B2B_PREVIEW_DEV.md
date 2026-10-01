# CHANGE #15B.2 — Preview B2B Analytics V1

Implementação offline baseada em `8f391945a96d309c63350471bf6b8ef0c5d32e53`. Nenhuma leitura BigQuery, GCP, deploy, Terraform, backfill, materialização ou execução do Python preview ocorreu neste change. O teste de navegador usa somente envelopes sintéticos interceptados no bridge, com Next isolado em localhost:3115, sem backend/credenciais. O build Next de produção permanece fora da validação.

## Caminho de leitura

Browser → Next same-origin `/api/dashboard/*` → allowlist explícita → binding DEV server-side → Python loopback → DashboardService → BigQuery DEV. `demo-up / mx-fashion-b2b / B2B` resolve para a loja canônica `mx-fashion`. IDs de workspace e de dados são diferentes. O browser não envia a loja canônica nem recebe token/URL do Python. `api = demoApi` permanece global. B2C e marcas sem binding continuam explicitamente demonstrativas.

O modo `DASHBOARD_DATA_MODE=read-api-preview` só funciona no Next em desenvolvimento. A allowlist Python exige token efêmero, GET, 127.0.0.1, projeto DEV, `--allow-bq-read`, policy e confirmação da loja. Não expõe Admin, Performance ou Meta. Isso **não é autenticação de produção**: requer host de desenvolvimento confiável e privado; a sessão Maria é apenas UI demo, não uma identidade de produção. Preservados guards de principal/grants no Python, isolamento por tenant/store/operação e entidade, projeções de PII e SQL parametrizado.

Cada request resolve HEAD + RECEIPT completed válida, fixa `snapshot_at` e aplica a mesma leitura temporal às fontes Analytics/CORE da request. CORE é snapshot de leitura atual, não o snapshot original da geração Analytics: essa limitação segue na metadata. Geração/policy diferentes não se combinam no cliente; uma geração nova invalida a resolução da publicação e reinicia a paginação. Cada nova request resolve novamente HEAD; não há promessa de transação global entre telas ou entre páginas CORE durante mutações simultâneas.

Para descobrir binding/cobertura, as páginas B2B usam uma leitura bounded de Overview da janela completa, compartilhada pelo cache de 30 s. Depois fazem somente a leitura do recurso permitido. Performance apenas usa essa cobertura para exibir indisponibilidade; não consulta endpoint Performance nem fixtures. Geography faz a leitura permitida e mantém 424. Falha de HEAD/upstream não seleciona demo para a loja vinculada.

## Matriz de fontes

| Página / rota existente | Fonte | Estado no piloto | Limitação |
|---|---|---|---|
| Overview `/b2b` | store_daily + purchase_sequence | real, histórico parcial | Novos definitivos, LTV completo, CAC, pagamento e leads sem cobertura |
| Pedidos `/b2b/commercial` | CORE orders | real, parcial | Snapshot atual; solicitado ≠ atendido ≠ pago; inclui cancelados |
| Aquisição `/b2b/acquisition` | purchase_sequence, purchase_number=1 | real, parcial | Primeira compra observada; novos confirmados NULL; sem LeadCards/velocidade demo |
| Retenção `/b2b/retention`, alias repurchase | purchase_sequence + purchase_distribution + cohorts | real, parcial | Cards no recorte; progressão/gaps/cohorts sobre publicação inteira; imaturos NULL; sem série diária inventada |
| Clientes `/b2b/customers`, alias `/customers` | customer_metrics + sequence + CORE profile permitido | real, parcial | Compradores no recorte; métricas individuais históricas; sem busca global/segmento/mídia demo |
| Detalhe `/customers/{id}` | customer_metrics + sequence | Customer Summary, parcial | Sem Customer 360/timeline/campanhas/produtos demo; sem CPF/CNPJ/email/telefone/endereço |
| Pedidos do cliente | CORE orders, customer validado na loja | real, parcial | Histórico observado até as_of; sem filtro global; inclui cancelados |
| Produtos `/b2b/products` | products_daily | real, parcial | ID/SKU nullable; sem nome inferido; estoque/grade/ABC/views/cores/tamanhos/compradores únicos indisponíveis |
| Geography `/b2b/geography` | publicação, depois endpoint 424 | unavailable-real | Mapa neutro preservado; sem heatmap/cidades/números demo |
| Performance `/b2b/performance` | apenas cobertura da publicação | unavailable-real | Camadas #08–#14 offline; sem endpoint fake, spend/CAC/ROAS/campanhas/influência demo |
| Funil | funnel_daily | endpoint/adapter preparado | Não há superfície B2B de funil acessível no HEAD; não criada navegação nova. Rota B2C continua demo |
| B2C / outras marcas | demoApi | demo | Sem cutover global |

## Endpoints e filtros

| Python | Next | Filtros além do escopo |
|---|---|---|
| `/v1/stores/{store}/overview` | `/api/dashboard/overview` | from/to |
| `/v1/orders` **novo** | `/api/dashboard/orders` | from/to, status, page_size, cursor |
| `/v1/acquisition` **novo** | `/api/dashboard/acquisition` | from/to |
| `/v1/customers` | `/api/dashboard/customers` | from/to aditivos, page_size, cursor |
| `/v1/customers/{id}` | `/api/dashboard/customers/{id}` | nenhum filtro de período |
| `/v1/customers/{id}/orders` | `/api/dashboard/customers/{id}/orders` | page_size, cursor |
| `/v1/retention` | `/api/dashboard/retention` | from/to |
| `/v1/products` | `/api/dashboard/products` | from/to, page_size, cursor |
| `/v1/funnel` | `/api/dashboard/funnel` | from/to |
| `/v1/geography` | `/api/dashboard/geography` | nenhum; 424 |

Python aceita `store_id` apenas quando validado pelo principal. Next aceita apenas workspace/tenant/operação e filtros listados, rejeita loja canônica/URL/path fornecidos pelo browser e parâmetros extras/duplicados. Erros retornam códigos sanitizados sem SQL, valores, IDs ou credenciais em logs. O Next desabilita o logging de desenvolvimento no modo read-api-preview, impedindo logs automáticos de URLs/query strings/IDs; Python QuietRequestHandler também não registra paths/headers. Logs estruturados BigQuery continuam limitados à allowlist operacional.

Pedidos gerais: DATE(created_at, timezone da policy) em `[from,to)`, created_at < as_of, store/source upzero antes do resultado, ordenação crescente `(created_at, order_id)`. Cursor HMAC opaco para o consumidor, vinculado a principal, tenant/store/operação, policy, geração, tamanho de página, janela/status/as_of; não concede autorização. Não é criptografia. Mudança desses campos invalida cursor. Não misturar com o endpoint do histórico de um cliente.

Aquisição: seleciona `purchase_number=1` **antes** do recorte; soma apenas os primeiros pedidos observados com order_date dentro do período. Valida unicidade por customer/order dos primeiros pedidos; duplicidade falha explicitamente. `confirmed_new_customers=NULL` sob histórico parcial. Receita com ausência de valor mantém NULL; seleção vazia realmente observada pode retornar zero. Ticket usa divisão decimal BigInt com arredondamento, sem float financeiro.

Clientes: período opcional/aditivo usa EXISTS sobre compras qualificantes, mesma loja/policy/snapshot. Sem período, mantém contrato histórico anterior; UI real envia a janela da publicação por default. Summary/history usam histórico observado inteiro disponível até as_of, com texto explícito e filtro global oculto. Perfis atuais continuam auditáveis na fonte sem inferência de estado/cidade.

## Cobertura, dinheiro, cache e escala

NULL ≠ zero; unknown ≠ false. Moedas continuam strings decimais. Tickets e formatação monetária de strings usam BigInt; Number só participa de desenho de gráfico/coloração, não cálculo financeiro. Retenção madura usa taxas certificadas; células imaturas permanecem traço. Produtos sem identidade canônica não recebem ID inventado, e nome ausente usa SKU ou “Produto não identificado”.

UI usa `to` inclusivo; bridge converte uma única vez para API exclusiva com helper existente/testado. A janela/presets reais vêm da publicação, nunca DEMO_TODAY. Fora da cobertura → erro, sem clipping silencioso. Fonte por página: demo/loading-real/real/partial-real/unavailable-real/error-real; badge, footer e PDF refletem o recurso atual. Sem busca/notificações demo em páginas reais.

Listas usam cursor, 25 por página na UI, máximo backend 100. Anterior/Próxima, sem carregar tudo. Período/status/workspace/operação/geração reiniciam cursores. Exportação real CSV/XLSX inclui **somente página carregada**, explicitamente rotulada; não promete exportação global. Cache inclui modo, sessão/role, tenant, workspace, operação, recurso, filtros, geração, policy, cursor e customer quando aplicável. Nenhum cache de dados reais em localStorage.

Custos inalterados: **1 GiB/query, 8 GiB/request, timeout 30 s/query**. Budgets são tetos, não previsão. Bootstrapping é uma request adicional quando sem cache; tetos não são orçamento agregado da sessão completa. Permissões futuras: `bigquery.jobs.create` no projeto DEV e leitura de dados apenas nos datasets/tabelas Analytics V1 e CORE permitidos; sem writer, mutação de Secret Manager ou acesso Meta. Nenhum IAM foi alterado.

## Validação offline executável

Na raiz, com dependências locais já instaladas:

```sh
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy
(cd frontend && npm test && npm run lint && npm run typecheck && npm run format:check)
(cd frontend && ./node_modules/.bin/playwright test --config=playwright.b2b-preview.config.ts)
git diff --check
```

Playwright padrão deste arquivo **intercepta todos os recursos** com envelopes sintéticos; não inicia Python preview, não fornece credenciais e usa Next isolado na porta 3115. Chrome pode ser selecionado por `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. `.next-offline`, test-results, caches e artefatos locais não são versionados. Não interpretar essa execução como validação BigQuery real. Produção build Next não validado nesta rodada.

Validação desta entrega: **597 testes Python, 99 testes frontend e 3 testes Playwright offline aprovados**; ruff, formatting, mypy, eslint, typecheck, Prettier e `git diff --check` aprovados. Warnings de execução: conflito NO_COLOR/FORCE_COLOR do runner, sem impacto funcional. Nenhum build Next de produção nem query real foi executado.

## Rodada DEV futura — somente após autorização live

Requisitos: pull do commit aprovado, ADC do operador/IAM read-only, policy atual e HEAD/RECEIPT completed, dependências Python/frontend e navegador Playwright instalado. Não migrar, materializar ou inicializar HEAD. Encerrar processos locais 3100/8765 antigos antes de iniciar; não expor túnel público.

Terminal 1, raiz do repo, **não executado neste change**:

```sh
export DASHBOARD_DEV_PREVIEW_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/python -m src.dashboard.dev_preview_server \
  --project up-data-intelligence-dev \
  --location southamerica-east1 \
  --policy config/analytics/mx-fashion.dev.json \
  --tenant-id demo-up --store-id mx-fashion --confirm-store mx-fashion \
  --host 127.0.0.1 --port 8765 --allow-bq-read &
b2b_preview_pid=$!
trap 'kill "$b2b_preview_pid" 2>/dev/null || true; unset DASHBOARD_DEV_PREVIEW_TOKEN' EXIT
cd frontend
DASHBOARD_DATA_MODE=read-api-preview \
DASHBOARD_READ_API_BASE_URL=http://127.0.0.1:8765/ npm run dev
```

Terminal 2, após Next pronto, na raiz:

```sh
cd frontend
DASHBOARD_E2E_LIVE=1 ./node_modules/.bin/playwright test \
  --config=playwright.b2b-preview.config.ts
```

`DASHBOARD_E2E_LIVE=1` desativa todos os mocks e não inicia servidores automaticamente. Faz a mesma rodada Maria → MX B2B → Overview → Pedidos → Aquisição → Retenção → Clientes → Summary + pedidos → voltar → Produtos → Geography 424/mapa → Performance indisponível → B2C demo; outro teste verifica marca não vinculada demo. Não imprime IDs/payloads. Resultados/artefatos locais são ignorados; não enviar capturas/exportações com dados pessoais ao Git. Referências de Overview: solicitado 86.319,62; atendido 73.220,13; taxa 84,82%; gap 13.099,49; cancelada 6.262,75; pedidos 18/cancelados 2; compradores 16/recorrentes 0/frequência 1, na publicação aprovada. Mudar publicação exige revisar referências, nunca substituir resposta por fixture.

Êxito: dados da geração/policy correta nas superfícies cobertas, NULL preservado nas incompletas, nenhuma fixture nas páginas reais, 424 apenas Geography, Performance explicitamente sem materialização, B2C/outras marcas demo; nenhum erro JS ou erro inesperado de leitura. Encerrar com Ctrl+C no terminal 1 e limpar token da sessão. Não há migration/schema/build obrigatório neste change: é código de leitura/preview; qualquer deploy público fica para etapa futura de auth real.
