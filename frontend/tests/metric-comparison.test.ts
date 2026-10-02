import { beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  compareMetric,
  compareMetrics,
  compareMetricTree,
  previousPeriod,
  periodCovered,
  sameComparisonPublication,
} from "@/lib/metric-comparison";
import { dateRange, presetRange } from "@/lib/period";
import { defaultFilters } from "@/config/tenants";
import { MetricComparisonLine } from "@/components/metric-comparison";
import {
  usePeriodComparison,
  demoComparisonAvailable,
} from "@/hooks/use-period-comparison";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { queryKey } from "@/hooks/use-resource";
import type { Metric, RequestContext } from "@/types/domain";

const harness = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({ useQuery: harness.query }));
const filters = { ...defaultFilters, from: "2026-09-16", to: "2026-09-30" };
const m = (
  value: string | null,
  format: Metric["format"] = "currency",
  label = "Receita",
): Metric => ({ label, value, format, hint: "Fixture sintética" });
const metadata = {
  store_id: "synthetic",
  generation: 1,
  policy_hash: "a",
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-09-30T03:00:00Z",
};
beforeEach(() => {
  harness.query.mockReset();
  harness.query.mockReturnValue({
    isError: false,
    isPending: false,
    data: undefined,
  });
});

describe("previous calendar period", () => {
  it.each(["7", "30", "90", "month", "year", "week", "last-month"])(
    "preserves duration and filters for %s",
    (preset) => {
      const current = { ...filters, ...presetRange(preset) };
      const prior = previousPeriod(current);
      expect(dateRange(prior).days).toBe(dateRange(current).days);
      expect(Date.parse(current.from) - Date.parse(prior.to!)).toBe(86400000);
      expect(prior.channel).toBe(current.channel);
      expect(prior.collection).toBe(current.collection);
      expect(prior.search).toBe(current.search);
    },
  );
  it.each([
    ["2024-03-01", "2024-03-01", "2024-02-29", "2024-02-29"],
    ["2026-01-01", "2026-01-07", "2025-12-25", "2025-12-31"],
    ["2026-09-16", "2026-09-30", "2026-09-01", "2026-09-15"],
  ])("handles boundaries %s–%s", (from, to, start, end) => {
    expect(previousPeriod({ ...filters, from, to })).toMatchObject({
      from: start,
      to: end,
    });
  });
  it("never claims coverage outside the demo or publication", () => {
    expect(demoComparisonAvailable(filters)).toBe(true);
    expect(demoComparisonAvailable(defaultFilters)).toBe(false);
    expect(
      periodCovered(previousPeriod(filters), "2026-09-01", "2026-09-28"),
    ).toBe(true);
    expect(
      periodCovered(previousPeriod(defaultFilters), "2026-09-01", "2026-09-28"),
    ).toBe(false);
  });
});
describe("exact comparable metrics", () => {
  it.each([
    ["150.00", "100.00", "50.00", "up"],
    ["75.00", "100.00", "-25.00", "down"],
    ["0", "0", "0.00", "flat"],
    ["0", "100", "-100.00", "down"],
    ["100.01", "100.00", "0.01", "up"],
    ["900719925474099300.00", "450359962737049650.00", "100.00", "up"],
    ["-50", "-100", "50.00", "up"],
  ])("computes %s / %s", (current, previous, change, direction) => {
    expect(compareMetric(m(current), m(previous), filters)).toMatchObject({
      state: "ready",
      change,
      direction,
      previous,
      unit: "%",
    });
  });
  it("uses percentage points for rates including zero baseline", () => {
    expect(
      compareMetric(m("60", "percent"), m("40", "percent"), filters),
    ).toMatchObject({ change: "20.00", unit: "p.p." });
    expect(
      compareMetric(m("5", "percent"), m("0", "percent"), filters),
    ).toMatchObject({ state: "ready", change: "5.00" });
  });
  it("does not invent infinity for zero baseline", () => {
    expect(compareMetric(m("100"), m("0"), filters)).toMatchObject({
      state: "no-baseline",
      change: null,
      previous: "0",
    });
  });
  it.each([
    [null, "0"],
    ["0", null],
    [null, null],
    ["NaN", "1"],
    ["", "1"],
  ])("preserves absent/invalid evidence %s / %s", (current, previous) => {
    expect(compareMetric(m(current), m(previous), filters).state).toBe(
      "unavailable",
    );
  });
  it("rejects incompatible formats, snapshots and missing prior metrics", () => {
    expect(compareMetric(m("1"), m("1", "number"), filters).state).toBe(
      "unavailable",
    );
    expect(
      compareMetric(
        { ...m("1"), comparisonBasis: "snapshot" },
        m("1"),
        filters,
      ),
    ).toMatchObject({ state: "unavailable", previous: null });
    expect(compareMetric(m("1"), undefined, filters).state).toBe("unavailable");
  });
  it("compares by label and includes nested acquisition/retention tickets", () => {
    const current = [
      {
        ...m("10", "number", "Novos"),
        secondary: { label: "Ticket", value: "120", hint: "Synthetic" },
      },
      m("100", "currency"),
    ];
    const previous = [
      m("50", "currency"),
      {
        ...m("5", "number", "Novos"),
        secondary: { label: "Ticket", value: "100", hint: "Synthetic" },
      },
    ];
    const result = compareMetrics(current, previous, filters);
    expect(result[0].comparison?.change).toBe("100.00");
    expect(result[0].secondary?.comparison?.change).toBe("20.00");
    expect(result[1].comparison?.change).toBe("100.00");
    expect(current[0]).not.toHaveProperty("comparison");
  });
  it("preserves all current decimal values, NULLs and metadata in nested data", () => {
    const current = { metadata, data: { metrics: [m("100.01"), m(null)] } };
    const result = compareMetricTree(
      current,
      { metadata, data: { metrics: [m("50.00"), m(null)] } },
      filters,
      "ready",
    );
    expect(result.metadata).toEqual(metadata);
    expect(result.data.metrics.map((m) => m.value)).toEqual(["100.01", null]);
    expect(result.data.metrics[0].comparison?.change).toBe("100.02");
  });
  it.each([
    "store_id",
    "generation",
    "policy_hash",
    "currency",
    "reporting_timezone",
    "as_of",
    "analytics_generation",
    "publication_domain",
    "publication_id",
  ])("rejects changed publication %s", (key) => {
    const other = {
      ...metadata,
      [key]:
        key === "generation" || key === "analytics_generation" ? 2 : "changed",
    };
    expect(sameComparisonPublication(metadata, other)).toBe(false);
  });
  it("does not treat unknown currency as certified", () => {
    expect(
      sameComparisonPublication(
        { ...metadata, currency: null },
        { ...metadata, currency: null },
      ),
    ).toBe(false);
    expect(sameComparisonPublication(metadata, metadata)).toBe(true);
  });
});

