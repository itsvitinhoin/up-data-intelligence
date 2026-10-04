/** Server-owned service identity, user session and workspace resolution. */
import { GoogleAuth } from "google-auth-library";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { parseCatalog } from "./catalog";
import { inclusiveToExclusive } from "@/lib/period";
import {
  decodeReadEnvelope,
  decodeOverviewEnvelope,
  type ReadResource,
} from "@/services/api/http";
import { parseInstallation } from "@/services/api/installation";
import { parseOnboarding } from "@/services/api/onboarding";

export const secureHeaders = {
  "Cache-Control": "private, no-store",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
};
export const authError = (status: number, code: string) =>
  Response.json({ error: { code } }, { status, headers: secureHeaders });
export function cookie(request: Request, name: string) {
  const values = (request.headers.get("cookie") ?? "")
    .split(";")
    .map((v) => v.trim())
    .filter((v) => v.startsWith(name + "="));
  return values.length === 1 ? values[0].slice(name.length + 1) : "";
}
export function assertCsrf(request: Request) {
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  if (
    url.protocol !== "https:" ||
    origin !== url.origin ||
    (site !== null && site !== "same-origin")
  )
    throw new Error("csrf_origin_required");
  const c = cookie(request, "__Host-up_csrf"),
    t = request.headers.get("x-up-csrf") ?? "";
  if (
    !/^[a-f0-9]{64}$/.test(c) ||
    !/^[a-f0-9]{64}$/.test(t) ||
    !timingSafeEqual(Buffer.from(c), Buffer.from(t))
  )
    throw new Error("csrf_token_required");
}
export function csrfResponse(request: Request) {
  if (new URL(request.url).protocol !== "https:")
    return authError(403, "https_required");
  const value = randomBytes(32).toString("hex");
  return Response.json(
    { data: { csrf_token: value } },
    {
      headers: {
        ...secureHeaders,
        "Set-Cookie": `__Host-up_csrf=${value}; Secure; SameSite=Strict; Path=/; Max-Age=43200`,
      },
    },
  );
}
export type PrivateCaller = (
  target: "read" | "admin",
  path: string,
  request: Request,
  body?: string,
) => Promise<Response>;
export const privateCall: PrivateCaller = async (
  target,
  path,
  request,
  body,
) => {
  if (typeof window !== "undefined") throw new Error("server_only");
  const base =
    process.env[
      target === "read" ? "UP_READ_SERVICE_URL" : "UP_ADMIN_SERVICE_URL"
    ];
  if (!base) throw new Error("private_service_missing");
  const url = new URL(base);
  if (
    url.protocol !== "https:" ||
    !url.hostname.endsWith(".run.app") ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    url.username ||
    url.password
  )
    throw new Error("invalid_private_service");
  const auth = new GoogleAuth();
  const client = await auth.getIdTokenClient(url.origin);
  const identityHeaders = await client.getRequestHeaders(url.origin);
  // A fresh header set overwrites browser attempts to supply any service/user identity.
  const headers = new Headers({
    Authorization: identityHeaders.get("authorization") ?? "",
    "X-UP-Session": cookie(request, "__Host-up_session"),
    "Content-Type": "application/json",
  });
  const key = request.headers.get("idempotency-key");
  if (key) headers.set("Idempotency-Key", key);
  return fetch(url.origin + path, {
    method: body !== undefined ? "POST" : "GET",
    body,
    headers,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(90000),
  });
};
class InputError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}
async function jsonBody(
  request: Request,
  maximum: number,
): Promise<{ raw: string; value: unknown }> {
  if (request.headers.get("content-type")?.split(";")[0] !== "application/json")
    throw new InputError(400, "invalid_json_request");
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > maximum))
    throw new InputError(413, "request_too_large");
  const reader = request.body?.getReader();
  if (!reader) throw new InputError(400, "invalid_json_request");
  const chunks: Uint8Array[] = [];
  let bytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    bytes += value.byteLength;
    if (bytes > maximum) {
      await reader.cancel();
      throw new InputError(413, "request_too_large");
    }
    chunks.push(value);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  try {
    return { raw, value: JSON.parse(raw) };
  } catch {
    throw new InputError(400, "invalid_json_request");
  }
}
async function safeResult(response: Response) {
  if (!response.ok)
    return authError(
      response.status,
      [401, 403, 400, 404, 424, 409].includes(response.status)
        ? `product_http_${response.status}`
        : "product_temporarily_unavailable",
    );
  return null;
}
export async function sessionResponse(
  request: Request,
  call: PrivateCaller = privateCall,
) {
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  try {
    const res = await call("read", "/v1/session", request);
    const failed = await safeResult(res);
    if (failed) return failed;
    return Response.json(parseCatalog(await res.json()), {
      headers: secureHeaders,
    });
  } catch {
    return authError(503, "session_unavailable");
  }
}
export async function authMutation(
  request: Request,
  operation: "session" | "logout",
  call: PrivateCaller = privateCall,
) {
  if (request.method !== "POST") return authError(405, "method_not_allowed");
  try {
    assertCsrf(request);
  } catch {
    return authError(403, "csrf_required");
  }
  try {
    let body = "{}";
    if (operation === "session") {
      const { value } = await jsonBody(request, 16384);
      if (
        !value ||
        typeof value !== "object" ||
        !("id_token" in value) ||
        typeof value.id_token !== "string" ||
        Object.keys(value).length !== 1
      )
        return authError(400, "invalid_session_request");
      body = JSON.stringify(value);
    }
    const res = await call("admin", `/v1/auth/${operation}`, request, body);
    if (operation === "logout" && res.status === 401) {
      // Already expired/revoked sessions cannot authorize requests; remove the stale browser cookie.
      return Response.json(
        { data: { authenticated: false } },
        {
          headers: {
            ...secureHeaders,
            "Set-Cookie":
              "__Host-up_session=; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=0",
          },
        },
      );
    }
    const failed = await safeResult(res);
    if (failed) return failed;
    const setCookie = res.headers.get("set-cookie");
    const value = setCookie?.match(/^__Host-up_session=([A-Za-z0-9._-]*);/);
    if (!value || (operation === "session" && !value[1]))
      return authError(503, "session_exchange_invalid");
    return Response.json(
      { data: { authenticated: operation === "session" } },
      {
        headers: {
          ...secureHeaders,
          "Set-Cookie": `__Host-up_session=${value[1]}; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=${operation === "session" ? 43200 : 0}`,
        },
      },
    );
  } catch (error) {
    if (error instanceof InputError) return authError(error.status, error.code);
    return authError(503, "authentication_unavailable");
  }
}
const resources: Record<string, string> = {
  customer: "customers",
  customerOrders: "customers",
  customer360: "customers",
  timeline: "customers",
  customerProducts: "customers",
  campaign: "campaigns",
  campaignCustomers: "campaigns",
  campaignOrders: "campaigns",
  influencedCustomers: "customers/influenced",
  influencedOrders: "orders/influenced",
};
const suffixes: Record<string, string> = {
  customerOrders: "/orders",
  customer360: "/intelligence",
  timeline: "/timeline",
  customerProducts: "/products",
  campaignCustomers: "/customers",
  campaignOrders: "/orders",
};
export async function liveRead(
  request: Request,
  resource: ReadResource | "installation",
  entity?: string,
  call: PrivateCaller = privateCall,
) {
  if (request.method !== "GET") return authError(405, "method_not_allowed");
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  try {
    const params = new URL(request.url).searchParams;
    if (
      [...params.keys()].some(
        (k) =>
          ![
            "tenant_id",
            "workspace_operation_id",
            "operation",
            "from",
            "to",
            "page_size",
            "cursor",
            "status",
          ].includes(k) || params.getAll(k).length !== 1,
      )
    )
      return authError(400, "invalid_read_scope");
    const scope = ["tenant_id", "workspace_operation_id", "operation"].map(
      (k) => params.get(k),
    );
    const catalogRes = await call("read", "/v1/session", request);
    const failed = await safeResult(catalogRes);
    if (failed) return failed;
    const catalog = parseCatalog(await catalogRes.json());
    if (
      !catalog.data.workspaces.some(
        (w) =>
          w.tenant_id === scope[0] &&
          w.workspace_operation_id === scope[1] &&
          w.operation === scope[2],
      )
    )
      return authError(403, "workspace_forbidden");
    if (scope[2] !== "B2B") return authError(424, "coverage_not_certified");
    if (
      entity &&
      (!entity.trim() || entity.length > 200 || /[\/\r\n]/.test(entity))
    )
      return authError(400, "invalid_entity");
    if (params.has("to"))
      params.set("to", inclusiveToExclusive(params.get("to")!));
    const path =
      (resources[resource] ?? resource) +
      (entity
        ? `/${encodeURIComponent(entity)}${suffixes[resource] ?? ""}`
        : "");
    const res = await call("read", `/v1/dashboard/${path}?${params}`, request);
    const error = await safeResult(res);
    if (error) return error;
    const value: unknown = await res.json();
    if (resource === "installation") parseInstallation(value);
    else if (resource === "overview") decodeOverviewEnvelope(value);
    else decodeReadEnvelope(resource, value, entity);
    return Response.json(value, { headers: secureHeaders });
  } catch {
    return authError(503, "product_read_unavailable");
  }
}
export async function liveOnboarding(
  request: Request,
  operation?: string,
  call: PrivateCaller = privateCall,
) {
  if (request.method === "POST") {
    try {
      assertCsrf(request);
    } catch {
      return authError(403, "csrf_required");
    }
  }
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  try {
    const session = await call("read", "/v1/session", request);
    const failed = await safeResult(session);
    if (failed) return failed;
    const catalog = parseCatalog(await session.json());
    if (catalog.data.role !== "ADMIN_UP")
      return authError(403, "admin_up_required");
    if (
      new URL(request.url).search ||
      (operation && !/^[a-f0-9-]{36}$/.test(operation)) ||
      request.method !== (operation ? "GET" : "POST")
    )
      return authError(400, "invalid_admin_request");
    let body: string | undefined;
    if (!operation) {
      const parsed = await jsonBody(request, 32768);
      body = parsed.raw;
      const value = parsed.value;
      if (
        !value ||
        typeof value !== "object" ||
        !("tenant_id" in value) ||
        !catalog.data.tenants.includes(String(value.tenant_id))
      )
        return authError(403, "tenant_forbidden");
    }
    const res = await call(
      "admin",
      "/v1/admin/onboarding" + (operation ? "/" + operation : ""),
      request,
      body,
    );
    const failure = await safeResult(res);
    if (failure) return failure;
    return Response.json(parseOnboarding(await res.json()), {
      status: res.status,
      headers: secureHeaders,
    });
  } catch (error) {
    if (error instanceof InputError) return authError(error.status, error.code);
    return authError(503, "onboarding_unavailable");
  }
}
