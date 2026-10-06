"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
import { useRequestContext } from "@/hooks/use-resource";
import { dashboardReadKey, readDashboard } from "@/hooks/use-dashboard-read";
import { exclusiveToInclusive } from "@/lib/period";
import { managerPage } from "./registry";
export function aggregatePrefetchAllowed(path: string) {
  const page = managerPage(path);
  return Boolean(
    page &&
    page.path.startsWith("/b2b") &&
    ["overview", "acquisition", "retention", "funnel"].includes(
      page.resource,
    ) &&
    page.group !== "ERP" &&
    page.group !== "WhatsApp" &&
    !page.body,
  );
}
export function useAggregatePrefetch() {
  const client = useQueryClient(),
    base = useRequestContext(),
    { dataMode, dashboardPageState } = useWorkspace();
  return (path: string) => {
    const metadata = dashboardPageState?.metadata,
      page = managerPage(path);
    if (
      !page ||
      !aggregatePrefetchAllowed(path) ||
      dataMode !== "live" ||
      !metadata ||
      metadata.publication_domain === "intelligence" ||
      dashboardPageState?.scopeKey !==
        `${base.scope.tenant_id}/${base.scope.store_id}/${base.scope.operation}`
    )
      return;
    const context = {
      ...base,
      filters: {
        ...base.filters,
        from: base.filters.from ?? metadata.report_from,
        to: base.filters.to ?? exclusiveToInclusive(metadata.report_to),
      },
    };
    void client.prefetchQuery({
      queryKey: dashboardReadKey(
        dataMode,
        page.resource,
        context,
        metadata.generation,
        {
          policy_hash: metadata.policy_hash,
          publication_domain: "analytics-v1",
          intelligence_generation: null,
          analytics_generation: metadata.generation,
        },
      ),
      queryFn: ({ signal }) =>
        readDashboard(page.resource, context, metadata.generation, {
          expectedPolicyHash: metadata.policy_hash,
          signal,
        }),
      staleTime: 30000,
      retry: false,
    });
  };
}
