import type { Metric, Order } from "@/services/demo/types";

// Observed commercial purchases, not a confirmation of financial payment.
export const qualifyingStatuses = new Set([
  "RESERVED",
  "CONFIRMED",
  "PROCESSING",
  "INVOICED",
  "SHIPPED",
]);
export function customerMetrics(
  history: Order[],
  approvals: Record<string, string | null>,
  from: string,
  to: string,
): Metric[] {
  const rows = [...new Map(history.map((order) => [order.id, order])).values()]
    .filter((o) => qualifyingStatuses.has(o.status) && o.date <= to)
    .sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
  const period = rows.filter((o) => o.date >= from);
  const buyers = new Set(period.map((o) => o.customer_id));
  const first = new Map<string, Order>();
  const previous = new Map<string, Order>();
  const recurringDays: number[] = [];
  for (const order of rows) {
    if (!first.has(order.customer_id)) first.set(order.customer_id, order);
    const prior = previous.get(order.customer_id);
    if (prior && order.date >= from)
      recurringDays.push(
        (Date.parse(order.date) - Date.parse(prior.date)) / 86400000,
      );
    previous.set(order.customer_id, order);
  }
  const firstDays = [...first.values()].flatMap((order) => {
    const approval = approvals[order.customer_id];
    if (order.date < from || !approval) return [];
    const days = (Date.parse(order.date) - Date.parse(approval)) / 86400000;
    return Number.isFinite(days) && days >= 0 ? [days] : [];
  });
  const mean = (values: number[]) =>
    values.length
      ? String(values.reduce((sum, value) => sum + value, 0) / values.length)
      : null;
  const observedRevenue = rows.reduce(
    (sum, order) => sum + Math.round(Number(order.fulfilled) * 100),
    0,
  );
  return [
    {
      label: "Frequência",
      value: buyers.size ? String(period.length / buyers.size) : null,
      format: "decimal",
      hint: "Média de pedidos qualificantes por cliente comprador no período, de todas as origens.",
    },
    {
      label: "LTV geral da marca",
      value: null,
      format: "currency",
      hint: "Histórico completo não confirmado. Receita comercial observada não equivale ao LTV definitivo.",
      secondary: {
        label: "Receita média observada por cliente",
        value: first.size
          ? (observedRevenue / 100 / first.size).toFixed(2)
          : null,
        hint: "Receita atendida qualificante / clientes no histórico disponível até o fim do período. Parcial; não confirma pagamento.",
      },
    },
    {
      label: "Dias médios para primeira compra",
      value: mean(firstDays),
      format: "days",
      hint: "Da aprovação até a primeira compra qualificante observada no período. Exclui datas ausentes ou inválidas; histórico parcial.",
    },
    {
      label: "Dias médios para compras recorrentes",
      value: mean(recurringDays),
      format: "days",
      hint: "Média dos intervalos entre compras qualificantes consecutivas cuja recompra está no período. Inclui a compra anterior ao recorte.",
    },
  ];
}
