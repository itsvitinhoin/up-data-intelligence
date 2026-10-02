"use client";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
import {
  usePeriodComparison,
  demoComparisonAvailable,
} from "./use-period-comparison";
import { api } from "@/services/api";
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
export function useResource<K extends Resource>(resource: K) {
  const context = useRequestContext();
  const result = useQuery({
    queryKey: queryKey(resource, context),
    queryFn: ({ signal }) => api.read(resource, { ...context, signal }),
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
    queryKey: queryKey(resource, context),
    read: (filters, signal) =>
      api.read(resource, { ...context, filters, signal }),
    available: temporal && demoComparisonAvailable(context.filters),
    reason: temporal
      ? "Período anterior fora da cobertura demonstrativa (setembro/2026)."
      : "Snapshot atual ou histórico integral; não há snapshot anterior comparável.",
  });
  return { ...result, ...comparison } as typeof result & typeof comparison;
}
export function useCustomer(id: string) {
  const context = useRequestContext();
  const result = useQuery({
    queryKey: queryKey(`customer:${id}`, context),
    queryFn: ({ signal }) => api.customer(id, { ...context, signal }),
  });
  const comparison = usePeriodComparison({
    current: result.data,
    filters: context.filters,
    queryKey: queryKey(`customer:${id}`, context),
    available:
      context.scope.operation === "B2B" &&
      demoComparisonAvailable(context.filters),
    reason:
      "Histórico integral ou período anterior fora da cobertura demonstrativa.",
    read: (filters, signal) =>
      api.customer(id, { ...context, filters, signal }),
  });
  return { ...result, ...comparison } as typeof result & typeof comparison;
}

export function useCampaign(id: string) {
  const context = useRequestContext();
  const result = useQuery({
    queryKey: queryKey(`campaign:${id}`, context),
    queryFn: ({ signal }) => api.campaign(id, { ...context, signal }),
  });
  const comparison = usePeriodComparison({
    current: result.data,
    filters: context.filters,
    queryKey: queryKey(`campaign:${id}`, context),
    available: demoComparisonAvailable(context.filters),
    reason:
      "Histórico integral ou período anterior fora da cobertura demonstrativa.",
    read: (filters, signal) =>
      api.campaign(id, { ...context, filters, signal }),
  });
  return { ...result, ...comparison } as typeof result & typeof comparison;
}

export function useOrder(id: string, enabled: boolean, allOrigins = false) {
  const base = useRequestContext();
  const context = allOrigins
    ? { ...base, filters: { ...base.filters, channel: "all", media: "all" } }
    : base;
  return useQuery({
    queryKey: queryKey(`order:${id}`, context),
    enabled,
    queryFn: ({ signal }) => api.order(id, { ...context, signal }),
  });
}
