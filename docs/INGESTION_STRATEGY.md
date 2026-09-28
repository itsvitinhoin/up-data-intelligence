# Ingestão — implementação da Fase 1

Contrato: [upzero-openapi.json](upzero-openapi.json). Implementados **somente GET customers, orders e analytics/facts** via X-API-Key. Demais endpoints do inventário arquitetural são futuros. Nenhum teste live foi executado.

| Recurso | Paginação | Incremental / reconciliação |
|---|---|---|
| customers | limit até 200; after_id = menor ID da página; ID estritamente decrescente; encerra em página vazia | Descoberta inicia no topo e atravessa maior ID anterior; alterações antigas são capturadas por reconcile completo |
| orders | page desde 1 até total_pages; limit até 200 | Filtros created_at inclusivos na timezone configurada; lookback de criação + faixas de datas de pedidos abertos + backfill/reconciliação histórica |
| analytics/facts | cursor opaco/next_cursor; limit até 1000 | Janela fixa [from,to), lookback configurável, backfill diário e atualização de Fact existente |

Datas de clientes usam UTC; inclusividade precisa de validação de contrato real. Datas sem offset na CLI significam dias UTC e podem gerar sobreposição de datas de pedidos após conversão local. Idempotência evita duplicar estado corrente. API não promete snapshot transacional; pedidos podem mudar de página, justificando reconciliação.

## RAW, checkpoint e promoção
Conector sanitiza antes de devolver página. Engine reaplica política defensivamente, grava RAW e checkpoint pending em transação; somente depois normaliza. CORE/histórico/qualidade/checkpoint são promovidos em outra transação. Hash representa payload sanitizado. Nenhum header entra nos registros.

Falha antes de promoção deixa RAW pending para replay automático na mesma execução lógica. Página com erro de paginação é preservada e não avança cursor. Erro de transformação mantém RAW e registra quality_results/records_failed, finalizando como completed_with_errors e checkpoint needs_review. Reprocessamento manual tem run próprio; após revisão, nova coleta validada pode fechar a janela.

Mesmo payload de mesma entidade não duplica CORE nem versão. Fonte com updated_at antigo não sobrepõe versão nova; empate de timestamp com conteúdo divergente gera alerta. Para facts/clientes sem timestamp de alteração, ordered observations são preservadas; replay de observação antiga não desfaz estado posterior. A mesma correção de Fact conserva identidade store_id+fact_id e cria uma versão.

## Operação
CLI em [README](../README.md): sync, backfill, reconcile, quality e replay. Retry somente para timeout/429/5xx, exponencial com jitter e Retry-After; limite padrão cinco tentativas. Retry-After superior a 300s adia o run com erro seguro, sem insistir antes do prazo. 3xx não é seguido; 4xx não recuperável encerra. Código não faz escrita UP Zero.

Lookbacks são configuráveis; não garantem capturar toda correção antiga. customers usa keyset, nunca assume primeira página completa. Pedidos abertos são reconsultados por **listagem nas datas de criação conhecidas**, pois endpoint de detalhe não está autorizado nesta fase. Não inventar filtro order_id/updated_since. Reconcile faz varredura histórica por datas; não limita a pedidos recentes.

Locks: flock offline, GCS create/delete com generation precondition no cloud. Um escritor por loja; sem takeover automático. Após crash abrupto/timeout, operador confirma ausência de execução ativa antes de retirar lock. Estado da loja continua no BigQuery, permitindo retomada.

## Escala e custos
Página é unidade de memória e transação; query parameters permitem staging sem load jobs por página. Limite preventivo 8 MB, ajustável indiretamente via page_limit; excesso falha, não trunca. BQ faz joins/qualidade em SQL, sem carregar milhões de eventos no processo. Replay lê páginas do run por iterador ordenado, sem carregar o run inteiro em memória; manter janelas pequenas também facilita operação e revisão. Medir quotas, custo e duração antes de aumentar volume ou número de lojas.

Sem rate limit/retention/SLA no OpenAPI, validação piloto é obrigatória antes de schedules. Terraform deixa schedules pausados. O source_connection resolve a loja por referência de secret; identidade tenant precisa ser confirmada externamente antes do primeiro uso real.
