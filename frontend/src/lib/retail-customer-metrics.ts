import { qualifyingStatuses } from "@/services/demo/customer-metrics";
import type { Metric, Order } from "@/types/domain";

/** Customer-level B2C metrics from observed commercial orders only. */
export function retailCustomerMetrics(orders: Order[]): Metric[] {
  const purchases = [
    ...new Map(orders.map((order) => [order.id, order])).values(),
  ]
    .filter((order) => qualifyingStatuses.has(order.status))
    .sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
  const revenueCents = purchases.reduce(
    (sum, order) => sum + Math.round(Number(order.requested) * 100),
    0,
  );
  const intervals = purchases
    .slice(1)
    .map(
      (order, index) =>
        (Date.parse(order.date) - Date.parse(purchases[index].date)) / 86400000,
    );
  const validIntervals = intervals.filter(
    (days) => Number.isFinite(days) && days >= 0,
  );
  return [
    {
      label: "Pedidos",
      value: String(purchases.length),
      format: "number",
      hint: "Pedidos com status comercial qualificante no histórico observado. Cancelados não contam como compra.",
    },
    {
      label: "Receita",
      value: (revenueCents / 100).toFixed(2),
      format: "currency",
      hint: "Valor captado dos pedidos qualificantes observados; não comprova aprovação ou pagamento.",
    },
    {
      label: "Frequência de Compra",
      value: validIntervals.length
        ? String(
            validIntervals.reduce((sum, days) => sum + days, 0) /
              validIntervals.length,
          )
        : null,
      format: "days",
      hint: "Intervalo médio em dias entre compras qualificantes consecutivas observadas. Uma única compra não permite calcular a frequência.",
    },
    {
      label: "LTV",
      value: null,
      format: "currency",
      hint: "LTV real requer histórico completo e receita financeira confirmada. A receita captada observada não substitui LTV.",
    },
  ];
}
