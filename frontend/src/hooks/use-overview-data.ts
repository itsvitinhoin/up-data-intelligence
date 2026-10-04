"use client";
import {
  usePeriodComparison,
  demoComparisonAvailable,
} from "./use-period-comparison";
import {
  previousPeriod,
  periodCovered,
  sameComparisonPublication,
} from "@/lib/metric-comparison";
import { exclusiveToInclusive } from "@/lib/period";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
import { usePageSource } from "./use-page-source";
import { useRequestContext, queryKey } from "./use-resource";
import { api } from "@/services/api";
import { ApiError } from "@/services/api/access";
import { decodeOverviewEnvelope } from "@/services/api/http";
import { presentLiveOverview } from "@/services/api/overview-presenter";
import type { Overview } from "@/types/domain";

export type OverviewData =
  | { source: "demo"; overview: Overview }
  | { source: "real"; overview: ReturnType<typeof presentLiveOverview> };

export function overviewQueryKey(
  mode: string,
  context: ReturnType<typeof useRequestContext>,
) {
  return [mode, ...queryKey("overview", context)] as const;
}

export async function readOverview(
  mode: string,
  context: ReturnType<typeof useRequestContext>,
  fetcher: typeof fetch = fetch,
): Promise<OverviewData> {
  if (mode === "live" && context.scope.operation !== "B2B")
    throw new ApiError(424, "Cobertura ainda não certificada.");
  if (mode === "demo" || context.scope.operation !== "B2B")
    return { source: "demo", overview: await api.read("overview", context) };
  const params = new URLSearchParams({
    tenant_id: context.scope.tenant_id,
    workspace_operation_id:
      context.scope.workspace_operation_id ?? context.scope.store_id,
    operation: context.scope.operation,
  });
  if (context.filters.from && context.filters.to) {
    params.set("from", context.filters.from);
    params.set("to", context.filters.to);
  }
  const response = await fetcher(`/api/dashboard/overview?${params}`, {
    method: "GET",
    signal: context.signal,
    cache: "no-store",
  });
  if (mode !== "live" && response.status === 404) {
    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "object" &&
      payload.error !== null &&
      "code" in payload.error &&
      payload.error.code === "preview_binding_absent"
    )
      return { source: "demo", overview: await api.read("overview", context) };
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      400: "Período fora da cobertura publicada.",
      401: "Acesso não autorizado à leitura.",
      403: "Acesso não autorizado à leitura.",
      424: "Dados ainda sem cobertura publicada.",
      503: "Dados temporariamente indisponíveis.",
    };
    throw new ApiError(
      response.status,
      messages[response.status] ?? "Não foi possível carregar os dados reais.",
    );
  }
  const envelope = decodeOverviewEnvelope(await response.json());
  return { source: "real", overview: presentLiveOverview(envelope) };
}

export function useOverviewData() {
  const context = useRequestContext();
  const { dataMode } = useWorkspace();
  const result = useQuery({
    queryKey: overviewQueryKey(dataMode, context),
    queryFn: ({ signal }) => readOverview(dataMode, { ...context, signal }),
    retry: false,
  });
  const publication =
    result.data?.source === "real" ? result.data.overview.metadata : undefined;
  const currentRange =
    publication && !context.filters.from
      ? {
          ...context.filters,
          from: publication.report_from,
          to: exclusiveToInclusive(publication.report_to),
        }
      : context.filters;
  const comparison = usePeriodComparison({
    current: result.data,
    filters: currentRange,
    queryKey: [
      ...overviewQueryKey(dataMode, context),
      result.data?.source,
      publication?.generation,
      publication?.policy_hash,
      publication?.as_of,
      publication?.currency,
      publication?.reporting_timezone,
    ],
    available: publication
      ? periodCovered(
          previousPeriod(currentRange),
          publication.report_from,
          publication.report_to,
        )
      : result.data?.source === "demo" && demoComparisonAvailable(currentRange),
    reason: "Período anterior fora da cobertura publicada.",
    read: async (filters, signal) => {
      const prior = await readOverview(dataMode, {
        ...context,
        filters,
        signal,
      });
      if (result.data?.source !== prior.source)
        throw new Error("Comparison source changed");
      if (
        publication &&
        (prior.source !== "real" ||
          !sameComparisonPublication(prior.overview.metadata, publication))
      )
        throw new Error("Comparison publication changed");
      return prior;
    },
  });
  usePageSource(
    result.isPending
      ? "loading-real"
      : result.isError
        ? "error-real"
        : result.data?.source === "real"
          ? result.data.overview.metadata.history_complete
            ? "real"
            : "partial-real"
          : "demo",
    result.data?.source === "real" ? result.data.overview.metadata : undefined,
  );
  return { ...result, data: comparison.data } as typeof result;
}
