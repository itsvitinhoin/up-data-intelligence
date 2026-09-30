# Customer metrics catalog — contrato 1.0.0

Escopo comum: uma loja, um customer_id, uma moeda/policy, uma geração consistente, snapshot observado antes de `as_of` exclusivo. Pedidos distintos por order_id; status vigente no snapshot. Não combinar lojas, moedas ou gerações. Cancelamento posterior exige recomputação autorizada em outra geração.

## Comercial

| Campo | Fórmula/fonte | Unidade e regra |
| --- | --- | --- |
| orders_count | COUNT pedidos distintos, todos status | Inteiro ≥0, inclusive cancelados |
| first_order_at | MIN created_at de todos pedidos | Timestamp; NULL sem pedidos |
| last_order_at | MAX created_at de todos pedidos | Timestamp; NULL sem pedidos |
| purchase_count | COUNT pedidos em qualifying_order_statuses | Inteiro; CANCELED excluído |
| requested_revenue | SUM requested_total, todos pedidos | Decimal/moeda; intenção comercial, não receita recebida |
| fulfilled_revenue | SUM fulfilled_total, todos pedidos | Decimal/moeda; atendimento, não pagamento |
| requested_quantity | SUM requested_items_qty | Decimal/unidades, sem arredondar para inteiro |
| fulfilled_quantity | SUM fulfilled_items_qty | Decimal/unidades |
| fulfillment_rate | fulfilled_revenue / requested_revenue | Razão, 0.85 = 85%; NULL denominador zero/desconhecido |
| quantity_fulfillment_rate | fulfilled_quantity / requested_quantity | Razão, mesmas regras |
| revenue_gap | requested_revenue − fulfilled_revenue | Decimal/moeda |
| quantity_gap | requested_quantity − fulfilled_quantity | Decimal/unidades |

Totais comerciais de todos os pedidos mantêm cancelamento visível; **não são totais qualificantes para LTV/cohort/retenção**. Recompra, frequência qualificante e LTV continuam usando a policy existente: RESERVED, CONFIRMED, PROCESSING, INVOICED, SHIPPED para MX Fashion; nunca CANCELED. Não embutir essa lista como política universal de todas as lojas.

Exemplo: solicitado 10000, atendido 8500 → fulfillment_rate="0.850000000", revenue_gap="1500". Solicitado 100 unidades, atendido 80 → quantity_fulfillment_rate="0.800000000", quantity_gap="20". Não chamar ambos de revenue.

Valores serializados como strings decimais, nunca floats binários. Referência offline usa precisão decimal ampliada e ratios com 9 casas, ROUND_HALF_EVEN. Componentes ausentes propagam NULL, não zero; coleção vazia soma zero. Quantidade/valor solicitado zero deixa taxa NULL. Não calcular média simples de taxas por pedido: dividir somas. Atendimento acima do solicitado produz taxa >1 e gap negativo, sem clamp; exige revisão de qualidade, não correção silenciosa. Valores negativos na entrada de totais são inválidos conforme referência atual, não representam automaticamente devolução.

## Compatibilidade com Epic #10

| Contrato oficial | Campo/cuidado atual |
| --- | --- |
| orders_count | profile.total_orders |
| requested_revenue / fulfilled_revenue | total_requested_revenue / total_fulfilled_revenue |
| requested_quantity / fulfilled_quantity | total_requested_quantity / total_fulfilled_quantity |
| first_order_at / last_order_at | Calcular sobre orders_summary de todos status; **não reutilizar** profile.first_order_at, que hoje representa primeira compra qualificante |
| purchase_count | Mesmo conceito qualificante, somente com mesma policy/cobertura |
| fulfillment rates/gaps | Projeções derivadas; ainda não campos físicos dos modelos |
| first_purchase_date / last_purchase_date | Datas locais da primeira/última compra qualificante, não dos pedidos cancelados |

Nenhum campo antigo é renomeado ou muda de significado nesta entrega. `src/intelligence/data_contract.py` é referência separada do novo contrato, não substitui Analytics V1, materializador #10 ou API #11. Um futuro adaptador deve aplicar esses mapeamentos explicitamente.

## Marketing, retenção e derivação

paid_media_influenced_lifetime = existência de contato pago resolvido na cobertura histórica; acquisition = participação na primeira compra observada; repeat = participação em compra 2+ após compra anterior. Não derivar lifetime somente de pedidos influenciados no report window. Campanhas: conjunto distinto de IDs conhecidos, primeira/última **identificada** por tempo e campaign_touch_count por Fact pago distinto com campanha. Sem somar solicitado/atendido entre campanhas.

has_repurchase = purchase_count > 1. first/last purchase respeitam `(created_at,order_id)` e status qualificantes. ltv_observed existente é solicitado qualificante observado, sem previsão ou margem; manter ltv_basis e history_complete. Eventos e compra derivada não somam uma venda duas vezes.

Recência futura deve declarar atividade elegível e usar as_of/timezone, não o relógio da interface. Segmentos e Health são definidos em CUSTOMER_INTELLIGENCE_CONTRACT.md. Fórmula de Health não existe nesta versão.

Cada métrica derivada precisa apontar grão, policy, janela/history_from, as_of, geração, cobertura, unidade e regra. Evidência de identidade não equivale à prova de completude financeira. Sem vínculo de cliente, pedido não entra nos totais de outro cliente por heurística; pendência deve permanecer auditável.
