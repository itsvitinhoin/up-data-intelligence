# Analytics / Business Metrics Foundation

Entrega offline para revisão. Fonte inspecionada: `docs/upzero-openapi.json`, catálogo e
normalização CORE existentes, identity resolution e contratos Meta do commit
`7cd5df149b26597457dcf4a3b08db53586a53dc0`. Não foi consultado GCP nem dado real.
As únicas medições desta entrega são testes com fixtures sintéticas.

## Arquitetura e limites

RAW → CORE → ANALYTICS → futuro dashboard/API/MCP/IA. Nenhum dashboard criado.
`src/analytics` implementa referência pura, com Decimal e entradas CORE em memória, sem
cliente de rede, credential loader, Repository writer, CLI ou job. Máximo de 100.000 entradas
por chamada para impedir uso acidental como full scan de produção. Não confundir esse
limite offline com paginação de ingestão: nenhum pipeline UP Zero/Meta foi modificado.

SQL BigQuery em `sql/analytics/*_reference.sql` prepara consultas parametrizadas e TEMP
TABLEs para evitar repetir janelas/joins; não grava tabelas persistentes. São referências
analíticas de negócio, não um job de materialização implantável: envelope de publicação,
chaves, pivô de LTV, execução/monitoramento e materialização ficam para etapa posterior.
Os testes executam a referência Python e verificam contratos estruturais de SQL/schema.
**SQL não foi executado, validado por dry-run ou comparado ao Python no BigQuery.** Isso
exigiria GCP, vedado nesta etapa. Compatibilidade SQL e paridade devem ser verificadas
antes de qualquer materialização. Não apresentar schemas propostos como tabelas existentes.

Sete tabelas propostas, manifest/schema/DDL separados em `infra/terraform/analytics_proposed`
e `sql/analytics/proposed_ddl`. O catálogo runtime, manifestos ativos, IAM, schemas CORE,
Terraform, DEV.4/digest, schedulers e execução de backfill não são modificados.

## Grãos e materialização futura

Toda chave inclui store_id e policy_hash. Policy hash cobre versão semântica, moeda,
timezone e status qualificantes; **não** cobre as_of, intervalo de consulta nem progresso de
backfill, para atualização idempotente do mesmo grão. calculated_at indica corte observado,
não o relógio real de execução. Definição diferente de política produz outra série, não
pode ser somada à anterior. Consumidor deve selecionar exatamente uma política.

| Modelo | Grão de negócio | Partição / clustering propostos |
|---|---|---|
| analytics_store_daily | loja + dia local de criação do pedido + política | order_date / store_id, policy_hash |
| analytics_customer_metrics | loja + customer_id resolvido + política | sem partição / store_id, customer_id, policy_hash |
| analytics_customer_purchase_sequence | loja + order_id qualificante e resolvido + política | order_date / store_id, customer_id, policy_hash |
| analytics_cohorts | loja + mês da primeira compra observada + diferença de meses + política | cohort_month / store_id, months_since_first_purchase, policy_hash |
| analytics_purchase_distribution | loja + cohort_month + ordinal 1/2/3/4/5+ + política | cohort_month / store_id, purchase_bucket, policy_hash |
| analytics_products_daily | loja + dia + chave asset/variant/SKU + política | order_date / store_id, product_key, policy_hash |
| analytics_funnel_daily | loja + dia local do evento + política | event_date / store_id, policy_hash |

A distribuição é auxiliar justificada: ordinal de recompra não é idade mensal da cohort.
Não criar outra tabela para cada janela de LTV; ficam colunas da mesma entidade Customer.
Preferir materializações incrementais comuns (não prometer BigQuery Materialized Views
nativas, dadas janelas e joins) para fatos grandes; consultas/views de consumo finas sobre
as tabelas. Schemas completos em `ANALYTICS_SCHEMAS.md`, todos os campos de negócio NULLABLE.

## Escopo temporal, cobertura e moeda

Policy exige loja, timezone, moeda, as_of UTC, intervalo [report_from, report_to) de datas
locais fechadas, flags history_complete/facts_complete e lista explícita de status que
constitui compra comercial. Não há configuração de produção nem inferência de moeda.
Orders CORE não expõe moeda: confirmar que a loja é monomoeda no período antes de fornecer
esse parâmetro. Se houver multimoeda, expandir a fonte/modelo e particionar as métricas por
moeda antes de habilitar. Nunca somar BRL e USD nem comparar spend com receita de moeda distinta.

