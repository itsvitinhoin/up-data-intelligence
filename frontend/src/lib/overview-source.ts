import type { DashboardDataMode, Scope } from "@/types/domain";
import type { OverviewReadState } from "@/features/providers";

export function overviewSourceLabel(
  path: string,
  mode: DashboardDataMode,
  scope: Scope | null,
  state: OverviewReadState | null,
) {
  if (
    path !== "/b2b" ||
    mode !== "read-api-preview" ||
    scope?.operation !== "B2B"
  )
    return "Dados demonstrativos";
  if (
    state?.scopeKey !==
    `${scope.tenant_id}/${scope.store_id}/${scope.operation}`
  )
    return "Conectando dados reais";
  if (state.source === "real") return "Dados reais · Analytics V1";
  if (state.source === "error") return "Dados reais indisponíveis";
  if (state.source === "loading") return "Conectando dados reais";
  return "Dados demonstrativos";
}
