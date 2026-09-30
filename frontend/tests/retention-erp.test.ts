import { describe, it, expect } from "vitest";
import ExcelJS from "exceljs";
import { summarizeRetention } from "@/services/demo/retention-summary";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { filterProducts } from "@/lib/erp";
import { csvContent, workbookBytes } from "@/lib/erp-export";
import { stockCoverage, stockTurnover } from "@/services/demo/erp";
import type { Order, RequestContext } from "@/types/domain";
const context = (): RequestContext => ({
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2b", operation: "B2B" },
  session: sessionFor("maria-demo"),
  filters: { ...defaultFilters },
});
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
  requested: "100.00",
  fulfilled: "80.00",
  requestedQuantity: 1,
  fulfilledQuantity: 1,
  paid: false,
});
describe("Retention and geographic registrations", () => {
  it("counts returning buyers using prior history, repeat-only ticket, null empty days and excludes cancellations", () => {
    const rows = [
      order("1", "a", "2026-08-01"),
      order("2", "a", "2026-09-01"),
      order("3", "b", "2026-09-01"),
      order("4", "b", "2026-09-02", "CANCELED"),
    ];
    const result = summarizeRetention(
      [...rows, rows[1]],
      "2026-09-01",
      "2026-09-03",
    );
    expect(result).toMatchObject({
      buyers: 2,
      recurring: 1,
      rate: 50,
      ticket: 80,
    });
    expect(result.series.map((p) => p.rate)).toEqual([50, null, null]);
    expect(result.weekly).toHaveLength(1);
    expect(result.weekly[0]).toMatchObject({
      buyers: 2,
      recurring: 1,
      rate: 50,
    });
    expect(summarizeRetention([], "2026-09-01", "2026-09-01")).toMatchObject({
      buyers: 0,
      recurring: 0,
      rate: null,
      ticket: null,
    });
  });
  it("reconciles state conversions with the same approved cohort, and keeps lead-only states visible", async () => {
    const c = context();
    const states = await demoApi.read("geography", c);
    const leads = await demoApi.read("leads", c);
    expect(
      states.reduce((s, r) => s + (r.approvedWithoutPurchase ?? 0), 0),
    ).toBe(leads.approved - leads.converted);
    expect(states.find((r) => r.uf === "SP")).toMatchObject({
      approvedWithoutPurchase: 1,
      conversionRate: 50,
    });
    c.filters.from = "2026-09-05";
    c.filters.to = "2026-09-06";
    expect(
      (await demoApi.read("geography", c)).find((r) => r.uf === "SP"),
    ).toMatchObject({
      customers: 0,
      orders: 0,
      approvedWithoutPurchase: 1,
      conversionRate: 0,
    });
  });
});
describe("ERP demonstration ledger", () => {
  it("reconciles net revenue, catalogue, variants, sellers and period series without duplicate orders", async () => {
    const d = await demoApi.read("erp", context());
    const k = d.dashboard.kpis;
    expect(new Set(d.orders.map((o) => o.id)).size).toBe(d.orders.length);
    expect(k.netRevenue).toBeCloseTo(
      k.grossRevenue - k.discountAmount - k.returnAmount,
      2,
    );
    expect(
      d.dashboard.revenueOverTime.reduce((s, p) => s + p.value, 0),
    ).toBeCloseTo(k.netRevenue, 2);
    expect(d.products.totalRevenue).toBeCloseTo(k.netRevenue, 1);
    expect(d.products.totalUnits).toBe(k.totalQuantity);
    expect(
      d.dashboard.breakdowns.sellers.reduce((s, p) => s + p.revenue, 0),
    ).toBeCloseTo(k.netRevenue, 2);
    expect(
      d.products.rows.reduce(
        (s, p) => s + p.variants.reduce((sum, v) => sum + v.revenue, 0),
        0,
      ),
    ).toBeCloseTo(k.netRevenue, 1);
    expect(d.products.negativeStockCount).toBe(1);
    expect(d.customers.every((c) => c.lifetimeValue === null)).toBe(true);
    expect(d.dashboard.kpis.newCustomers).toBeNull();
  });
  it("preserves order values across narrower periods and scopes history to the authorized operation", async () => {
    const c = context();
    const all = await demoApi.read("erp", c);
    c.filters.from = "2026-09-20";
    c.filters.to = "2026-09-25";
    const window = await demoApi.read("erp", c);
    expect(window.orders.length).toBeLessThan(all.orders.length);
    for (const o of window.orders)
      expect(o).toEqual(all.orders.find((row) => row.id === o.id));
    expect(window.history.some((o) => o.createdAt < c.filters.from!)).toBe(
      true,
    );
    expect(window.history.every((o) => o.createdAt <= c.filters.to!)).toBe(
      true,
    );
    c.scope.store_id = "lume-b2b";
    await expect(demoApi.read("erp", c)).rejects.toMatchObject({ status: 403 });
  });
  it("filters variant stock, category and SKU and calculates stock coverage safely", async () => {
    const { products } = await demoApi.read("erp", context());
    const negative = filterProducts(
      products.rows,
      "",
      "all",
      "negative",
      "stock",
    );
    expect(negative).toHaveLength(1);
    expect(negative[0].variants.some((v) => v.stock < 0)).toBe(true);
    const sku = products.rows[0].variants[0].sku;
    expect(
      filterProducts(products.rows, sku, "all", "all", "revenue"),
    ).toHaveLength(1);
    expect(
      filterProducts(products.rows, "nothing-found", "all", "all", "revenue"),
    ).toEqual([]);
    expect(stockTurnover(10, 30)).toBe(25);
    expect(stockCoverage(10, 30, 10)).toBe(30);
    expect(stockCoverage(0, 30, 10)).toBeNull();
    expect(stockCoverage(10, -2, 10)).toBe(0);
  });
  it("exports genuine XLSX including empty headers, and protects CSV formula cells", async () => {
    const columns = [
      { header: "Cliente", value: (r: { name: string }) => r.name },
    ];
    const bytes = await workbookBytes([{ name: "=1+1" }], columns);
    const book = new ExcelJS.Workbook();
    await book.xlsx.load(bytes as unknown as ExcelJS.Buffer);
    expect(book.worksheets[0].getCell("A2").value).toBe("=1+1");
    expect(book.worksheets[0].getCell("A2").type).toBe(
      ExcelJS.ValueType.String,
    );
    const empty = new ExcelJS.Workbook();
    await empty.xlsx.load(
      (await workbookBytes([], columns)) as unknown as ExcelJS.Buffer,
    );
    expect(empty.worksheets[0].rowCount).toBe(1);
    expect(csvContent([{ name: "=1+1" }], columns)).toContain("'=1+1");
  });
});
