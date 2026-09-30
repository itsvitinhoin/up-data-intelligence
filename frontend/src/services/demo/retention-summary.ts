import type { Order, RequestContext } from "@/types/domain";
import { dateRange, periodDays, DEMO_TODAY } from "@/lib/period";
import { ordersFor, total } from "./business";
import { qualifyingStatuses } from "./customer-metrics";
export function summarizeRetention(history: Order[], from: string, to: string) {
  const rows = [...new Map(history.map((o) => [o.id, o])).values()]
    .filter((o) => qualifyingStatuses.has(o.status) && o.date <= to)
    .sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
  const seen = new Set<string>();
  const repeats = new Set<string>();
  for (const row of rows) {
    if (seen.has(row.customer_id)) repeats.add(row.id);
    seen.add(row.customer_id);
  }
  const selected = rows.filter((o) => o.date >= from);
  function point(orders: Order[]) {
    const repeatOrders = orders.filter((o) => repeats.has(o.id));
    const buyers = new Set(orders.map((o) => o.customer_id)).size;
    const recurring = new Set(repeatOrders.map((o) => o.customer_id)).size;
    return {
      buyers,
      recurring,
      rate: buyers ? (recurring / buyers) * 100 : null,
      ticket: repeatOrders.length
        ? Number(total(repeatOrders, "fulfilled")) / repeatOrders.length
        : null,
    };
  }
  const days = periodDays({
    from,
    to,
    days: 1,
    channel: "all",
    collection: "all",
  });
  const weekStart = (day: string) => {
    const d = new Date(day + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  };
  const weeks = [...new Set(days.map(weekStart))];
  return {
    ...point(selected),
    weekly: weeks.map((date) => ({
      date,
      ...point(selected.filter((o) => weekStart(o.date) === date)),
    })),
    series: periodDays({
      from,
      to,
      days: 1,
      channel: "all",
      collection: "all",
    }).map((date) => ({
      date,
      ...point(selected.filter((o) => o.date === date)),
    })),
  };
}
export type RetentionSummary = ReturnType<typeof summarizeRetention>;
export function retentionSummaryFor(c: RequestContext): RetentionSummary {
  const { from, to: end } = dateRange(c.filters);
  const to = end < DEMO_TODAY ? end : DEMO_TODAY;
  return summarizeRetention(
    ordersFor({ ...c, filters: { ...c.filters, from: "2000-01-01", to } }),
    from,
    to,
  );
}
