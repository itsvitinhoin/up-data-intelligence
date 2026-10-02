import type { Filters, Metric } from "@/types/domain";
import { dateRange, shiftIsoDay } from "./period";

export type ComparisonState =
  "ready" | "loading" | "unavailable" | "no-baseline";
export interface MetricComparison {
  state: ComparisonState;
  previous: string | null;
  from: string;
  to: string;
  change: string | null;
  unit: "%" | "p.p.";
  direction: "up" | "down" | "flat" | null;
  reason?: string;
}
export type MetricItems = [
  string,
  string | number | null,
  Metric["format"],
  string?,
][];

/** Inclusive local calendar days, preserving every non-temporal filter. */
export function previousPeriod(filters: Filters): Filters {
  const current = dateRange(filters);
  return {
    ...filters,
    period: "custom",
    days: current.days,
    from: shiftIsoDay(current.from, -current.days),
    to: shiftIsoDay(current.from, -1),
  };
}
function decimal(value: string | null) {
  if (value === null || !/^-?\d+(?:\.\d+)?$/.test(value)) return null;
  const [integer, fraction = ""] = value.split(".");
  const sign = value.startsWith("-") ? -1n : 1n;
  return {
    value: sign * BigInt(integer.replace("-", "") + fraction),
    scale: fraction.length,
  };
}
function rounded(n: bigint, d: bigint): string {
  const negative = n < 0n;
  const absolute = negative ? -n : n;
  const cents = (absolute * 100n + d / 2n) / d;
  return `${negative && cents !== 0n ? "-" : ""}${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}
/** Exact decimal arithmetic; monetary input stays a string, never a float. */
export function compareMetric(
  current: Metric,
  previous: Metric | undefined,
  filters: Filters,
  state: ComparisonState = "ready",
  reason?: string,
): MetricComparison {
  const range = dateRange(previousPeriod(filters));
  const base: MetricComparison = {
    state,
    previous: previous?.value ?? null,
    from: range.from,
    to: range.to,
    change: null,
    unit: current.format === "percent" ? "p.p." : "%",
    direction: null,
    reason,
  };
  if (current.comparisonBasis === "snapshot")
    return {
      ...base,
      state: "unavailable",
      previous: null,
      reason:
        "Resumo histórico ou snapshot atual sem versão anterior comparável.",
    };
  if (state !== "ready") return base;
  const a = decimal(current.value),
    b = decimal(previous?.value ?? null);
  if (!a || !b || current.format !== previous?.format)
    return {
      ...base,
      state: "unavailable",
      reason: "Métrica sem cobertura comparável nos dois períodos.",
    };
  const scale = Math.max(a.scale, b.scale);
  const av = a.value * 10n ** BigInt(scale - a.scale);
  const bv = b.value * 10n ** BigInt(scale - b.scale);
  const difference = av - bv;
  const direction = difference > 0n ? "up" : difference < 0n ? "down" : "flat";
  if (current.format === "percent")
    return {
      ...base,
      change: rounded(difference, 10n ** BigInt(scale)),
      direction,
    };
  if (bv === 0n && av !== 0n)
    return {
      ...base,
      state: "no-baseline",
      reason:
        "O período anterior tem valor zero; a variação percentual não é definida.",
    };
  return {
    ...base,
    change: bv === 0n ? "0.00" : rounded(difference * 100n, bv < 0n ? -bv : bv),
    direction,
  };
}
export function compareMetrics(
  current: Metric[],
  previous: Metric[] | undefined,
  filters: Filters,
  state: ComparisonState = "ready",
  reason?: string,
): Metric[] {
  return current.map((item) => {
    const prior = previous?.find(
      (m) => m.label === item.label && m.format === item.format,
    );
    return {
      ...item,
      comparison: compareMetric(item, prior, filters, state, reason),
      secondary: item.secondary
        ? {
            ...item.secondary,
            comparison: compareMetric(
              { ...item, ...item.secondary, format: "currency" },
              prior?.secondary
                ? { ...prior, ...prior.secondary, format: "currency" }
                : undefined,
              filters,
              state,
              reason,
            ),
          }
        : undefined,
    };
  });
}
export function compareMetricTree<T>(
  current: T,
  previous: T | undefined,
  filters: Filters,
  state: ComparisonState,
  reason?: string,
): T {
  if (Array.isArray(current)) {
    if (
      current.length &&
      current.every(
        (v) =>
          v &&
          typeof v === "object" &&
          "label" in v &&
          "format" in v &&
          "hint" in v,
      )
    )
      return compareMetrics(
        current,
        Array.isArray(previous) ? previous : undefined,
        filters,
        state,
        reason,
      ) as T;
    return current.map((v, i) =>
      compareMetricTree(
        v,
        Array.isArray(previous) ? previous[i] : undefined,
        filters,
        state,
        reason,
      ),
    ) as T;
  }
  if (current && typeof current === "object")
    return Object.fromEntries(
      Object.entries(current).map(([key, v]) => [
        key,
        compareMetricTree(
          v,
          previous && typeof previous === "object"
            ? (previous as Record<string, unknown>)[key]
            : undefined,
          filters,
          state,
          reason,
        ),
      ]),
    ) as T;
  return current;
}

export function periodCovered(
  filters: Filters,
  from: string,
  toExclusive: string,
) {
  const range = dateRange(filters);
  return range.from >= from && range.to < toExclusive;
}
export function sameComparisonPublication(
  a: {
    store_id: string;
    generation: number;
    policy_hash: string;
    currency: string | null;
    reporting_timezone: string;
    as_of: string;
    analytics_generation?: number;
    publication_domain?: string;
    publication_id?: string;
  },
  b: typeof a,
) {
  return (
    a.currency !== null &&
    b.currency !== null &&
    a.store_id === b.store_id &&
    a.generation === b.generation &&
    a.policy_hash === b.policy_hash &&
    a.currency === b.currency &&
    a.reporting_timezone === b.reporting_timezone &&
    a.as_of === b.as_of &&
    a.analytics_generation === b.analytics_generation &&
    a.publication_domain === b.publication_domain &&
    a.publication_id === b.publication_id
  );
}
