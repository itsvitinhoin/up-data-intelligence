import type { Metric, Overview } from "@/types/domain";
import type { LiveOverview, ReadEnvelope } from "./http";

export type PreviewOverview = {
  data: Pick<
    NonNullable<Overview["b2b"]>,
    "revenue" | "orders" | "customers" | "relationship" | "series"
  >;
  goal: {
    requested: string | null;
    fulfilled: string | null;
    rate: string | null;
  };
  metadata: ReadEnvelope<LiveOverview>["metadata"];
};

function card(
  label: string,
  value: string | number | null,
  format: Metric["format"],
  hint: string,
): Metric {
  return {
    label,
    value: value === null ? null : String(value),
    format,
    hint,
    displayDigits:
      format === "currency" || format === "percent" ? 2 : undefined,
  };
}

/** Exact decimal shift: the API rate is a ratio, while MetricCard displays percent units. */
export function percentOfRatio(value: string | null): string | null {
  if (value === null) return null;
  const negative = value.startsWith("-");
  const digits = negative ? value.slice(1) : value;
  const [integer, fraction = ""] = digits.split(".");
  const shifted = (
    BigInt(integer) * 100n +
    BigInt((fraction + "00").slice(0, 2))
  ).toString();
  return `${negative ? "-" : ""}${shifted}${fraction.length > 2 ? `.${fraction.slice(2)}` : ""}`;
}

/** Decimal money to cents, divided with half-up rounding; no floating-point arithmetic. */
export function ticket(
  revenue: string | null,
  orders: number | null,
): string | null {
  if (revenue === null || orders === null || orders <= 0) return null;
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(revenue);
  if (!match) return null;
  const fraction = match[3] ?? "";
  const scale = 10n ** BigInt(fraction.length);
  const amount = BigInt(match[2]) * scale + BigInt(fraction || "0");
  const divisor = BigInt(orders) * scale;
  const rounded = (amount * 200n + divisor) / (2n * divisor);
  return `${match[1]}${rounded / 100n}.${String(rounded % 100n).padStart(2, "0")}`;
}

function chartNumber(value: string | null): number | null {
  return value === null ? null : Number(value);
}

export function presentLiveOverview(
  envelope: ReadEnvelope<LiveOverview>,
): PreviewOverview {
  const v = envelope.data;
  const unknown = "Ainda não disponível na Analytics V1.";
  const history =
    "Histórico comercial incompleto; não é possível confirmar esta métrica.";
  const payment = "Status de pagamento ainda não certificado.";
  const observed = "Indicador observado apenas no histórico disponível.";
  let repurchase: string | null = null;
  if (
    v.buyers_observed !== null &&
    v.buyers_observed > 0 &&
    v.recurring_buyers_observed !== null
  ) {
    repurchase = (
      (BigInt(v.recurring_buyers_observed) * 10000n +
        BigInt(v.buyers_observed) / 2n) /
      BigInt(v.buyers_observed)
    ).toString();
    repurchase = `${repurchase.slice(0, -2) || "0"}.${repurchase.slice(-2).padStart(2, "0")}`;
  }
  return {
    metadata: envelope.metadata,
    goal: {
      requested: v.requested_revenue,
      fulfilled: v.fulfilled_revenue,
      rate: v.fulfillment_rate,
    },
    data: {
      revenue: [
        card(
          "Faturamento Solicitado",
          v.requested_revenue,
          "currency",
          "Valor solicitado nos pedidos observados.",
        ),
        card(
          "Faturamento Atendido",
          v.fulfilled_revenue,
          "currency",
          "Valor atendido; não confirma pagamento.",
        ),
        card(
          "% de Atendimento",
          percentOfRatio(v.fulfillment_rate),
          "percent",
          "Razão de atendimento certificada pela Read API.",
        ),
        card(
          "Gap de Atendimento",
          v.fulfillment_gap,
          "currency",
          "Diferença entre solicitado e atendido.",
        ),
        card(
          "Receita Cancelada",
          v.cancelled_requested_revenue,
          "currency",
          "Valor solicitado de pedidos cancelados.",
        ),
        card(
          "Crescimento Receita",
          null,
          "percent",
          "Comparação com período anterior ainda não disponível na Read API.",
        ),
      ],
      orders: [
        card(
          "Pedidos Solicitados",
          v.orders_requested,
          "number",
          "Pedidos observados no período.",
        ),
        card(
          "Pedidos Atendidos",
          null,
          "number",
          "Definição de pedido atendido ainda não certificada; quantidade atendida não confirma pagamento.",
        ),
        card(
          "Pedidos Cancelados",
          v.orders_cancelled,
          "number",
          "Status de cancelamento observado.",
        ),
        card(
          "Pedidos Pagos",
          v.orders_paid ?? null,
          "number",
          v.orders_paid == null
            ? payment
            : "Pedidos com status pago explícito UP Zero. A contagem não certifica o valor monetário pago.",
        ),
        card(
          "Ticket Médio Solicitado",
          ticket(v.requested_revenue, v.orders_requested),
          "currency",
          "Faturamento solicitado dividido pelos pedidos solicitados.",
        ),
        card(
          "Ticket Médio Atendido",
          ticket(v.fulfilled_revenue, v.orders_requested),
          "currency",
          "Faturamento atendido dividido pelos pedidos solicitados; não é ticket pago.",
        ),
        card(
          "Peças Solicitadas",
          v.requested_pieces ?? null,
          "number",
          "Quantidade solicitada nos snapshots canônicos dos pedidos do período.",
        ),
        card(
          "Peças Atendidas",
          v.fulfilled_pieces ?? null,
          "number",
          "Quantidade atendida; não confirma pagamento.",
        ),
        card(
          "Peças por Pedido",
          v.requested_pieces_per_order ?? null,
          "decimal",
          "Peças solicitadas divididas pelos pedidos observados do período.",
        ),
      ],
      customers: [
        card("Clientes Compradores", v.buyers_observed, "number", observed),
        {
          ...card("Novos", v.new_customers_confirmed, "number", history),
          secondary: {
            label: "Ticket Médio de Aquisição",
            value: null,
            hint: history,
          },
        },
        {
          ...card(
            "Recorrentes",
            v.recurring_buyers_observed,
            "number",
            observed,
          ),
          secondary: {
            label: "Ticket Médio de Retenção",
            value: v.retention_ticket_observed ?? null,
            hint: observed,
          },
        },
        card(
          "% de Retenção",
          repurchase,
          "percent",
          "Recompra observada no histórico disponível; não é retenção histórica completa.",
        ),
        card("Reativados", null, "number", unknown),
      ],
      relationship: [
        card("Frequência", v.purchase_frequency_observed, "decimal", observed),
        card(
          "LTV Geral",
          envelope.metadata.history_complete ? v.ltv_complete : null,
          "currency",
          history,
        ),
        card("Dias para primeira compra", null, "days", unknown),
        card(
          "Dias para compras recorrentes",
          v.repeat_mean_days_observed ?? null,
          "days",
          observed,
        ),
      ],
      series: v.series.map((point) => ({
        date: point.date,
        requested: chartNumber(point.requested),
        fulfilled: chartNumber(point.fulfilled),
        newCustomers: point.new_customers_confirmed,
        recurringCustomers: null,
        mediaRevenue: null,
        spend: null,
      })),
    },
  };
}
