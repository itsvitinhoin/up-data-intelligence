/** Explicit, loopback-only resource allowlist. No browser-selected upstream paths. */
import {
  intelligenceResources,
  type IntelligenceResource,
} from "./intelligence";
import { ApiError } from "./access";
import { inclusiveToExclusive, validDate } from "@/lib/period";
import {
  resolveDevOverviewBinding,
  toReadScope,
  type WorkspaceOperationScope,
} from "./preview-binding.server";
import { createServerDashboardReadApi, getDashboardDataMode } from "./server";
import type { ReadResource, ReadOptions } from "./http";
const headers = {
  "Cache-Control": "private, no-store",
  "X-Content-Type-Options": "nosniff",
};
const error = (status: number, code: string) =>
  Response.json({ error: { code } }, { status, headers });
export async function handleReadBridge(
  request: Request,
  resource: ReadResource,
  customerId?: string,
  dependencies: {
    mode?: typeof getDashboardDataMode;
    readApi?: typeof createServerDashboardReadApi;
  } = {},
) {
  if ((dependencies.mode ?? getDashboardDataMode)() !== "read-api-preview")
    return error(404, "preview_disabled");
  const url = new URL(request.url);
  if (!["127.0.0.1", "localhost"].includes(url.hostname))
    return error(403, "preview_loopback_required");
  const origin = request.headers.get("origin");
  if (
    (origin && origin !== url.origin) ||
    request.headers.get("sec-fetch-site") === "cross-site"
  )
    return error(403, "preview_same_origin_required");
  if (request.method !== "GET") return error(405, "method_not_allowed");
  const intelligence = intelligenceResources.includes(
    resource as IntelligenceResource,
  );
  const period =
    intelligence ||
    [
      "overview",
      "orders",
      "acquisition",
      "customers",
      "retention",
      "products",
      "funnel",
    ].includes(resource);
  const paged =
    (intelligence && !["performance", "customer360"].includes(resource)) ||
    ["orders", "customers", "customerOrders", "products"].includes(resource);
  const allowed = new Set([
    "tenant_id",
    "workspace_operation_id",
    "operation",
    ...(period ? ["from", "to"] : []),
    ...(paged ? ["page_size", "cursor"] : []),
    ...(resource === "orders" ? ["status"] : []),
  ]);
  const params = url.searchParams;
  if (
    [...params.keys()].some(
      (key) => !allowed.has(key) || params.getAll(key).length !== 1,
    )
  )
    return error(400, "invalid_preview_request");
  const scope: WorkspaceOperationScope = {
    tenant_id: params.get("tenant_id") ?? "",
    workspace_operation_id: params.get("workspace_operation_id") ?? "",
    operation: params.get("operation") as WorkspaceOperationScope["operation"],
  };
  if (
    !scope.tenant_id ||
    !scope.workspace_operation_id ||
    scope.operation !== "B2B"
  )
    return error(403, "preview_scope_forbidden");
  const binding = resolveDevOverviewBinding(scope);
  if (!binding) return error(404, "preview_binding_absent");
  if (
    [
      "customer",
      "customerOrders",
      "customer360",
      "timeline",
      "customerProducts",
      "campaign",
      "campaignCustomers",
      "campaignOrders",
    ].includes(resource) &&
    (!customerId ||
      customerId.length > 200 ||
      /[\/\r\n]/.test(customerId) ||
      !customerId.trim())
  )
    return error(400, "invalid_customer");
  const from = params.get("from"),
    to = params.get("to");
  if (
    (from === null) !== (to === null) ||
    (from !== null &&
      to !== null &&
      (!validDate(from) || !validDate(to) || from > to))
  )
    return error(400, "invalid_period");
  const size = params.get("page_size"),
    cursor = params.get("cursor"),
    status = params.get("status");
  if (
    (size !== null &&
      (!/^\d+$/.test(size) || Number(size) < 1 || Number(size) > 100)) ||
    (cursor !== null && (!cursor || cursor.length > 8192)) ||
    (status !== null && !/^[A-Z][A-Z0-9_]{0,49}$/.test(status))
  )
    return error(400, "invalid_preview_request");
  try {
    const api = (dependencies.readApi ?? createServerDashboardReadApi)();
    const options: ReadOptions = {
      from: from ?? undefined,
      to: to === null ? undefined : inclusiveToExclusive(to),
      pageSize: size === null ? undefined : Number(size),
      cursor: cursor ?? undefined,
      status: status ?? undefined,
      signal: request.signal,
    };
    const readScope = toReadScope(binding);
    const response = intelligence
      ? await api.intelligence(
          resource as IntelligenceResource,
          readScope,
          customerId,
          options,
        )
      : resource === "customer"
        ? await api.customer(readScope, customerId!, options)
        : resource === "customerOrders"
          ? await api.customerOrders(readScope, customerId!, options)
          : await api[
              resource as Exclude<
                ReadResource,
                IntelligenceResource | "customer" | "customerOrders"
              >
            ](readScope, options);
    return Response.json(response, { headers });
  } catch (cause) {
    if (cause instanceof ApiError) {
      if ([401, 403].includes(cause.status))
        return error(cause.status, "read_access_forbidden");
      if (cause.status === 404) return error(404, "read_entity_not_found");
      if (cause.status === 400)
        return error(400, "read_filter_or_cursor_invalid");
      if (cause.status === 424)
        return error(
          424,
          resource === "geography"
            ? "geography_coverage_not_certified"
            : "read_coverage_unavailable",
        );
    }
    return error(503, "read_temporarily_unavailable");
  }
}
