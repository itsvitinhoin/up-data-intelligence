"use client";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
import {
  usePeriodComparison,
  demoComparisonAvailable,
} from "./use-period-comparison";
import { api as demoApi } from "@/services/api";
import { createLiveDataApi } from "@/services/api/live";
import { useMemo } from "react";
import { usePublicationMetadata, usePreviewDemo } from "./publication-context";
import type { DataApi } from "@/types/domain";
import { periodCovered, previousPeriod } from "@/lib/metric-comparison";
import { ApiError } from "@/services/api/access";
export function requireDemoResource(mode: string) {
  if (mode === "live")
    throw new ApiError(424, "Cobertura ainda não certificada.");
}
import type { Resource, RequestContext } from "@/types/domain";
export function useRequestContext(): RequestContext {
  const { scope, session, filters } = useWorkspace();
  if (!scope || !session)
    throw new Error("Select an authorized workspace first");
  return { scope, session, filters };
}
export function queryKey(resource: string, c: RequestContext) {
  return [
    c.session.id,
    c.session.role,
    c.scope.tenant_id,
    c.scope.store_id,
    c.scope.operation,
    resource,
    c.filters,
  ] as const;
}
export function useDataApi(): DataApi {
  const { dataMode, scope } = useWorkspace();
  const metadata = usePublicationMetadata();
  const previewDemo = usePreviewDemo();
  return useMemo(
    () =>
      dataMode === "demo" ||
      (dataMode === "read-api-preview" &&
        (scope?.operation === "B2C" || previewDemo))
        ? demoApi
        : createLiveDataApi(metadata),
    [dataMode, scope?.operation, metadata, previewDemo],
  );
}
function useComparisonCoverage(context: RequestContext) {
  const { dataMode } = useWorkspace();
  const metadata = usePublicationMetadata();
  return {
    available:
      dataMode === "demo"
        ? demoComparisonAvailable(context.filters)
        : Boolean(
            metadata &&
            periodCovered(
              previousPeriod(context.filters),
              metadata.report_from,
              metadata.report_to,
            ),
          ),
    reason:
      dataMode === "demo"
        ? "Período anterior fora da cobertura demonstrativa (setembro/2026)."
        : "Período anterior fora da cobertura publicada.",
  };
}
export function useResource<K extends Resource>(resource: K) {
  const context = useRequestContext();
  const api = useDataApi();
  const coverage = useComparisonCoverage(context);
  const { dataMode } = useWorkspace();
  const publication = usePublicationMetadata();
  const result = useQuery({
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(resource, context),
    ],
    queryFn: ({ signal }) => {
      return api.read(resource, { ...context, signal });
    },
  });
  const temporal = ![
    "companies",
    "users",
    "integrations",
    "inventory_products",
    "order_history",
  ].includes(resource);
  const comparison = usePeriodComparison({
    current: result.data,
    filters: context.filters,
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(resource, context),
    ],
    read: (filters, signal) => {
      return api.read(resource, { ...context, filters, signal });
    },
    available: temporal && coverage.available,
    reason: temporal
      ? coverage.reason
      : "Snapshot atual ou histórico integral; não há snapshot anterior comparável.",
  });
  return { ...result, ...comparison } as typeof result & typeof comparison;
}
export function useCustomer(id: string) {
  const context = useRequestContext();
  const api = useDataApi();
  const coverage = useComparisonCoverage(context);
  const { dataMode } = useWorkspace();
  const publication = usePublicationMetadata();
  const result = useQuery({
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(`customer:${id}`, context),
    ],
    queryFn: ({ signal }) => {
      return api.customer(id, { ...context, signal });
    },
  });
  const comparison = usePeriodComparison({
    current: result.data,
    filters: context.filters,
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(`customer:${id}`, context),
    ],
    available:
      dataMode === "demo" &&
      context.scope.operation === "B2B" &&
      coverage.available,
    reason:
      "Histórico observado integral; não há snapshot anterior comparável.",
    read: (filters, signal) => {
      return api.customer(id, { ...context, filters, signal });
    },
  });
  return { ...result, ...comparison } as typeof result & typeof comparison;
}

export function useCampaign(id: string) {
  const context = useRequestContext();
  const api = useDataApi();
  const coverage = useComparisonCoverage(context);
  const { dataMode } = useWorkspace();
  const publication = usePublicationMetadata();
  const result = useQuery({
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(`campaign:${id}`, context),
    ],
    queryFn: ({ signal }) => {
      return api.campaign(id, { ...context, signal });
    },
  });
  const comparison = usePeriodComparison({
    current: result.data,
    filters: context.filters,
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(`campaign:${id}`, context),
    ],
    available: coverage.available,
    reason:
      "Histórico observado integral; não há snapshot anterior comparável.",
    read: (filters, signal) => {
      return api.campaign(id, { ...context, filters, signal });
    },
  });
  return { ...result, ...comparison } as typeof result & typeof comparison;
}

export function useOrder(id: string, enabled: boolean, allOrigins = false) {
  const base = useRequestContext();
  const api = useDataApi();
  const { dataMode } = useWorkspace();
  const publication = usePublicationMetadata();
  const context = allOrigins
    ? { ...base, filters: { ...base.filters, channel: "all", media: "all" } }
    : base;
  return useQuery({
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(`order:${id}`, context),
    ],
    enabled,
    queryFn: ({ signal }) => {
      return api.order(id, { ...context, signal });
    },
  });
}

export function useProduct(id: string, enabled: boolean) {
  const context = useRequestContext(),
    api = useDataApi();
  const { dataMode } = useWorkspace();
  const publication = usePublicationMetadata();
  return useQuery({
    queryKey: [
      dataMode,
      publication?.policy_hash,
      publication?.generation,
      ...queryKey(`product:${id}`, context),
    ],
    enabled,
    queryFn: async ({ signal }) => {
      if (api.product) return api.product(id, { ...context, signal });
      const rows = await api.read("products", { ...context, signal });
      const row = rows.find((r) => r.id === id);
      if (!row) throw new ApiError(404, "Produto não encontrado.");
      return row;
    },
  });
}
