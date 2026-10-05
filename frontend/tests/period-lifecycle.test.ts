import { describe, it, expect } from "vitest";
import { dateRange, periodDays, periodError, presetRange } from "@/lib/period";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { summarizeLifecycle } from "@/services/demo/lifecycle";
import type { Order } from "@/services/demo/types";
import type { RequestContext } from "@/types/domain";
const context = (): RequestContext => ({
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2b", operation: "B2B" },
  session: sessionFor("maria-demo"),
  filters: { ...defaultFilters },
});
describe("Global periods", () => {
  it("resolves inclusive presets including month/year boundaries and leap years", () => {
    expect(presetRange("7")).toEqual({ from: "2026-09-24", to: "2026-09-30" });
    expect(presetRange("week")).toEqual({
      from: "2026-09-28",
      to: "2026-09-30",
    });
    expect(presetRange("month").from).toBe("2026-09-01");
    expect(presetRange("year").from).toBe("2026-01-01");
    expect(presetRange("last-month", "2024-03-10")).toEqual({
      from: "2024-02-01",
      to: "2024-02-29",
    });
    expect(presetRange("last-month", "2026-01-01")).toEqual({
      from: "2025-12-01",
      to: "2025-12-31",
    });
    expect(periodError("2026-02-30", "2026-03-01")).not.toBeNull();
    expect(periodError("2026-09-02", "2026-09-01")).not.toBeNull();
    expect(
      dateRange({ ...defaultFilters, from: "2026-09-01", to: "2026-09-01" })
        .days,
    ).toBe(1);
    expect(
      periodDays({ ...defaultFilters, from: "2026-09-30", to: "2026-10-01" }),
    ).toEqual(["2026-09-30", "2026-10-01"]);
  });
  it("filters actual orders and revenue without rescaling each order", async () => {
    const c = context();
    const all = await demoApi.read("orders", c);
    c.filters = { ...c.filters, from: "2026-09-25", to: "2026-09-27" };
    const selected = await demoApi.read("orders", c);
    expect(selected.length).toBeLessThan(all.length);
    expect(
      selected.every((o) => o.date >= "2026-09-25" && o.date <= "2026-09-27"),
    ).toBe(true);
    expect(selected[0].requested).toBe(
      all.find((o) => o.id === selected[0].id)?.requested,
    );
    const overview = await demoApi.read("overview", c);
    expect(overview.series).toHaveLength(3);
    expect(overview.goal.fulfilled).toBeCloseTo(
      selected.reduce((s, o) => s + Number(o.fulfilled), 0),
    );
    c.filters = { ...c.filters, from: "2026-08-01", to: "2026-08-31" };
    expect(await demoApi.read("orders", c)).toEqual([]);
    expect((await demoApi.read("marketing", c)).creatives).toEqual([]);
  });
});
describe("Order detail and variants", () => {
  it("returns only the selected order's items and customer, reconciles values and rejects access", async () => {
    const c = context();
    const order = (await demoApi.read("orders", c))[0];
    const detail = await demoApi.order(order.id, c);
    expect(detail.customer.id).toBe(order.customer_id);
    expect(detail.customer.email).toMatch(/@clientes\.example$/);
    expect(detail.items.reduce((s, i) => s + i.requestedQuantity, 0)).toBe(
      order.requestedQuantity,
    );
    expect(
      detail.items.reduce((s, i) => s + Number(i.fulfilled), 0),
    ).toBeCloseTo(Number(order.fulfilled), 2);
    expect(detail.items.every((i) => i.color && i.size)).toBe(true);
    await expect(demoApi.order("unknown", c)).rejects.toMatchObject({
      status: 404,
    });
    c.scope.store_id = "lume-b2b";
    await expect(demoApi.order(order.id, c)).rejects.toMatchObject({
      status: 403,
    });
  });
  it("preserves product stock totals across size and color combinations", async () => {
    const products = await demoApi.read("products", context());
    for (const product of products) {
      expect(new Set(product.variants?.map((v) => v.color)).size).toBe(2);
      expect(product.variants?.reduce((s, v) => s + (v.stock ?? 0), 0)).toBe(
        product.stock,
      );
      expect(
        product.variants
          ?.filter((v) => v.size !== null && !product.sizes[v.size])
          .every((v) => v.stock === 0),
      ).toBe(true);
    }
  });
});
describe("Lifecycle semantics", () => {
  const order = (
    id: string,
    customer_id: string,
    date: string,
    status = "CONFIRMED",
  ): Order => ({
    id,
    customer_id,
    date,
    status,
    requested: "10.00",
    fulfilled: "10.00",
    requestedQuantity: 1,
    fulfilledQuantity: 1,
    paid: false,
  });
  it("counts stages, accumulates revenue once, and separates zero from immature cohorts", () => {
    const rows = [
      order("1", "a", "2026-06-01"),
      order("2", "a", "2026-07-01"),
      order("3", "b", "2026-07-01"),
      order("4", "b", "2026-08-01"),
      order("5", "c", "2026-09-01"),
      order("6", "a", "2026-08-01", "CANCELED"),
    ];
    const d = summarizeLifecycle(
      rows,
      { a: "2026-05-31", b: "2026-06-20", c: null },
      "2026-06-01",
      "2026-09-15",
    );
    expect(d.stages.map((s) => s.customers)).toEqual([3, 2, 0, 0, 0]);
    expect(d.stages[1].revenue).toBe(20);
    expect(d.stages[4].accumulated).toBe(50);
    expect(d.cohorts[0].rates).toEqual([100, 100, 0, null]);
    expect(d.cohorts[2].rates).toEqual([100, null, null, null]);
    expect(d.conversion.buyers).toBe(2);
    expect(d.conversion.excluded).toBe(1);
    expect(d.conversion.buckets.reduce((s, b) => s + b.count, 0)).toBe(2);
    expect(d.conversion.mean).toBe(6);
    expect(d.conversion.median).toBe(6);
    expect(d.conversion.withinWeek).toBe(1);
  });
  it("groups fifth and later purchases without double counting buyers", () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      order(String(i), "a", `2026-09-0${i + 1}`),
    );
    const d = summarizeLifecycle(
      rows,
      { a: "2026-09-02" },
      "2026-09-01",
      "2026-09-30",
    );
    expect(d.stages[4].customers).toBe(1);
    expect(d.stages[4].revenue).toBe(20);
    expect(d.stages[4].accumulated).toBe(60);
    expect(d.conversion.buyers).toBe(0);
    expect(d.conversion.mean).toBeNull();
  });
});
