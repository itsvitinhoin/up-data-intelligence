/** Same-origin browser transport; the server resolves the technical store. */
import type { RequestContext } from "@/types/domain";
import { decodeReadEnvelope, type ReadResource } from "./http";
import {
  intelligenceResources,
  type IntelligenceResource,
} from "./intelligence";
import { ApiError } from "./access";
export async function readDashboard<K extends ReadResource>(
  resource: K,
  context: RequestContext,
  generation: number,
  options: {
    expectedPolicyHash?: string;
    expectedIntelligenceGeneration?: number;
    customerId?: string;
    cursor?: string;
    status?: string;
    firstPurchase?: boolean;
    signal?: AbortSignal;
    pageSize?: number;
    expectedStoreId?: string;
  } = {},
  fetcher: typeof fetch = fetch,
) {
  const intelligence = intelligenceResources.includes(
    resource as IntelligenceResource,
  );
  const params = new URLSearchParams({
    tenant_id: context.scope.tenant_id,
    workspace_operation_id:
      context.scope.workspace_operation_id ?? context.scope.store_id,
    operation: context.scope.operation,
  });
  if (
    !["customer", "customerOrders", "order"].includes(resource) &&
    context.filters.from &&
    context.filters.to
  ) {
    params.set("from", context.filters.from);
    params.set("to", context.filters.to);
  }
  if (
    (intelligence && !["customer360", "performance"].includes(resource)) ||
    ["customers", "orders", "customerOrders", "products"].includes(resource)
  )
    params.set("page_size", String(options.pageSize ?? 25));
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.status) params.set("status", options.status);
  if (options.firstPurchase !== undefined)
    params.set("first_purchase", String(options.firstPurchase));
  const paths: Record<ReadResource, string> = {
    performance: "performance",
    campaigns: "campaigns",
    campaign: `campaigns/${encodeURIComponent(options.customerId ?? "")}`,
    campaignCustomers: `campaigns/${encodeURIComponent(options.customerId ?? "")}/customers`,
    campaignOrders: `campaigns/${encodeURIComponent(options.customerId ?? "")}/orders`,
    customer360: `customers/${encodeURIComponent(options.customerId ?? "")}/intelligence`,
    timeline: `customers/${encodeURIComponent(options.customerId ?? "")}/timeline`,
    customerProducts: `customers/${encodeURIComponent(options.customerId ?? "")}/products`,
    customerCampaigns: `customers/${encodeURIComponent(options.customerId ?? "")}/campaigns`,
    influencedOrders: "orders/influenced",
    influencedCustomers: "customers/influenced",
    overview: "overview",
    orders: "orders",
    order: `orders/${encodeURIComponent(options.customerId ?? "")}`,
    product: `products/${encodeURIComponent(options.customerId ?? "")}`,
    acquisition: "acquisition",
    customers: "customers",
    customer: `customers/${encodeURIComponent(options.customerId ?? "")}`,
    customerOrders: `customers/${encodeURIComponent(options.customerId ?? "")}/orders`,
    retention: "retention",
    products: "products",
    funnel: "funnel",
    geography: "geography",
    creatives: "creatives",
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
    (options.expectedStoreId !== undefined &&
      envelope.metadata.store_id !== options.expectedStoreId) ||
    (intelligence
      ? envelope.metadata.analytics_generation !== generation
      : envelope.metadata.generation !== generation) ||
    (intelligence &&
      options.expectedIntelligenceGeneration !== undefined &&
      envelope.metadata.generation !==
        options.expectedIntelligenceGeneration) ||
    (options.expectedPolicyHash !== undefined &&
      envelope.metadata.policy_hash !== options.expectedPolicyHash)
  )
    throw new ApiError(
      409,
      "Publicação mudou. Atualize para reiniciar a paginação.",
    );
  return envelope;
}
