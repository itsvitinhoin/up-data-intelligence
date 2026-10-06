/** One deterministic local B2C projection. Never imported by server/API composition. */
import type { RequestContext, Metric } from "@/types/domain";
import { ordersFor, customersFor, total, campaignsFor } from "./business";
import { periodDays } from "@/lib/period";
import { marketingFor } from "./marketing";
import { MetricRegistry } from "@/dashboard/registry";
export function managerDemoValues(
  c: RequestContext,
): Record<string, string | null> {
  if (c.scope.operation !== "B2C") return {};
  const orders = ordersFor(c),
    paid = orders.filter((o) => o.status !== "CANCELED"),
    canceled = orders.filter((o) => o.status === "CANCELED"),
    customers = customersFor(c);
  const captured = total(orders, "requested"),
    approved = total(paid, "requested"),
    cancelled = total(canceled, "requested");
  const campaign = campaignsFor(c),
    meta = campaign.reduce((s, r) => s + Number(r.spend), 0),
    google = meta / 2,
    tiktok = meta / 4,
    spend = meta + google + tiktok;
  const sessions =
    periodDays(c.filters).filter((d) => d >= "2026-09-01" && d <= "2026-09-30")
      .length * 320;
  const recurring = customers.filter((r) => r.orders > 1).length,
    fresh = customers.length - recurring,
    cart = Math.round(sessions * 0.12),
    checkout = Math.round(cart * 0.6),
    marketing = marketingFor(c),
    impressions = marketing.creatives.reduce(
      (sum, r) => sum + r.impressions,
      0,
    ),
    clicks = marketing.creatives.reduce((sum, r) => sum + r.clicks, 0);
  const ratio = (n: number, d: number, m = 1) =>
    d ? String((n / d) * m) : null;
  return {
    orders_generated: String(orders.length),
    orders_paid: String(paid.length),
    revenue_captured: captured,
    revenue_approved: approved,
    revenue_cancelled: cancelled,
    approval_rate: ratio(Number(approved), Number(captured), 100),
    average_ticket: ratio(Number(captured), orders.length),
    new_customers: String(fresh),
    recurring_customers: String(recurring),
    repurchasers: String(recurring),
    repurchase_rate: ratio(recurring, customers.length, 100),
    ltv_complete: ratio(Number(captured), customers.length),
    cac: ratio(spend, fresh),
    meta_spend: String(meta),
    google_spend: String(google),
    tiktok_spend: String(tiktok),
    total_media_spend: String(spend),
    roas_captured: ratio(Number(captured), spend),
    roas_approved: ratio(Number(approved), spend),
    cost_per_sale: ratio(spend, paid.length),
    ctr: ratio(clicks, impressions, 100),
    cpm: ratio(spend, impressions, 1000),
    cpc: ratio(spend, clicks),
    sessions: String(sessions),
    cost_per_session: ratio(spend, sessions),
    final_conversion_rate: ratio(paid.length, sessions, 100),
    add_to_cart: String(cart),
    cost_per_add_to_cart: ratio(spend, cart),
    session_to_cart_rate: ratio(cart, sessions, 100),
    checkout_started: String(checkout),
    cost_per_checkout: ratio(spend, checkout),
    cart_to_checkout_rate: ratio(checkout, cart, 100),
    checkout_to_sale_rate: ratio(paid.length, checkout, 100),
  };
}
export function managerDemoMetrics(ids: string[], c: RequestContext): Metric[] {
  const values = managerDemoValues(c);
  return ids.map((id) => ({
    label: MetricRegistry[id].label,
    value: values[id] ?? null,
    format: MetricRegistry[id].format,
    hint: "B2C · DADOS DEMONSTRATIVOS · cenário sintético determinístico; não representa MX real.",
  }));
}

export function managerDemoRetail(c: RequestContext) {
  const values = managerDemoValues(c),
    orders = ordersFor(c),
    metrics = (ids: string[]) => managerDemoMetrics(ids, c);
  return {
    overview: metrics([
      "revenue_captured",
      "revenue_approved",
      "revenue_cancelled",
      "approval_rate",
      "new_customers",
      "recurring_customers",
      "cac",
      "repurchase_rate",
    ]).map((m, i) => ({
      ...m,
      label: [
        "Faturamento Captado",
        "Faturamento Aprovado",
        "Receita Cancelada",
        "% de Aprovação",
        "Clientes Novos",
        "Clientes Recorrentes",
        "CAC",
        "% de Recompra",
      ][i],
    })),
    performance: metrics([
      "meta_spend",
      "google_spend",
      "tiktok_spend",
      "total_media_spend",
      "roas_captured",
      "roas_approved",
      "sessions",
      "cost_per_session",
      "final_conversion_rate",
    ]).map((m, i) => ({
      ...m,
      label: [
        "Investimento em Meta",
        "Investimento em Google",
        "Investimento em TikTok Ads",
        "Investimento de Mídia Total",
        "ROAS Captado",
        "ROAS Aprovado",
        "Sessões",
        "Custo por Sessão",
        "Taxa de Conversão",
      ][i],
    })),
    series: periodDays(c.filters).map((date) => {
      const rows = orders.filter((o) => o.date === date);
      return {
        date,
        captured: Number(total(rows, "requested")),
        approved: Number(
          total(
            rows.filter((o) => o.status !== "CANCELED"),
            "requested",
          ),
        ),
      };
    }),
    paidRate: orders.length
      ? (orders.filter((o) => o.status !== "CANCELED").length / orders.length) *
        100
      : null,
    funnel: [
      { label: "Sessões", value: Number(values.sessions) },
      { label: "Carrinho", value: Number(values.add_to_cart) },
      { label: "Checkout", value: Number(values.checkout_started) },
      { label: "Compras", value: Number(values.orders_paid) },
    ],
  };
}
