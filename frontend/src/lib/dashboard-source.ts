import type { DashboardDataMode, Scope } from "@/types/domain";
import type { ReadMetadata } from "@/services/api/http";
export type DashboardPageState = {
  path: string;
  scopeKey: string;
  source:
    | "demo"
    | "loading-real"
    | "real"
    | "partial-real"
    | "unavailable-real"
    | "error-real";
  metadata?: ReadMetadata;
};
export function isB2BReadPage(path: string) {
  return (
    [
      "/b2b",
      "/b2b/commercial",
      "/b2b/acquisition",
      "/b2b/retention",
      "/b2b/products",
      "/b2b/geography",
      "/b2b/performance",
      "/b2b/funnel",
      "/b2b/customers",
      "/b2b/repurchase",
      "/products",
      "/performance",
      "/media",
      "/campaigns",
      "/campaigns/meta",
      "/customers",
    ].includes(path) || /^\/(?:customers|campaigns)\/[^/]+$/.test(path)
  );
}
export function activePageState(
  path: string,
  mode: DashboardDataMode,
  scope: Scope | null,
  state: DashboardPageState | null,
) {
  if (
    mode !== "read-api-preview" ||
    scope?.operation !== "B2B" ||
    !isB2BReadPage(path)
  )
    return null;
  return state?.path === path &&
    state.scopeKey === `${scope.tenant_id}/${scope.store_id}/${scope.operation}`
    ? state
    : null;
}
export function dashboardSourceLabel(
  path: string,
  mode: DashboardDataMode,
  scope: Scope | null,
  state: DashboardPageState | null,
) {
  if (
    mode !== "read-api-preview" ||
    scope?.operation !== "B2B" ||
    !isB2BReadPage(path)
  )
    return "Dados demonstrativos";
  const current = activePageState(path, mode, scope, state);
  switch (current?.source) {
    case "demo":
      return "Dados demonstrativos";
    case "real":
      return current.metadata?.publication_domain === "intelligence"
        ? "Dados reais · Intelligence"
        : "Dados reais · Analytics V1";
    case "partial-real":
      return "Dados reais · Histórico parcial";
    case "unavailable-real":
      return "Cobertura ainda não disponível";
    case "error-real":
      return "Dados reais indisponíveis";
    default:
      return "Conectando dados reais";
  }
}
