import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { readOverview, overviewQueryKey } from "@/hooks/use-overview-data";
import { overviewScopeKey } from "@/features/providers";
import {
  getDashboardDataMode,
  createServerDashboardReadApi,
} from "@/services/api/server";
import { handleOverviewBridge } from "@/services/api/overview-bridge.server";
import { resolveDevOverviewBinding } from "@/services/api/preview-binding.server";
import { decodeOverviewEnvelope } from "@/services/api/http";
import { presentLiveOverview, ticket } from "@/services/api/overview-presenter";
import { overviewSourceLabel } from "@/lib/overview-source";
import {
  inclusiveToExclusive,
  exclusiveToInclusive,
  presetRange,
} from "@/lib/period";
import type { RequestContext } from "@/types/domain";

const live = {
  data: {
    requested_revenue: "86319.62",
    fulfilled_revenue: "73220.13",
    fulfillment_gap: "13099.49",
    fulfillment_rate: "0.8482443504732759481563982789",
    cancelled_requested_revenue: "6262.75",
    orders_requested: 18,
    orders_cancelled: 2,
    buyers_observed: 16,
    recurring_buyers_observed: 0,
    purchase_frequency_observed: "1",
    new_customers_confirmed: null,
    ltv_complete: null,
    cac: null,
    revenue_paid: null,
    series: [
      {
        date: "2026-09-01",
        requested: "100.25",
        fulfilled: null,
        orders: 1,
        new_customers_confirmed: null,
      },
      {
        date: "2026-09-02",
        requested: null,
        fulfilled: "75.50",
        orders: 1,
        new_customers_confirmed: null,
      },
    ],
  },
  pagination: null,
  metadata: {
    contract_version: "1.0.0",
    store_id: "mx-fashion",
    generation: 1,
    policy_hash: "a".repeat(64),
    currency: "BRL",
    reporting_timezone: "America/Sao_Paulo",
    as_of: "2026-09-28T03:00:00Z",
    report_from: "2026-09-01",
    report_to: "2026-09-28",
    history_complete: false,
    facts_complete: true,
    limitations: [
      "history_incomplete",
      "leads_not_in_analytics_v1",
      "paid_media_not_materialized",
    ],
  },
};
function context(
  store = "mx-fashion-b2b",
  operation: "B2B" | "B2C" = "B2B",
): RequestContext {
  return {
    session: sessionFor("up-admin"),
    scope: { tenant_id: "demo-up", store_id: store, operation },
    filters: { ...defaultFilters },
  };
}
function url(store = "mx-fashion-b2b", extra = "") {
  return new Request(
    `http://127.0.0.1:3100/api/dashboard/overview?tenant_id=demo-up&workspace_operation_id=${store}&operation=B2B${extra}`,
  );
}
const preview = () => "read-api-preview" as const;
const readApi = vi.fn(() => ({
  overview: vi.fn().mockResolvedValue(live),
})) as unknown as typeof createServerDashboardReadApi;
afterEach(() => vi.unstubAllEnvs());

