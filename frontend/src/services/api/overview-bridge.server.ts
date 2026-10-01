/** Same-origin B2B Overview bridge; only the local DEV server receives the token. */
import { ApiError } from "./access";
import { inclusiveToExclusive, validDate } from "@/lib/period";
import {
  resolveDevOverviewBinding,
  toReadScope,
  type WorkspaceOperationScope,
} from "./preview-binding.server";
import { createServerDashboardReadApi, getDashboardDataMode } from "./server";

const noStore = {
  "Cache-Control": "private, no-store",
  "X-Content-Type-Options": "nosniff",
};
function error(status: number, code: string): Response {
  return Response.json({ error: { code } }, { status, headers: noStore });
}

export async function handleOverviewBridge(
  request: Request,
  dependencies: {
    mode?: typeof getDashboardDataMode;
    readApi?: typeof createServerDashboardReadApi;
  } = {},
): Promise<Response> {
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
  const params = url.searchParams;
  const allowed = new Set([
    "tenant_id",
    "workspace_operation_id",
    "operation",
    "from",
    "to",
  ]);
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
  const from = params.get("from"),
    to = params.get("to");
  if ((from === null) !== (to === null)) return error(400, "invalid_period");
  if (
    from !== null &&
    to !== null &&
    (!validDate(from) || !validDate(to) || from > to)
  )
    return error(400, "invalid_period");
  try {
    const api = (dependencies.readApi ?? createServerDashboardReadApi)();
    const response = await api.overview(toReadScope(binding), {
      from: from ?? undefined,
      to: to === null ? undefined : inclusiveToExclusive(to),
      signal: request.signal,
    });
    return Response.json(response, { headers: noStore });
  } catch (cause) {
    if (cause instanceof ApiError) {
      if (cause.status === 401 || cause.status === 403)
        return error(cause.status, "read_access_forbidden");
      if (cause.status === 400)
        return error(400, "interval_outside_publication");
      if (cause.status === 424) return error(424, "read_coverage_unavailable");
    }
    return error(503, "read_temporarily_unavailable");
  }
}
