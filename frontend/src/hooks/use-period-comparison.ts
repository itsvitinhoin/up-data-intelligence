"use client";
import { useQuery } from "@tanstack/react-query";
import {
  compareMetrics,
  compareMetricTree,
  previousPeriod,
  type MetricItems,
} from "@/lib/metric-comparison";
import { dateRange } from "@/lib/period";
import type { Filters, Metric } from "@/types/domain";

export function usePeriodComparison<T>({
  current,
  filters,
  queryKey,
  read,
  available,
  reason,
}: {
  current: T | undefined;
  filters: Filters;
  queryKey: readonly unknown[];
  read: (filters: Filters, signal: AbortSignal) => Promise<T>;
  available: boolean;
  reason?: string;
}) {
  available = available && filters.compare !== false;
  const previousFilters = previousPeriod(filters);
  const previous = useQuery({
    queryKey: [...queryKey, "previous-period", previousFilters],
    queryFn: ({ signal }) => read(previousFilters, signal),
    enabled: available,
    retry: false,
  });
  const state =
    !available || previous.isError
      ? "unavailable"
      : previous.isPending
        ? "loading"
        : "ready";
  const limitation =
    filters.compare === false
      ? "Comparação desativada."
      : !available
        ? reason
        : previous.isError
          ? "Leitura do período anterior indisponível."
          : undefined;
  function compare(select: (data: T) => Metric[]): Metric[] {
    if (current === undefined) return [];
    return compareMetrics(
      select(current),
      previous.data === undefined ? undefined : select(previous.data),
      filters,
      state,
      limitation,
    );
  }
  function compareCards(
    select: (data: T) => MetricItems,
  ): (MetricItems[number] & { comparison?: Metric["comparison"] })[] {
    const toMetrics = (value: T) =>
      select(value).map(([label, value, format, hint]): Metric => ({
        label,
        value: value === null ? null : String(value),
        format,
        hint: hint ?? "Indicador observado",
      }));
    return compare(toMetrics).map((m) =>
      Object.assign(
        [m.label, m.value, m.format, m.hint] as MetricItems[number],
        { comparison: m.comparison },
      ),
    );
  }
  return {
    compare,
    compareCards,
    comparison: previous,
    data:
      current === undefined
        ? undefined
        : compareMetricTree(current, previous.data, filters, state, limitation),
  };
}
export function demoComparisonAvailable(filters: Filters) {
  const range = dateRange(previousPeriod(filters));
  const current = dateRange(filters);
  return (
    range.from >= "2026-09-01" &&
    range.to <= "2026-09-30" &&
    current.from >= "2026-09-01" &&
    current.to <= "2026-09-30"
  );
}