describe("comparison request lifecycle and cards", () => {
  const read = vi.fn(async () => [m("100")]);
  function probe(available: boolean) {
    let returned!: ReturnType<typeof usePeriodComparison<Metric[]>>;
    function Probe() {
      returned = usePeriodComparison({
        current: [m("150")],
        filters,
        queryKey: ["store-a", "overview"],
        read,
        available,
        reason: "Sem cobertura",
      });
      return null;
    }
    renderToStaticMarkup(createElement(Probe));
    return returned;
  }
  it("disables out-of-coverage reads and keeps current data", () => {
    const result = probe(false);
    expect(harness.query.mock.calls[0][0].enabled).toBe(false);
    expect(result.data?.[0].value).toBe("150");
    expect(result.data?.[0].comparison?.state).toBe("unavailable");
  });
  it("keeps current data when comparison is loading or failed", () => {
    for (const state of [
      { isPending: true, isError: false },
      { isPending: false, isError: true },
    ]) {
      harness.query.mockReturnValue(state);
      const result = probe(true);
      expect(result.data?.[0].value).toBe("150");
      expect(result.data?.[0].comparison?.state).toBe(
        state.isPending ? "loading" : "unavailable",
      );
    }
  });
  it("uses one deduplicated, scoped previous query and forwards cancellation", async () => {
    harness.query.mockReturnValue({
      data: [m("100")],
      isPending: false,
      isError: false,
    });
    const result = probe(true),
      options = harness.query.mock.calls[0][0];
    expect(harness.query).toHaveBeenCalledTimes(1);
    expect(options.queryKey).toContain("store-a");
    expect(options.queryKey.at(-1)).toMatchObject({
      from: "2026-09-01",
      to: "2026-09-15",
    });
    const signal = new AbortController().signal;
    await options.queryFn({ signal });
    expect(read).toHaveBeenCalledWith(previousPeriod(filters), signal);
    expect(result.data?.[0].comparison?.change).toBe("50.00");
  });
  it("keeps store/customer/session/filter isolation in query keys", () => {
    const context: RequestContext = {
      filters,
      scope: {
        tenant_id: "demo-up",
        store_id: "mx-fashion-b2b",
        operation: "B2B",
      },
      session: sessionFor("up-admin"),
    };
    expect(queryKey("customers", context)).not.toEqual(
      queryKey("customers", {
        ...context,
        scope: { ...context.scope, store_id: "lume-b2b" },
      }),
    );
    expect(queryKey("customer:a", context)).not.toEqual(
      queryKey("customer:b", context),
    );
    expect(queryKey("customers", context)).not.toEqual(
      queryKey("customers", { ...context, filters: previousPeriod(filters) }),
    );
  });
  it("shows previous value, percentage points, correct direction and unavailable status", () => {
    const render = (item: Metric) =>
      renderToStaticMarkup(createElement(MetricComparisonLine, { item }));
    expect(
      render({
        ...m("60", "percent"),
        comparison: compareMetric(
          m("60", "percent"),
          m("40", "percent"),
          filters,
        ),
      }),
    ).toContain("p.p.");
    expect(
      render({
        ...m("75", "currency", "CAC"),
        comparison: compareMetric(m("75"), m("100"), filters),
      }),
    ).toContain("delta--good");
    expect(render(m(null))).toContain("Comparação indisponível");
    expect(
      render({
        ...m("150"),
        comparison: compareMetric(m("150"), m("100"), filters),
      }),
    ).toContain("Anterior:");
  });
  it("reads both demo periods without manufacturing earlier history", async () => {
    const context: RequestContext = {
      filters,
      scope: {
        tenant_id: "demo-up",
        store_id: "mx-fashion-b2b",
        operation: "B2B",
      },
      session: sessionFor("up-admin"),
    };
    const [current, prior] = await Promise.all([
      demoApi.read("overview", context),
      demoApi.read("overview", {
        ...context,
        filters: previousPeriod(filters),
      }),
    ]);
    const result = compareMetricTree(current, prior, filters, "ready");
    expect(result.b2b?.revenue[0].comparison?.state).toBe("ready");
    expect(
      result.b2b?.customers.find((m) => m.label === "Novos")?.value,
    ).toBeNull();
    expect(
      result.b2b?.relationship.find((m) => m.label === "LTV geral da marca")
        ?.value,
    ).toBeNull();
  });
});