- `order_at`/`first_purchase_at`: timestamps UTC. Datas derivadas pela timezone da loja,
  `America/Sao_Paulo` apenas no piloto, sem hardcode no motor.
- `order_date`/`first_purchase_date`: data local de created_at do pedido qualificante.
- `event_date`: data local de occurred_at; não substitui order_date.
- `payment_date`: NULL: não existe timestamp de liquidação nas fontes CORE usadas.
- Dados current são **restated** no estado atual conhecido. as_of corta instantes de negócio;
  não reconstrói magicamente como o banco era historicamente. Se observed_at informado for
  posterior ao corte, o motor rejeita. Snapshot consistente/as-of histórico exige extrair
  versões/Time Travel em etapa futura. Reclassificação de status pode mudar primeira compra.

history_complete só pode ser true após evidência de cobertura **desde a origem comercial**
até as_of, não apenas conclusão de uma janela de backfill. Sem isso: contagens/valores são
observados, new_customers é NULL, primeira compra é `first_observed`, taxas completas de
recompra/retenção são NULL. Valores de LTV continuam observados a partir da primeira compra
vista, com flags indicando limitação. facts_complete governa taxas de funil. Zeros em dias
sem linhas significam zero **observado**; a flag de cobertura deve acompanhar a apresentação.

## OBSERVED / TRANSFORMED / CALCULATED / ATTRIBUTED

- OBSERVED: requested_total, fulfilled_total, total, statuses, quantities, IDs, timestamps,
  customer_type, eventos e métricas reportadas pela Meta nos contratos existentes.
- TRANSFORMED: datas locais, tipos exatos, resolução Order.customer_id → Customer.customer_id
  dentro da loja, chave de SKU e classificação por status configurado. Não há fuzzy matching.
- CALCULATED: somas, contagens, razões, sequência, LTV observado, cohort e bruto de linha.
- ATTRIBUTED: métricas que exigem política comercial + evidência de touchpoint. No build
  atual ficam NULL; helper separado apenas testa contratos sintéticos já atribuídos.

Não assumir user_id=customer_id; não usar nome, telefone, CPF/CNPJ ou cookies como chave.
`identity.resolve_event_customer` existente continua disponível para futuras projeções
Fact→Order→Customer; o funil de sessão não precisa inferir Customer. Pedidos sem cadastro
resolvido ficam nos totais financeiros, com warning, mas fora de sequência/LTV/cohort.

## Receita e vendas

Todos os totais diários são agrupados pela **criação do pedido**, inclusive paid/cancelled:
não são fluxo de caixa do dia do pagamento nem cancelamentos ocorridos naquele dia.
Status documentados OrderResponse: RESERVED, CONFIRMED, PROCESSING, INVOICED, SHIPPED,
CANCELED; payment_status: unpaid, paid, canceled. Status novo/desconhecido bloqueia o modelo
até revisão, não é traduzido por adivinhação. As fixtures usam explicitamente
CONFIRMED/PROCESSING/INVOICED/SHIPPED como compra qualificante; essa proposta precisa de
aprovação comercial para uso live. Não confundir customer.status=APPROVED com pedido aprovado.

| KPI | Fórmula/fonte e interpretação |
|---|---|
| orders_generated | count de orders atuais criados no período, inclusive cancelados |
| revenue_generated | sum(orders.requested_total), preserva solicitado inclusive itens removed; valor restated da fonte, não promessa de snapshot original imutável |
| revenue_fulfilled | sum(orders.fulfilled_total), valor atendido informado pela fonte, sem inferir pagamento |
| orders_paid | count payment_status='paid', situação atual observada, não contagem de transações |
| revenue_paid | NULL: não há paid_amount/ledger/reembolsos conciliados no CORE usado |
| orders_cancelled | count order_status='CANCELED'; payment_status='canceled' sozinho não cancela um pedido |
| revenue_cancelled | sum(requested_total de orders CANCELED): solicitado associado a pedidos integralmente cancelados, não perda líquida reconhecida/reembolso |
| revenue_unfulfilled | generated−fulfilled quando componentes completos e diferença não negativa; inclui pendência/parcial, não é sinônimo de cancelled |
| approval_rate | pedidos cujo order_status está na política de compra / orders_generated; proxy de status comercial atual, não aprovação bancária |
| average_order_value_generated | revenue_generated / orders_generated |
| average_order_value_paid | NULL enquanto revenue_paid indisponível |
| items_per_order_generated | sum(requested_items_qty) / orders_generated |
| items_per_order_fulfilled | sum(fulfilled_items_qty) / orders_generated; inclui pedidos com zero atendido |

