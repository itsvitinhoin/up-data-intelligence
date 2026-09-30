import type { Lifecycle, Order, RequestContext } from "@/types/domain";
import { dateRange, inPeriod, isoDay, DEMO_TODAY } from "@/lib/period";
import { ordersFor, total } from "./business";
import { qualifyingStatuses as qualifying } from "./customer-metrics";
import { approvals } from "./fixtures";
export function summarizeLifecycle(
  orders: Order[],
  approvals: Record<string, string | null>,
  from: string,
  to: string,
): Lifecycle {
  const grouped = new Map<string, Order[]>();
  orders
    .filter((o) => qualifying.has(o.status) && o.date <= to)
    .toSorted(
      (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
    )
    .forEach((o) =>
      grouped.set(o.customer_id, [...(grouped.get(o.customer_id) ?? []), o]),
    );
  const sequences = [...grouped.values()].filter((rows) =>
    inPeriod(rows[0].date, {
      from,
      to,
      days: 1,
      channel: "all",
      collection: "all",
    }),
  );
  const size = sequences.length;
  let accumulated = 0;
  const stages = [1, 2, 3, 4, 5].map((stage) => {
    const selected = sequences.filter((rows) => rows.length >= stage);
    const stageOrders = selected.flatMap((rows) =>
      stage === 5 ? rows.slice(4) : [rows[stage - 1]],
    );
    const revenue = Number(total(stageOrders, "fulfilled"));
    accumulated += revenue;
    const previous =
      stage === 1
        ? size
        : sequences.filter((rows) => rows.length >= stage - 1).length;
    const gaps =
      stage === 1
        ? []
        : selected.map(
            (rows) =>
              (Date.parse(rows[stage - 1].date) -
                Date.parse(rows[stage - 2].date)) /
              86400000,
          );
    return {
      stage,
      customers: selected.length,
      share: size ? (selected.length / size) * 100 : null,
      continuation: previous ? (selected.length / previous) * 100 : null,
      revenue,
      accumulated,
      meanDays: gaps.length
        ? gaps.reduce((s, v) => s + v, 0) / gaps.length
        : null,
    };
  });
  const cohorts = [
    ...new Set(sequences.map((rows) => rows[0].date.slice(0, 7))),
  ]
    .sort()
    .map((month) => {
      const base = sequences.filter((rows) => rows[0].date.startsWith(month));
      const [year, m] = month.split("-").map(Number);
      return {
        month,
        customers: base.length,
        rates: [0, 1, 2, 3].map((offset) => {
          if (offset === 0) return 100;
          const start = isoDay(Date.UTC(year, m - 1 + offset, 1));
          const end = isoDay(Date.UTC(year, m + offset, 0));
          if (end > to) return null;
          return (
            (base.filter((rows) =>
              rows.slice(1).some((o) => o.date >= start && o.date <= end),
            ).length /
              base.length) *
            100
          );
        }),
      };
    });
  const delays = sequences
    .flatMap((rows) => {
      const approval = approvals[rows[0].customer_id];
      if (!approval) return [];
      const days = (Date.parse(rows[0].date) - Date.parse(approval)) / 86400000;
      return Number.isFinite(days) && days >= 0 ? [days] : [];
    })
    .sort((a, b) => a - b);
  const limits = [0, 3, 7, 14, 30, 60, Infinity];
  const names = [
    "Mesmo dia",
    "1–3 dias",
    "4–7 dias",
    "8–14 dias",
    "15–30 dias",
    "31–60 dias",
    "Mais de 60",
  ];
  const buckets = limits.map((limit, i) => {
    const count = delays.filter(
      (day) => day <= limit && (i === 0 || day > limits[i - 1]),
    ).length;
    return {
      label: names[i],
      count,
      percent: delays.length ? (count / delays.length) * 100 : null,
    };
  });
  const midpoint = Math.floor(delays.length / 2);
  return {
    stages,
    cohorts,
    conversion: {
      buckets,
      buyers: delays.length,
      excluded: size - delays.length,
      mean: delays.length
        ? delays.reduce((s, v) => s + v, 0) / delays.length
        : null,
      median: delays.length
        ? delays.length % 2
          ? delays[midpoint]
          : (delays[midpoint - 1] + delays[midpoint]) / 2
        : null,
      withinWeek: delays.filter((d) => d <= 7).length,
      withinMonth: delays.filter((d) => d <= 30).length,
    },
  };
}
export function lifecycleFor(c: RequestContext): Lifecycle {
  const { from, to: requestedTo } = dateRange(c.filters);
  const to = requestedTo > DEMO_TODAY ? DEMO_TODAY : requestedTo;
  const rows = ordersFor({
    ...c,
    filters: { ...c.filters, from: "2000-01-01", to },
  });
  return summarizeLifecycle(rows, approvals, from, to);
}
