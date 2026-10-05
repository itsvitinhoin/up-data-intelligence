import type {
  Geography,
  LeadSummary,
  Order,
  RequestContext,
} from "@/services/demo/types";
import { dateRange, DEMO_TODAY } from "@/lib/period";
import { geographyFor, hasDemoData, ordersFor } from "./business";
import { approvals, customers, geography } from "./fixtures";
import { qualifyingStatuses } from "./customer-metrics";
export interface DemoLead {
  state?: string | null;
  id: string;
  registeredAt: string;
  approvedAt: string | null;
  customerId: string | null;
}
// Explicit synthetic registrations, including non-buyers. Never inferred from Meta leads.
const demoLeads: DemoLead[] = [
  ...Object.entries(approvals).map(([customerId, approvedAt]) => ({
    id: `lead-${customerId}`,
    state: customers.find((c) => c.id === customerId)?.state ?? null,
    registeredAt: approvedAt,
    approvedAt,
    customerId,
  })),
  {
    id: "lead-9",
    state: "SP",
    registeredAt: "2026-09-05",
    approvedAt: "2026-09-06",
    customerId: null,
  },
  {
    id: "lead-10",
    registeredAt: "2026-09-15",
    approvedAt: "2026-10-02",
    customerId: null,
  },
  {
    id: "lead-11",
    state: "MG",
    registeredAt: "2026-09-20",
    approvedAt: "2026-09-23",
    customerId: null,
  },
  ...["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"].map(
    (registeredAt, i) => ({
      id: `pending-${i}`,
      registeredAt,
      approvedAt: null,
      customerId: null,
    }),
  ),
];
export function summarizeLeads(
  leads: DemoLead[],
  orders: Order[],
  from: string,
  to: string,
): LeadSummary {
  const cohort = [
    ...new Map(leads.map((lead) => [lead.id, lead])).values(),
  ].filter((lead) => lead.registeredAt >= from && lead.registeredAt <= to);
  const approved = cohort.filter(
    (lead) =>
      lead.approvedAt !== null &&
      lead.approvedAt >= lead.registeredAt &&
      lead.approvedAt <= to,
  );
  const converted = approved.filter(
    (lead) =>
      lead.customerId !== null &&
      orders.some(
        (order) =>
          order.customer_id === lead.customerId &&
          qualifyingStatuses.has(order.status) &&
          order.date >= lead.approvedAt! &&
          order.date <= to,
      ),
  );
  return {
    leads: cohort.length,
    approved: approved.length,
    converted: converted.length,
    qualificationRate: cohort.length
      ? (approved.length / cohort.length) * 100
      : null,
    conversionRate: approved.length
      ? (converted.length / approved.length) * 100
      : null,
  };
}
export function leadsFor(context: RequestContext): LeadSummary {
  // Brand-wide registration cohort; campaign, customer and product-collection filters do not apply to registrations.
  const { from, to: end } = dateRange(context.filters);
  const to = end < DEMO_TODAY ? end : DEMO_TODAY;
  const orders = ordersFor({
    ...context,
    filters: {
      ...context.filters,
      from,
      to,
      channel: "all",
      collection: "all",
      media: "all",
    },
  });
  return summarizeLeads(
    hasDemoData(context) ? demoLeads : [],
    orders,
    from,
    to,
  );
}

export function geographyWithLeads(c: RequestContext): Geography[] {
  const base = geographyFor(c);
  if (!hasDemoData(c)) return base;
  const { from, to: end } = dateRange(c.filters);
  const to = end < DEMO_TODAY ? end : DEMO_TODAY;
  const orders = ordersFor({
    ...c,
    filters: { ...c.filters, from, to, channel: "all", collection: "all" },
  });
  const states = new Set([
    ...base.map((r) => r.uf),
    ...demoLeads
      .filter((l) => l.state && l.registeredAt >= from && l.registeredAt <= to)
      .map((l) => l.state!),
  ]);
  return [...states].map((uf) => {
    const leads = summarizeLeads(
      demoLeads.filter((l) => l.state === uf),
      orders,
      from,
      to,
    );
    const existing = base.find((r) => r.uf === uf);
    return {
      ...(existing ?? {
        uf,
        name: geography.find((g) => g.uf === uf)?.name ?? uf,
        requested: 0,
        fulfilled: 0,
        customers: 0,
        orders: 0,
        newCustomers: null,
        influencedCustomers: 0,
        averageTicket: null,
        cities: [],
      }),
      approvedWithoutPurchase: leads.approved - leads.converted,
      conversionRate: leads.conversionRate,
    };
  });
}
