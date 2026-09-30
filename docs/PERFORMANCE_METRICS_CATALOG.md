# Performance metrics — contrato offline 1.0.0

Todas as métricas devem carregar loja, conta, moeda, timezone, janela, escopo, policy, geração e cobertura. Receita influenciada não é atribuição exclusiva nem prova de pagamento. Nunca usar `revenue` genérico.

| Métrica | Fórmula/definição |
| --- | --- |
| spend / meta_spend | Soma de spend da série Meta campaign/dia, sem breakdown, configuração única, cobertura certificada |
| observed_spend / observed_meta_spend | Soma observada disponível, mesmo quando cobertura não está completa; não usar como denominador certificado |
| impressions / clicks | Valores Meta do dia/campanha; ausência NULL salvo ausência de linha sob cobertura completa certificada |
| ctr | clicks × 100 / impressions, percentual |
| cpc | spend / clicks, moeda por clique total |
| cpm | spend × 1000 / impressions |
| influenced_customers | Customer_ids distintos com pedido qualificante influenciado na seleção |
| influenced_orders | Order_ids distintos qualificantes com contato pago anterior comprovado |
| new_customers_influenced | Customer_ids distintos cuja primeira compra qualificante confirmada foi influenciada; NULL se candidatos/cobertura impedem classificar |
| requested_revenue_influenced | SUM requested_total por pedido distinto selecionado |
| fulfilled_revenue_influenced | SUM fulfilled_total por pedido distinto selecionado |
| requested_quantity_influenced | SUM requested_items_qty por pedido distinto selecionado |
| fulfilled_quantity_influenced | SUM fulfilled_items_qty por pedido distinto selecionado |
| roas_requested | requested_revenue_influenced / spend |
| roas_fulfilled | fulfilled_revenue_influenced / spend |
| cac_new_customer | spend / new_customers_influenced |
| fulfillment_rate | fulfilled_revenue_influenced / requested_revenue_influenced |

No modelo campanha/cliente, métricas B2B usam requested_revenue/fulfilled_revenue e requested_quantity/fulfilled_quantity. No modelo campanha/pedido, preservar requested_total/fulfilled_total e requested_items_qty/fulfilled_items_qty. Solicitação e atendimento não provam liquidação. Cancelados ficam fora das compras qualificantes, influência comercial e novos clientes, mas investimento não desaparece por cancelar pedido.

## Precisão e ausências

Decimal, nunca float para dinheiro. NUMERIC serializado em string, razões com 9 casas, HALF_EVEN. NULL propaga ausência de componentes; conjunto vazio observado soma zero. Denominador zero→NULL. Receita zero com spend positivo→ROAS zero; spend zero→ROAS NULL; spend zero e novos clientes confirmados positivos→CAC zero; novos clientes zero/desconhecidos→CAC NULL. Sem completar cobertura, não substituir NULL por zero.

ROAS/CAC exigem influência completa e gasto completo. Novos clientes exigem classificação histórica suficiente; histórico completo depende de evidência da origem/ausência de lacunas, não tamanho arbitrário da janela. first purchase e previous purchase são definidos em PERFORMANCE_INTELLIGENCE.md; nenhuma equivalência com novo cadastro/aprovado.

Valores de atendimento acima do solicitado não são limitados artificialmente a 100%; devem ser revisados como qualidade. Valores negativos de gasto ou das bases comerciais são inválidos. Não calcular médias simples de taxas; recomputar por numeradores/denominadores compatíveis. Não somar séries diferentes, scopes ou campanhas com pedidos compartilhados.

## Exemplo e consistência

Para investimento R$5.000, solicitado R$500.000 e atendido R$420.000:

- ROAS solicitado: 100x.
- ROAS atendido: 84x.
- Atendimento: 84%.
- 35 novos clientes confirmados e influenciados → CAC R$142,857142857, exibível como **R$142,86**, não R$142.

O exemplo de 100 clientes influenciados para 80 pedidos não pode representar 100 compradores distintos se cada pedido tem um único customer_id. Neste contrato, influenced_customers ≤ influenced_orders; se 100 representar pessoas expostas à mídia, seria outra métrica e não o denominador desta camada. Não fabricar pedidos/clientes para encaixar o exemplo.

Resumo da loja deve deduplicar pedidos compartilhados: campanha A e B participam de um mesmo pedido solicitado de R$100; ambas podem mostrar R$100 de participação, mas a loja continua R$100. A receita por campanha não deve ser somada como se fosse exclusiva. Spend das duas campanhas é somado uma única vez por série/dia.

## Novas compras e cobertura

Campos is_new_customer/previous_purchase_exists são triestado. Evidência de compra antiga comprova não novidade mesmo com histórico incompleto; ausência de compra antiga só comprova novidade com history_complete e HistoryCoverage válidos. historical_purchase_count_before_first_purchase é contagem observada antes do classification_order_id, cujo significado fica explícito nos dados. history_complete=false mantém first_purchase_at como primeira observada, não primeira absoluta.

Contagem mensal não é soma de clientes diários: um cliente pode comprar em vários dias. Também não somar novos clientes ou pedidos entre campanhas. Use a união de IDs no summary. As datas diárias de pedido e gasto são distintas bases temporais alinhadas por dia local; uma compra de hoje pode ter touchpoint de mês anterior, portanto ROAS diário mede eficiência comercial associada ao período, não retorno causal do investimento daquele dia.

ROAS pago, CAC causal, Payment Ledger, margem, lucro e LTV pago não existem nesta entrega. Custos externos à Meta também não entram no gasto apresentado. A interface futura deve exibir qualificadores “solicitado”, “atendido”, “influenciado” e cobertura, nunca vender esses números como receita paga ou atribuição exclusiva.
