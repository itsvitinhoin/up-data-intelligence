import type { Metric } from "@/types/domain";
import type { ReadMetadata, ReadResource } from "@/services/api/http";
import { MetricRegistry } from "./registry";
// Projection only: a semantic slot cannot borrow a different commercial state.
const fields: Partial<Record<ReadResource, Record<string, string>>> = {
  overview: {
    new_customers: "new_customers_confirmed",
    repurchasers: "recurring_buyers_observed",
  },
  acquisition: { new_customers: "confirmed_new_customers" },
  retention: {
    repurchasers: "recurring_buyers_observed",
    recurring_customers: "recurring_buyers_observed",
  },
  performance: {
    meta_spend: "meta_spend",
    total_media_spend: "meta_spend",
    roas_requested: "roas_requested",
    cac: "cac_new_customer",
  },
};
export function managerMetrics(
  ids: string[],
  resource: ReadResource,
  data: unknown,
  metadata?: ReadMetadata,
): Metric[] {
  const row =
    data && typeof data === "object" && !Array.isArray(data)
      ? (data as Record<string, unknown>)
      : {};
  return ids.map((id) => {
    const definition = MetricRegistry[id];
    if (!definition) throw new Error("Unregistered metric");
    const field = fields[resource]?.[id];
    // A platform-only spend is not certified total media spend. Paid metrics have no mapping.
    const supported =
      field &&
      id !== "total_media_spend" &&
      (!(id === "new_customers" || id === "cac") ||
        metadata?.history_complete === true);
    const raw = supported ? row[field] : null;
    const value =
      typeof raw === "string" && /^-?\d+(?:\.\d+)?$/.test(raw)
        ? raw
        : typeof raw === "number" && Number.isSafeInteger(raw)
          ? String(raw)
          : null;
    return {
      label: definition.label,
      value,
      format: definition.format,
      hint:
        value === null
          ? "Fonte ainda não disponível / cobertura ainda não certificada. Pagamento não é inferido de atendimento; aquisição definitiva exige histórico completo."
          : id === "repurchasers" || id === "recurring_customers"
            ? "Compradores recorrentes observados no período; histórico parcial não comprova lifetime."
            : "Métrica certificada pelo contrato da publicação selecionada.",
    };
  });
}
