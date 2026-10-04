import type { Session, Tenant } from "@/types/domain";
export type SessionCatalog = {
  data: {
    role: "ADMIN_UP" | "CLIENT_USER";
    tenants: string[];
    workspaces: {
      tenant_id: string;
      brand_id: string;
      workspace_operation_id: string;
      operation: "B2B" | "B2C";
    }[];
  };
};
export function parseCatalog(value: unknown): SessionCatalog {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    !("data" in value) ||
    Object.keys(value).length !== 1
  )
    throw new Error("invalid_session_catalog");
  const data = value.data;
  if (
    !data ||
    typeof data !== "object" ||
    Array.isArray(data) ||
    Object.keys(data).some(
      (k) => !["role", "tenants", "workspaces"].includes(k),
    ) ||
    !("role" in data) ||
    !["ADMIN_UP", "CLIENT_USER"].includes(String(data.role)) ||
    !("tenants" in data) ||
    !Array.isArray(data.tenants) ||
    data.tenants.length > 100 ||
    !data.tenants.every((t) => typeof t === "string" && t) ||
    new Set(data.tenants).size !== data.tenants.length ||
    !("workspaces" in data) ||
    !Array.isArray(data.workspaces) ||
    data.workspaces.length > 1000
  )
    throw new Error("invalid_session_catalog");
  const keys = new Set<string>();
  for (const w of data.workspaces) {
    if (
      !w ||
      typeof w !== "object" ||
      !["tenant_id", "brand_id", "workspace_operation_id", "operation"].every(
        (k) => typeof w[k] === "string" && w[k],
      ) ||
      !data.tenants.includes(w.tenant_id) ||
      !["B2B", "B2C"].includes(w.operation) ||
      Object.keys(w).some(
        (k) =>
          ![
            "tenant_id",
            "brand_id",
            "workspace_operation_id",
            "operation",
          ].includes(k),
      )
    )
      throw new Error("invalid_session_catalog");
    const key = `${w.tenant_id}/${w.workspace_operation_id}`;
    if (keys.has(key)) throw new Error("invalid_session_catalog");
    keys.add(key);
  }
  return value as SessionCatalog;
}
export function catalogView(catalog: SessionCatalog): {
  session: Session;
  tenants: Tenant[];
} {
  const { data } = catalog;
  const tenants: Tenant[] = data.tenants.map((t) => ({
    id: t,
    name: t,
    brands: [
      ...new Set(
        data.workspaces.filter((w) => w.tenant_id === t).map((w) => w.brand_id),
      ),
    ].map((b) => ({
      id: b,
      name: b.replace(/^brand-/, "").replaceAll("-", " "),
      operations: data.workspaces
        .filter((w) => w.tenant_id === t && w.brand_id === b)
        .map((w) => ({ id: w.workspace_operation_id, type: w.operation })),
    })),
  }));
  return {
    session: {
      id: "authenticated-session",
      name: data.role === "ADMIN_UP" ? "UP" : "Sua marca",
      role: data.role === "ADMIN_UP" ? "ADMIN" : "VIEWER",
      tenant_ids: data.tenants,
      store_ids: data.workspaces.map((w) => w.workspace_operation_id),
    },
    tenants,
  };
}
