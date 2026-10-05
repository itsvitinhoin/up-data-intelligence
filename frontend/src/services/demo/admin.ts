import { platforms, erps } from "@/services/demo/types";
import type { Company, Session, User, Tenant } from "@/services/demo/types";
import { tenants } from "@/config/tenants";
import { ApiError } from "@/services/api/access";
export type MetaAccount = {
  meta_account_id: string;
  account_name: string;
  status: "AVAILABLE" | "LINKED";
  last_sync: string | null;
};
export const demoUsers: User[] = [
  {
    id: "up-admin",
    name: "Equipe UP",
    email: "admin@up.example",
    phone: "",
    role: "ADMIN",
    brand_id: null,
  },
  {
    id: "maria-demo",
    name: "Maria · demonstração",
    email: "maria@mx-fashion.example",
    phone: "",
    role: "VIEWER",
    brand_id: "demo-mx",
  },
  {
    id: "lume-demo",
    name: "Gestor Lume · demonstração",
    email: "gestor@lume.example",
    phone: "",
    role: "MANAGER",
    brand_id: "demo-lume",
  },
];
const brands: Company[] = tenants.flatMap((t) =>
  t.brands.map((b) => ({
    id: b.id,
    name: b.name,
    cnpj: "Não informado",
    logo: "",
    segment: "Moda",
    operation: b.operations.length === 2 ? "Ambos" : b.operations[0].type,
    status: "ACTIVE" as const,
    meta_account_id: null,
  })),
);
const accounts: MetaAccount[] = [
  {
    meta_account_id: "demo-meta-mx",
    account_name: "MX Fashion Ads Account · demo",
    status: "AVAILABLE",
    last_sync: null,
  },
  {
    meta_account_id: "demo-meta-lume",
    account_name: "Lume Ads Account · demo",
    status: "AVAILABLE",
    last_sync: null,
  },
];
let globalMetaConfigured = false;
export function assertUp(session: Session) {
  if (session.role !== "ADMIN" || session.id !== "up-admin")
    throw new ApiError(403, "Área exclusiva da UP.");
}
export function sessionFor(userId: string): Session {
  const u = demoUsers.find((u) => u.id === userId);
  if (!u) throw new ApiError(401, "Usuário demonstrativo não encontrado.");
  const allowed = tenants.flatMap((t) =>
    t.brands
      .filter((b) => u.role === "ADMIN" || b.id === u.brand_id)
      .map((b) => ({ tenant: t.id, brand: b })),
  );
  return {
    id: u.id,
    name: u.name,
    role: u.role,
    brand_id: u.brand_id,
    tenant_ids: [...new Set(allowed.map((a) => a.tenant))],
    store_ids: allowed.flatMap((a) => a.brand.operations.map((o) => o.id)),
  };
}
export function authorizedTenants(session: Session): Tenant[] {
  return tenants
    .map((t) => ({
      ...t,
      brands: t.brands
        .filter((b) => session.role === "ADMIN" || b.id === session.brand_id)
        .map((b) => ({
          ...b,
          operations: b.operations.filter((o) =>
            session.store_ids.includes(o.id),
          ),
        }))
        .filter((b) => b.operations.length),
    }))
    .filter((t) => session.tenant_ids.includes(t.id) && t.brands.length);
}
export const adminApi = {
  async brands(s: Session) {
    assertUp(s);
    return structuredClone(brands);
  },
  async users(s: Session) {
    assertUp(s);
    return structuredClone(demoUsers.filter((u) => u.role !== "ADMIN"));
  },
  async meta(s: Session) {
    assertUp(s);
    return {
      configured: globalMetaConfigured,
      accounts: globalMetaConfigured ? structuredClone(accounts) : [],
    };
  },
  async configureMetaDemo(s: Session) {
    assertUp(s);
    globalMetaConfigured = true;
  },
  async saveBrand(value: Company, s: Session) {
    assertUp(s);
    if (
      (value.platform && !platforms.includes(value.platform)) ||
      (value.erp && !erps.includes(value.erp))
    )
      throw new ApiError(400, "Plataforma ou ERP inválido.");
    if (
      value.integrations?.some(
        (i) =>
          ![
            "Plataforma",
            "Meta Ads",
            "Google Ads",
            "TikTok Ads",
            "ERP",
          ].includes(i.provider) ||
          typeof i.enabled !== "boolean" ||
          typeof i.accountId !== "string" ||
          i.accountId.length > 120 ||
          Object.keys(i).some(
            (k) => !["provider", "enabled", "accountId"].includes(k),
          ),
      )
    )
      throw new ApiError(400, "Configuração de integração inválida.");
    if (!value.name.trim()) throw new ApiError(400, "Informe a marca.");
    if (
      value.meta_account_id &&
      (!globalMetaConfigured ||
        !accounts.some((a) => a.meta_account_id === value.meta_account_id) ||
        brands.some(
          (b) =>
            b.id !== value.id && b.meta_account_id === value.meta_account_id,
        ))
    )
      throw new ApiError(400, "Conta indisponível ou vinculada a outra marca.");
    const index = brands.findIndex((b) => b.id === value.id);
    const stored = {
      ...value,
      createdAt:
        index < 0
          ? new Date().toISOString()
          : (brands[index].createdAt ?? null),
      activeConnections: index < 0 ? 0 : (brands[index].activeConnections ?? 0),
    };
    if (index < 0) {
      brands.push(structuredClone(stored));
      tenants.push({
        id: `tenant-${value.id}`,
        name: value.name,
        brands: [
          {
            id: value.id,
            name: value.name,
            operations: (value.operation === "Ambos"
              ? (["B2B", "B2C"] as const)
              : [value.operation]
            ).map((type) => ({
              id: `${value.id}-${type.toLowerCase()}`,
              type,
            })),
          },
        ],
      });
    } else brands[index] = structuredClone(stored);
    for (const account of accounts)
      account.status = brands.some(
        (b) => b.meta_account_id === account.meta_account_id,
      )
        ? "LINKED"
        : "AVAILABLE";
  },
  async saveUser(value: User, s: Session) {
    assertUp(s);
    if (
      value.role === "ADMIN" ||
      !brands.some((b) => b.id === value.brand_id) ||
      !value.name.trim() ||
      !value.email?.includes("@")
    )
      throw new ApiError(400, "Informe usuário, email, marca e perfil válido.");
    if (demoUsers.some((u) => u.id !== value.id && u.email === value.email))
      throw new ApiError(400, "Email já cadastrado.");
    const index = demoUsers.findIndex((u) => u.id === value.id);
    if (index < 0) demoUsers.push(structuredClone(value));
    else demoUsers[index] = structuredClone(value);
  },
};
