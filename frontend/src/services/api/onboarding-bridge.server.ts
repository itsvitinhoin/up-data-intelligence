/** Explicit local DEV only. Demo identity never becomes production ADMIN_UP. */
import { parseOnboarding } from "./onboarding";
export function onboardingDevEnabled() {
  return (
    process.env.NODE_ENV === "development" &&
    process.env.UP_ADMIN_ONBOARDING_DEV === "1"
  );
}
function configuration() {
  if (!onboardingDevEnabled()) return null;
  const base = process.env.UP_ADMIN_API_BASE_URL,
    token = process.env.UP_ADMIN_DEV_TOKEN;
  if (!base || !token || token.length < 32) return null;
  const url = new URL(base);
  if (
    url.protocol !== "http:" ||
    url.hostname !== "127.0.0.1" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  )
    return null;
  return { base, token };
}
const headers = {
  "Cache-Control": "private, no-store",
  "X-Content-Type-Options": "nosniff",
};
const error = (status: number, code: string) =>
  Response.json({ error: { code } }, { status, headers });
export async function handleOnboardingBridge(
  request: Request,
  operationId?: string,
  deps: {
    config?: () => { base: string; token: string } | null;
    fetcher?: typeof fetch;
  } = {},
) {
  try {
    const config = (deps.config ?? configuration)();
    if (!config) return error(404, "admin_preview_disabled");
    const url = new URL(request.url);
    const origin = request.headers.get("origin");
    if (
      !["127.0.0.1", "localhost"].includes(url.hostname) ||
      (origin
        ? origin !== url.origin
        : request.method !== "GET" ||
          request.headers.get("sec-fetch-site") !== "same-origin") ||
      request.headers.get("sec-fetch-site") === "cross-site"
    )
      return error(403, "admin_preview_origin_required");
    if (
      url.search ||
      (operationId ? request.method !== "GET" : request.method !== "POST")
    )
      return error(400, "invalid_admin_request");
    let body: string | undefined,
      key: string | null = null;
    if (operationId) {
      if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(operationId))
        return error(400, "invalid_operation_id");
    } else {
      key = request.headers.get("idempotency-key");
      if (!key || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(key))
        return error(400, "invalid_idempotency_key");
      if (
        request.headers.get("content-type")?.split(";", 1)[0] !==
        "application/json"
      )
        return error(415, "content_type_required");
      if (Number(request.headers.get("content-length")) > 32768)
        return error(413, "request_body_too_large");
      const reader = request.body?.getReader();
      if (!reader) return error(400, "invalid_admin_request");
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        while (true) {
          const next = await reader.read();
          if (next.done) break;
          size += next.value.length;
          if (size > 32768) {
            await reader.cancel();
            return error(413, "request_body_too_large");
          }
          chunks.push(next.value);
        }
        const bytes = new Uint8Array(size);
        let at = 0;
        for (const chunk of chunks) {
          bytes.set(chunk, at);
          at += chunk.length;
        }
        body = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } finally {
        reader.releaseLock();
        chunks.length = 0;
      }
    }
    try {
      const upstream = await (deps.fetcher ?? fetch)(
        new URL(
          `/v1/admin/onboarding${operationId ? `/${operationId}` : ""}`,
          config.base,
        ),
        {
          method: request.method,
          cache: "no-store",
          credentials: "omit",
          signal: request.signal,
          headers: {
            "Content-Type": "application/json",
            "X-UP-Admin-Preview-Token": config.token,
            ...(key ? { "Idempotency-Key": key } : {}),
          },
          body,
        },
      );
      if (!upstream.ok)
        return error(
          [400, 401, 403, 409, 413].includes(upstream.status)
            ? upstream.status
            : 503,
          "onboarding_not_completed",
        );
      return Response.json(parseOnboarding(await upstream.json()), {
        status: operationId ? 200 : 201,
        headers,
      });
    } finally {
      body = undefined;
    }
  } catch {
    return error(503, "onboarding_temporarily_unavailable");
  }
}
