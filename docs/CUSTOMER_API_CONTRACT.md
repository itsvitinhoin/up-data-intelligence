# Customer API — contrato futuro 1.0.0

CHANGE #12 não publica servidor, não altera o adaptador `/v1` do Epic #11 e não consulta BigQuery. As rotas abaixo são nomes lógicos do contrato futuro; prefixo/versionamento de transporte deve ser aprovado antes de disponibilizar HTTP. O contrato legível por máquina está em `config/contracts/customer-intelligence.v1.json`. O OpenAPI anterior permanece inalterado e descreve somente a implementação anterior.

## Contexto obrigatório

Todas as chamadas exigem store_id e principal autenticado com autorização dessa loja, inclusive rotas por customer_id/order_id. Identidade completa é `(store_id,customer_id)`. Autorização precede acesso e cache; store_id fornecido pelo usuário não concede permissão.

Metadata comum: contract_version, store_id, generation, policy_hash, currency, reporting_timezone, as_of, calculated_at, history_from, report_from/report_to, history_complete, facts_complete e limitations. Cada coleção/entidade deve ter loja explícita. Usar uma geração consistente em toda a resposta; não misturar timeline velha com pedidos novos. Coverage false/unknown deve aparecer, não ser substituída por certeza.

## Contratos

| GET | Estrutura/finalidade |
| --- | --- |
| `/customers/{customer_id}` | profile, commercial, marketing, timeline_summary, orders_summary, products_summary, segmentation, health, metadata |
| `/customers` | data (identidade/resumo permitido), pagination, metadata |
| `/customers/{customer_id}/timeline` | data com eventos oficiais cronológicos, pagination, metadata |
| `/customers/{customer_id}/orders` | data com histórico comercial por pedido distinto, pagination, metadata |
| `/orders/influenced` | data com order, customer, campaigns, requested_total, fulfilled_total, requested_quantity, fulfilled_quantity, influence_scope/evidence_type, pagination, metadata |

Detalhe: profile possui somente customer_id/store_id/customer_type/company_name/trade_name/state/city. Commercial usa exatamente o catálogo, sem campo revenue genérico. Marketing inclui três flags nullable, campaigns_participated, first_campaign_id, last_campaign_id, campaign_touch_count e escopo/cobertura. Timeline_summary contém limites/contagens resolvidas; orders_summary e products_summary são resumos, nunca arrays ilimitados. Histórico completo é paginado nas rotas próprias. Produtos sem vínculo canônico mantêm product_id=null e limitation explícita. Health retorna score/status null e NOT_DEFINED, nunca uma pontuação fictícia.

Exemplo parcial sintético de commercial (com store_id/customer_id na entidade):

```json
{
  "store_id": "synthetic",
  "customer_id": "c1",
  "requested_revenue": "10000",
  "fulfilled_revenue": "8500",
  "fulfillment_rate": "0.850000000",
  "revenue_gap": "1500"
}
```

Pedidos influenciados incluem um pedido uma vez, mesmo com várias campanhas. Filtro de campanha seleciona participação, não crédito exclusivo. Não utilizar um JOIN que multiplique requested_total. Arrays de campanha devem ter limite explícito e truncation/count ou paginação: nunca truncar sem indicar.

## Filtros e paginação

`/customers`: store_id, customer_type, state, city, paid_media_influenced, has_repurchase, first_purchase_date, last_purchase_date, min_requested_revenue, max_requested_revenue. Boolean estrito true/false; texto exato; AND entre filtros; datas de compra qualificante no timezone da policy; min/max decimais inclusivos. Unknown não satisfaz filtro false nem true. Na **futura** API, paid_media_influenced corresponde à flag lifetime oficial; na API offline anterior corresponde à influência em pedidos na janela. Não trocar silenciosamente essa semântica.

`/orders/influenced`: campaign_id, customer_id, date_from inclusivo/date_to exclusivo na data local do pedido, min/max requested_revenue e influence_scope LIFETIME/ACQUISITION/REPEAT_PURCHASE. `/customers/{id}/orders` inclui cancelados e pode filtrar status/data; purchase_number permanece NULL quando não qualificante.

Coleções exigem pagination com page (≥1), page_size (padrão20, máximo100) e cursor (próxima página ou NULL). Página2+ requer token anterior, sem offset arbitrário. Cursor opaco assinado deve estar vinculado a loja, principal/autorização, rota, filtros, policy/geração e page_size. Reiniciar quando mudar geração. Ordenação estável: timeline `(occurred_at,event_key)`, pedidos `(created_at,order_id)`, clientes por customer_id dentro da loja. Token não é autorização nem deve conter PII aberta.

Não calcular milhões de eventos por requisição: API → leitura materializada Customer360, com armazenamento/índices, orçamento, rate limits e cache futuro por tenant/geração/autorização. O adaptador atual é referência em memória; não representa prova de escala.

## Erros, evidência e segurança

200 lista vazia quando nenhum resultado; 404 cliente autorizado inexistente; 401 principal ausente/inválido; 403 loja negada; 400 filtro/cursor inválido; 405 método não permitido. Evitar erros que revelem entidades de outra loja. Pending métrica retorna NULL + motivo/cobertura, não número zero inventado. Evento sem evidência não ganha cliente; dados rejeitados permanecem auditáveis upstream.

Timeline retorna event_type/occurred_at/customer_id/store_id/order_id/campaign_id/evidence_type e chave estável. evidence_refs internas não são expostas automaticamente. paid_touch, order_updated ou reactivation não surgem somente por serem nomes no catálogo: exigem produtor/regra comprovados.

INTERNAL, ANALYTICS e RESTRICTED são classificações de campos, não roles ou permissões herdadas. Nenhuma resposta contém CPF, CNPJ completo, telefone ou email por padrão. viewer/manager/admin não recebem bypass de loja/PII. company_name/trade_name podem identificar pessoas: ainda exigem controle de acesso e minimização. Autenticação HTTP, retenção/LGPD, autorização externa e auditoria de acessos são futuras integrações.

## Compatibilidade e pendências

Não ativar estas rotas como aliases automáticos de `/v1`. O contrato #11 usa journey/orders/products, sem rota própria de orders; #12 especifica novos nomes e contrato de consumo. Não renomear campos físicos nem alterar respostas existentes. first_order_at de todos status exige orders_summary; o campo homônimo do profile atual é primeira compra qualificante. Lifetime/contact e primeira/última campanha identificada também exigem adaptação explícita.

Pendências para implementação futura: decisões comerciais de ACTIVE/HIGH_VALUE/AT_RISK/reativação; fórmula de Health; produtores de eventos ainda não demonstrados; adaptação da cobertura de mídia lifetime; autenticação/armazenamento de leitura/paginação de produção. Este CHANGE entrega contrato, referência pura e testes, não materialização/deploy adicional.
