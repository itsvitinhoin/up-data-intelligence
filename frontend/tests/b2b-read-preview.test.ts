import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { handleReadBridge } from "@/services/api/read-bridge.server";
import { createServerDashboardReadApi } from "@/services/api/server";
import { decodeReadEnvelope, type ReadResource } from "@/services/api/http";
import { readDashboard, dashboardReadKey } from "@/hooks/use-dashboard-read";
import { dashboardSourceLabel, activePageState } from "@/lib/dashboard-source";
import { ticket } from "@/services/api/overview-presenter";
import { money } from "@/lib/format";
import { defaultFilters } from "@/config/tenants";
import { sessionFor } from "@/services/api";
const metadata = {
  contract_version: "1.0.0",
  store_id: "mx-fashion",
  generation: 7,
  policy_hash: "b".repeat(64),
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-09-28T03:00:00Z",
  report_from: "2026-09-01",
  report_to: "2026-09-28",
  history_complete: false,
  facts_complete: true,
  limitations: ["history_incomplete"],
};
const customer = {
  store_id: "mx-fashion",
  customer_id: "synthetic-c",
  customer_type: "B2B",
  name: "Cliente sintético",
  state: null,
  city: null,
  purchases_observed: 1,
  first_purchase_at_observed: "2026-09-01T12:00:00Z",
  requested_lifetime_observed: "50.01",
  ltv_complete: null,
};
const order = {
  store_id: "mx-fashion",
  customer_id: "synthetic-c",
  order_id: "synthetic-o",
  created_at: "2026-09-01T12:00:00Z",
  order_status: "CANCELED",
  payment_status: "unpaid",
  requested_total: "50.01",
  fulfilled_total: null,
  requested_items_qty: 2,
  fulfilled_items_qty: null,
};
const acquisition = {
  buyers_observed: 1,
  first_purchase_customers_observed: 1,
  first_purchase_orders_observed: 1,
  requested_first_purchase_observed: "50.01",
  fulfilled_first_purchase_observed: null,
  confirmed_new_customers: null,
};
const pagination = { page_size: 25, cursor: null, has_more: false };
const envelope = (data: unknown, paged = false) => ({
  data,
  metadata,
  pagination: paged ? pagination : null,
});
const scope = {
  tenant_id: "demo-up",
  store_id: "mx-fashion-b2b",
  operation: "B2B" as const,
};
const context = {
  scope,
  session: sessionFor("up-admin"),
  filters: defaultFilters,
};
const request = (resource: string, extra = "") =>
  new Request(
    `http://127.0.0.1:3100/api/dashboard/${resource}?tenant_id=demo-up&workspace_operation_id=mx-fashion-b2b&operation=B2B${extra}`,
  );
