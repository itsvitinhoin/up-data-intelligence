/** Optional server-side composition for a future authenticated DEV preview. */
import { createHttpApi } from "./http";

export function createServerDashboardReadApi(fetcher?: typeof fetch) {
  if (typeof window !== "undefined")
    throw new Error("Server-only read configuration");
  if (process.env.DASHBOARD_DATA_MODE !== "read-api")
    throw new Error("Dashboard read mode is not explicitly enabled");
  const baseUrl = process.env.DASHBOARD_READ_API_BASE_URL;
  if (!baseUrl) throw new Error("Dashboard read API URL is not configured");
  return createHttpApi(baseUrl, fetcher);
}
