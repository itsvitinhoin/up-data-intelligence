import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { decodeReadEnvelope, createHttpApi } from "@/services/api/http";
import {
  parseIntelligence,
  type IntelligenceResource,
} from "@/services/api/intelligence";
import { dashboardReadKey, readDashboard } from "@/hooks/use-dashboard-read";
import { demoApi } from "@/services/demo/adapter";
import { api } from "@/services/api";
const meta = {
  contract_version: "1.0.0",
  store_id: "synthetic",
  generation: 2,
  policy_hash: "a".repeat(64),
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-09-28T03:00:00Z",
  report_from: "2026-09-01",
  report_to: "2026-09-28",
  history_complete: false,
  facts_complete: true,
  limitations: ["history_incomplete"],
  publication_domain: "intelligence",
  analytics_generation: 7,
  publication_id: "b".repeat(64),
  meta_complete: true,
  influence_complete: false,
  customer_intelligence_complete: true,
  performance_complete: true,
};
const data = {
  meta_spend: "123456789012345.123456789",
  observed_meta_spend: "123456789012345.123456789",
  influenced_orders: 0,
  influenced_customers: 0,
  requested_revenue_influenced: "0.00",
  fulfilled_revenue_influenced: null,
  roas_requested: null,
  roas_fulfilled: null,
  new_customers_influenced: null,
  cac_new_customer: null,
};
describe("CHANGE16 typed materialized DTOs", () => {
  it("keeps null, exact decimal and distinct generations", () => {
    const r = decodeReadEnvelope("performance", {
      metadata: meta,
      data,
      pagination: null,
    });
    expect(r.data.meta_spend).toBe(data.meta_spend);
    expect(r.data.fulfilled_revenue_influenced).toBeNull();
    expect(r.metadata.analytics_generation).toBe(7);
    expect(r.metadata.generation).toBe(2);
  });
  it.each([
    "email",
    "phone",
    "cnpj",
    "cpf",
    "identity_path",
    "session_id",
    "visitor_id",
    "user_id",
    "fbclid",
    "fbc",
    "fbp",
    "gclid",
    "access_token",
    "payload",
  ])("rejects prohibited %s recursively", (key) => {
    expect(() =>
      parseIntelligence("performance", {
        ...data,
        nested: { [key]: "SYNTHETIC" },
      }),
    ).toThrow();
  });
  it("rejects numeric money and invalid publication", () => {
    expect(() =>
      decodeReadEnvelope("performance", {
        metadata: meta,
        data: { ...data, meta_spend: 5 },
        pagination: null,
      }),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope("performance", {
        metadata: { ...meta, publication_domain: undefined },
        data,
        pagination: null,
      }),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope("performance", {
        metadata: meta,
        data: { ...data, cac_new_customer: "1.00" },
        pagination: null,
      }),
    ).toThrow();
  });
  it("requires scoped campaign and pagination", () => {
    expect(() =>
      parseIntelligence(
        "campaignOrders",
        [{ campaign_id: "foreign" }],
        "approved",
      ),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope(
        "timeline",
        { metadata: meta, data: [], pagination: null },
        "customer",
      ),
    ).toThrow();
  });
  it.each([
    "timeline",
    "customerProducts",
    "campaigns",
    "campaign",
    "campaignCustomers",
    "campaignOrders",
    "influencedOrders",
    "influencedCustomers",
  ] as IntelligenceResource[])(
    "rejects a structurally empty %s row",
    (resource) => {
      expect(() => parseIntelligence(resource, [{}], "synthetic")).toThrow();
      expect(parseIntelligence(resource, [], "synthetic")).toEqual([]);
    },
  );
  it("HTTP adapter preserves demoApi", async () => {
    expect(api).toBe(demoApi);
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ metadata: meta, data, pagination: null }),
        ),
      );
    const http = createHttpApi("http://127.0.0.1:8765", fetcher);
    await http.intelligence("performance", {
      store_id: "synthetic",
      tenant_id: "synthetic",
      operation: "B2B",
    });
    expect(String(fetcher.mock.calls[0][0])).toContain("/v1/performance?");
  });
  it("no token config in the client", () => {
    expect(
      readFileSync("src/services/api/intelligence.ts", "utf8"),
    ).not.toMatch(
      /UP_META_DEV_TOKEN|process\.env|SecretManager|DASHBOARD_DEV_PREVIEW_TOKEN/,
    );
  });
  it("cache separates generations", () => {
    const context = {
      session: {
        id: "synthetic",
        name: "Synthetic",
        role: "VIEWER",
        tenant_ids: ["tenant"],
        store_ids: ["store"],
      },
      scope: { tenant_id: "tenant", store_id: "store", operation: "B2B" },
      filters: { days: 30, channel: "all", collection: "all" },
    } as Parameters<typeof dashboardReadKey>[2];
    expect(
      dashboardReadKey("read-api-preview", "timeline", context, 7, {
        customerId: "c1",
        publication_domain: "intelligence",
        intelligence_generation: 2,
      }),
    ).not.toEqual(
      dashboardReadKey("read-api-preview", "timeline", context, 7, {
        customerId: "c1",
        publication_domain: "intelligence",
        intelligence_generation: 3,
      }),
    );
  });
  it("checks analytics parent independently", async () => {
    const context = {
      session: {
        id: "synthetic",
        name: "Synthetic",
        role: "VIEWER",
        tenant_ids: ["tenant"],
        store_ids: ["store"],
      },
      scope: { tenant_id: "tenant", store_id: "store", operation: "B2B" },
      filters: { days: 30, channel: "all", collection: "all" },
    } as Parameters<typeof readDashboard>[1];
    const fetcher = () =>
      Promise.resolve(
        new Response(
          JSON.stringify({ metadata: meta, data, pagination: null }),
        ),
      );
    expect(
      (await readDashboard("performance", context, 7, {}, fetcher)).metadata
        .generation,
    ).toBe(2);
    await expect(
      readDashboard("performance", context, 8, {}, fetcher),
    ).rejects.toThrow();
  });
});
