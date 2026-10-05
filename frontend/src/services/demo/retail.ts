import type { Metric, RequestContext } from "@/services/demo/types";
import {
  ordersFor,
  customersFor,
  total,
  factor,
  hasDemoData,
} from "./business";
import { marketingFor } from "./marketing";
import { periodDays } from "@/lib/period";
export interface RetailSummary {
  overview: Metric[];
  performance: Metric[];
  series: { date: string; captured: number; approved: number | null }[];
  paidRate: number | null;
  funnel: { label: string; value: number }[];
}
const ratio = (a: number, b: number) => (b ? a / b : null);
export function retailFor(c: RequestContext): RetailSummary {
  const orders = ordersFor(c);
  const customers = customersFor({
    ...c,
    filters: {
      ...c.filters,
      media: "all",
      segment: "all",
      search: "",
      state: "all",
    },
  });
  const recurring = customers.filter((c) => c.orders > 1).length;
  const captured = Number(total(orders, "requested"));
  const canceled = Number(
    total(
      orders.filter((o) => o.status === "CANCELED"),
      "requested",
    ),
  );
  const covered = periodDays(c.filters).filter(
    (d) => d >= "2026-09-01" && d <= "2026-09-30",
  );
  const weight = hasDemoData(c) ? (factor(c) * covered.length) / 30 : 0;
  const sessions = Math.round(32000 * weight);
  const meta = marketingFor(c).creatives.reduce((sum, r) => sum + r.spend, 0);
  const metric = (
    label: string,
    value: number | null,
    format: Metric["format"],
    hint: string,
  ): Metric => ({
    label,
    value: value == null ? null : String(value),
    format,
    hint,
  });
  const financial =
    "Fonte financeira não conectada. Status comercial e influência de mídia não comprovam aprovação ou pagamento.";
  return {
    overview: [
      metric(
        "Faturamento Captado",
        captured,
        "currency",
        "Soma dos valores captados de todos os pedidos do período, inclusive cancelados. Base demonstrativa.",
      ),
      metric("Faturamento Aprovado", null, "currency", financial),
      metric(
        "Receita Cancelada",
        canceled,
        "currency",
        "Valor captado dos pedidos com status CANCELED; não representa estorno financeiro.",
      ),
      metric(
        "% de Aprovação",
        null,
        "percent",
        "Faturamento aprovado / captado × 100. Requer confirmação financeira.",
      ),
      metric(
        "Clientes Novos",
        null,
        "number",
        "Exige histórico completo para confirmar a primeira compra. Primeira compra observada não comprova aquisição histórica.",
      ),
      metric(
        "Clientes Recorrentes",
        recurring,
        "number",
        "Compradores do recorte com mais de uma compra no histórico demonstrativo observado.",
      ),
      metric(
        "CAC",
        null,
        "currency",
        "Investimento total / novos compradores confirmados. Exige cobertura de mídia e histórico de aquisição.",
      ),
      metric(
        "% de Recompra",
        ratio(recurring * 100, customers.length),
        "percent",
        "Compradores recorrentes / compradores do período × 100. Histórico observado.",
      ),
    ],
    performance: [
      metric(
        "Investimento em Meta",
        meta,
        "currency",
        "Soma dos gastos dos anúncios Meta no recorte; dados demonstrativos.",
      ),
      metric(
        "Investimento em Google",
        null,
        "currency",
        "Google Ads sem cobertura disponível neste ambiente; ausência não equivale a zero.",
      ),
      metric(
        "Investimento em TikTok Ads",
        null,
        "currency",
        "TikTok Ads sem cobertura disponível neste ambiente; ausência não equivale a zero.",
      ),
      metric(
        "Investimento de Mídia Total",
        null,
        "currency",
        "Meta + Google + TikTok. Total não confirmado enquanto houver plataforma sem cobertura.",
      ),
      metric(
        "ROAS Captado",
        null,
        "ratio",
        "Receita captada / investimento total. Relação agregada da marca, sem atribuição causal de vendas à mídia.",
      ),
      metric(
        "ROAS Aprovado",
        null,
        "ratio",
        "Receita aprovada / investimento total. Requer cobertura financeira e de todas as plataformas.",
      ),
      metric(
        "Sessões",
        sessions,
        "number",
        "Sessões demonstrativas no período e operação selecionados.",
      ),
      metric(
        "Custo por Sessão",
        null,
        "currency",
        "Investimento total / sessões. Investimento incompleto não é tratado como total.",
      ),
      metric(
        "Taxa de Conversão",
        ratio(
          orders.filter((o) => o.status !== "CANCELED").length * 100,
          sessions,
        ),
        "percent",
        "Pedidos não cancelados / sessões × 100. Conversão comercial observada, sem confirmação de pagamento.",
      ),
    ],
    series: periodDays(c.filters).map((date) => ({
      date,
      captured: Number(
        total(
          orders.filter((o) => o.date === date),
          "requested",
        ),
      ),
      approved: null,
    })),
    paidRate: null,
    funnel: [
      { label: "Sessões", value: sessions },
      { label: "Produto visto", value: Math.round(18000 * weight) },
      { label: "Carrinho", value: Math.round(4200 * weight) },
      { label: "Checkout", value: Math.round(2200 * weight) },
      {
        label: "Pedido não cancelado",
        value: orders.filter((o) => o.status !== "CANCELED").length,
      },
    ],
  };
}
