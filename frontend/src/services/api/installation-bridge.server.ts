import { liveRead } from "@/services/auth/bff.server";
/** DEV loopback only; production identity semantics are unchanged. */
import { createServerDashboardReadApi, getDashboardDataMode } from "./server";
import {
  resolveDevOverviewBinding,
  toReadScope,
  type WorkspaceOperationScope,
} from "./preview-binding.server";
import { ApiError } from "./access";
const headers = {
  "Cache-Control": "private, no-store",
  "X-Content-Type-Options": "nosniff",
};
const error = (status: number, code: string) =>
  Response.json({ error: { code } }, { status, headers });
export async function handleInstallationBridge(
  request: Request,
  dependencies: {
    mode?: typeof getDashboardDataMode;
    readApi?: typeof createServerDashboardReadApi;
  } = {},
) {
  if (getDashboardDataMode() === "live")
    return liveRead(request, "installation");

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
  const p = url.searchParams;
  if (
    [...p.keys()].some(
      (k) =>
        !["tenant_id", "workspace_operation_id", "operation"].includes(k) ||
        p.getAll(k).length !== 1,
    )
  )
    return error(400, "invalid_preview_request");
  const scope: WorkspaceOperationScope = {
    tenant_id: p.get("tenant_id") ?? "",
    workspace_operation_id: p.get("workspace_operation_id") ?? "",
    operation: p.get("operation") as WorkspaceOperationScope["operation"],
  };
  if (
    !scope.tenant_id ||
    !scope.workspace_operation_id ||
    scope.operation !== "B2B"
  )
    return error(403, "preview_scope_forbidden");
  const binding = resolveDevOverviewBinding(scope);
  if (!binding) return error(404, "preview_binding_absent");
  try {
    const result = await (
      dependencies.readApi ?? createServerDashboardReadApi
    )().installation(toReadScope(binding), { signal: request.signal });
    return Response.json(result, { headers });
  } catch (cause) {
    if (cause instanceof ApiError && [401, 403].includes(cause.status))
      return error(cause.status, "read_access_forbidden");
    // A configured binding with a missing registry is an operational failure, never demo fallback.
    return error(503, "installation_temporarily_unavailable");
  }
}
