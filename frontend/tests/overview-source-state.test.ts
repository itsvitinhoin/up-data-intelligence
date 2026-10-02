import { beforeEach, describe, expect, it, vi } from "vitest";
import { createElement, type EffectCallback } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { sessionFor } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import { useOverviewData } from "@/hooks/use-overview-data";
import { overviewScopeKey } from "@/features/providers";
import { PeriodFilter } from "@/components/period-filter";
import { PrintContext } from "@/components/exports";
import { activePageState, dashboardSourceLabel } from "@/lib/dashboard-source";
import type { DashboardPageState } from "@/lib/dashboard-source";
import { presentLiveOverview } from "@/services/api/overview-presenter";
import type { ReadMetadata } from "@/services/api/http";
import type { Scope } from "@/types/domain";

const harness = vi.hoisted(() => ({
  effects: [] as EffectCallback[],
  query: vi.fn(),
  workspace: vi.fn(),
  context: vi.fn(),
  pathname: vi.fn(),
}));
vi.mock("react", async (original) => ({
  ...(await original<typeof import("react")>()),
  // Flush effects explicitly to exercise the shared hook without a live server.
  useEffect: (effect: EffectCallback) => harness.effects.push(effect),
}));
vi.mock("@tanstack/react-query", async (original) => ({
  ...(await original<typeof import("@tanstack/react-query")>()),
  useQuery: harness.query,
}));
vi.mock("@/features/providers", async (original) => ({
  ...(await original<typeof import("@/features/providers")>()),
  useWorkspace: harness.workspace,
}));
vi.mock("@/hooks/use-resource", async (original) => ({
  ...(await original<typeof import("@/hooks/use-resource")>()),
  useRequestContext: harness.context,
}));
vi.mock("next/navigation", () => ({ usePathname: harness.pathname }));
// This suite exercises Overview's query state, not the independent installation query.
vi.mock("@/hooks/use-installation", () => ({
  useInstallation: () => ({ enabled: false, data: null }),
}));
const scope: Scope = {
  tenant_id: "demo-up",
  store_id: "mx-fashion-b2b",
  operation: "B2B",
};
const metadata: ReadMetadata = {
  contract_version: "1.0.0",
  store_id: "mx-fashion",
  generation: 7,
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
function realData(historyComplete = false) {
  return {
    source: "real" as const,
    overview: presentLiveOverview({
      data: {
        requested_revenue: "100.01",
        fulfilled_revenue: "80.00",
        fulfillment_gap: "20.01",
        fulfillment_rate: "0.79992000799920007999",
        cancelled_requested_revenue: "0",
        orders_requested: 1,
        orders_cancelled: 0,
        buyers_observed: 1,
        recurring_buyers_observed: 0,
        purchase_frequency_observed: "1",
        new_customers_confirmed: null,
        ltv_complete: null,
        cac: null,
        revenue_paid: null,
        series: [],
      },
      pagination: null,
      metadata: { ...metadata, history_complete: historyComplete },
    }),
  };
}
let state: DashboardPageState | null;
let selected: Scope;
function flushOverview(result: object) {
  harness.query.mockReturnValue(result);
  let returned!: ReturnType<typeof useOverviewData>;
  function Probe() {
    returned = useOverviewData();
    return null;
  }
  renderToStaticMarkup(createElement(Probe));
  harness.effects.splice(0).forEach((effect) => effect());
  return returned;
}
function label() {
  return dashboardSourceLabel("/b2b", "read-api-preview", selected, state);
}
beforeEach(() => {
  vi.clearAllMocks();
  harness.effects.length = 0;
  state = null;
  selected = scope;
  harness.pathname.mockReturnValue("/b2b");
  harness.context.mockImplementation(() => ({
    scope: selected,
    session: sessionFor("up-admin"),
    filters: defaultFilters,
  }));
  harness.workspace.mockImplementation(() => ({
    scope: selected,
    filters: defaultFilters,
    dataMode: "read-api-preview",
    dashboardPageState: state,
    setFilters: vi.fn(),
    setDashboardPageState: (next: DashboardPageState | null) => {
      state = next;
    },
  }));
});
describe("Overview canonical page source", () => {
  it("publishes pending as loading-real with the current path and scope", () => {
    flushOverview({ isPending: true, isError: false });
    expect(state).toEqual({
      path: "/b2b",
      scopeKey: overviewScopeKey(scope),
      source: "loading-real",
      metadata: undefined,
    });
    expect(label()).toBe("Conectando dados reais");
    const html = renderToStaticMarkup(createElement(PeriodFilter));
    expect(html).toContain("Aguardando cobertura publicada");
    expect(html).toContain('disabled=""');
  });
  it.each([
    [false, "partial-real", "Dados reais · Histórico parcial"],
    [true, "real", "Dados reais · Analytics V1"],
  ] as const)(
    "keeps rendered real data and the badge consistent for history_complete=%s",
    (complete, source, badge) => {
      const data = realData(complete);
      const result = flushOverview({
        isPending: false,
        isError: false,
        data,
      });
      expect(result.data?.source).toBe(data.source);
      if (result.data?.source !== "real") throw new Error("Expected real data");
      expect(result.data.overview.metadata).toEqual(data.overview.metadata);
      expect(result.data.overview.data.revenue[0].value).toBe(
        data.overview.data.revenue[0].value,
      );
      expect(result.data.overview.data.revenue[0].comparison?.state).toBe(
        "unavailable",
      );
      expect(result.data?.source).toBe("real");
      expect(state?.source).toBe(source);
      expect(state?.metadata).toBe(data.overview.metadata);
      expect(label()).toBe(badge);
      expect(state?.metadata?.generation).toBe(7);
      expect(state?.metadata?.policy_hash).toBe(metadata.policy_hash);
    },
  );
  it("publishes errors without labeling cached data as a successful read", () => {
    flushOverview({
      isPending: false,
      isError: true,
      data: realData(),
    });
    expect(state?.source).toBe("error-real");
    expect(label()).toBe("Dados reais indisponíveis");
  });
  it("publishes explicit demo and clears previous real metadata", () => {
    flushOverview({ isPending: false, isError: false, data: realData() });
    flushOverview({
      isPending: false,
      isError: false,
      data: { source: "demo", overview: {} },
    });
    expect(state?.source).toBe("demo");
    expect(state?.metadata).toBeUndefined();
    expect(label()).toBe("Dados demonstrativos");
  });
  it("rejects the previous scope immediately and replaces it without leaking metadata", () => {
    flushOverview({ isPending: false, isError: false, data: realData() });
    const previous = state;
    selected = { ...scope, store_id: "lume-b2b" };
    expect(
      activePageState("/b2b", "read-api-preview", selected, previous),
    ).toBeNull();
    expect(label()).toBe("Conectando dados reais");
    flushOverview({ isPending: true, isError: false });
    expect(state?.scopeKey).toBe(overviewScopeKey(selected));
    expect(state?.metadata).toBeUndefined();
  });
  it("propagates Overview coverage to the real PeriodFilter and PDF source indicator", () => {
    flushOverview({ isPending: false, isError: false, data: realData() });
    const html = renderToStaticMarkup(createElement(PeriodFilter));
    expect(html).toContain("Filtrar período: 01/09/2026 – 27/09/2026");
    expect(html).not.toContain('disabled=""');
    expect(html).not.toContain("Aguardando cobertura");
    const pdf = renderToStaticMarkup(createElement(PrintContext));
    expect(pdf).toContain("Dados reais · Histórico parcial");
    expect(pdf).toContain("01/09/2026 – 27/09/2026");
    expect(pdf).not.toContain("Dados demonstrativos");
  });
});
