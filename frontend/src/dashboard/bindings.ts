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
    "REQUIRES_HISTORICAL_BACKFILL · history_complete=false; aquisição lifetime não certificada.",
  history: true,
};
const payment: MetricBinding = {
  resource: null,
  path: null,
  category: "D",
  reason: "PAYMENT_SOURCE_NOT_CERTIFIED · atendimento não comprova pagamento.",
};
const overrides: Record<string, MetricBinding> = {
  meta_impressions: source("performance", "impressions"),
  meta_clicks: source("performance", "clicks"),
  meta_link_clicks: source("performance", "link_clicks"),
  meta_reach_campaign_day_sum: source(
    "performance",
    "reach_campaign_day_sum",
    "Soma no grão campanha/dia; não é alcance único do período.",
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
    "roas_requested",
    "Receita solicitada influenciada / investimento Meta; influência não é atribuição financeira.",
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
    "REGISTRATION_CUSTOMER_IDENTITY_NOT_CERTIFIED · exige vínculo determinístico e pedido qualificante após aprovação.",
  ),
  approved_converted: source(
    "acquisition",
    "approved_converted",
    "REGISTRATION_CUSTOMER_IDENTITY_NOT_CERTIFIED · não inferir identidade por user_id.",
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
    "ERP_PAID_ATTRIBUTION_CONNECTOR_REQUIRED · falta receita paga e vínculo ERP/anúncio.",
  ),
  google_spend: gap("D", "GOOGLE_ADS_CONNECTOR_REQUIRED"),
  tiktok_spend: gap("D", "TIKTOK_ADS_CONNECTOR_REQUIRED"),
  total_media_spend: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · Meta não é soma de Google/TikTok desconectados.",
  ),
  registration_cost: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · custo geral exige investimento total certificado.",
  ),
  approved_registration_cost: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · custo geral exige investimento total certificado.",
  ),
  registration_first_purchase_mean: gap(
    "A",
    "REGISTRATION_CUSTOMER_IDENTITY_NOT_CERTIFIED · falta vínculo entre cadastro e compra qualificante.",
  ),
  registration_first_purchase_median: gap(
    "A",
    "REGISTRATION_CUSTOMER_IDENTITY_NOT_CERTIFIED · falta vínculo entre cadastro e compra qualificante.",
  ),
  cost_per_sale: gap("D", "PAID_SALES_AND_TOTAL_MEDIA_CONNECTORS_REQUIRED"),
  roas_captured: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · ROAS geral exige investimento total.",
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
  cost_per_session: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · custo geral exige investimento total.",
  ),
  cost_per_add_to_cart: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · custo geral exige investimento total.",
  ),
  cost_per_checkout: gap(
    "D",
    "MEDIA_PLATFORM_COVERAGE_INCOMPLETE · custo geral exige investimento total.",
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
