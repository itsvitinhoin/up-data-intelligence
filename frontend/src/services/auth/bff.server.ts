/** Server-owned service identity, user session and workspace resolution. */
import { serviceAuthorization } from "./service-identity.server";
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
import {
  parseIntegrationHealth,
  parseBrandSummaries,
} from "@/services/api/brand-integrations";

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
function servingOrigin(request: Request) {
  const url = new URL(request.url);
  if (process.env.K_SERVICE === "up-web") {
    // Cloud Run terminates TLS. Next standalone may build request.url with its
    // internal 0.0.0.0:$PORT hostname. Use the actual incoming serving authority,
    // never X-Forwarded-Host, and require this service's generated HTTPS host.
    const host = request.headers.get("host") ?? "";
    if (
      request.headers.get("x-forwarded-proto") !== "https" ||
      !/^up-web-[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app$/.test(host)
    )
      throw new Error("https_serving_origin_required");
    return "https://" + host;
  }
  if (url.protocol !== "https:") throw new Error("https_required");
  return url.origin;
}
export function assertCsrf(request: Request) {
  const expectedOrigin = servingOrigin(request);
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  if (origin !== expectedOrigin || (site !== null && site !== "same-origin"))
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
  try {
    servingOrigin(request);
  } catch {
    return authError(403, "https_required");
  }
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
  const started = performance.now();
  const authorization = await serviceAuthorization(url.origin);
  const identityReady = performance.now();
  // A fresh header set overwrites browser attempts to supply any service/user identity.
  const headers = new Headers({
    Authorization: authorization,
    "X-UP-Session": cookie(request, "__Host-up_session"),
    "Content-Type": "application/json",
  });
  const key = request.headers.get("idempotency-key");
  if (key) headers.set("Idempotency-Key", key);
  const response = await fetch(url.origin + path, {
    method: body !== undefined ? "POST" : "GET",
    body,
    headers,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(90000),
  });
  const headersOut = new Headers(response.headers);
  // Durations only. Never attach scope, credentials or upstream result data.
  headersOut.set(
    "Server-Timing",
    [
      ...(response.headers.get("Server-Timing") ?? "")
        .split(",")
        .map((v) => v.trim())
        .filter((v) =>
          /^(auth|bq|serialization|api_total);dur=\d+(\.\d+)?$/.test(v),
        ),
      `wif;dur=${(identityReady - started).toFixed(1)}`,
      `upstream;dur=${(performance.now() - identityReady).toFixed(1)}`,
    ].join(", "),
  );
  return new Response(response.body, {
    status: response.status,
    headers: headersOut,
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
import { decodeContactEnvelope } from "@/services/api/contact-contract";
const resources: Record<string, string> = {
  order: "orders",
  product: "products",
  customer: "customers",
  customerOrders: "customers",
  customerContact: "customers",
  customer360: "customers",
  timeline: "customers",
  customerProducts: "customers",
  customerCampaigns: "customers",
  campaign: "campaigns",
  campaignCustomers: "campaigns",
  campaignOrders: "campaigns",
  influencedCustomers: "customers/influenced",
  influencedOrders: "orders/influenced",
};
const suffixes: Record<string, string> = {
  customerOrders: "/orders",
  customerContact: "/contact",
  customer360: "/intelligence",
  timeline: "/timeline",
  customerProducts: "/products",
  customerCampaigns: "/campaigns",
  campaignCustomers: "/customers",
  campaignOrders: "/orders",
};
export async function liveRead(
  request: Request,
  resource: ReadResource | "installation" | "customerContact",
  entity?: string,
  call: PrivateCaller = privateCall,
) {
  const started = performance.now();
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
            "first_purchase",
          ].includes(k) || params.getAll(k).length !== 1,
      )
    )
      return authError(400, "invalid_read_scope");
    const scope = ["tenant_id", "workspace_operation_id", "operation"].map(
      (k) => params.get(k),
    );
    if (
      !scope
        .slice(0, 2)
        .every((v) => v && /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(v)) ||
      !["B2B", "B2C"].includes(scope[2] ?? "")
    )
      return authError(400, "invalid_read_scope");
    // The private API verifies the session and canonical tenant/workspace grant
    // before constructing any business reader. A second /v1/session roundtrip
    // adds no authorization evidence. Forward scope as a claim, never a grant.
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
    let value: unknown = await res.json();
    if (resource === "customerContact") {
      value = decodeContactEnvelope(value);
    } else if (resource === "installation") parseInstallation(value);
    else if (resource === "overview") decodeOverviewEnvelope(value);
    else decodeReadEnvelope(resource, value, entity);
    const upstreamTiming = res.headers.get("Server-Timing") ?? "";
    // Only our numeric diagnostic categories may reach the browser.
    const timing = upstreamTiming
      .split(",")
      .map((part) => part.trim())
      .filter((part) =>
        /^(auth|bq|wif|upstream|serialization|api_total);dur=\d+(\.\d+)?$/.test(
          part,
        ),
      );
    const serializationStart = performance.now();
    const body = JSON.stringify(value);
    const serializationDuration = performance.now() - serializationStart;
    timing.push(`bff;dur=${(performance.now() - started).toFixed(1)}`);
    timing.push(`bff_serialization;dur=${serializationDuration.toFixed(1)}`);
    return new Response(body, {
      headers: {
        ...secureHeaders,
        "Content-Type": "application/json",
        "Server-Timing": timing.join(", "),
      },
    });
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

export async function liveBrandSummaries(
  request: Request,
  call: PrivateCaller = privateCall,
) {
  if (request.method !== "GET") return authError(405, "method_not_allowed");
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  if (new URL(request.url).search) return authError(400, "unsupported_filter");
  try {
    // Private Read independently requires ADMIN_UP and uses only canonical grants.
    const res = await call("read", "/v1/admin/brands", request);
    const failure = await safeResult(res);
    if (failure) return failure;
    return Response.json(parseBrandSummaries(await res.json()), {
      headers: secureHeaders,
    });
  } catch {
    return authError(503, "brand_metadata_unavailable");
  }
}

export async function liveIntegrationHealth(
  request: Request,
  call: PrivateCaller = privateCall,
) {
  if (request.method !== "GET") return authError(405, "method_not_allowed");
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  const params = new URL(request.url).searchParams;
  if (
    [...params.keys()].some(
      (key) =>
        !["tenant_id", "workspace_operation_id", "operation"].includes(key) ||
        params.getAll(key).length !== 1,
    ) ||
    ["tenant_id", "workspace_operation_id"].some(
      (key) => !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(params.get(key) ?? ""),
    ) ||
    !["B2B", "B2C"].includes(params.get("operation") ?? "")
  )
    return authError(400, "invalid_admin_scope");
  try {
    const res = await call(
      "read",
      `/v1/admin/integrations/health?${params}`,
      request,
    );
    const failure = await safeResult(res);
    if (failure) return failure;
    const value = parseIntegrationHealth(await res.json());
    if (
      value.data.tenant_id !== params.get("tenant_id") ||
      value.data.workspace_operation_id !== params.get("workspace_operation_id")
    )
      return authError(503, "integration_metadata_scope_mismatch");
    return Response.json(value, { headers: secureHeaders });
  } catch {
    return authError(503, "integration_health_unavailable");
  }
}

export async function liveHistory(
  request: Request,
  call: PrivateCaller = privateCall,
) {
  if (!["GET", "POST"].includes(request.method))
    return authError(405, "method_not_allowed");
  if (request.method === "POST") {
    try {
      assertCsrf(request);
    } catch {
      return authError(403, "csrf_required");
    }
  }
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  const params = new URL(request.url).searchParams;
  if (
    [...params.keys()].some(
      (k) =>
        !["tenant_id", "workspace_operation_id", "operation"].includes(k) ||
        params.getAll(k).length !== 1,
    ) ||
    ["tenant_id", "workspace_operation_id"].some(
      (k) => !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(params.get(k) ?? ""),
    ) ||
    params.get("operation") !== "B2B"
  )
    return authError(400, "invalid_admin_scope");
  try {
    const { parseHistory } = await import("@/services/api/history");
    let body: string | undefined;
    if (request.method === "POST") {
      const parsed = await jsonBody(request, 4096);
      const value = parsed.value;
      if (
        !value ||
        typeof value !== "object" ||
        Object.keys(value).sort().join(",") !== "from,provider,to" ||
        !("provider" in value) ||
        !["upzero", "meta"].includes(String(value.provider)) ||
        !("from" in value) ||
        !("to" in value) ||
        ![value.from, value.to].every(
          (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v),
        )
      )
        return authError(400, "invalid_history_request");
      body = parsed.raw;
    }
    const res = await call(
      "admin",
      `/v1/admin/integrations/history?${params}`,
      request,
      body,
    );
    const failed = await safeResult(res);
    if (failed) return failed;
    const raw: unknown = await res.json();
    parseHistory(raw, request.method === "POST");
    return Response.json(raw, { status: res.status, headers: secureHeaders });
  } catch (error) {
    if (error instanceof InputError) return authError(error.status, error.code);
    return authError(503, "history_request_unconfirmed");
  }
}

export async function liveConnectionConfiguration(
  request: Request,
  call: PrivateCaller = privateCall,
) {
  if (!["GET", "POST"].includes(request.method))
    return authError(405, "method_not_allowed");
  if (request.method === "POST") {
    try {
      assertCsrf(request);
    } catch {
      return authError(403, "csrf_required");
    }
  }
  if (!cookie(request, "__Host-up_session"))
    return authError(401, "unauthenticated");
  const params = new URL(request.url).searchParams;
  if (
    [...params.keys()].some(
      (k) =>
        !["tenant_id", "workspace_operation_id", "operation"].includes(k) ||
        params.getAll(k).length !== 1,
    ) ||
    ["tenant_id", "workspace_operation_id"].some(
      (k) => !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(params.get(k) ?? ""),
    ) ||
    params.get("operation") !== "B2B"
  )
    return authError(400, "invalid_admin_scope");
  try {
    let body: string | undefined;
    if (request.method === "POST") {
      const key = request.headers.get("Idempotency-Key");
      if (
        !key ||
        !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(
          key,
        )
      )
        return authError(400, "invalid_idempotency_key");
      const parsed = await jsonBody(request, 16384),
        value = parsed.value;
      const addition =
        value &&
        typeof value === "object" &&
        "action" in value &&
        value.action === "add" &&
        Object.keys(value).sort().join(",") ===
          "account_id,action,api_version,provider" &&
        "provider" in value &&
        value.provider === "meta" &&
        "account_id" in value &&
        typeof value.account_id === "string" &&
        /^[0-9]+$/.test(value.account_id) &&
        "api_version" in value &&
        typeof value.api_version === "string" &&
        /^v[0-9]+\.0$/.test(value.api_version);
      if (
        !addition &&
        (!value ||
          typeof value !== "object" ||
          Object.keys(value).sort().join(",") !==
            "action,credential,provider" ||
          !("provider" in value) ||
          !["upzero", "meta"].includes(String(value.provider)) ||
          !("action" in value) ||
          !["rotate", "disable", "enable"].includes(String(value.action)))
      )
        return authError(400, "invalid_integration_request");
      body = parsed.raw;
    }
    const res = await call(
      "admin",
      `/v1/admin/integrations/configuration?${params}`,
      request,
      body,
    );
    const failed = await safeResult(res);
    if (failed) return failed;
    const { parseConnections, parseConnectionResult } =
      await import("@/services/api/connections");
    const value: unknown = await res.json();
    if (request.method === "GET") {
      const parsed = parseConnections(value);
      if (
        parsed.data.tenant_id !== params.get("tenant_id") ||
        parsed.data.workspace_operation_id !==
          params.get("workspace_operation_id")
      )
        return authError(503, "integration_scope_mismatch");
    } else parseConnectionResult(value);
    return Response.json(value, { headers: secureHeaders });
  } catch (error) {
    if (error instanceof InputError) return authError(error.status, error.code);
    return authError(503, "integration_change_unconfirmed");
  }
}
