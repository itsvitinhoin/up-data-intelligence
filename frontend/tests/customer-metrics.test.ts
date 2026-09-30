import { describe, expect, it } from "vitest";
import { customerMetrics } from "@/services/demo/customer-metrics";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { metric } from "@/lib/format";
import type { Order, RequestContext } from "@/types/domain";
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
  requested: "120.00",
  fulfilled: "100.00",
  requestedQuantity: 12,
  fulfilledQuantity: 10,
  paid: false,
});
const rows = [
  order("1", "a", "2026-08-31"),
  order("2", "a", "2026-09-02"),
  order("3", "a", "2026-09-08"),
  order("4", "b", "2026-09-04"),
  order("5", "b", "2026-09-05", "CANCELED"),
];
describe("Overview customer relationship metrics", () => {
  it("uses qualifying purchases, deduplicates and weights every repeat interval including previous history", () => {
    const data = customerMetrics(
      [...rows, rows[1]],
      { b: "2026-09-01" },
      "2026-09-01",
      "2026-09-30",
    );
    expect(data.map((m) => m.value)).toEqual(["1.5", null, "3", "4"]);
    expect(data[1].secondary?.value).toBe("200.00");
    expect(metric(data[0].value, data[0].format)).toBe("1,5");
    expect(metric(data[3].value, data[3].format)).toBe("4 dias");
  });
  it("keeps missing and invalid durations unknown, and avoids future purchases and zero denominators", () => {
    const data = customerMetrics(
      rows,
      { b: "2026-09-05" },
      "2026-09-03",
      "2026-09-04",
    );
    expect(data.map((m) => m.value)).toEqual(["1", null, null, null]);
    expect(
      customerMetrics([], {}, "2026-09-01", "2026-09-30").every(
        (m) => m.value === null,
      ),
    ).toBe(true);
    expect(
      customerMetrics(rows, {}, "2026-10-01", "2026-10-31").map((m) => m.value),
    ).toEqual([null, null, null, null]);
  });
  it("serves all brand origins and agrees with acquisition conversion without confirming historical LTV", async () => {
    const c: RequestContext = {
      scope: {
        tenant_id: "demo-up",
        store_id: "mx-fashion-b2b",
        operation: "B2B",
      },
      session: sessionFor("maria-demo"),
      filters: { ...defaultFilters },
    };
    const overview = await demoApi.read("overview", c);
    const lifecycle = await demoApi.read("lifecycle", c);
    expect(Number(overview.b2b!.relationship[2].value)).toBe(
      lifecycle.conversion.mean,
    );
    expect(overview.b2b!.relationship[1].value).toBeNull();
    c.filters.channel = "meta";
    expect((await demoApi.read("overview", c)).b2b!.relationship).toEqual(
      overview.b2b!.relationship,
    );
  });
});
