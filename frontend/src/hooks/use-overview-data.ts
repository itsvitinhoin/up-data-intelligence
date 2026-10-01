"use client";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace, overviewScopeKey } from "@/features/providers";
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
  if (mode !== "read-api-preview" || context.scope.operation !== "B2B")
    return { source: "demo", overview: await api.read("overview", context) };
  const params = new URLSearchParams({
    tenant_id: context.scope.tenant_id,
    workspace_operation_id: context.scope.store_id,
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
  if (response.status === 404) {
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
  const { dataMode, setOverviewReadState, setDashboardPageState } =
    useWorkspace();
  const path = usePathname();
  const scopeKey = overviewScopeKey(context.scope);
  const result = useQuery({
    queryKey: overviewQueryKey(dataMode, context),
    queryFn: ({ signal }) => readOverview(dataMode, { ...context, signal }),
    retry: false,
  });
  useEffect(() => {
    setDashboardPageState((previous) => ({
      path,
      scopeKey,
      source: result.isPending
        ? "loading-real"
        : result.isError
          ? "error-real"
          : result.data?.source === "real"
            ? result.data.overview.metadata.history_complete
              ? "real"
              : "partial-real"
            : "demo",
      metadata:
        result.data?.source === "real"
          ? result.data.overview.metadata
          : previous?.scopeKey === scopeKey
            ? previous.metadata
            : undefined,
    }));
  }, [
    path,
    scopeKey,
    result.isPending,
    result.isError,
    result.data,
    setDashboardPageState,
  ]);
  useEffect(() => {
    if (result.isPending)
      setOverviewReadState((previous) => ({
        scopeKey,
        source: "loading",
        metadata:
          previous?.scopeKey === scopeKey ? previous.metadata : undefined,
      }));
    else if (result.isError)
      setOverviewReadState((previous) => ({
        scopeKey,
        source: "error",
        metadata:
          previous?.scopeKey === scopeKey ? previous.metadata : undefined,
      }));
    else if (result.data?.source === "real")
      setOverviewReadState({
        scopeKey,
        source: "real",
        metadata: result.data.overview.metadata,
      });
    else if (result.data?.source === "demo")
      setOverviewReadState({ scopeKey, source: "demo" });
  }, [
    result.isPending,
    result.isError,
    result.data,
    scopeKey,
    setOverviewReadState,
  ]);
  return result;
}
