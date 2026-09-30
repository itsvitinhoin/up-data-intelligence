import type {
  DataApi,
  RequestContext,
  Resource,
  ResourceMap,
} from "@/types/domain";
import { assertAccess, ApiError } from "./access";
/** Future transport. Never selected automatically and no credentials in public environment. */
export function createHttpApi(baseUrl: string): DataApi {
  async function request<T>(
    path: string,
    c: RequestContext,
    body?: unknown,
  ): Promise<T> {
    assertAccess(c, !!body);
    const url = new URL(path, baseUrl);
    url.searchParams.set("tenant_id", c.scope.tenant_id);
    url.searchParams.set("store_id", c.scope.store_id);
    Object.entries(c.filters).forEach(([k, v]) =>
      url.searchParams.set(k, String(v)),
    );
    const response = await fetch(url, {
      credentials: "include",
      signal: c.signal,
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok)
      throw new ApiError(
        response.status,
        "Não foi possível concluir a solicitação.",
      );
    return response.status === 204
      ? (undefined as T)
      : ((await response.json()) as T);
  }
  return {
    read<K extends Resource>(r: K, c: RequestContext) {
      return request<ResourceMap[K]>(
        `/v1/${["companies", "users", "integrations"].includes(r) ? "admin/" : ""}${r}`,
        c,
      );
    },
    campaign(id, c) {
      return request(`/v1/campaigns/${encodeURIComponent(id)}`, c);
    },
    order(id, c) {
      return request(`/v1/orders/${encodeURIComponent(id)}`, c);
    },
    customer(id, c) {
      return request(`/v1/customers/${encodeURIComponent(id)}`, c);
    },
    saveCompany(value, c) {
      return request("/v1/admin/companies", c, value);
    },
    saveIntegration(value, c) {
      return request("/v1/admin/integrations", c, value);
    },
    saveUser(value, c) {
      return request("/v1/admin/users", c, value);
    },
  };
}
