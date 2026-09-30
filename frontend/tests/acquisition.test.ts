import { describe, it, expect } from "vitest";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { navigation } from "@/config/navigation";
import type { RequestContext } from "@/types/domain";
const context = (): RequestContext => ({
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2b", operation: "B2B" },
  session: sessionFor("maria-demo"),
  filters: { ...defaultFilters },
});
describe("Acquisition and paid performance boundaries", () => {
  it("includes unpaid origins and does not inherit a media restriction", async () => {
    const c = context();
    const all = await demoApi.read("acquisition", c);
    c.filters.channel = "meta";
    c.filters.media = "yes";
    const filtered = await demoApi.read("acquisition", c);
    expect(filtered).toEqual(all);
    expect(all.customers.some((customer) => !customer.paid)).toBe(true);
    expect(all.confirmedNewCustomers).toBeNull();
    expect(all.historyComplete).toBe(false);
    expect(
      new Set(all.firstOrders.map((order) => order.customer_id)).size,
    ).toBe(all.firstOrders.length);
    expect(
      all.firstOrders.reduce((sum, order) => sum + Number(order.fulfilled), 0),
    ).toBeCloseTo(Number(all.fulfilled), 2);
    const paid = await demoApi.read("influence", context());
    expect(paid.customers.length).toBeLessThan(all.customers.length);
    expect(paid.orders.every((order) => order.paid)).toBe(true);
  });
  it("uses complete observed sequence before selecting the period, and enforces brand access", async () => {
    const c = context();
    c.filters.from = "2026-09-25";
    c.filters.to = "2026-09-27";
    const data = await demoApi.read("acquisition", c);
    expect(data.firstOrders.every((order) => order.date >= "2026-09-25")).toBe(
      true,
    );
    expect(data.customers.some((customer) => customer.id === "c1")).toBe(false);
    expect(data.customers.length).toBeLessThan(data.buyerCount);
    c.scope.store_id = "lume-b2b";
    await expect(demoApi.read("acquisition", c)).rejects.toMatchObject({
      status: 403,
    });
  });
  it("orders the B2B menu while keeping the existing commercial URL compatible", () => {
    expect(
      navigation
        .filter((item) => item.operation === "B2B")
        .map((item) => item.label),
    ).toEqual([
      "Overview",
      "Pedidos",
      "Aquisição",
      "Retenção",
      "Clientes",
      "Produtos",
      "Geografia",
      "Performance",
    ]);
    expect(navigation[1].href).toBe("/b2b/commercial");
  });
});