describe("controlled B2B Overview preview", () => {
  it("keeps the global demo composition and private mode default", () => {
    expect(readFileSync("src/services/api/index.ts", "utf8")).toContain(
      "export const api = demoApi",
    );
    expect(getDashboardDataMode()).toBe("demo");
    expect(readFileSync("src/services/api/server.ts", "utf8")).not.toContain(
      "NEXT_PUBLIC",
    );
    expect(
      readFileSync("src/hooks/use-overview-data.ts", "utf8"),
    ).not.toContain("DASHBOARD_DEV_PREVIEW_TOKEN");
  });
  it("keeps the ephemeral token on the server side and rejects public backend URLs", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("DASHBOARD_DATA_MODE", "read-api-preview");
    vi.stubEnv("DASHBOARD_DEV_PREVIEW_TOKEN", "t".repeat(40));
    vi.stubEnv("DASHBOARD_READ_API_BASE_URL", "http://127.0.0.1:8765/");
    const upstream = vi.fn().mockResolvedValue(Response.json(live));
    const result = await createServerDashboardReadApi(upstream).overview({
      tenant_id: "demo-up",
      store_id: "mx-fashion",
      operation: "B2B",
    });
    expect(result.metadata.store_id).toBe("mx-fashion");
    expect(upstream.mock.calls[0][1].headers["X-Dashboard-Preview-Token"]).toBe(
      "t".repeat(40),
    );
    expect(upstream.mock.calls[0][1].credentials).toBe("omit");
    expect(JSON.stringify(result)).not.toContain(
      "synthetic-ephemeral-preview-token",
    );
    vi.stubEnv("DASHBOARD_READ_API_BASE_URL", "http://0.0.0.0:8765/");
    expect(() => createServerDashboardReadApi(upstream)).toThrow("loopback");
  });
  it("uses demo in demo mode and for B2C or an unbound brand", async () => {
    const unused = vi.fn();
    expect((await readOverview("demo", context(), unused)).source).toBe("demo");
    expect(
      (
        await readOverview(
          "read-api-preview",
          context("mx-fashion-b2c", "B2C"),
          unused,
        )
      ).source,
    ).toBe("demo");
    const absent = vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { code: "preview_binding_absent" } },
          { status: 404 },
        ),
      );
    expect(
      (await readOverview("read-api-preview", context("lume-b2b"), absent))
        .source,
    ).toBe("demo");
  });
  it("uses the same-origin bridge, omits initial dates and does not send the canonical store", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(live));
    const result = await readOverview("read-api-preview", context(), fetcher);
    expect(result.source).toBe("real");
    const requestUrl = new URL(fetcher.mock.calls[0][0], "http://localhost");
    expect(requestUrl.pathname).toBe("/api/dashboard/overview");
    expect(requestUrl.searchParams.get("workspace_operation_id")).toBe(
      "mx-fashion-b2b",
    );
    expect(requestUrl.searchParams.has("store_id")).toBe(false);
    expect(requestUrl.searchParams.has("data_store_id")).toBe(false);
    expect(requestUrl.searchParams.has("from")).toBe(false);
    expect(requestUrl.searchParams.has("to")).toBe(false);
    expect(fetcher.mock.calls[0][1].cache).toBe("no-store");
  });
  it("never falls back to fixtures when a bound real read fails", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { code: "read_temporarily_unavailable" } },
          { status: 503 },
        ),
      );
    await expect(
      readOverview("read-api-preview", context(), fetcher),
    ).rejects.toMatchObject({ status: 503 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("resolves the DEV binding on the server and rejects arbitrary stores, methods and operations", async () => {
    expect(
      resolveDevOverviewBinding({
        tenant_id: "demo-up",
        workspace_operation_id: "mx-fashion-b2b",
        operation: "B2B",
      })?.data_store_id,
    ).toBe("mx-fashion");
    expect(
      resolveDevOverviewBinding({
        tenant_id: "demo-up",
        workspace_operation_id: "lume-b2b",
        operation: "B2B",
      }),
    ).toBeNull();
    const allowed = await handleOverviewBridge(url(), {
      mode: preview,
      readApi,
    });
    expect(allowed.status).toBe(200);
    expect(JSON.stringify(await allowed.json())).not.toMatch(
      /preview.token|credential/i,
    );
    expect((readApi as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
    expect(
      (readApi as ReturnType<typeof vi.fn>).mock.results[0].value.overview.mock
        .calls[0][0].store_id,
    ).toBe("mx-fashion");
    expect(
      (await handleOverviewBridge(url("lume-b2b"), { mode: preview, readApi }))
        .status,
    ).toBe(404);
    expect(
      (
        await handleOverviewBridge(
          url("mx-fashion-b2b", "&data_store_id=other"),
          { mode: preview, readApi },
        )
      ).status,
    ).toBe(400);
    expect(
      (
        await handleOverviewBridge(new Request(url().url, { method: "POST" }), {
          mode: preview,
          readApi,
        })
      ).status,
    ).toBe(405);
    expect(
      (
        await handleOverviewBridge(
          new Request(url().url, {
            headers: { origin: "https://other.example" },
          }),
          { mode: preview, readApi },
        )
      ).status,
    ).toBe(403);
    expect(
      (await handleOverviewBridge(url(), { mode: () => "demo", readApi }))
        .status,
    ).toBe(404);
  });
  it("converts inclusive UI dates to exclusive API dates and rejects invalid periods", async () => {
    const upstream = vi.fn().mockResolvedValue(live);
    const injected = vi.fn(() => ({
      overview: upstream,
    })) as unknown as typeof createServerDashboardReadApi;
    const response = await handleOverviewBridge(
      url("mx-fashion-b2b", "&from=2026-09-01&to=2026-09-27"),
      { mode: preview, readApi: injected },
    );
    expect(response.status).toBe(200);
    expect(upstream.mock.calls[0][1]).toMatchObject({
      from: "2026-09-01",
      to: "2026-09-28",
    });
    expect(inclusiveToExclusive("2026-09-27")).toBe("2026-09-28");
    expect(exclusiveToInclusive("2026-09-28")).toBe("2026-09-27");
    expect(presetRange("7", "2026-09-27")).toEqual({
      from: "2026-09-21",
      to: "2026-09-27",
    });
    expect(
      (
        await handleOverviewBridge(
          url("mx-fashion-b2b", "&from=2026-09-30&to=2026-09-01"),
          { mode: preview, readApi: injected },
        )
      ).status,
    ).toBe(400);
  });
  it("keeps observed values, genuine zero and unknown fields distinct", () => {
    const p = presentLiveOverview(decodeOverviewEnvelope(live));
    const values = (items: typeof p.data.revenue) =>
      Object.fromEntries(items.map(({ label, value }) => [label, value]));
    expect(values(p.data.revenue)).toMatchObject({
      "Faturamento Solicitado": "86319.62",
      "Faturamento Atendido": "73220.13",
      "% de Atendimento": "84.82443504732759481563982789",
      "Gap de Atendimento": "13099.49",
      "Receita Cancelada": "6262.75",
      "Crescimento Receita": null,
    });
    expect(values(p.data.orders)).toMatchObject({
      "Pedidos Solicitados": "18",
      "Pedidos Cancelados": "2",
      "Pedidos Pagos": null,
      "Ticket Médio Solicitado": "4795.53",
      "Ticket Médio Atendido": "4067.79",
    });
    expect(values(p.data.customers)).toMatchObject({
      "Clientes Compradores": "16",
      Novos: null,
      Recorrentes: "0",
      "% de Retenção": "0.00",
    });
    expect(values(p.data.relationship)).toMatchObject({
      Frequência: "1",
      "LTV Geral": null,
    });
    expect(p.data.series).toHaveLength(2);
    expect(p.data.series[0].fulfilled).toBeNull();
    expect(p.data.series[1].requested).toBeNull();
    expect(JSON.stringify(p)).not.toMatch(
      /LeadCards|mediaRevenue":\d|attributedOrders/,
    );
    expect(p.metadata.history_complete).toBe(false);
  });
  it("never converts an unknown denominator into zero and separates query keys", () => {
    expect(ticket("50.00", 0)).toBeNull();
    expect(ticket(null, 2)).toBeNull();
    expect(overviewQueryKey("demo", context())).not.toEqual(
      overviewQueryKey("read-api-preview", context()),
    );
    expect(overviewQueryKey("read-api-preview", context())).not.toEqual(
      overviewQueryKey("read-api-preview", context("lume-b2b")),
    );
    expect(overviewScopeKey(context().scope)).toBe(
      "demo-up/mx-fashion-b2b/B2B",
    );
  });
  it("labels only a successfully connected B2B Overview as real", () => {
    const mx = context().scope;
    const real = {
      scopeKey: overviewScopeKey(mx),
      source: "real" as const,
      metadata: live.metadata,
    };
    expect(overviewSourceLabel("/b2b", "read-api-preview", mx, real)).toBe(
      "Dados reais · Analytics V1",
    );
    expect(
      overviewSourceLabel("/b2b/products", "read-api-preview", mx, real),
    ).toBe("Dados demonstrativos");
    expect(overviewSourceLabel("/b2b", "demo", mx, real)).toBe(
      "Dados demonstrativos",
    );
    expect(
      overviewSourceLabel(
        "/b2b",
        "read-api-preview",
        context("lume-b2b").scope,
        real,
      ),
    ).toBe("Conectando dados reais");
    expect(
      overviewSourceLabel("/b2b", "read-api-preview", mx, {
        ...real,
        source: "error",
      }),
    ).toBe("Dados reais indisponíveis");
    expect(readFileSync("src/features/b2b-overview.tsx", "utf8")).toContain(
      "preview ?",
    );
  });
});
