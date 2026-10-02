"use client";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
import { authorizedTenants } from "@/services/api";
import { ApiError } from "@/services/api/access";
import {
  installationPollingInterval,
  parseInstallation,
} from "@/services/api/installation";
import type { Scope, Session } from "@/types/domain";

export function installationKey(session: Session | null, scope?: Scope | null) {
  return [
    "installation",
    session?.id,
    session?.role,
    scope?.tenant_id,
    scope?.store_id,
    scope?.operation,
  ];
}
export async function readInstallation(
  scope: Scope,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
) {
  if (scope.operation !== "B2B")
    throw new ApiError(403, "Contrato B2B necessário.");
  const params = new URLSearchParams({
    tenant_id: scope.tenant_id,
    workspace_operation_id: scope.store_id,
    operation: scope.operation,
  });
  const response = await fetcher(`/api/dashboard/installation?${params}`, {
    method: "GET",
    cache: "no-store",
    credentials: "same-origin",
    signal,
  });
  if (response.status === 404) {
    const e: unknown = await response.json();
    if (
      e &&
      typeof e === "object" &&
      "error" in e &&
      e.error &&
      typeof e.error === "object" &&
      "code" in e.error &&
      e.error.code === "preview_binding_absent"
    )
      return null;
  }
  if (!response.ok)
    throw new ApiError(
      response.status,
      "Não foi possível verificar a instalação.",
    );
  return parseInstallation(await response.json());
}
export function useInstallation(suppliedScope?: Scope | null) {
  const { scope: current, session, dataMode } = useWorkspace();
  const scope = suppliedScope === undefined ? current : suppliedScope;
  const authorized =
    !!scope &&
    !!session &&
    authorizedTenants(session).some(
      (t) =>
        t.id === scope.tenant_id &&
        t.brands.some((b) =>
          b.operations.some(
            (o) => o.id === scope.store_id && o.type === scope.operation,
          ),
        ),
    );
  const enabled =
    dataMode === "read-api-preview" && scope?.operation === "B2B" && authorized;
  const result = useQuery({
    queryKey: installationKey(session, scope),
    queryFn: ({ signal }) => readInstallation(scope!, signal),
    enabled,
    retry: false,
    refetchInterval: (q) => installationPollingInterval(q.state.data?.data),
    refetchIntervalInBackground: false,
  });
  return { ...result, enabled };
}
