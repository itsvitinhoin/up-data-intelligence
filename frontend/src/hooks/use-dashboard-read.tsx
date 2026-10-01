"use client";
import { useEffect, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useRequestContext, queryKey } from "./use-resource";
import { useWorkspace, overviewScopeKey } from "@/features/providers";
import { defaultFilters } from "@/config/tenants";
import { readOverview, overviewQueryKey } from "./use-overview-data";
import {
  decodeReadEnvelope,
  type ReadResource,
  type ReadMetadata,
} from "@/services/api/http";
import { exclusiveToInclusive } from "@/lib/period";
import { ApiError } from "@/services/api/access";
import { Failure, Loading } from "@/components/ui-kit";

export function B2BReadBoundary({
  children,
  real,
}: {
  children: ReactNode;
  real: (metadata: ReadMetadata) => ReactNode;
}) {
  const context = useRequestContext();
  const { dataMode, setDashboardPageState } = useWorkspace();
  const path = usePathname(),
    scopeKey = overviewScopeKey(context.scope);
  const base = { ...context, filters: defaultFilters };
  const preview =
    dataMode === "read-api-preview" && context.scope.operation === "B2B";
  const result = useQuery({
    queryKey: overviewQueryKey(dataMode, base),
    queryFn: ({ signal }) => readOverview(dataMode, { ...base, signal }),
    enabled: preview,
    retry: false,
  });
  useEffect(() => {
    if (!preview || result.data?.source === "demo")
      setDashboardPageState({ path, scopeKey, source: "demo" });
    else if (result.isPending || result.isError)
      setDashboardPageState({
        path,
        scopeKey,
        source: result.isError ? "error-real" : "loading-real",
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
  if (!preview || result.data?.source === "demo") return children;
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
      {real(metadata)}
    </div>
  );
}
export { usePageSource } from "./use-page-source";
export async function readDashboard<K extends ReadResource>(
  resource: K,
  context: ReturnType<typeof useRequestContext>,
  generation: number,
  options: {
    expectedPolicyHash?: string;
    customerId?: string;
    cursor?: string;
    status?: string;
    signal?: AbortSignal;
  } = {},
  fetcher: typeof fetch = fetch,
) {
  const params = new URLSearchParams({
    tenant_id: context.scope.tenant_id,
    workspace_operation_id: context.scope.store_id,
    operation: context.scope.operation,
  });
  if (
    !["customer", "customerOrders", "geography"].includes(resource) &&
    context.filters.from &&
    context.filters.to
  ) {
    params.set("from", context.filters.from);
    params.set("to", context.filters.to);
  }
  if (["customers", "orders", "customerOrders", "products"].includes(resource))
    params.set("page_size", "25");
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.status) params.set("status", options.status);
  const paths: Record<ReadResource, string> = {
    overview: "overview",
    orders: "orders",
    acquisition: "acquisition",
    customers: "customers",
    customer: `customers/${encodeURIComponent(options.customerId ?? "")}`,
    customerOrders: `customers/${encodeURIComponent(options.customerId ?? "")}/orders`,
    retention: "retention",
    products: "products",
    funnel: "funnel",
    geography: "geography",
  };
  const response = await fetcher(
    `/api/dashboard/${paths[resource]}?${params}`,
    { method: "GET", cache: "no-store", signal: options.signal },
  );
  if (!response.ok)
    throw new ApiError(
      response.status,
      response.status === 424
        ? "Cobertura ainda não certificada."
        : response.status === 400
          ? "Filtro ou cursor inválido. Reinicie a página."
          : "Leitura real indisponível.",
    );
  const envelope = decodeReadEnvelope(
    resource,
    await response.json(),
    options.customerId,
  );
  if (
    envelope.metadata.generation !== generation ||
    (options.expectedPolicyHash !== undefined &&
      envelope.metadata.policy_hash !== options.expectedPolicyHash)
  )
    throw new ApiError(
      409,
      "Publicação mudou. Atualize para reiniciar a paginação.",
    );
  return envelope;
}
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
  const context = ["customer", "customerOrders", "geography"].includes(resource)
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
      { ...options, policy_hash: metadata.policy_hash },
    ),
    queryFn: ({ signal }) =>
      readDashboard(resource, context, metadata.generation, {
        ...options,
        expectedPolicyHash: metadata.policy_hash,
        signal,
      }),
    retry: false,
  });
  useEffect(() => {
    if (result.error instanceof ApiError && result.error.status === 409)
      void client.invalidateQueries({ queryKey: publicationKey });
  }, [result.error, client, publicationKey]);
  return result;
}
