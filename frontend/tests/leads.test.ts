import { describe, expect, it } from "vitest";
import { summarizeLeads, type DemoLead } from "@/services/demo/leads";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import type { Order } from "@/services/demo/types";
import type { RequestContext } from "@/types/domain";
const orders: Order[] = ["CONFIRMED", "SHIPPED", "CANCELED"].map(
  (status, i) => ({
    id: String(i),
    customer_id: i === 2 ? "b" : "a",
    status,
    date: "2026-09-10",
    requested: "100.00",
    fulfilled: "100.00",
    requestedQuantity: 1,
    fulfilledQuantity: 1,
    paid: false,
  }),
);
const leads: DemoLead[] = [
  {
    id: "a",
    customerId: "a",
    registeredAt: "2026-09-01",
    approvedAt: "2026-09-02",
  },
  {
    id: "b",
    customerId: "b",
    registeredAt: "2026-09-01",
    approvedAt: "2026-09-02",
  },
  {
    id: "pending",
    customerId: null,
    registeredAt: "2026-09-03",
    approvedAt: null,
  },
  {
    id: "future",
    customerId: null,
    registeredAt: "2026-09-04",
    approvedAt: "2026-10-02",
  },
  {
    id: "older",
    customerId: "a",
    registeredAt: "2026-08-01",
    approvedAt: "2026-09-02",
  },
];
describe("Brand lead cohort", () => {
  it("deduplicates leads, counts conversions once and excludes canceled purchases and future approvals", () => {
    expect(
      summarizeLeads([...leads, leads[0]], orders, "2026-09-01", "2026-09-30"),
    ).toEqual({
      leads: 4,
      approved: 2,
      converted: 1,
      qualificationRate: 50,
      conversionRate: 50,
    });
  });
  it("excludes purchases before approval and after the period, and preserves missing denominators", () => {
    expect(
      summarizeLeads(
        leads,
        orders.map((o) => ({ ...o, date: "2026-09-01" })),
        "2026-09-01",
        "2026-09-30",
      ).converted,
    ).toBe(0);
    expect(
      summarizeLeads(leads, orders, "2026-09-01", "2026-09-09").converted,
    ).toBe(0);
    expect(
      summarizeLeads([leads[2]], orders, "2026-09-01", "2026-09-30"),
    ).toMatchObject({ qualificationRate: 0, conversionRate: null });
    expect(
      summarizeLeads([], orders, "2026-09-01", "2026-09-30"),
    ).toMatchObject({ qualificationRate: null, conversionRate: null });
  });
  it("keeps brand leads separate from marketing, respects dates and enforces store access", async () => {
    const c: RequestContext = {
      scope: {
        tenant_id: "demo-up",
        store_id: "mx-fashion-b2b",
        operation: "B2B",
      },
      session: sessionFor("maria-demo"),
      filters: { ...defaultFilters },
    };
    const base = await demoApi.read("leads", c);
    expect(base).toEqual({
      leads: 12,
      approved: 7,
      converted: 5,
      qualificationRate: (7 / 12) * 100,
      conversionRate: (5 / 7) * 100,
    });
    c.filters.channel = "meta";
    c.filters.collection = "primavera";
    expect(await demoApi.read("leads", c)).toEqual(base);
    c.filters.from = "2026-09-28";
    c.filters.to = "2026-09-28";
    expect(await demoApi.read("leads", c)).toEqual({
      leads: 1,
      approved: 0,
      converted: 0,
      qualificationRate: 0,
      conversionRate: null,
    });
    c.scope.store_id = "lume-b2b";
    await expect(demoApi.read("leads", c)).rejects.toMatchObject({
      status: 403,
    });
  });
});
