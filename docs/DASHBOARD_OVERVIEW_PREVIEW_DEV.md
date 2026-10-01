# Atualização CHANGE #15B.2

O preview B2B foi ampliado. A execução vigente e a matriz por página estão em [DASHBOARD_B2B_PREVIEW_DEV.md](DASHBOARD_B2B_PREVIEW_DEV.md). A descrição abaixo registra o estágio anterior; não use suas limitações de Overview-only para a rodada atual.

# CHANGE #15B.1 — Preview local do Overview B2B

O cutover é **apenas da rota `/b2b`**, no Next.js em modo desenvolvimento e com `DASHBOARD_DATA_MODE=read-api-preview` definido no **servidor**. `api = demoApi` permanece global; B2C e as demais rotas B2B continuam demonstrativas. O badge, o footer e o cabeçalho do PDF sinalizam dados reais somente depois de uma resposta real válida. A busca global de clientes e as notificações demo ficam indisponíveis nessa rota durante o preview para evitar mistura de fontes. Falha da leitura exibe erro, sem recorrer a fixtures.

## Caminho e limites

`Browser → GET /api/dashboard/overview (same-origin) → binding DEV server-side → Dashboard Read API local → DashboardService → BigQuery DEV`. O browser envia `tenant_id=demo-up`, `workspace_operation_id=mx-fashion-b2b`, `operation=B2B` e opcionalmente `from/to` inclusivos. O binding temporário em `frontend/src/services/api/preview-binding.server.ts` resolve esse workspace para `data_store_id=mx-fashion`; o navegador não fornece `data_store_id`. A rota rejeita parâmetros adicionais, operações/lojas fora da allowlist e modo não habilitado. Nenhum token ou URL do backend é exposto ao browser.

O servidor Python só aceita GET `/v1/stores/mx-fashion/overview`, exige token efêmero por header e comparação segura, usa a policy versionada, ADC/IAM do operador e `ReadBudget`: 1 GiB por query, 8 GiB por request, timeout 30 s. Rejeita bind público, projeto sem sufixo `-dev`, ausência de `--allow-bq-read` e confirmação de loja divergente. **Este token local não é autenticação de produção.** O preview só é apropriado em máquina de desenvolvimento confiável, com ambos os processos no mesmo host e Next acessível apenas por loopback. Não publicar esse servidor nem fazer deploy da rota como solução de autenticação. A UI demo não concede direitos de leitura em produção.

## Janela, cobertura e métricas

Sem seleção explícita, a rota omite `from/to` e a API retorna a janela da publicação HEAD/RECEIPT. `metadata.report_to` é exclusivo: `2026-09-28` aparece como `27/09/2026`. O filtro converte o `to` inclusivo da UI para o dia seguinte por DATE UTC, sem timezone do navegador. Presets usam o último dia fechado da publicação; período fora da cobertura retorna erro controlado. Cache TanStack separa modo, usuário, tenant, workspace, operação e filtros. Cada request real mantém metadata de geração, policy, cobertura e limitações. A série do gráfico vem diretamente da API, com gaps `NULL`.

Cards reais: receita solicitada/atendida/cancelada, taxa e gap de atendimento, pedidos solicitados/cancelados, tickets solicitados/atendidos (divisão decimal por BigInt), compradores observados, recorrentes observados e frequência observada. O gauge usa `fulfillment_rate` certificado. Novos definitivos, LTV completo, CAC, receita paga, pedidos pagos, peças, reativados e dias de conversão ficam `NULL` quando sem cobertura. Leads e gráfico diário Novos × Recorrentes exibem estado indisponível; não recebem dados demo. O painel de mídia não é incluído.

## Execução futura, somente após aprovação da leitura DEV

Executar em **um terminal** na raiz do repositório, sem gravar segredo em arquivo ou histórico. O processo do Python e o Next precisam compartilhar a mesma interface loopback; não usar `0.0.0.0`, túnel público ou Cloud Run:

```sh
export DASHBOARD_DEV_PREVIEW_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/python -m src.dashboard.dev_preview_server \
  --project up-data-intelligence-dev \
  --location southamerica-east1 \
  --policy config/analytics/mx-fashion.dev.json \
  --tenant-id demo-up \
  --store-id mx-fashion \
  --confirm-store mx-fashion \
  --host 127.0.0.1 \
  --port 8765 \
  --allow-bq-read &
preview_pid=$!
trap 'kill "$preview_pid" 2>/dev/null || true; unset DASHBOARD_DEV_PREVIEW_TOKEN' EXIT
cd frontend
DASHBOARD_DATA_MODE=read-api-preview \
DASHBOARD_READ_API_BASE_URL=http://127.0.0.1:8765/ \
npm run dev
```

Abrir `http://127.0.0.1:3100/b2b`, selecionar o workspace MX Fashion B2B e conferir o badge **Dados reais · Analytics V1**, o intervalo da publicação e as limitações. Todas as outras páginas mantêm o badge demonstrativo. Se a API falhar ou o período estiver fora da cobertura, o Overview mostra erro, nunca fixture. Encerrar com Ctrl+C; o `trap` encerra o servidor Python. O comando acima **não foi executado neste change**.

Requisitos para uma solução pública futura: identidade verificada no backend, grants reais por tenant/store/operação, proteção CSRF/sessão, rede/IAM apropriados e revisão de observabilidade. Este preview não substitui essas etapas.