Nenhum fallback de requested_total/fulfilled_total para total. Se faltar componente, sua soma
fica NULL (com warning) em vez de publicar uma soma parcial. Divisor zero/NULL → NULL.
Pedidos cancelados não entram em compras qualificantes/Customer LTV, mas seu solicitado
permanece em receita gerada bruta. Cancelamento parcial por item é tratado no modelo de produto.
Pagamento pago com pedido cancelado continua um estado observado; não inferimos estorno.

## Clientes, frequência, recorrência e LTV

Somente compras qualificantes com customer_id único resolvido participam. Ordenação:
created_at UTC, depois order_id STRING como desempate estável, sem inferir ordem numérica
ou cronologia comercial entre timestamps empatados. purchase_number começa em 1.

- `new_customer` por pedido: ordinal 1 e histórico completo; senão `first_observed`.
- `returning_customer` por pedido: ordinal >1 no histórico observado.
- `new_customers` diário: clientes distintos cuja primeira compra é naquele dia, somente
  com histórico completo. `returning_customers`: clientes que já tinham primeira compra
  antes daquele dia. São buckets exclusivos diários; um segundo pedido no dia da aquisição
  é returning na sequência, mas não duplica a contagem diária do cliente.
- `customer_repurchase_rate` do intervalo: clientes ativos no intervalo com pelo menos duas
  compras acumuladas antes de report_to / clientes ativos no intervalo. Não consulta compras
  futuras ao intervalo e não é probabilidade de recompra de uma cohort recém-adquirida.
- `purchase_frequency`: compras qualificantes resolvidas no intervalo / clientes distintos
  com essas compras. Unidade: pedidos por cliente ativo nesse intervalo, não taxa anualizada.
- `customer_retention_rate` do intervalo: clientes ativos tanto no intervalo atual quanto no
  anterior de igual duração em **dias locais** / clientes ativos no intervalo anterior.
  Não é média de cohorts; o retorno informa as datas do baseline e denominador.
- first/second/third/fourth_purchase_at: posição 1/2/3/4; faltantes NULL. Intervalos em dias
  decorridos de 24h, fracionários, não diferença de datas locais arredondada.
- Distribuição por primeira cohort: clientes que alcançaram 1,2,3,4,5+ compras / população
  original da cohort, fração 0–1 (formatar % na UI). Buckets de clientes são cumulativos e
  **não aditivos**; receita de cada bucket usa só os pedidos daquele ordinal; 5+ soma todos
  os pedidos desde o quinto e conta cada cliente uma vez.

`customer_ltv` = receita gerada observada das compras qualificantes resolvidas, sem margem,
sem previsão, sem usar receita Meta. `ltv_30d/60d/90d/180d/365d` somam requested_total em
[first_purchase_at, first_purchase_at + N×24h). Janela imatura → NULL, nunca zero completo.
`ltv_Nd_complete` exige também histórico completo. `ltv_lifetime_observed` inclui tudo até
as_of conhecido; não significa lifetime futuro/total da empresa. `ltv_paid` é NULL.
Clientes sem compra qualificante não recebem uma linha de LTV zero inventada.

## Cohort

cohort_month = primeiro dia do mês **local** da primeira compra observada qualificante.
months_since_first_purchase = diferença de ano/mês civil (não dias/30).
customers_in_cohort = clientes originais distintos; active_customers = clientes da cohort
com compra no mês relativo; orders e receita = compras desses membros nesse mês.
retention_rate = active_customers / customers_in_cohort, somente mês fechado e histórico
completo. observed_retention_rate continua disponível com período incompleto marcado.
Meses observados sem atividade recebem zero; meses futuros não são gerados. O modelo de
cohort e LTV usa toda a história fornecida até as_of, independentemente da janela diária de
report. Não truncar o input de Customer à janela do dashboard.

## Funil

Nomes exatos documentados: product_view, add_to_cart, checkout_started, purchase.
product_views/add_to_cart/checkout_started/purchase contam **Facts por fact_id**, inclusive
órfãos de sessão. purchase_item/order_created/order_paid não são aliases de purchase.
Fact duplicado bloqueia; dois fact_ids distintos com mesmo event_id continuam dois fatos
observados — auditoria de duplicação de instrumentação deve preceder consumo comercial.

sessions = session_id não vazio distinto por loja + dia local, observando qualquer evento
(não se presume evento session_start). Uma sessão que cruza meia-noite aparece nos dois dias:
essa métrica diária não pode ser somada e chamada de sessões únicas do período.

