import { describe, expect, it } from "vitest";
import { retailCustomerMetrics } from "@/lib/retail-customer-metrics";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import type { Order, RequestContext } from "@/types/domain";

const order = (id: string, date: string, status = "CONFIRMED"): Order => ({
  id,
  customer_id: "synthetic-customer",
  date,
  requested: "100.00",
  fulfilled: "80.00",
  requestedQuantity: 2,
  fulfilledQuantity: 2,
  status,
  paid: false,
});

describe("B2C customer detail", () => {
  it("shows exactly four commercial metrics without treating captured revenue as LTV", () => {
    const metrics = retailCustomerMetrics([
      order("1", "2026-09-01"),
      order("2", "2026-09-03"),
      order("2", "2026-09-03"),
      order("3", "2026-09-05", "CANCELED"),
    ]);
    expect(metrics.map((item) => item.label)).toEqual([
      "Pedidos",
      "Receita",
      "Frequência de Compra",
      "LTV",
    ]);
    expect(metrics.map((item) => item.value)).toEqual([
      "2",
      "200.00",
      "2",
      null,
    ]);
    expect(
      retailCustomerMetrics([order("1", "2026-09-01")])[2].value,
    ).toBeNull();
  });

  it("keeps the B2C customer history scoped to the operation and independent of the top period", async () => {
    const context: RequestContext = {
      scope: {
        tenant_id: "demo-up",
        store_id: "mx-fashion-b2c",
        operation: "B2C",
      },
      session: sessionFor("maria-demo"),
      filters: {
        ...defaultFilters,
        from: "2027-01-01",
        to: "2027-01-07",
      },
    };
    const detail = await demoApi.customer("c1", context);
    expect(detail.orders.length).toBeGreaterThan(1);
    expect(detail.orders.every((item) => item.customer_id === "c1")).toBe(true);
    expect(detail.timeline).toEqual([]);
    expect(detail.campaigns).toEqual([]);
    expect(detail.history_complete).toBe(false);
  });
});
