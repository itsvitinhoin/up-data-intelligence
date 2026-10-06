import { describe, expect, it } from "vitest";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { managerDemoRetail } from "@/services/demo/manager-v2";
import { orderItemsFor } from "@/services/demo/details";
import { groupedSales } from "@/lib/product-analysis";
import { defaultFilters } from "@/config/tenants";
import type { RequestContext } from "@/services/demo/types";

const cents = (value: string | null) => BigInt(value!.replace(".", ""));
const context = (from: string, to: string): RequestContext => ({
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2c", operation: "B2C" },
  session: sessionFor("maria-demo"),
  filters: { ...defaultFilters, from, to },
});

describe("one B2C demo commercial ledger", () => {
  it.each([
    ["2026-09-01", "2026-09-30"],
    ["2026-09-24", "2026-09-30"],
    ["2026-09-01", "2026-09-15"],
  ])(
    "reconciles orders, products, quantities and retail revenue for %s–%s",
    async (from, to) => {
      const c = context(from, to);
      const [orders, products] = await Promise.all([
        demoApi.read("orders", c),
        demoApi.read("products", c),
      ]);
      const requested = orders.reduce(
        (sum, order) => sum + cents(order.requested),
        0n,
      );
      const fulfilled = orders.reduce(
        (sum, order) => sum + cents(order.fulfilled),
        0n,
      );
      const units = orders.reduce(
        (sum, order) => sum + order.requestedQuantity,
        0,
      );
      expect(
        products.reduce((sum, product) => sum + cents(product.requested), 0n),
      ).toBe(requested);
      expect(
        products.reduce((sum, product) => sum + cents(product.fulfilled), 0n),
      ).toBe(fulfilled);
      expect(products.reduce((sum, product) => sum + product.units, 0)).toBe(
        units,
      );
      for (const key of ["category", "size", "color"] as const)
        expect(
          groupedSales(products, key).reduce((sum, row) => sum + row.value, 0),
        ).toBe(units);
      expect(
        managerDemoRetail(c).series.reduce(
          (sum, row) => sum + BigInt(Math.round(row.captured * 100)),
          0n,
        ),
      ).toBe(requested);
      for (const product of products) {
        const matching = orders.filter((order) =>
          orderItemsFor(order).some((item) => item.product_id === product.id),
        );
        expect(product.orders).toBe(matching.length);
        expect(product.customers).toBe(
          new Set(matching.map((order) => order.customer_id)).size,
        );
      }
    },
  );

  it("keeps historical inventory independent of date and reconciles its sales to all orders", async () => {
    const c = context("2027-01-01", "2027-01-07");
    const [orders, products, selected] = await Promise.all([
      demoApi.read("order_history", c),
      demoApi.read("inventory_products", c),
      demoApi.read("products", c),
    ]);
    expect(selected).toEqual([]);
    expect(
      products.reduce((sum, product) => sum + cents(product.requested), 0n),
    ).toBe(orders.reduce((sum, order) => sum + cents(order.requested), 0n));
    expect(products).toEqual(
      await demoApi.read(
        "inventory_products",
        context("2026-09-24", "2026-09-30"),
      ),
    );
  });

  it("keeps filtered line values equal to the selected order without changing B2B fixtures", async () => {
    const c = context("2026-09-24", "2026-09-30");
    c.filters.channel = "google";
    const [orders, products] = await Promise.all([
      demoApi.read("orders", c),
      demoApi.read("products", c),
    ]);
    const detail = await demoApi.order(orders[0].id, c);
    expect(detail?.order.requested).toBe(orders[0].requested);
    expect(
      detail?.items.reduce((sum, item) => sum + cents(item.requested), 0n),
    ).toBe(cents(orders[0].requested));
    expect(
      products.reduce((sum, product) => sum + cents(product.requested), 0n),
    ).toBe(orders.reduce((sum, order) => sum + cents(order.requested), 0n));
    const b2b = {
      ...c,
      scope: {
        ...c.scope,
        store_id: "mx-fashion-b2b",
        operation: "B2B" as const,
      },
    };
    expect((await demoApi.read("products", b2b))[0].orders).toBe(114);
  });
});
