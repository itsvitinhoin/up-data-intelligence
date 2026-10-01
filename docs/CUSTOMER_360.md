# Customer 360 — CHANGE #10 (offline)

> Proposta/reference offline histórica. O contrato físico live DEV vigente é [CHANGE #16](CHANGE_16_DEV.md): nomes Meta `meta_live_*`, generation INT64 e publicação Intelligence independente. Conteúdo anterior preservado para auditoria.

Quatro modelos propostos, sem alteração em RAW, CORE, Analytics V1, Meta ou Terraform ativo. O materializador Python trabalha com snapshots locais, reutiliza a resolução determinística da Influence Layer e gera um artefato JSON. Não consulta BigQuery nem inicializa HEAD/receipts remotos.

## Entidades e grãos

| Modelo | Grão por loja | Conteúdo |
| --- | --- | --- |
| `analytics_customer_360_profile` | customer_id | Identidade comercial permitida, totais, primeira compra observada, frequência, LTV observado, flags de influência |
| `analytics_customer_journey_summary` | customer_id | Contatos e campanhas cronológicos, contagens de Facts/sessões/produtos vistos, limites da timeline |
| `analytics_customer_orders_summary` | customer_id + order_id | Um pedido, valores solicitados/atendidos, sequência qualificante, campanhas e evidências por escopo |
| `analytics_customer_products_summary` | customer_id + product_key técnico | Quantidade e receita de linhas de pedidos qualificantes por variante/SKU/asset observado |

Schemas e manifesto: `infra/terraform/customer_intelligence_proposed/`. O manifesto ativo não é modificado. Proposta: cluster por loja/cliente, pedidos particionados por `created_at`, deletion protection habilitada. Os modelos incluem `row_key`, `store_id`, `policy_hash`, `generation`, `calculated_at`, `as_of`, `currency`. Nenhuma tabela física é criada.

**Limitação de produto:** CORE order_items não fornece product_id canônico. Não equiparamos asset_id, SKU ou variante a produto. `product_id=null`, `resolution_status=UNRESOLVED_CANONICAL_PRODUCT`; o grão técnico usa a mesma `product_key` da referência Analytics existente. Portanto ainda não há consolidação canônica de todas as variantes de um produto. Uma relação explícita e validada será necessária em etapa posterior.

## Métricas e cobertura

- `total_orders`, totais solicitados/atendidos e quantidades incluem todos os pedidos observados do cliente antes de `as_of`, inclusive CANCELED. Não são receita recebida ou líquida.
- Primeira compra (`first_order_at`), sequência, frequência, recompra e `ltv_observed` incluem somente status qualificantes da policy. CANCELED permanece no histórico comercial/timeline, com purchase_number nulo.
- `ltv_basis=requested_qualifying_orders_observed`: soma solicitada de compras qualificantes observadas. Não é previsão, lucro, valor efetivamente pago ou histórico completo.
- Primeiro/último pedido qualificante são ordenados por `(created_at, order_id)`. `days_since_last_purchase` usa dias locais entre a última compra e `as_of`.
- Ausências monetárias propagam NULL conforme a referência existente; cliente sem compras tem contagem zero e datas nulas. Valores NUMERIC são serializados em strings decimais exatas.
- Produtos usam original_qty para solicitado e qty para atendido; item removed tem atendimento zero. Receita de linha = quantidade × preço unitário atual, sem ratear frete/desconto de pedido. `revenue_basis=line_gross_at_current_unit_price`; não exigir reconciliação automática com total financeiro do pedido.
- Só entram itens do snapshot atual de pedidos qualificantes; versão de item incompatível com pedido interrompe a materialização, sem publicação parcial.
- Journey total_events conta somente FACT, não ORDER derivado; total_sessions conta sessões distintas; total_products_viewed conta product_id distintos em product_view. Cart e checkout contam add_to_cart e checkout_started.
- Timeline inclui Facts resolvidos e eventos ORDER derivados; somente evidências resolvidas podem compor a jornada de um cliente. Não é garantia de captura de todos os contatos reais.

O snapshot de entrada deve conter o histórico observado pretendido até `as_of`. A completude é declarada pela policy, nunca inferida de um mês preenchido. `history_complete=false` permanece false. As flags e pedidos de influência respeitam `report_from/report_to` da Influence Layer, com report_to exclusivo; os totais comerciais usam o histórico fornecido antes de as_of. Não interpretar uma flag false como prova de ausência de mídia fora dessa cobertura.

## Identidade e influência

Pedido → cliente por customer_id explícito. Fact → pedido → cliente e caminhos temporais de sessão/visitante/usuário seguem a Influence Layer existente. Não unimos clientes por nome, CPF/CNPJ, email/telefone fuzzy ou user_id igual a customer_id. Ambiguidade não ganha identidade por fallback. Aprovação de cadastro depende da evidência explícita suportada; o produtor dessa evidência continua uma limitação documentada na Influence Layer.

Três artefatos coerentes são exigidos:

- LIFETIME: contatos históricos anteriores ao pedido qualificante no intervalo do relatório.
- ACQUISITION: influência na primeira compra observada.
- REPEAT_PURCHASE: contatos entre a compra anterior e a compra 2+; não herda automaticamente mídia de aquisição.

Flags do profile correspondem a esses três escopos. Resumo de pedidos guarda `influence_by_scope` separadamente. Evidência principal usa a prioridade determinística da Influence Layer; identity_path preserva os caminhos no artefato interno, mas não é exposto na API. Primeira/última campanha seguem a ordem dos touchpoints e podem ser NULL quando o sinal pago não identifica campanha.

Múltiplas campanhas não duplicam o pedido nem o dinheiro no Customer 360. Participação de campanhas não significa crédito exclusivo: não somar receitas de campanhas como se fossem disjuntas; não representa atribuição causal, ROAS, CAC ou mídia investida.

## Consistência e execução local

`src/intelligence/materialization.py` valida loja, policy, cobertura, janela, hashes de conteúdo/origem dos três escopos e cutoff de cálculo. Misturar snapshots incompatíveis falha. IDs de cliente/pedido e pares de itens duplicados falham. `generation` depende das entradas, publicações de influência, policy e calculated_at. Repetir as mesmas entradas reproduz o artefato.

Entrada JSON: arrays `customers`, `orders`, `items`, `events`, `identity_links`. Usar somente fixtures sintéticas em desenvolvimento. CLI local:

```sh
python -m src.intelligence.offline \
  --policy /caminho/policy-sintetica.json \
  --input /caminho/snapshot-sintetico.json \
  --calculated-at 2026-09-29T00:00:00Z \
  --output /tmp/customer360-sintetico.json
```

O CLI calcula os três escopos offline e publica os quatro modelos junto à timeline materializada. Publicação local exclusiva e atômica, permissões 0600; replay idêntico não altera arquivo, conteúdo diferente no mesmo destino falha. Não é protocolo de publicação BigQuery nem migration. Snapshots com mais de 100.000 registros de entrada são recusados: implementação de referência limitada em memória, não motor de produção para milhões de eventos.

## Classificação e evolução

company_name/trade_name, localização, customer_id e compras são dados comerciais restritos, potencialmente pessoais. Omitir CPF/CNPJ/email/telefone não torna o artefato anônimo. Artefatos internos de timeline e identity_path contêm identificadores pseudônimos e exigem proteção. Não versionar snapshots reais ou servir o JSON interno diretamente.

Para produção: fonte de snapshot consistente/fechada, publicação atômica por geração, retenção e exclusão LGPD, autenticação, autorização por loja, consulta indexada dos modelos e comprovação de custos/escala serão etapas separadas. Nenhum recurso, integração ou runtime existente é alterado neste epic.