const preview = () => "read-api-preview" as const;
describe("B2B Analytics V1 preview", () => {
  it("disables automatic dev request logs for the private real preview", () => {
    const config = readFileSync("next.config.ts", "utf8");
    expect(config).toContain(
      'process.env.DASHBOARD_DATA_MODE === "read-api-preview"',
    );
    expect(config).toMatch(/\? false\s*:\s*undefined/);
  });
  it.each([
    "orders",
    "acquisition",
    "customers",
    "customer",
    "customerOrders",
    "retention",
    "products",
    "funnel",
    "geography",
  ] as ReadResource[])("binds %s on the server only", async (resource) => {
    const call = vi.fn().mockResolvedValue(envelope(resource));
    const readApi = (() => ({
      [resource]: call,
    })) as unknown as typeof createServerDashboardReadApi;
    const response = await handleReadBridge(
      request(resource),
      resource,
      "synthetic-c",
      { mode: preview, readApi },
    );
    expect(response.status).toBe(200);
    expect(call.mock.calls[0][0].store_id).toBe("mx-fashion");
    expect(response.headers.get("Cache-Control")).toContain("no-store");
  });
  it.each([
    "&store_id=other",
    "&data_store_id=other",
    "&url=http://external",
    "&page_size=101",
    "&status=bad",
    "&cursor=",
    "&from=2026-09-01",
  ])("rejects unsafe order filters %s", async (extra) => {
    const upstream = vi.fn();
    expect(
      (
        await handleReadBridge(request("orders", extra), "orders", undefined, {
          mode: preview,
          readApi: upstream,
        })
      ).status,
    ).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });
  it("converts dates once, forwards opaque pagination and status, disallows history period", async () => {
    const call = vi.fn().mockResolvedValue(envelope([order], true));
    const readApi = (() => ({
      orders: call,
    })) as unknown as typeof createServerDashboardReadApi;
    expect(
      (
        await handleReadBridge(
          request(
            "orders",
            "&from=2026-09-01&to=2026-09-27&page_size=25&cursor=opaque&status=CANCELED",
          ),
          "orders",
          undefined,
          { mode: preview, readApi },
        )
      ).status,
    ).toBe(200);
    expect(call.mock.calls[0][1]).toMatchObject({
      from: "2026-09-01",
      to: "2026-09-28",
      pageSize: 25,
      cursor: "opaque",
      status: "CANCELED",
    });
    expect(
      (
        await handleReadBridge(
          request("customers/synthetic-c", "&from=2026-09-01&to=2026-09-27"),
          "customer",
          "synthetic-c",
          { mode: preview, readApi },
        )
      ).status,
    ).toBe(400);
  });
  it("preserves NULL, money strings, canceled orders and rejects cross-customer records", () => {
    const parsed = decodeReadEnvelope("orders", envelope([order], true));
    expect(parsed.data[0]).toMatchObject({
      requested_total: "50.01",
      fulfilled_total: null,
      order_status: "CANCELED",
    });
    expect(
      decodeReadEnvelope(
        "orders",
        envelope([{ ...order, customer_id: null }], true),
      ).data[0].customer_id,
    ).toBeNull();
    expect(() =>
      decodeReadEnvelope(
        "customerOrders",
        envelope([order], true),
        "foreign-c",
      ),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope(
        "customers",
        envelope([{ ...customer, store_id: "foreign" }], true),
      ),
    ).toThrow();
    expect(() => decodeReadEnvelope("orders", envelope([order]))).toThrow();
  });
  it("never certifies new customers or LTV under partial history", () => {
    expect(
      decodeReadEnvelope("acquisition", envelope(acquisition)).data
        .confirmed_new_customers,
    ).toBeNull();
    expect(() =>
      decodeReadEnvelope(
        "acquisition",
        envelope({ ...acquisition, confirmed_new_customers: 0 }),
      ),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope(
        "customers",
        envelope([{ ...customer, ltv_complete: "50.01" }], true),
      ),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope(
        "customer",
        envelope({
          profile: customer,
          commercial: {
            qualifying_orders_observed: 1,
            requested_revenue_observed: "50.01",
            fulfilled_revenue_observed: null,
            first_purchase_at_observed: null,
            last_purchase_at_observed: null,
            ltv_complete: "50.01",
          },
        }),
        "synthetic-c",
      ),
    ).toThrow();
  });
  it("does not turn immature cohort into zero", () => {
    const retention = {
      buyers_observed: 1,
      recurring_buyers_observed: 0,
      retention_observed: "0",
      retention_ticket_observed: null,
      frequency_observed: "1",
      progression: [],
      cohorts: [
        {
          cohort_month: "2026-09-01",
          reporting_month: "2026-09-01",
          month: 0,
          buyers_observed: 1,
          rate: null,
          observed_rate: null,
          period_complete: false,
        },
      ],
    };
    expect(
      decodeReadEnvelope("retention", envelope(retention)).data.cohorts[0].rate,
    ).toBeNull();
    expect(() =>
      decodeReadEnvelope(
        "retention",
        envelope({
          ...retention,
          cohorts: [{ ...retention.cohorts[0], observed_rate: "0" }],
        }),
      ),
    ).toThrow();
  });
  it("uses exact decimal ticket and formatting even above JS integer precision", () => {
    expect(ticket("100", 3)).toBe("33.33");
    expect(ticket("100.005", 1)).toBe("100.01");
    expect(ticket(null, 3)).toBeNull();
    expect(ticket("0", 1)).toBe("0.00");
    expect(money("9007199254740993.25", 2)).toContain(
      "9.007.199.254.740.993,25",
    );
  });
  it("fails closed on generation changes and real errors, does not pass store or backend token", async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(Response.json(envelope([order], true))),
      );
    await readDashboard(
      "orders",
      context,
      7,
      { status: "CANCELED", cursor: "opaque" },
      fetcher,
    );
    const url = new URL(fetcher.mock.calls[0][0], "http://localhost");
    expect(url.pathname).toBe("/api/dashboard/orders");
    expect(url.searchParams.has("store_id")).toBe(false);
    expect(url.searchParams.get("cursor")).toBe("opaque");
    await expect(
      readDashboard("orders", context, 8, {}, fetcher),
    ).rejects.toMatchObject({ status: 409 });
    const failed = vi
      .fn()
      .mockResolvedValue(
        Response.json({ error: { code: "unavailable" } }, { status: 503 }),
      );
    await expect(
      readDashboard("orders", context, 7, {}, failed),
    ).rejects.toMatchObject({ status: 503 });
  });
  it("separates cache and source by resource, period, generation, scope and page", () => {
    const key = dashboardReadKey(
      "read-api-preview",
      "customers",
      context,
      7,
      {},
    );
    expect(key).not.toEqual(
      dashboardReadKey("demo", "customers", context, 7, {}),
    );
    expect(key).not.toEqual(
      dashboardReadKey("read-api-preview", "orders", context, 7, {}),
    );
    expect(key).not.toEqual(
      dashboardReadKey("read-api-preview", "customers", context, 8, {}),
    );
    expect(key).not.toEqual(
      dashboardReadKey(
        "read-api-preview",
        "customers",
        { ...context, filters: { ...defaultFilters, from: "2026-09-02" } },
        7,
        {},
      ),
    );
    const state = {
      path: "/b2b/retention",
      scopeKey: "demo-up/mx-fashion-b2b/B2B",
      source: "partial-real" as const,
      metadata,
    };
    expect(
      dashboardSourceLabel(state.path, "read-api-preview", scope, state),
    ).toContain("Histórico parcial");
    expect(
      activePageState("/b2b/products", "read-api-preview", scope, state),
    ).toBeNull();
    expect(
      dashboardSourceLabel("/b2b/performance", "read-api-preview", scope, {
        ...state,
        path: "/b2b/performance",
        source: "unavailable-real",
      }),
    ).toBe("Cobertura ainda não disponível");
  });
  it("retains demo default, no credentials in client modules, no fixture real performance", () => {
    expect(readFileSync("src/services/api/index.ts", "utf8")).toContain(
      "export const api = demoApi",
    );
    for (const path of [
      "src/hooks/use-dashboard-read.tsx",
      "src/services/api/live.ts",
    ])
      expect(readFileSync(path, "utf8")).not.toMatch(
        /DASHBOARD_DEV_PREVIEW_TOKEN|google.auth|NEXT_PUBLIC.*TOKEN|localStorage/,
      );
    const boundary = readFileSync("src/hooks/use-dashboard-read.tsx", "utf8");
    expect(boundary).not.toContain("real(metadata)");
    const adapter = readFileSync("src/services/api/live.ts", "utf8");
    expect(adapter).not.toMatch(/services\/demo|demoApi/);
    expect(readFileSync("src/features/commerce.tsx", "utf8")).toContain(
      "<ProductDrawer",
    );
  });
});
