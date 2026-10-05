/** Loopback-only DEV preview composition. Never imported by client components. */
import { createHttpApi } from "./http";
import type { DashboardDataMode } from "@/types/domain";

export function getDashboardDataMode(): DashboardDataMode {
  // The canonical deployed frontend cannot silently become a demo on missing live configuration.
  if (process.env.VERCEL === "1") return "live";
  if (process.env.DASHBOARD_DATA_MODE === "live") return "live";
  return process.env.NODE_ENV === "development" &&
    process.env.DASHBOARD_DATA_MODE === "read-api-preview"
    ? "read-api-preview"
    : "demo";
}

export function createServerDashboardReadApi(fetcher?: typeof fetch) {
  if (typeof window !== "undefined")
    throw new Error("Server-only read configuration");
  if (getDashboardDataMode() !== "read-api-preview")
    throw new Error("Dashboard read mode is not explicitly enabled");
  const baseUrl = process.env.DASHBOARD_READ_API_BASE_URL;
  const token = process.env.DASHBOARD_DEV_PREVIEW_TOKEN;
  if (!baseUrl || !token || token.length < 32)
    throw new Error("Dashboard preview server configuration is incomplete");
  const target = new URL(baseUrl);
  if (
    target.protocol !== "http:" ||
    target.hostname !== "127.0.0.1" ||
    target.username ||
    target.password ||
    target.pathname !== "/" ||
    target.search ||
    target.hash
  )
    throw new Error("Dashboard preview must use a loopback URL");
  const upstream = fetcher ?? fetch;
  const authorizedFetch: typeof fetch = (input, init) =>
    upstream(input, {
      ...init,
      credentials: "omit",
      headers: {
        ...init?.headers,
        "X-Dashboard-Preview-Token": token,
      },
    });
  return createHttpApi(baseUrl, authorizedFetch);
}
