import { describe, expect, it } from "vitest";
import {
  managerPage,
  managerPages,
  MetricRegistry,
  DashboardTemplateRegistry,
  pageWidgetIds,
  WidgetRegistry,
} from "@/dashboard/registry";
import {
  validatedPagePreference,
  preferenceKey,
} from "@/dashboard/preferences";
import { managerMetrics } from "@/dashboard/presenters";
import { parseCustomerContact } from "@/services/api/contact-contract";
import { metadata as overviewMetadata } from "./fixtures/restoration";

describe("controlled manager templates", () => {
  it("keeps V1 and distinct B2B/B2C versions without formula/SQL execution", () => {
    expect(Object.keys(DashboardTemplateRegistry)).toEqual([
      "current-standard.v1",
      "b2b-standard.v2",
      "b2c-standard.v2",
    ]);
    expect(new Set(managerPages.map((page) => page.path)).size).toBe(
      managerPages.length,
    );
    for (const page of managerPages) {
      for (const id of page.metricIds) expect(MetricRegistry[id]).toBeDefined();
      for (const id of page.widgets) expect(WidgetRegistry[id]).toBeDefined();
    }
    expect(JSON.stringify(managerPages)).not.toMatch(/SELECT |INSERT |eval\(/);
  });
  it("keeps compatibility and ERP/WhatsApp slots", () => {
    expect(managerPage("/b2b/acquisition")?.path).toBe(
      "/b2b/performance/new-customers",
    );
    expect(managerPages.filter((page) => page.group === "ERP")).toHaveLength(7);
    expect(
      managerPages.filter((page) => page.group === "WhatsApp"),
    ).toHaveLength(3);
    expect(managerPage("/b2c/revenue")?.path).toBe("/b2c/orders");
  });
  it("requires exact semantic slots: fulfilled is never paid, observed never definitive", () => {
    const ids = managerPage("/b2b")!.metricIds;
    const cards = managerMetrics(
      ids,
      "overview",
      {
        fulfilled_revenue: "999.00",
        new_customers_confirmed: 5,
        recurring_buyers_observed: 3,
      },
      overviewMetadata,
    );
    expect(
      cards.find((card) => card.label === "Faturamento pago Ecommerce")?.value,
    ).toBeNull();
    expect(
      cards.find((card) => card.label === "Novos clientes adquiridos")?.value,
    ).toBeNull();
    expect(
      cards.find((card) => card.label === "Clientes que recompraram")?.value,
    ).toBe("3");
    expect(
      managerMetrics(
        ["meta_spend", "total_media_spend", "roas_paid"],
        "performance",
        {
          meta_spend: "12.3400",
          observed_meta_spend: "500",
          roas_fulfilled: "4",
        },
        overviewMetadata,
      ).map((card) => card.value),
    ).toEqual(["12.3400", null, null]);
  });
  it("isolates preferences and removes unregistered widgets/sizes", () => {
    const a = preferenceKey("user-a", "tenant", "workspace", "b2b-standard.v2");
    for (const b of [
      preferenceKey("user-b", "tenant", "workspace", "b2b-standard.v2"),
      preferenceKey("user-a", "other", "workspace", "b2b-standard.v2"),
      preferenceKey("user-a", "tenant", "other", "b2b-standard.v2"),
      preferenceKey("user-a", "tenant", "workspace", "current-standard.v1"),
    ])
      expect(a).not.toBe(b);
    const pref = validatedPagePreference("/b2b", {
      order: ["evil", "metrics", "metrics"],
      hidden: ["evil"],
      sizes: { evil: "half", metrics: "half" },
    });
    expect(pref.order).toEqual(pageWidgetIds(managerPage("/b2b")!));
    expect(pref.hidden).toEqual([]);
    expect(pref.sizes).toEqual({ metrics: "half" });
  });
  it("rejects contact payload extras and preserves unknown contact fields", () => {
    const contact = {
      basis: "current_core_profile",
      observed_at: null,
      cpf: null,
      cnpj: null,
      email: "synthetic@example.invalid",
      phone: null,
    };
    expect(parseCustomerContact(contact)).toEqual(contact);
    expect(() =>
      parseCustomerContact({ ...contact, secret: "forbidden" }),
    ).toThrow();
    expect(() =>
      parseCustomerContact({ ...contact, email: { raw: "forbidden" } }),
    ).toThrow();
    expect(() =>
      parseCustomerContact({ ...contact, phone: undefined }),
    ).toThrow();
  });
});
// Only aggregate requests are eligible; no contact/customer/order list prefetch.
import { aggregatePrefetchAllowed } from "@/dashboard/prefetch";
it("does not prefetch PII or unsupported sources", () => {
  for (const path of [
    "/customers/x",
    "/b2b/ecommerce/customers",
    "/b2b/ecommerce/orders",
    "/b2b/erp/overview",
    "/b2b/whatsapp/analysis",
    "/b2c",
  ])
    expect(aggregatePrefetchAllowed(path)).toBe(false);
  expect(aggregatePrefetchAllowed("/b2b/performance/new-customers")).toBe(true);
});

import { managerNavigation } from "@/dashboard/navigation";
it("has deterministic root paths for every B2B/B2C menu", () => {
  for (const op of ["B2B", "B2C"] as const) {
    const nav = managerNavigation(op);
    expect(new Set(nav.map((item) => item.href)).size).toBe(nav.length);
    expect(nav[0].href).toBe(`/${op.toLowerCase()}`);
    expect(
      nav.every((item) => item.href.startsWith(`/${op.toLowerCase()}`)),
    ).toBe(true);
  }
});
