import { describe, it, expect, vi } from "vitest";
import { WidgetBindings, BodyBindings } from "@/dashboard/widgets";
import { MetricBindings, bindingResources } from "@/dashboard/bindings";
import {
  managerPages,
  MetricRegistry,
  WidgetRegistry,
} from "@/dashboard/registry";
import { managerMetrics, divideDecimal } from "@/dashboard/presenters";
import {
  managerDemoValues,
  managerDemoRetail,
} from "@/services/demo/manager-v2";
import { demoApi } from "@/services/demo/adapter";
import { createLiveDataApi } from "@/services/api/live";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { metadata } from "./fixtures/restoration";
import { parseIntelligence } from "@/services/api/intelligence";
import { parseCustomerContact } from "@/services/api/contact-contract";
import type { RequestContext } from "@/types/domain";
const context: RequestContext = {
  session: sessionFor("up-admin"),
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2c", operation: "B2C" },
  filters: { ...defaultFilters, from: "2026-09-01", to: "2026-09-30" },
};
describe("#19.3D exact bindings and demo isolation", () => {
  it("resolves every metric, widget and unique visible slot with explicit provenance", () => {
    expect(Object.keys(MetricBindings).sort()).toEqual(
      Object.keys(MetricRegistry).sort(),
    );
    for (const p of managerPages) {
      expect(new Set(p.metricIds).size).toBe(p.metricIds.length);
      for (const id of p.metricIds) {
        const b = MetricBindings[id];
        expect(b).toBeDefined();
        expect(b.reason).not.toMatch(/OR_CERTIFIED_READ_FIELD/);
        expect(Boolean(b.resource)).toBe(Boolean(b.path));
      }
      if (p.body) expect(BodyBindings[p.body]).toBeDefined();
      for (const w of p.widgets) {
        expect(WidgetRegistry[w]).toBeDefined();
        expect(WidgetBindings[w]).toBeDefined();
        for (const id of WidgetBindings[w].metricIds)
          expect(MetricBindings[id]).toBeDefined();
      }
    }
  });
  it("preserves Meta NUMERIC projection without integer rounding", () => {
    const performance = {
      meta_spend: "1.01",
      influenced_orders: 0,
      influenced_customers: 0,
      requested_revenue_influenced: "0",
      fulfilled_revenue_influenced: "0",
      roas_requested: null,
      roas_fulfilled: null,
      new_customers_influenced: null,
      cac_new_customer: null,
      landing_page_views: "1.500000000",
      link_clicks: 2,
      reach_campaign_day_sum: 3,
      action_types: [],
      action_types_complete: false,
    };
    const result = parseIntelligence("performance", performance);
    expect(result.landing_page_views).toBe("1.500000000");
    expect(result.action_types_complete).toBe(false);
    expect(() =>
      parseIntelligence("performance", {
        ...performance,
        landing_page_views: 1.5,
      }),
    ).toThrow();
  });
  it("selects resources per semantic metric instead of borrowing page overview", () => {
    expect(
      bindingResources(["meta_spend", "registrations", "repurchasers"]),
    ).toEqual(["performance", "acquisition", "retention"]);
    expect(
      managerMetrics(
        ["registrations", "approval_rate"],
        "acquisition",
        { leads_generated: 2, lead_qualification_rate: "150" },
        metadata,
      ).map((m) => m.value),
    ).toEqual(["2", "150"]);
    expect(
      managerMetrics(
        ["registrations"],
        "overview",
        { leads_generated: 2 },
        metadata,
      )[0].value,
    ).toBeNull();
  });
  it("preserves decimal text, zero, unknown and history limitations", () => {
    expect(divideDecimal("9007199254740993.0100", "2")).toBe(
      "4503599627370496.505000000000",
    );
    expect(divideDecimal("0", "2")).toBe("0.000000000000");
    expect(divideDecimal("2", "0")).toBeNull();
    const values = managerMetrics(
      ["meta_spend", "cpc", "google_spend", "cac"],
      "performance",
      {
        meta_spend: "9007199254740993.0100",
        cpc: "0.0000",
        google_spend: "50",
        cac_new_customer: "4",
      },
      metadata,
    );
    expect(values.map((v) => v.value)).toEqual([
      "9007199254740993.0100",
      "0.0000",
      null,
      null,
    ]);
    expect(
      managerMetrics(
        ["registrations", "approved_conversion"],
        "acquisition",
        { leads_generated: 0, approved_conversion_rate: null },
        metadata,
      ).map((v) => v.value),
    ).toEqual(["0", null]);
    expect(
      managerMetrics(
        ["recurring_fulfilled_observed", "revenue_paid"],
        "retention",
        { recurring_fulfilled_observed: "75.50", revenue_paid: "75.50" },
        metadata,
      ).map((v) => v.value),
    ).toEqual(["75.50", null]);
  });
  it("populates deterministic B2C metrics coherent with order fixtures", async () => {
    const values = managerDemoValues(context);
    expect(managerDemoValues(context)).toEqual(values);
    for (const p of managerPages.filter((p) => p.path.startsWith("/b2c")))
      for (const id of p.metricIds) expect(values[id], id).not.toBeNull();
    const orders = await demoApi.read("orders", context);
    expect(Number(values.orders_generated)).toBe(orders.length);
    expect(Number(values.revenue_captured)).toBe(
      orders.reduce((s, r) => s + Number(r.requested), 0),
    );
    expect(
      Number(values.meta_spend) +
        Number(values.google_spend) +
        Number(values.tiktok_spend),
    ).toBe(Number(values.total_media_spend));
    const retail = managerDemoRetail(context);
    expect(retail.paidRate).toBe(
      (orders.filter((o) => o.status !== "CANCELED").length / orders.length) *
        100,
    );
    expect(retail.series.reduce((s, r) => s + r.approved, 0)).toBe(
      Number(values.revenue_approved),
    );
    const smaller = managerDemoValues({
      ...context,
      filters: { ...context.filters, from: "2026-09-20", to: "2026-09-25" },
    });
    expect(Number(smaller.sessions)).toBeLessThan(Number(values.sessions));
  });
  it("never supplies demo values to live B2C or calls the real API", async () => {
    const fetcher = vi.fn();
    const api = createLiveDataApi(metadata, fetcher);
    await expect(api.read("retail", context)).rejects.toMatchObject({
      status: 424,
    });
    expect(fetcher).not.toHaveBeenCalled();
    expect(
      managerDemoValues({
        ...context,
        scope: { ...context.scope, operation: "B2B" },
      }),
    ).toEqual({});
  });
  it("validates snapshot provenance and contact-only projection", () => {
    const c = {
      basis: "order_snapshot",
      observed_at: null,
      cpf: null,
      cnpj: null,
      email: null,
      phone: null,
      state: "SP",
      city: "Cidade Sintética",
    };
    expect(parseCustomerContact(c)).toEqual(c);
    expect(() =>
      parseCustomerContact({ ...c, payload: { contact: "forbidden" } }),
    ).toThrow();
    expect(() => parseCustomerContact({ ...c, basis: "inferred" })).toThrow();
  });
});
