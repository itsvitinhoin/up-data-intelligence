import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import {
  createHttpApi,
  customerCard,
  type LiveScope,
} from "@/services/api/http";
import { api } from "@/services/api";
import { demoApi } from "@/services/demo/adapter";

const scope: LiveScope = {
  tenant_id: "tenant-synthetic",
  store_id: "mx-fashion",
  operation: "B2B",
};
const metadata = {
  contract_version: "1.0.0",
  store_id: scope.store_id,
  generation: 4,
  policy_hash: "a".repeat(64),
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-09-28T03:00:00Z",
  report_from: "2026-09-01",
  report_to: "2026-09-28",
  history_complete: false,
  facts_complete: true,
  limitations: ["history_incomplete"],
};
function transport(
  data: unknown,
  meta: unknown = metadata,
  pagination: unknown = null,
) {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        data,
        pagination,
        metadata: meta,
      }),
      { status: 200 },
    ),
  );
  return { api: createHttpApi("https://api.example.test", fetcher), fetcher };
}
const customer = {
  store_id: "mx-fashion",
  customer_id: "synthetic-c1",
  customer_type: "B2B",
  name: null,
  state: null,
  city: null,
  purchases_observed: 2,
  first_purchase_at_observed: "2026-09-01T12:00:00Z",
  requested_lifetime_observed: "123.45",
  ltv_complete: null,
};
describe("Analytics V1 HTTP boundary", () => {
  it("keeps demoApi as the active UI adapter", () => {
    expect(api).toBe(demoApi);
    const source = readFileSync("src/services/api/index.ts", "utf8");
    expect(source).toContain("export const api = demoApi");
  });
  it("maps a validated envelope without converting NULL or monetary decimals", async () => {
    const { api: real, fetcher } = transport([customer], metadata, {
      page_size: 20,
      cursor: null,
      has_more: false,
    });
    const result = await real.customers(scope, { pageSize: 20 });
    expect(result.data[0].requested_lifetime_observed).toBe("123.45");
    expect(result.data[0].ltv_complete).toBeNull();
    expect(customerCard(result.data[0])).toMatchObject({
      id: "synthetic-c1",
      name: null,
      fulfilledObserved: null,
    });
    expect(result.pagination?.has_more).toBe(false);
    expect(result.metadata.generation).toBe(4);
    const [url, options] = fetcher.mock.calls[0];
    expect(url.searchParams.get("store_id")).toBe(scope.store_id);
    expect(url.searchParams.get("tenant_id")).toBe(scope.tenant_id);
    expect(options.credentials).toBe("include");
    expect(options.cache).toBe("no-store");
    expect(JSON.stringify(options)).not.toMatch(/Authorization|api.key|token/i);
  });
  it("keeps requested and fulfilled separate, and history-dependent values unknown", async () => {
    const { api: real } = transport({
      requested_revenue: "100.25",
      fulfilled_revenue: "75.50",
      fulfillment_rate: "0.7531172069825436408977556109",
      fulfillment_gap: "24.75",
      cancelled_requested_revenue: "20.00",
      orders_requested: 2,
      orders_cancelled: 1,
      buyers_observed: 1,
      recurring_buyers_observed: 1,
      purchase_frequency_observed: "2",
      new_customers_confirmed: null,
      ltv_complete: null,
      cac: null,
      revenue_paid: null,
      series: [
        {
          date: "2026-09-01",
          requested: "100.25",
          fulfilled: "75.50",
          orders: 2,
          new_customers_confirmed: null,
        },
      ],
    });
    const result = await real.overview(scope, {
      from: "2026-09-01",
      to: "2026-09-02",
    });
    expect(result.data.requested_revenue).toBe("100.25");
    expect(result.data.fulfilled_revenue).toBe("75.50");
    expect(result.data.new_customers_confirmed).toBeNull();
  });
  it("rejects a list shape without the envelope", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([customer])));
    await expect(
      createHttpApi("https://api.example.test", fetcher).customers(scope),
    ).rejects.toMatchObject({ status: 502 });
  });
  it("requires a pagination contract for every list", async () => {
    const { api: real } = transport([customer]);
    await expect(real.customers(scope)).rejects.toMatchObject({ status: 502 });
  });
  it("rejects a cross-store row, wrong generation metadata and float money", async () => {
    const wrongStore = transport(
      [{ ...customer, store_id: "another-store" }],
      metadata,
      { page_size: 20, cursor: null, has_more: false },
    );
    await expect(wrongStore.api.customers(scope)).rejects.toMatchObject({
      status: 502,
    });
    const wrongMetadata = transport(
      [customer],
      { ...metadata, store_id: "another-store" },
      { page_size: 20, cursor: null, has_more: false },
    );
    await expect(wrongMetadata.api.customers(scope)).rejects.toMatchObject({
      status: 502,
    });
    const floatMoney = transport(
      [{ ...customer, requested_lifetime_observed: 123.45 }],
      metadata,
      { page_size: 20, cursor: null, has_more: false },
    );
    await expect(floatMoney.api.customers(scope)).rejects.toMatchObject({
      status: 502,
    });
  });
  it("rejects falsely complete LTV under partial history", async () => {
    const { api: real } = transport(
      [{ ...customer, ltv_complete: "123.45" }],
      metadata,
      { page_size: 20, cursor: null, has_more: false },
    );
    await expect(real.customers(scope)).rejects.toMatchObject({ status: 502 });
  });
  it("does not fall back to demo data on HTTP errors", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 503 }));
    await expect(
      createHttpApi("https://api.example.test", fetcher).customers(scope),
    ).rejects.toMatchObject({ status: 503 });
  });
  it("keeps product_id unresolved when the Analytics model cannot resolve it", async () => {
    const { api: real } = transport(
      [
        {
          store_id: "mx-fashion",
          product_key: "synthetic-key",
          product_id: null,
          sku: null,
          name: null,
          requested_revenue: "50.00",
          fulfilled_revenue: "30.00",
          units_requested: "2",
          units_fulfilled: "1",
          orders_observed: 1,
          buyers_unique: null,
        },
      ],
      metadata,
      { page_size: 20, cursor: null, has_more: false },
    );
    const result = await real.products(scope);
    expect(result.data[0].product_id).toBeNull();
    expect(result.data[0].buyers_unique).toBeNull();
  });
  it("keeps read configuration server-only without embedded credentials", () => {
    const server = readFileSync("src/services/api/server.ts", "utf8");
    const http = readFileSync("src/services/api/http.ts", "utf8");
    expect(server).not.toMatch(
      /NEXT_PUBLIC|Authorization|api_key|client_secret/i,
    );
    expect(http).not.toMatch(/NEXT_PUBLIC|Bearer |api_key|client_secret/i);
  });
});
