import type { ReadResource } from "@/services/api/http";
import { MetricRegistry } from "./registry";
export type GapCategory = "A" | "B" | "C" | "D" | "E";
export type MetricBinding = {
  resource: ReadResource | null;
  path: string | null;
  category: GapCategory;
  reason: string;
  history?: boolean;
  multiplier?: number;
};
const source = (
  resource: ReadResource,
  path: string,
  reason = "Histórico observado; não confirma pagamento.",
  multiplier?: number,
): MetricBinding => ({ resource, path, category: "A", reason, multiplier });
const history: MetricBinding = {
  resource: null,
  path: null,
  category: "C",
  reason:
    "HISTORY_NOT_AVAILABLE_FROM_SOURCE · history_complete=false; aquisição lifetime não certificada.",
  history: true,
};
const payment: MetricBinding = {
  resource: null,
  path: null,
  category: "D",
  reason:
    "SOURCE_DOES_NOT_PROVIDE · valor pago não certificado; atendimento não comprova pagamento.",
};
const overrides: Record<string, MetricBinding> = {
  purchase_frequency_observed: source(
    "overview",
    "purchase_frequency_observed",
    "Pedidos qualificantes / compradores observados no período selecionado. Não certifica frequência lifetime.",
  ),
  orders_paid: source(
    "overview",
    "orders_paid",
    "Pedidos com status de pagamento paid explícito no UP Zero; não certifica valor monetário pago.",
  ),
  total_media_spend: source(
    "performance",
    "available_media_spend",
    "Investimento disponível: Meta certificado. Google e TikTok não conectados.",
  ),
  roas_captured: source(
    "performance",
    "commercial_roas_requested",
    "Receita solicitada UP Zero / investimento Meta certificado.",
  ),
  registration_cost: source(
    "performance",
    "registration_cost",
    "Investimento Meta certificado / cadastros no período.",
  ),
  approved_registration_cost: source(
    "performance",
    "approved_registration_cost",
    "Investimento Meta certificado / aprovações no período.",
  ),
  cost_per_session: source(
    "performance",
    "cost_per_session",
    "Investimento Meta certificado / sessões UP Zero observadas.",
  ),
  cost_per_add_to_cart: source(
    "performance",
    "cost_per_add_to_cart",
    "Investimento Meta certificado / eventos de carrinho UP Zero.",
  ),
  cost_per_checkout: source(
    "performance",
    "cost_per_checkout",
    "Investimento Meta certificado / eventos de checkout UP Zero.",
  ),

  meta_impressions: source("performance", "impressions"),
  meta_clicks: source("performance", "clicks"),
  meta_link_clicks: source("performance", "link_clicks"),
  meta_reach_campaign_day_sum: source(
    "metaAds",
    "summary.reach",
    "Alcance único reportado pelo Meta para o período completo; não soma dias ou campanhas.",
  ),
  facts_product_views: source("funnel", "totals.product_views"),
  facts_purchase: source("funnel", "totals.purchase"),
  facts_purchase_items: source("funnel", "totals.purchase_item"),
  new_customers: {
    ...source("acquisition", "confirmed_new_customers"),
    history: true,
    category: "C",
    reason: history.reason,
  },
  cac: {
    ...source("performance", "cac_new_customer"),
    history: true,
    category: "C",
    reason: history.reason,
  },
  ltv_complete: { ...history },
  repurchasers: source("retention", "recurring_buyers_observed"),
  recurring_customers: source("retention", "recurring_buyers_observed"),
  meta_spend: source(
    "performance",
    "meta_spend",
    "Investimento Meta certificado; não representa soma de plataformas desconectadas.",
  ),
  roas_requested: source(
    "performance",
    "commercial_roas_requested",
    "Receita solicitada UP Zero / investimento Meta certificado. Apenas Meta conectado.",
  ),
  ctr: source(
    "performance",
    "ctr",
    "CTR Meta · percentual de cliques / impressões.",
  ),
  cpc: source("performance", "cpc", "Investimento Meta / cliques."),
  cpm: source("performance", "cpm", "Investimento Meta / impressões × 1.000."),
  registrations: source(
    "acquisition",
    "leads_generated",
    "Cadastros register_submitted no período; identidade canônica de evento, não pessoas lifetime.",
  ),
  approved_registrations: source(
    "acquisition",
    "leads_approved",
    "Aprovações register_approved no período, incluindo backlog de cadastros anteriores.",
  ),
  approval_rate: source(
    "acquisition",
    "lead_qualification_rate",
    "Taxa de aprovação / qualificação: aprovações / cadastros × 100. Pode exceder 100% por backlog.",
  ),
  approved_conversion: source(
    "acquisition",
    "approved_conversion_rate",
    "IDENTITY_RELATIONSHIP_NOT_PROVABLE · exige vínculo determinístico e pedido qualificante após aprovação.",
  ),
  approved_converted: source(
    "acquisition",
    "approved_converted",
    "IDENTITY_RELATIONSHIP_NOT_PROVABLE · não inferir identidade por user_id.",
  ),
  new_requested_observed: source(
    "acquisition",
    "requested_first_purchase_observed",
  ),
  new_ticket_observed: source("acquisition", "ticket_first_purchase_observed"),
  repurchase_fulfilled_observed: source(
    "retention",
    "recurring_fulfilled_observed",
  ),
  repurchase_orders_observed: source("retention", "recurring_orders_observed"),
  repurchase_ticket_observed: source("retention", "retention_ticket_observed"),
  new_orders_observed: source("acquisition", "first_purchase_orders_observed"),
  recurring_fulfilled_observed: source(
    "retention",
    "recurring_fulfilled_observed",
  ),
  recurring_orders_observed: source("retention", "recurring_orders_observed"),
  recurring_ticket_observed: source("retention", "retention_ticket_observed"),
  repeat_mean_days: source("retention", "repeat_mean_days_observed"),
  repeat_median_days: source("retention", "repeat_median_days_observed"),
  orders_generated: source("overview", "orders_requested"),
  revenue_captured: source("overview", "requested_revenue"),
  revenue_cancelled: source("overview", "cancelled_requested_revenue"),
  sessions: source("funnel", "totals.sessions"),
  add_to_cart: source("funnel", "totals.add_to_cart"),
  checkout_started: source("funnel", "totals.checkout_started"),
  session_to_cart_rate: source(
    "funnel",
    "session_to_cart_rate",
    undefined,
    100,
  ),
  cart_to_checkout_rate: source(
    "funnel",
    "cart_to_checkout_rate",
    undefined,
    100,
  ),
  checkout_to_sale_rate: source(
    "funnel",
    "checkout_to_purchase_rate",
    undefined,
    100,
  ),
};
const gap = (category: GapCategory, reason: string): MetricBinding => ({
  resource: null,
  path: null,
  category,
  reason,
});
const gaps: Record<string, MetricBinding> = {
  erp_ad_share: gap(
    "D",
    "FUTURE_CONNECTOR_REQUIRED · ERP não conectado; atribuição paga não está certificada.",
  ),
  google_spend: gap(
    "D",
    "FUTURE_CONNECTOR_REQUIRED · Google Ads não conectado.",
  ),
  tiktok_spend: gap(
    "D",
    "FUTURE_CONNECTOR_REQUIRED · TikTok Ads não conectado.",
  ),
  registration_first_purchase_mean: gap(
    "A",
    "IDENTITY_RELATIONSHIP_NOT_PROVABLE · falta vínculo entre cadastro e compra qualificante.",
  ),
  registration_first_purchase_median: gap(
    "A",
    "IDENTITY_RELATIONSHIP_NOT_PROVABLE · falta vínculo entre cadastro e compra qualificante.",
  ),
  cost_per_sale: source(
    "performance",
    "cost_per_sale",
    "Investimento Meta certificado / pedidos com status pago UP Zero; não comprova valor pago.",
  ),
  average_ticket: source(
    "overview",
    "average_requested_ticket",
    "Ticket solicitado observado; não comprova pagamento.",
  ),
  repurchase_rate: source(
    "retention",
    "retention_observed",
    "Compradores recorrentes / compradores observados × 100.",
    100,
  ),
  final_conversion_rate: source(
    "funnel",
    "session_to_purchase_rate",
    "Sessões com compra observada / sessões, sem confirmação financeira.",
    100,
  ),
};
export const MetricBindings: Readonly<Record<string, MetricBinding>> =
  Object.fromEntries(
    Object.keys(MetricRegistry).map((id) => {
      const binding =
        overrides[id] ??
        gaps[id] ??
        (id.startsWith("erp_")
          ? gap(
              "D",
              "FUTURE_CONNECTOR_REQUIRED · ERP ainda não conectado para esta marca. Conecte um ERP no Admin para habilitar estes dados.",
            )
          : undefined) ??
        (id.startsWith("reactivated_") || id === "new_ad_customers"
          ? history
          : id.endsWith("_paid") ||
              ["orders_paid", "revenue_approved", "roas_approved"].includes(id)
            ? payment
            : undefined);
      if (!binding) throw new Error("Metric requires explicit binding: " + id);
      return [id, binding];
    }),
  );
export function bindingResources(ids: string[]): ReadResource[] {
  return [
    ...new Set(
      ids
        .map((id) => MetricBindings[id]?.resource)
        .filter((r): r is ReadResource => Boolean(r)),
    ),
  ];
}
export function readPath(data: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (row, key) =>
        row && typeof row === "object" && !Array.isArray(row)
          ? (row as Record<string, unknown>)[key]
          : undefined,
      data,
    );
}