- session_to_cart_rate = sessões do dia com cart / sessões do dia.
- cart_to_checkout_rate = sessões com checkout posterior ao cart / sessões com cart.
- checkout_to_purchase_rate = sessões com purchase posterior ao checkout posterior ao cart /
  sessões com checkout posterior ao cart.
- session_conversion_rate = sessões com qualquer purchase / sessões do dia.

A cadeia exige ordem dentro do mesmo dia/sessão; desempate occurred_at + fact_id. Não une
visitors/users nem atribui compra por cookie. Eventos sem sessão entram em counts e em
`events_without_session`, não nos denominadores. Essas taxas não são simples divisões dos
counts de eventos, evitando resultados >100% por repetição. Facts de purchase sem order_id
continuam eventos de funil, sem virar venda ou receita. Custos futuros permanecem NULL:
spend correspondente precisa de escopo de tráfego atribuído, não todos os eventos da loja.

## Produtos e segmentação

Grão provisório por hash(asset_id, variant_id, sku), todos IDs STRING. CORE.order_items não
possui mapeamento comprovado asset_id/variant_id → product_id do Facts nem campo reference;
ambos ficam NULL. Nunca renomear asset_id para product_id silenciosamente. Itens sem identidade
suficiente podem compor bucket desconhecido; antes de dashboard de produto é necessário
qualificar catálogo/coverage. SKU não é chave global nem identificador de cliente.

Somente present_in_latest_snapshot=true e parent_order_version_id = versão do pedido atual.
Itens de snapshot antigo/desconhecido são excluídos com warning, não ligados arbitrariamente.
original_qty de todos os itens, inclusive removed → units_requested; qty dos active/attended
→ units_fulfilled. unit_price × essas quantidades produz receita **bruta de linha ao preço
unitário atual**; não rateia descontos, frete, imposto nem valor pago. Pode não reconciliar
com total financeiro do pedido. average_selling_price = bruto fulfilled / units_fulfilled.
cancellation_rate = original_qty de itens explicitamente removed / units_requested; diferença
requested−fulfilled não prova cancelamento parcial. orders/customers são distintos por grão.

customer_type é preservado como RETAIL/WHOLESALE/valor da fonte nas métricas e sequência,
sem converter automaticamente em B2C/B2B. Orders CORE não tem order_type/channel próprio;
channel do evento não deve ser promovido a canal do pedido. Não há hardcode comercial da MX.

## Meta, CAC, ROAS e atribuição futura

Tabelas Meta ainda não são assumidas existentes. Nenhuma consulta padrão referencia essas
tabelas. Colunas reservadas no store_daily: meta_spend/impressions/clicks e
meta_reported_purchases/value, separadas de first_party_*_attributed.

`media_metrics` aceita apenas contratos de agregados com escopo idêntico de loja, moeda,
timezone, datas e hash de contas/configuração. É helper offline; não calcula atribuição nem
lê Meta. AttributionEvidence exige LAST_PAID_TOUCH, janela explícita >0, touchpoint_id e
IDs account/campaign/adset/ad quando presentes, preservados como strings. Não há default
de dias nem derivação comercial habilitada. A evidência exemplifica o contrato de origem;
um agregado real deverá guardar um conjunto versionado de evidências, não uma única prova
fictícia para todas as suas compras.

- new_customer_cac = spend / first_party_new_customers_attributed.
- roas_generated = first_party_revenue_generated_attributed / spend.
- roas_paid = first_party_revenue_paid_attributed / spend.
- cost_per_session/add_to_cart/checkout futuros = spend / denominador do mesmo tráfego
  pago e período explicitamente atribuídos; não implementado com alocação artificial.

Meta reported purchases nunca entra no denominador first-party. Ausência de spend ou
atribuição → NULL. Zero spend conhecido permite CAC zero quando há aquisição atribuída,
mas ROAS com divisor zero permanece NULL. Daily Insights de timezone diferente não pode
ser convertido para timezone de loja sem granularidade mais fina. Produtos não recebem
spend, impressions, clicks ou ROAS por divisão proporcional sem evidência futura.

## Quality e publicação futura

Bloqueantes: negative_revenue, duplicate_order/customer/fact/item, purchase_sequence_gap,
cohort_negative_month, invalid_first_purchase, funnel_negative_counts, customer_ltv_negative,
analytics_duplicate_grain, status comercial não revisado. Checagem de grão usa dimensões,
não apenas row_key, e não escolhe um duplicado com ROW_NUMBER arbitrário.
paid_revenue_greater_than_generated é bloqueante **apenas quando as bases são comparáveis
e a política veda sobrepagamento**; helper permite exceção explícita. Atualmente paid=NULL.
Warnings: order_without_customer, paid_orders_without_paid_revenue enquanto o valor pago
não existe, componente monetário ausente, snapshot de item incompatível, fulfilled maior
que solicitado. Esses findings são agregados sem PII; não alteram gate de ingestão UP Zero.

