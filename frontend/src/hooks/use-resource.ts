"use client";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
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
  return useQuery({
    queryKey: queryKey(resource, context),
    queryFn: ({ signal }) => api.read(resource, { ...context, signal }),
  });
}
export function useCustomer(id: string) {
  const context = useRequestContext();
  return useQuery({
    queryKey: queryKey(`customer:${id}`, context),
    queryFn: ({ signal }) => api.customer(id, { ...context, signal }),
  });
}

export function useCampaign(id: string) {
  const context = useRequestContext();
  return useQuery({
    queryKey: queryKey(`campaign:${id}`, context),
    queryFn: ({ signal }) => api.campaign(id, { ...context, signal }),
  });
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
