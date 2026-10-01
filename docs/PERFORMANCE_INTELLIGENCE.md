# CHANGE #14 — Performance Intelligence Foundation

> Proposta/reference offline histórica. O contrato físico live DEV vigente é [CHANGE #16](CHANGE_16_DEV.md): nomes Meta `meta_live_*`, generation INT64 e publicação Intelligence independente. Conteúdo anterior preservado para auditoria.

Somente offline. Quatro modelos propostos e referência pura em `src/performance/engine.py`, sem alterar código/schemas da Foundation, UP Zero, Analytics V1, Customer Intelligence, Paid Influence ou Meta Foundation. Não registrar job, schema ativo, API, Scheduler ou publicação remota.

## Fluxo e contratos de entrada

```text
Snapshot CORE coerente → resolução Paid Influence existente → campanha/pedido qualificante
Proposta Meta normalizada → campanha + Insights diário → gasto por campanha/dia
                         ↓
Performance offline: pedidos, clientes, dia, resumo de loja
```

`build(policy, snapshot, accounts=..., meta_insights=..., meta_campaigns=..., coverage=..., calculated_at=..., influence_scope=...)` retorna `{tables, metadata}` em memória. Usa a resolução existente sem alterar suas regras. Snapshot contém customers/orders/events/identity_links; opcional paid_evidence legado não estabelece identidade por si. Entradas precisam representar versões correntes consistentes e incluir **todo histórico conhecido de pedidos**, não somente o intervalo do relatório.

Inputs Meta seguem a proposta separada do CHANGE #13, não o schema antigo de tabelas com o mesmo nome. Não adaptar por renomeação cega. Exigem binding explícito loja/conta, moeda e timezone iguais à policy e observação não posterior ao cálculo. Apenas Insights **level=campaign, sem breakdown**, uma configuration_hash por execução. Não combinar níveis ad/adset/campaign nem séries de configuração distintas. Dados de outras lojas são filtrados antes do cálculo e não mudam a geração local.

Inventário de contas exige proprietário único. A referência suporta uma conta explícita por loja; múltiplas contas da mesma loja são bloqueadas, não somadas parcialmente como se fossem total. Agregação multicon­ta futura exige união de pedidos/clientes e alinhamento de moeda/timezone/cobertura antes de dividir. Múltiplas lojas são processadas isoladamente.

`MediaCoverage` exige loja, conta, período [period_start,period_end), configuration_hash, complete e evidence_ref quando completo. É declaração explícita do chamador autorizado, não verificação automática de completude da API. Apenas uma cobertura certificada permite interpretar ausência de linha como zero gasto. Sem isso: spend/meta_spend=NULL; observed_spend/observed_meta_spend preservam o montante presente. Sem cobertura confiável, não calcular eficiência usando um gasto parcial.

Datas de conversão são derivadas de created_at do pedido no timezone aprovado. Dias da Meta já representam data local da conta. Janela fechada da policy é [report_from,report_to), as_of exclusivo. Receita diária é agrupada pelo **dia do pedido**, gasto pelo **dia da veiculação**; isso não constitui análise causal de coorte de anúncios.

## Modelos propostos

Schemas em `infra/terraform/performance_proposed/`; gerador `python -m src.performance.schema`. Nenhuma inclusão em tables.json ativo.

| Modelo | Grão lógico e conteúdo |
| --- | --- |
| analytics_campaign_performance_daily | loja/conta/campanha/dia/escopo dentro da janela; gasto, impressões/cliques/taxas, compradores/pedidos influenciados, novos, solicitado/atendido/quantidades e eficiência |
| analytics_campaign_customer_performance | loja/conta/campanha/customer_id/escopo/janela; contatos, pedidos, totais B2B e classificação de novo cliente |
| analytics_campaign_order_performance | loja/conta/campanha/order_id/escopo/janela; sequência, contatos distintos, evidência/path, B2B e classificação |
| analytics_performance_summary | loja/período/escopo (uma conta certificada); gasto e contagens/totais **deduplicados** |

Cada linha tem row_key, store_id, account_id, policy_hash, generation, currency, timezone, influence_scope, period_start/end, as_of, calculated_at e flags de cobertura. Schemas de controle adicionais tornam escopo e período explícitos; não somar gerações/scopes. row_key inclui janela/escopo para evitar colisão entre resultados de configurações temporais distintas; generation identifica versão completa. Seleção futura deve fixar uma única geração/janela.

No grão campanha/dia, adset_id/ad_id ficam NULL: uma campanha pode conter vários anúncios, e escolher um arbitrariamente corromperia o grão. Não criar uma linha por anúncio disfarçada de campanha. Linhas diárias existem onde há gasto observado ou pedido influenciado; não materializar calendário vazio completo. Summary existe mesmo sem movimento.

## Novo cliente: observado versus confirmado

Identidade continua `(store_id,customer_id)`. Não agrupar CNPJs entre customer_ids sem mapa canônico explicitamente aprovado. O termo “Customer/CNPJ” não autoriza deduplicação por documento. Portanto esta referência mede clientes canônicos existentes; uma pessoa jurídica cadastrada com dois IDs permanece uma limitação explícita.

Considerar exclusivamente pedidos qualificantes conforme AnalyticsPolicy. Cadastros, leads, aprovação, cancelados ou primeira visita não estabelecem primeira compra. Ordenação de compras `(created_at,order_id)`; empate temporal tem ordem estável observada, não causalidade inferida.

- Pedido com compra qualificante anterior conhecida: is_new_customer=false, previous_purchase_exists=true, mesmo com histórico incompleto.
- Primeira compra observada e histórico completo comprovado pela HistoryCoverage da policy: is_new_customer=true, previous_purchase_exists=false.
- Primeira compra observada com history_complete=false: ambos NULL; nunca promover ausência de evidência a cliente novo confirmado.

`first_purchase_at` e `first_qualified_order_id` apontam a primeira compra qualificante **observada em todo snapshot**, inclusive fora da janela. `classification_order_id` explicita o pedido sendo classificado: no modelo de pedidos, aquele pedido; no de clientes, o primeiro pedido influenciado da campanha na janela. `historical_purchase_count_before_first_purchase` conta compras qualificantes observadas **anteriores a esse pedido de referência**; nome preservado do requisito, não significa contar compras antes da primeira compra global (o que seria sempre zero). Contagem observada não prova exaustividade com histórico incompleto.

new_customers_influenced conta customer_ids distintos cuja primeira compra qualificante confirmada tem influência na seleção. Recompra não acrescenta novo cliente. Se algum candidato não puder ser classificado por cobertura histórica, o total fica NULL (não apenas contagem dos confirmados), e CAC fica NULL. Registros com compra antiga comprovada podem ser classificados como não novos sem exigir conhecimento de toda origem.

Com a policy atual MX Fashion history_complete=false, não esperar CAC confirmado para primeiras compras apenas observadas. Aumentar janela de setembro não certifica histórico desde a origem.

## Influência e deduplicação

Só entram pedidos qualificantes com touchpoint pago demonstrado **estritamente anterior** à conversão. Evidências DIRECT, CUSTOMER_JOURNEY e SUPPORTED e identity_path vêm do resolver existente. Contato no mesmo instante ou posterior não conta. Não criar identidade por nome/documento/email ou user_id igual a customer_id.

Aceitar somente campanhas encontradas no catálogo da conta explicitamente configurada. Participações sem campanha/fora do catálogo são excluídas e contabilizadas em `unmapped_influenced_order_campaign_pairs`; influence_complete=false e ROAS/CAC=NULL. Não classificar silenciosamente mídia de outra origem como campanha Meta. Falta de entidade deve ser revisada upstream, não apagada do RAW.

Uma campanha participa da jornada; não recebe crédito exclusivo. Vários touchpoints da mesma campanha mantêm um par campaign/order, touch_count distinto. Um pedido pode aparecer em duas campanhas. No **summary**, receitas/quantidades e contagens de pedidos são calculadas pela união de order_ids e clientes pela união de customer_ids; não pela soma das linhas de campanhas. Investimento inclui campanhas sem conversão. Totais por campanha não são aditivos.

Um escopo por build: LIFETIME (default), ACQUISITION ou REPEAT_PURCHASE. Recompra respeita contato posterior à compra anterior, sem herdar aquisição automaticamente. Gasto da mesma janela pode aparecer em cada visão; nunca somar gasto entre escopos. Cliente influenciado aqui significa **comprador com pedido qualificante influenciado**, não qualquer visitante exposto.

## Eficiência, cobertura e limites

ROAS solicitado/atendido são razões comerciais influenciadas, não ROAS pago ou atribuição exclusiva. CAC novo cliente influenciado também não é custo causal de aquisição. Não calcular Payment Ledger, receita liquidada, margem, lucro ou LTV pago.

facts_complete=false ou campanhas não resolvidas deixam contagens/receita como **observadas parciais**, identificadas nas flags; eficiência ROAS/CAC fica NULL. Cobertura de spend incompleta também bloqueia divisão. Fulfillment_rate mede atendimento dos pedidos observados selecionados, preservando NULL quando valores faltam.

A referência é limitada a 100.000 entradas combinadas, em memória; não constitui solução de escala ou pipeline de publicação. Chaves duplicadas, dados Meta incompatíveis, múltiplas contas não suportadas e schemas divergentes falham. Mesmas entradas/cutoffs reproduzem geração e resultado; mudança do snapshot/cobertura exige nova geração. Não escrever checkpoint ou executar replay real.

identity_path contém identificadores internos: não servir o artefato inteiro ao frontend nem versionar dados reais. Não há credenciais, fonte live ou API pública. Testes usam apenas fixtures sintéticas. A autorização de ROAS/CAC comerciais deste change aplica-se só à camada nova; proibições do CHANGE #13 sobre cálculos naquela camada permanecem preservadas.
