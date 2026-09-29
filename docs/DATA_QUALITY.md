# Data Quality — Fase 1

> Política do CLI atualizada: [Quality Gate por recurso](RESOURCE_SCOPED_QUALITY_GATE.md). Severidade global permanece visível e não equivale a falha da ingestão de outro recurso.

Implementada em [rules.py](../src/quality/rules.py), [engine.py](../src/ingestion/engine.py) e [reconcile.sql](../sql/quality/reconcile.sql). Qualidade não apaga RAW sanitizado. Nenhuma validação foi feita contra dados reais.

| Regra | Tratamento |
|---|---|
| Duplicatas facts/orders/customers | Repetição de chave em página gera warning; estado corrente é idempotente. Query verifica unicidade por loja. event_id duplicado em IDs distintos é indício, não remoção automática |
| Fact sem store_id técnico | Bloqueia promoção; ausência no payload original é normal, pois store_id vem da conexão |
| Pedido sem cliente | Mantido com customer_id nulo e warning, sem inventar relacionamento |
| purchase/purchase_item sem order_id | Warning antes da data configurada por loja ou quando não configurada; alert após vigência, por occurred_at |
| order_id sem Order | Link pending e warning, reavaliado após carga de pedidos; nenhuma aproximação por horário/valor/produto |
| Parser Meta inválido | parse_status específico, valores conflitantes/placeholders não são IDs válidos; warning e preservação de RAW |
| Cursor repetido / after_id sem progresso | Página sanitizada preservada, run falha, checkpoint não avança |
| Sync atrasado | Última execução completa por recurso contra stale_after_minutes; não usa idade do último evento como substituto |
| Transformação monetária inválida | Não converter para zero/NULL silencioso; RAW preservado, registro não promovido, alerta |
| Versão antiga / timestamps iguais divergentes | Não regredir corrente; warning para versão antiga, alerta para conflito |

A consulta de qualidade reavalia eventos atuais quando muda purchase_order_id_effective_at, mesmo sem novo payload. Denominadores checked_count e failed_count permitem calcular cobertura; nenhum LTV/CAC é criado. Todos os checks são tenant-scoped.

## Semântica comercial
Total, solicitado e atendido são mantidos em colunas separadas. Removed items continuam presentes, com qty/original_qty/status originais. Não há soma de purchase + purchase_item para receita, nem payment_id/paid_at inventados. Divergências de fixtures documentadas no Architecture Discovery (items_count e invoice.order_id) não são usadas como verdade de produção.

Validações financeiras mais específicas (tolerância de reconciliação entre subtotal/desconto/frete, quantidades fracionárias e regras de receita) dependem de confirmação de negócio e não foram transformadas em métricas finais.

## Testes e observabilidade
Testes sintéticos cobrem paginação, retry, redaction, multi-tenant, removed, versões, correção de Fact, parser, replay/retomada e relações determinísticas. Rede é bloqueada na suíte. SQLite testa transações locais e mocks validam os contratos do adaptador BigQuery; execução SQL/IAM real fica para dev autorizado.

up_ops.sync_runs registra contagens, páginas, retries, bytes, horários e códigos seguros; quality_results registra regra, severidade, contagens e referência técnica. Os alertas são registros consultáveis e logs; integração externa de notificação não faz parte desta fase.
