import { describe, it, expect } from "vitest";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import {
  atRisk,
  brokenGrade,
  groupedSales,
  promising,
  stockPower,
  turnoverPercent,
} from "@/lib/product-analysis";
import { navigation } from "@/config/navigation";
import type { RequestContext } from "@/types/domain";
const context = (): RequestContext => ({
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2c", operation: "B2C" },
  session: sessionFor("maria-demo"),
  filters: { ...defaultFilters, from: "2026-09-24", to: "2026-09-30" },
});
describe("B2C separated period and inventory contracts", () => {
  it("lists all scoped orders independently of the global period and opens a historical order", async () => {
    const c = context();
    const range = await demoApi.read("orders", c);
    const all = await demoApi.read("order_history", c);
    expect(all.length).toBeGreaterThan(range.length);
    expect(range.every((o) => o.date >= c.filters.from!)).toBe(true);
    expect(all.some((o) => o.date < c.filters.from!)).toBe(true);
    const old = all.find((o) => o.date < c.filters.from!)!;
    const detail = await demoApi.order(old.id, c);
    expect(detail?.order.id).toBe(old.id);
    expect(
      detail?.items.reduce((sum, item) => sum + Number(item.requested), 0),
    ).toBeCloseTo(Number(old.requested), 2);
    c.filters.channel = "google";
    c.filters.collection = "verao";
    expect(await demoApi.read("order_history", c)).toEqual(all);
  });
  it("keeps stock independent of date and preserves explicit active, price and HEX metadata", async () => {
    const c = context();
    const stock = await demoApi.read("inventory_products", c);
    c.filters.from = "2027-01-01";
    c.filters.to = "2027-01-07";
    expect(await demoApi.read("inventory_products", c)).toEqual(stock);
    expect(await demoApi.read("products", c)).toEqual([]);
    const active = stock.filter((p) => p.active === true);
    expect(stock.some((p) => p.active === false)).toBe(true);
    expect(stockPower(stock)).toBeCloseTo(
      active.reduce((s, p) => s + p.stock * Number(p.salePrice), 0),
      2,
    );
    expect(
      stock.every((p) =>
        p.variants?.every((v) => !v.hex || /^#[0-9A-Fa-f]{6}$/.test(v.hex)),
      ),
    ).toBe(true);
  });
  it("reconciles category, size and color sales and classifies grade/risk transparently", async () => {
    const rows = await demoApi.read("inventory_products", context());
    const sold = rows.reduce((s, p) => s + p.units, 0);
    for (const key of ["category", "size", "color"] as const)
      expect(groupedSales(rows, key).reduce((s, r) => s + r.value, 0)).toBe(
        sold,
      );
    expect(rows.some((p) => brokenGrade(p) && atRisk(p))).toBe(true);
    expect(rows.some((p) => promising(p, rows))).toBe(true);
    expect(turnoverPercent(200, 100)).toBe(200);
    expect(turnoverPercent(200, 0)).toBeNull();
    expect(stockPower([{ ...rows[0], salePrice: null }])).toBeNull();
  });
  it("offers campaign platform routes in the approved order", () => {
    const entry = navigation.find((n) => n.label === "Campanhas")!;
    expect(entry.children).toEqual([
      ["Meta Ads", "/campaigns/meta"],
      ["Google Ads", "/campaigns/google"],
      ["Pinterest Ads", "/campaigns/pinterest"],
      ["TikTok Ads", "/campaigns/tiktok"],
    ]);
    expect(navigation.some((n) => n.href === "/b2c/revenue")).toBe(false);
    expect(navigation.find((n) => n.href === "/b2c/products")?.label).toBe(
      "Análise de Produtos",
    );
  });
});