Valores monetários são Decimal; somas/produtos usam precisão ampla. `encode_tables` converte
NUMERIC para strings com até nove casas, ROUND_HALF_UP e valida faixa; nenhuma passagem por
float monetário. Ratios internos são Decimal e exportados com a mesma política. Saídas
não escrevem em Repository ou disco automaticamente.

## Custo, incremental e migrations

- Orders: predicate em created_at com limites UTC/partições + store_id. Products: pruning
  de order_created_at e created_at. Facts: occurred_at entre TIMESTAMP(data_local, timezone).
  Filtros apenas em DATE(timestamp) seriam insuficientes como única estratégia de pruning.
- Sequência/Customer/cohort precisam de história anterior ao relatório. SQL exige history_from
  explícito. Bootstrap histórico terá scan histórico controlado; não esconder esse custo.
- Janelas de sequência são particionadas por Customer; cohorts expandem só meses observados,
  e LTV/distribuição só cinco buckets. Nada faz event × order × ad como CROSS JOIN.
- Python é referência limitada. Produção deve materializar incrementais no BigQuery por
  partição de data, com conjunto de clientes afetados por novas versões/cancelamentos.
  Recalcular história desses clientes e cohorts antigas afetadas; somente lookback fixo
  não garante correção. Atualizações tardias podem mudar primeira compra e todos os ordinais.
- Ao publicar uma versão restated, substituir o recorte analítico autorizado atomicamente,
  removendo do **destino analítico** linhas obsoletas que deixaram de qualificar. Um MERGE
  apenas de novas linhas deixaria resíduos de pedidos cancelados/cohorts deslocadas.
  Nenhum procedimento de exclusão está implementado/executado nesta tarefa.
- Reusar writer/job idempotência existente após integrar tabelas ao catálogo; nesta fase
  elas ficam isoladas. Definir checkpoint analítico, snapshot consistente e SLA na integração.
- Sem números fictícios de bytes/custo: dependem de cardinalidade, partições, colunas e
  histórico. Antes do live, dry-run autorizado + maximum_bytes_billed, plano de slots/quota,
  testes de paridade SQL/Python e benchmark com dados controlados.

Nenhuma migration executada ou alteração de tabela existente necessária. Futuramente,
provisionar **sete tabelas novas em up_analytics existente** ou aprovar views equivalentes;
manifesto separado não é referenciado pelo Terraform principal. Não executar os DDLs e
Terraform como donos concorrentes. Precisará IAM de leitura CORE e escrita somente ANALYTICS
para a identidade de transformação, além de jobUser; dashboard apenas leitura apropriada.
Não reutilizar automaticamente IAM de ingestão para conceder escrita analítica. Nenhum secret
novo necessário para cálculo sobre CORE; nenhum API Key/configuração foi adicionado.

## Decisões humanas pendentes

1. Aprovar quais status constituem compra e se approval_rate é o nome adequado ao proxy.
2. Confirmar moeda da loja e cobertura desde origem; backfill ativo não autoriza completeness.
3. Obter ledger/valor/data de pagamento e política de estornos, chargebacks e cancelamentos.
4. Confirmar catálogo product_id/variant/asset/SKU/reference e reconciliação de preço/desconto.
5. Aprovar funil por session-day ou outro modelo para sessões que cruzam dias, e dedupe de
   instrumentação distinto de dedupe técnico de Facts.
6. Aprovar janela/modelo de atribuição, paid touch, coortes de aquisição e granularidade Meta.
7. Aprovar storage/materialização, IAM, custo, retenção e testes BigQuery em próxima etapa.

A definição de cada KPI também está em `analytics_kpi_catalog.json`; a especificação exata
de colunas e tipos está em `ANALYTICS_SCHEMAS.md`. Nenhum dado real foi usado como fixture.

## Materialization readiness (offline)

Contrato de policy, cobertura, runner transacional local, incrementalidade e os sete
comandos futuros de dry-run estão em [Analytics Materialization Readiness](ANALYTICS_MATERIALIZATION_READINESS.md).
SQL ainda não validado no BigQuery; nenhuma tabela analytics foi criada.
