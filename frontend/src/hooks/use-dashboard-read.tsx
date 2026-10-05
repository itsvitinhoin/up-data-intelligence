"use client";
import { usePeriodComparison } from "./use-period-comparison";
import {
  previousPeriod,
  periodCovered,
  sameComparisonPublication,
} from "@/lib/metric-comparison";
import { useEffect, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useRequestContext, queryKey } from "./use-resource";
import { useWorkspace, overviewScopeKey } from "@/features/providers";
import { defaultFilters } from "@/config/tenants";
import { readOverview, overviewQueryKey } from "./use-overview-data";
import { type ReadResource, type ReadMetadata } from "@/services/api/http";
import { exclusiveToInclusive } from "@/lib/period";
import { ApiError } from "@/services/api/access";
import { readDashboard } from "@/services/api/read-client";
export { readDashboard } from "@/services/api/read-client";
import { PublicationContext, PreviewDemoContext } from "./publication-context";
import { Failure, Loading } from "@/components/ui-kit";

export function B2BReadBoundary({ children }: { children: ReactNode }) {
  const context = useRequestContext();
  const { dataMode, setDashboardPageState } = useWorkspace();
  const path = usePathname(),
    scopeKey = overviewScopeKey(context.scope);
  const base = { ...context, filters: defaultFilters };
  const preview = dataMode !== "demo" && context.scope.operation === "B2B";
  const result = useQuery({
    queryKey: overviewQueryKey(dataMode, base),
    queryFn: ({ signal }) => readOverview(dataMode, { ...base, signal }),
    enabled: preview,
    retry: false,
  });
  useEffect(() => {
    if (!preview || result.data?.source === "demo")
      setDashboardPageState({ path, scopeKey, source: "demo" });
    else
      setDashboardPageState({
        path,
        scopeKey,
        source: result.isError
          ? "error-real"
          : result.isPending
            ? "loading-real"
            : result.data?.source === "real" &&
                !result.data.overview.metadata.history_complete
              ? "partial-real"
              : "real",
        metadata:
          result.data?.source === "real"
            ? result.data.overview.metadata
            : undefined,
      });
  }, [
    preview,
    result.isPending,
    result.isError,
    result.data,
    path,
    scopeKey,
    setDashboardPageState,
  ]);
  if (!preview) return children;
  if (dataMode === "read-api-preview" && result.data?.source === "demo")
    return <PreviewDemoContext value={true}>{children}</PreviewDemoContext>;
  if (result.isError)
    return (
      <Failure
        retry={() => void result.refetch()}
        description="Publicação real indisponível."
      />
    );
  if (!result.data || result.data.source !== "real") return <Loading />;
  const metadata = result.data.overview.metadata;
  return (
    <div
      key={`${scopeKey}/${metadata.generation}/${context.filters.from}/${context.filters.to}`}
    >
      <PublicationContext value={metadata}>{children}</PublicationContext>
    </div>
  );
}
export { usePageSource } from "./use-page-source";
export function dashboardReadKey(
  mode: string,
  resource: string,
  context: ReturnType<typeof useRequestContext>,
  generation: number,
  options: object,
) {
  return [mode, ...queryKey(resource, context), generation, options];
}
export function useDashboardRead<K extends ReadResource>(
  resource: K,
  metadata: ReadMetadata,
  options: { customerId?: string; cursor?: string; status?: string } = {},
) {
  const base = useRequestContext(),
    { dataMode } = useWorkspace(),
    client = useQueryClient();
  const context = ["customer", "customerOrders", "order"].includes(resource)
    ? { ...base, filters: defaultFilters }
    : {
        ...base,
        filters: {
          ...base.filters,
          from: base.filters.from ?? metadata.report_from,
          to: base.filters.to ?? exclusiveToInclusive(metadata.report_to),
        },
      };
  const publicationKey = useMemo(
    () =>
      overviewQueryKey(dataMode, {
        session: base.session,
        scope: base.scope,
        filters: defaultFilters,
      }),
    [dataMode, base.session, base.scope],
  );
  const result = useQuery({
    queryKey: dashboardReadKey(
      dataMode,
      resource,
      context,
      metadata.generation,
      {
        ...options,
        policy_hash: metadata.policy_hash,
        publication_domain: metadata.publication_domain ?? "analytics-v1",
        intelligence_generation:
          metadata.publication_domain === "intelligence"
            ? metadata.generation
            : null,
        analytics_generation:
          metadata.analytics_generation ?? metadata.generation,
      },
    ),
    queryFn: ({ signal }) =>
      readDashboard(
        resource,
        context,
        metadata.analytics_generation ?? metadata.generation,
        {
          ...options,
          expectedPolicyHash: metadata.policy_hash,
          expectedIntelligenceGeneration:
            metadata.publication_domain === "intelligence"
              ? metadata.generation
              : undefined,
          signal,
        },
      ),
    retry: false,
  });
  const comparable = [
    "overview",
    "acquisition",
    "retention",
    "funnel",
    "performance",
    "campaign",
  ].includes(resource);
  // Resolve the resource's publication first. Intelligence can have its own
  // generation even when the Analytics generation used by the page is unchanged.
  const comparisonPublication = result.data?.metadata;
  const comparison = usePeriodComparison({
    current: result.data?.data,
    filters: context.filters,
    queryKey: [
      ...dashboardReadKey(dataMode, resource, context, metadata.generation, {
        ...options,
        policy_hash: metadata.policy_hash,
      }),
      comparisonPublication?.publication_domain,
      comparisonPublication?.generation,
      comparisonPublication?.analytics_generation,
      comparisonPublication?.as_of,
    ],
    available:
      comparable &&
      Boolean(comparisonPublication) &&
      periodCovered(
        previousPeriod(context.filters),
        comparisonPublication?.report_from ?? metadata.report_from,
        comparisonPublication?.report_to ?? metadata.report_to,
      ),
    reason: comparable
      ? "Período anterior fora da cobertura publicada."
      : "Resumo histórico ou lista paginada; não há agregado anterior comparável neste contrato.",
    read: async (filters, signal) => {
      if (!comparisonPublication)
        throw new ApiError(409, "Publicação da comparação não resolvida.");
      const previous = await readDashboard(
        resource,
        { ...context, filters },
        comparisonPublication.analytics_generation ??
          comparisonPublication.generation,
        {
          ...options,
          cursor: undefined,
          expectedPolicyHash: comparisonPublication.policy_hash,
          expectedIntelligenceGeneration:
            comparisonPublication.publication_domain === "intelligence"
              ? comparisonPublication.generation
              : undefined,
          signal,
        },
      );
      if (!sameComparisonPublication(previous.metadata, comparisonPublication))
        throw new ApiError(409, "Publicação da comparação mudou.");
      return previous.data;
    },
  });
  // Publication resolution is separate from the immutable generation cache.
  const immutable = useQuery({
    queryKey: dashboardReadKey(
      dataMode,
      resource,
      context,
      result.data?.metadata.analytics_generation ?? metadata.generation,
      {
        ...options,
        publication_domain: "intelligence",
        policy_hash: metadata.policy_hash,
        intelligence_generation:
          result.data?.metadata.publication_domain === "intelligence"
            ? result.data.metadata.generation
            : null,
      },
    ),
    queryFn: async () => {
      if (!result.data) throw new Error("Publication unresolved");
      return result.data;
    },
    enabled: false,
    initialData: result.data,
  });
  useEffect(() => {
    if (result.error instanceof ApiError && result.error.status === 409) {
      void client.invalidateQueries({ queryKey: publicationKey });
      void client.invalidateQueries({
        predicate: (q) =>
          q.queryKey[0] === dataMode &&
          q.queryKey.includes(base.scope.store_id) &&
          q.queryKey.includes(base.scope.tenant_id),
      });
    }
  }, [
    result.error,
    client,
    publicationKey,
    dataMode,
    base.scope.store_id,
    base.scope.tenant_id,
  ]);
  return {
    ...result,
    compare: comparison.compare,
    compareCards: comparison.compareCards,
    data:
      result.data?.metadata.publication_domain === "intelligence"
        ? immutable.data
        : result.data,
  };
}
