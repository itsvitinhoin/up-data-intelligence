# CHANGE #19.3F — Dashboard wiring matrix

Implementation classification only; final-host certification is PENDING.
All live readings require real authenticated scope and current certified source
evidence. Classification is not a claim that the new deployment or materialization
is already live. Missing certified source data never becomes demo or numeric zero.

## Metrics

| Metric | Classification | Resource / field | Contract / limitation |
|---|---|---|---|
| Frequência de compra observada (purchase_frequency_observed) | LIVE_REAL | overview / purchase_frequency_observed | Pedidos qualificantes / compradores observados no período; não é frequência lifetime. |
| Impressões Meta (meta_impressions) | LIVE_REAL | performance / impressions | Histórico observado; não confirma pagamento. |
| Cliques Meta (meta_clicks) | LIVE_REAL | performance / clicks | Histórico observado; não confirma pagamento. |
| Cliques no link Meta (meta_link_clicks) | LIVE_REAL | performance / link_clicks | Histórico observado; não confirma pagamento. |
| Alcance Meta · único no período (meta_reach_campaign_day_sum) | LIVE_REAL | metaAds / summary.reach | Alcance único reportado pelo Meta para o período completo; não soma dias ou campanhas. |
| Visualizações de produto (facts_product_views) | LIVE_REAL | funnel / totals.product_views | Histórico observado; não confirma pagamento. |
| Eventos purchase (facts_purchase) | LIVE_REAL | funnel / totals.purchase | Histórico observado; não confirma pagamento. |
| Eventos purchase_item (facts_purchase_items) | LIVE_REAL | funnel / totals.purchase_item | Histórico observado; não confirma pagamento. |
| Receita atendida · recompra observada (repurchase_fulfilled_observed) | LIVE_REAL | retention / recurring_fulfilled_observed | Histórico observado; não confirma pagamento. |
| Pedidos · recompra observada (repurchase_orders_observed) | LIVE_REAL | retention / recurring_orders_observed | Histórico observado; não confirma pagamento. |
| Ticket atendido · recompra observada (repurchase_ticket_observed) | LIVE_REAL | retention / retention_ticket_observed | Histórico observado; não confirma pagamento. |
| Ticket solicitado · primeira compra observada (new_ticket_observed) | LIVE_REAL | acquisition / ticket_first_purchase_observed | Histórico observado; não confirma pagamento. |
| Receita solicitada · primeira compra observada (new_requested_observed) | LIVE_REAL | acquisition / requested_first_purchase_observed | Histórico observado; não confirma pagamento. |
| Pedidos · primeira compra observada (new_orders_observed) | LIVE_REAL | acquisition / first_purchase_orders_observed | Histórico observado; não confirma pagamento. |
| Receita atendida · recompra observada (recurring_fulfilled_observed) | LIVE_REAL | retention / recurring_fulfilled_observed | Histórico observado; não confirma pagamento. |
| Pedidos recorrentes observados (recurring_orders_observed) | LIVE_REAL | retention / recurring_orders_observed | Histórico observado; não confirma pagamento. |
| Ticket atendido · retenção observada (recurring_ticket_observed) | LIVE_REAL | retention / retention_ticket_observed | Histórico observado; não confirma pagamento. |
| Faturamento pago ERP (erp_revenue_paid) | FUTURE_CONNECTOR | unavailable / NULL | FUTURE_CONNECTOR_REQUIRED · ERP ainda não conectado para esta marca. Conecte um ERP no Admin para habilitar estes dados. |
| Pedidos pagos ERP (erp_orders_paid) | FUTURE_CONNECTOR | unavailable / NULL | FUTURE_CONNECTOR_REQUIRED · ERP ainda não conectado para esta marca. Conecte um ERP no Admin para habilitar estes dados. |
| Faturamento pago Ecommerce (ecommerce_revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Faturamento pago via anúncios (ad_revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| ROAS pago (roas_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Investimento total em Ads (total_media_spend) | LIVE_REAL | performance / available_media_spend | Investimento disponível: Meta certificado. Google e TikTok não conectados. |
| % faturamento ERP atribuído aos anúncios (erp_ad_share) | FUTURE_CONNECTOR | unavailable / NULL | FUTURE_CONNECTOR_REQUIRED · ERP não conectado; atribuição paga não está certificada. |
| Novos clientes adquiridos (new_customers) | LIVE_REAL_PARTIAL_COVERAGE | acquisition / confirmed_new_customers | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Faturamento novos clientes (new_revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Vendas novos clientes (new_sales_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Novos clientes vindos de anúncios (new_ad_customers) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Clientes que recompraram (repurchasers) | LIVE_REAL | retention / recurring_buyers_observed | Histórico observado; não confirma pagamento. |
| Faturamento recompra (repurchase_revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Vendas recompra (repurchase_sales_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Faturamento (revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Investimento Meta (meta_spend) | LIVE_REAL | performance / meta_spend | Investimento Meta certificado; não representa soma de plataformas desconectadas. |
| Investimento Google (google_spend) | FUTURE_CONNECTOR | unavailable / NULL | FUTURE_CONNECTOR_REQUIRED · Google Ads não conectado. |
| Ticket Aquisição (new_ticket_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Ticket Retenção (repurchase_ticket_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Conversão Aprovados (approved_conversion) | SOURCE_IDENTITY_GAP | acquisition / approved_conversion_rate | IDENTITY_RELATIONSHIP_NOT_PROVABLE · exige vínculo determinístico e pedido qualificante após aprovação. |
| CAC (cac) | LIVE_REAL_PARTIAL_COVERAGE | performance / cac_new_customer | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Cadastros Aprovados (approved_registrations) | LIVE_REAL | acquisition / leads_approved | Aprovações register_approved no período, incluindo backlog de cadastros anteriores. |
| Cadastros Gerados (registrations) | LIVE_REAL | acquisition / leads_generated | Cadastros register_submitted no período; identidade canônica de evento, não pessoas lifetime. |
| Custo por Cadastro Aprovado (approved_registration_cost) | LIVE_REAL | performance / approved_registration_cost | Investimento Meta certificado / aprovações no período. |
| Taxa de Aprovação (approval_rate) | LIVE_REAL | acquisition / lead_qualification_rate | Taxa de aprovação / qualificação: aprovações / cadastros × 100. Pode exceder 100% por backlog. |
| ROAS Solicitado (roas_requested) | LIVE_REAL | performance / commercial_roas_requested | Receita solicitada UP Zero / investimento Meta certificado. Apenas Meta conectado. |
| Custo por cadastro (registration_cost) | LIVE_REAL | performance / registration_cost | Investimento Meta certificado / cadastros no período. |
| Aprovados convertidos (approved_converted) | SOURCE_IDENTITY_GAP | acquisition / approved_converted | IDENTITY_RELATIONSHIP_NOT_PROVABLE · não inferir identidade por user_id. |
| Tempo médio cadastro → primeira compra (registration_first_purchase_mean) | SOURCE_IDENTITY_GAP | unavailable / NULL | IDENTITY_RELATIONSHIP_NOT_PROVABLE · falta vínculo entre cadastro e compra qualificante. |
| Mediana cadastro → primeira compra (registration_first_purchase_median) | SOURCE_IDENTITY_GAP | unavailable / NULL | IDENTITY_RELATIONSHIP_NOT_PROVABLE · falta vínculo entre cadastro e compra qualificante. |
| Clientes recorrentes (recurring_customers) | LIVE_REAL | retention / recurring_buyers_observed | Histórico observado; não confirma pagamento. |
| Faturamento recorrente (recurring_revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Ticket recorrente (recurring_ticket_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Vendas recorrentes (recurring_sales_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Clientes reativados (reactivated_customers) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Faturamento reativado (reactivated_revenue_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Ticket reativado (reactivated_ticket_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Vendas reativadas (reactivated_sales_paid) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Tempo médio entre compras (repeat_mean_days) | LIVE_REAL | retention / repeat_mean_days_observed | Histórico observado; não confirma pagamento. |
| Mediana entre compras (repeat_median_days) | LIVE_REAL | retention / repeat_median_days_observed | Histórico observado; não confirma pagamento. |
| Vendas (orders_generated) | LIVE_REAL | overview / orders_requested | Histórico observado; não confirma pagamento. |
| ROAS Geral (roas_approved) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| CPA Geral (cost_per_sale) | LIVE_REAL | performance / cost_per_sale | Investimento Meta certificado / pedidos com status pago UP Zero; não comprova valor pago. |
| Taxa de Recompra (repurchase_rate) | LIVE_REAL | retention / retention_observed | Compradores recorrentes / compradores observados × 100. |
| LTV da Base (ltv_complete) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada. |
| Faturamento captado (revenue_captured) | LIVE_REAL | overview / requested_revenue | Histórico observado; não confirma pagamento. |
| ROAS (roas_captured) | LIVE_REAL | performance / commercial_roas_requested | Receita solicitada UP Zero / investimento Meta certificado. |
| CPM (cpm) | LIVE_REAL | performance / cpm | Investimento Meta / impressões × 1.000. |
| CTR (ctr) | LIVE_REAL | performance / ctr | CTR Meta · percentual de cliques / impressões. |
| CPC (cpc) | LIVE_REAL | performance / cpc | Investimento Meta / cliques. |
| Faturamento aprovado (revenue_approved) | LIVE_REAL_PARTIAL_COVERAGE | unavailable / NULL | SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento. |
| Receita cancelada (revenue_cancelled) | LIVE_REAL | overview / cancelled_requested_revenue | Histórico observado; não confirma pagamento. |
| Ticket médio solicitado (average_ticket) | LIVE_REAL | overview / average_requested_ticket | Ticket solicitado observado; não comprova pagamento. |
| Vendas pagas (orders_paid) | LIVE_REAL | overview / orders_paid | Pedidos com status de pagamento paid explícito no UP Zero; não certifica valor monetário pago. |
| Investimento TikTok (tiktok_spend) | FUTURE_CONNECTOR | unavailable / NULL | FUTURE_CONNECTOR_REQUIRED · TikTok Ads não conectado. |
| Sessões (sessions) | LIVE_REAL | funnel / totals.sessions | Histórico observado; não confirma pagamento. |
| Custo por sessão (cost_per_session) | LIVE_REAL | performance / cost_per_session | Investimento Meta certificado / sessões UP Zero observadas. |
| Taxa de conversão (final_conversion_rate) | LIVE_REAL | funnel / session_to_purchase_rate | Sessões com compra observada / sessões, sem confirmação financeira. |
| Adições ao carrinho (add_to_cart) | LIVE_REAL | funnel / totals.add_to_cart | Histórico observado; não confirma pagamento. |
| Custo por adição ao carrinho (cost_per_add_to_cart) | LIVE_REAL | performance / cost_per_add_to_cart | Investimento Meta certificado / eventos de carrinho UP Zero. |
| Sessão → carrinho (session_to_cart_rate) | LIVE_REAL | funnel / session_to_cart_rate | Histórico observado; não confirma pagamento. |
| Checkouts iniciados (checkout_started) | LIVE_REAL | funnel / totals.checkout_started | Histórico observado; não confirma pagamento. |
| Custo por checkout (cost_per_checkout) | LIVE_REAL | performance / cost_per_checkout | Investimento Meta certificado / eventos de checkout UP Zero. |
| Carrinho → checkout (cart_to_checkout_rate) | LIVE_REAL | funnel / cart_to_checkout_rate | Histórico observado; não confirma pagamento. |
| Checkout → compra (checkout_to_sale_rate) | LIVE_REAL | funnel / checkout_to_purchase_rate | Histórico observado; não confirma pagamento. |

## Widgets

| Widget | Classification | Read resources | Contract / limitation |
|---|---|---|---|
| commercial-trend | LIVE_REAL | overview | GENERATION_PINNED_READ_MODEL |
| paid-media-trend | LIVE_REAL_PARTIAL_COVERAGE | performance | SOURCE_DOES_NOT_PROVIDE · Meta spend existe; receita paga não é receita atendida. |
| acquisition-retention | LIVE_REAL | acquisition, retention | GENERATION_PINNED_READ_MODEL |
| funnel | LIVE_REAL | funnel, metaAds, overview, acquisition | GENERATION_PINNED_READ_MODEL |
| new-revenue-ticket | LIVE_REAL | acquisition | GENERATION_PINNED_READ_MODEL |
| new-sales-customers | LIVE_REAL | acquisition | GENERATION_PINNED_READ_MODEL |
| investment-cac | LIVE_REAL_PARTIAL_COVERAGE | performance | HISTORY_NOT_AVAILABLE_FROM_SOURCE · CAC definitivo exige novos clientes lifetime. |
| approved-conversion | SOURCE_IDENTITY_GAP | acquisition | IDENTITY_RELATIONSHIP_NOT_PROVABLE |
| registration-cohort | SOURCE_IDENTITY_GAP | none | IDENTITY_RELATIONSHIP_NOT_PROVABLE · contagens operacionais não são cohort de cadastro. |
| repeat-revenue-ticket | LIVE_REAL | retention | GENERATION_PINNED_READ_MODEL |
| recurring-reactivated | LIVE_REAL_PARTIAL_COVERAGE | retention | HISTORY_NOT_AVAILABLE_FROM_SOURCE · reativação definitiva exige histórico e cobertura mínima da regra de 90 dias. |
| repurchase-cohort | LIVE_REAL | retention | GENERATION_PINNED_READ_MODEL |
| purchase-progression | LIVE_REAL | retention | GENERATION_PINNED_READ_MODEL |
| journey-guidance | LIVE_REAL | customers, customer360, timeline, customerCampaigns | GENERATION_PINNED_READ_MODEL |
| monthly-history | LIVE_REAL | overview, performance, funnel | GENERATION_PINNED_READ_MODEL |
| provider-unavailable | FUTURE_CONNECTOR | none | FUTURE_CONNECTOR_REQUIRED · ERP/WhatsApp não conectados. |
| retail-overview | B2C_DEMO | none | B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE |
| retail-retention | B2C_DEMO | none | B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE |
| retail-platforms | B2C_DEMO | none | B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE |
| retail-funnel | B2C_DEMO | none | B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE |
| forecast | LIVE_REAL_PARTIAL_COVERAGE | none | SOURCE_DOES_NOT_PROVIDE · projeção futura não pertence às observações certificadas. |

## Reused bodies

| Body | Classification | Read resources | Fields |
|---|---|---|---|
| overview | LIVE_REAL_PARTIAL_COVERAGE | overview, acquisition, retention | requested_revenue, fulfilled_revenue, fulfillment_rate, fulfillment_gap, leads_generated, leads_approved, lead_qualification_rate, approved_conversion_rate, purchase_frequency_observed, ltv_complete, series |
| orders | LIVE_REAL_PARTIAL_COVERAGE | orders, order | order_id, created_at, order_status, payment_status, requested_total, fulfilled_total, requested_items_qty, fulfilled_items_qty, items |
| customers | LIVE_REAL_PARTIAL_COVERAGE | customers, customer360, timeline | customer_id, purchases_observed, requested_lifetime_observed, fulfilled_lifetime_observed, first_purchase_at_observed, last_purchase_at_observed, timeline |
| products | LIVE_REAL_PARTIAL_COVERAGE | products, product | name, reference, requested_revenue, fulfilled_revenue, units_requested, units_fulfilled, orders, buyers_unique, catalog, image |
| stock | LIVE_REAL_PARTIAL_COVERAGE | products, product | catalog.current_stock, catalog.variants, catalog.grade, catalog.color_hex |
| geography | LIVE_REAL_PARTIAL_COVERAGE | geography | state, cities, customers, orders, requested_revenue, fulfilled_revenue, requested_ticket |
| campaigns | LIVE_REAL_PARTIAL_COVERAGE | metaAds, creatives | campaign_id, campaign_name, spend, impressions, clicks, ctr, cpc, cpm, preview, actions, frequency |
| retail-orders | B2C_DEMO | none | demo.orders, demo.captured, demo.approved, demo.cancelled |
| retail-products | B2C_DEMO | none | demo.products, demo.stock, demo.color, demo.size |
| retail-stock | B2C_DEMO | none | demo.products, demo.stock, demo.color, demo.size |

## Page coverage

| Route | Metric IDs | Widgets / body |
|---|---|---|
| /b2b | erp_revenue_paid, erp_orders_paid, ecommerce_revenue_paid, ad_revenue_paid, roas_paid, total_media_spend, erp_ad_share, new_customers, new_requested_observed, new_orders_observed, new_ad_customers, repurchasers, recurring_fulfilled_observed, recurring_orders_observed | commercial-trend / none |
| /b2b/performance | revenue_captured, orders_generated, orders_paid, roas_requested, meta_impressions, meta_clicks, average_ticket, purchase_frequency_observed, repurchase_rate, revenue_paid, roas_paid, total_media_spend, meta_spend, google_spend, new_requested_observed, new_ticket_observed, new_orders_observed, recurring_fulfilled_observed, recurring_ticket_observed, recurring_orders_observed, approved_conversion, cac, approved_registrations, registrations, approved_registration_cost, approval_rate | paid-media-trend, acquisition-retention / none |
| /b2b/performance/funnel | total_media_spend, roas_requested, roas_paid, approved_conversion | funnel / none |
| /b2b/performance/new-customers | new_requested_observed, new_ticket_observed, new_orders_observed, new_customers, cac, registration_cost, approved_registration_cost, total_media_spend, approved_registrations, approved_converted, approved_conversion, registration_first_purchase_mean, registration_first_purchase_median | new-revenue-ticket, new-sales-customers, investment-cac, approved-conversion, registration-cohort / none |
| /b2b/performance/repurchase | repurchase_fulfilled_observed, repurchase_ticket_observed, repurchase_orders_observed, repurchasers, recurring_customers, recurring_fulfilled_observed, recurring_ticket_observed, recurring_orders_observed, reactivated_customers, reactivated_revenue_paid, reactivated_ticket_paid, reactivated_sales_paid, repeat_mean_days, repeat_median_days | repeat-revenue-ticket, recurring-reactivated, repurchase-cohort, purchase-progression / none |
| /b2b/performance/registrations | approved_registrations, approved_converted, approved_conversion |  / none |
| /b2b/performance/ads |  |  / campaigns |
| /b2b/performance/journey |  | journey-guidance / none |
| /b2b/ecommerce/overview |  |  / overview |
| /b2b/ecommerce/orders |  |  / orders |
| /b2b/ecommerce/registrations | approved_registrations, approved_converted, approved_conversion |  / none |
| /b2b/ecommerce/products |  |  / products |
| /b2b/ecommerce/stock |  |  / stock |
| /b2b/ecommerce/sellers |  |  / none |
| /b2b/ecommerce/geography |  |  / geography |
| /b2b/ecommerce/customers |  |  / customers |
| /b2b/ecommerce/history |  | monthly-history / none |
| /b2b/erp/overview |  | provider-unavailable / none |
| /b2b/erp/orders |  | provider-unavailable / none |
| /b2b/erp/customers |  | provider-unavailable / none |
| /b2b/erp/products |  | provider-unavailable / none |
| /b2b/erp/stock |  | provider-unavailable / none |
| /b2b/erp/sellers |  | provider-unavailable / none |
| /b2b/erp/geography |  | provider-unavailable / none |
| /b2b/whatsapp/analysis |  | provider-unavailable / none |
| /b2b/whatsapp/conversations |  | provider-unavailable / none |
| /b2b/whatsapp/connections |  | provider-unavailable / none |
| /b2c | orders_generated, total_media_spend, roas_approved, cost_per_sale | retail-overview / none |
| /b2c/orders |  |  / retail-orders |
| /b2c/customers/overview | new_customers, recurring_customers, repurchase_rate, ltv_complete | retail-retention / none |
| /b2c/customers |  |  / customers |
| /b2c/products |  |  / retail-products |
| /b2c/stock |  |  / retail-stock |
| /b2c/performance | total_media_spend, orders_generated, revenue_captured, roas_captured, cpm, ctr, cpc | retail-platforms / none |
| /b2c/performance/funnel |  | retail-funnel / none |
| /b2c/performance/campaigns |  |  / campaigns |
| /b2c/performance/history |  | monthly-history / none |

Detail-only contacts are excluded from list/bulk exports, aggregate cache, logs
and reports. Customer snapshot contact requires its dedicated authorized detail
request. Meta value is never general commercial revenue. Paid order status certifies
counts, not paid monetary amount. A complete bounded observation is not lifetime
proof. All B2C pages retain the persistent explicit Demo banner.
