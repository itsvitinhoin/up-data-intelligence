/** Materialized #16 DTOs; money stays decimal text and unknown stays null. */
import { ApiError } from "./access";
export const intelligenceResources = [
  "customer360",
  "timeline",
  "customerProducts",
  "customerCampaigns",
  "performance",
  "campaigns",
  "campaign",
  "campaignCustomers",
  "campaignOrders",
  "influencedOrders",
  "influencedCustomers",
] as const;
export type IntelligenceResource = (typeof intelligenceResources)[number];
export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type IntelligenceRow = { [key: string]: JsonValue };
export type Customer360 = {
  profile: IntelligenceRow;
  journey: IntelligenceRow;
  marketing: IntelligenceRow[];
  health_score: null;
  health_status: null;
  health_policy: "NOT_DEFINED";
  ltv_complete: null;
};
export type IntelligenceResourceMap = {
  customer360: Customer360;
  performance: IntelligenceRow;
  timeline: IntelligenceRow[];
  customerProducts: IntelligenceRow[];
  customerCampaigns: IntelligenceRow[];
  campaigns: IntelligenceRow[];
  campaign: IntelligenceRow[];
  campaignCustomers: IntelligenceRow[];
  campaignOrders: IntelligenceRow[];
  influencedOrders: IntelligenceRow[];
  influencedCustomers: IntelligenceRow[];
};
const denied = new Set(
  "cpf cnpj email phone identity_path session_id visitor_id user_id fbclid fbc fbp gclid access_token raw payload".split(
    " ",
  ),
);
const monetary = new Set(
  "spend observed_spend meta_spend observed_meta_spend ctr cpc cpm roas_requested roas_fulfilled cac_new_customer fulfillment_rate requested_total fulfilled_total value ltv_observed total_requested_revenue total_fulfilled_revenue first_purchase_requested_revenue first_purchase_fulfilled_revenue requested_revenue fulfilled_revenue requested_revenue_influenced fulfilled_revenue_influenced".split(
    " ",
  ),
);
const counts = new Set(
  "impressions clicks influenced_orders influenced_customers new_customers_influenced purchase_count total_orders orders_count orders_influenced campaign_count paid_touch_count total_events total_sessions total_products_viewed total_cart_events total_checkout_events influenced_orders purchase_number".split(
    " ",
  ),
);
const flags = new Set(
  "paid_media_influenced acquisition_influenced repeat_purchase_influenced has_repurchase history_complete facts_complete is_new_customer previous_purchase_exists".split(
    " ",
  ),
);
function invalid(): never {
  throw new ApiError(503, "Contrato de inteligência inválido.");
}
function record(v: unknown): IntelligenceRow {
  if (!v || typeof v !== "object" || Array.isArray(v)) return invalid();
  const result: IntelligenceRow = {};
  for (const [k, value] of Object.entries(v)) {
    if (denied.has(k)) return invalid();
    if (
      counts.has(k) &&
      value !== null &&
      (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    )
      return invalid();
    if (flags.has(k) && value !== null && typeof value !== "boolean")
      return invalid();
    if (
      monetary.has(k) &&
      value !== null &&
      (typeof value !== "string" || !/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value))
    )
      return invalid();
    result[k] = json(value);
  }
  return result;
}
function json(v: unknown): JsonValue {
  if (v === null || typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (Array.isArray(v)) return v.map(json);
  return record(v);
}
export function parseIntelligence<K extends IntelligenceResource>(
  resource: K,
  value: unknown,
  entity?: string,
): IntelligenceResourceMap[K] {
  let result: Customer360 | IntelligenceRow | IntelligenceRow[];
  if (resource === "customer360") {
    const row = record(value);
    if (
      row.health_score !== null ||
      row.health_status !== null ||
      row.health_policy !== "NOT_DEFINED" ||
      row.ltv_complete !== null ||
      !Array.isArray(row.marketing)
    )
      return invalid();
    const profile = record(row.profile),
      journey = record(row.journey);
    if (profile.customer_id !== entity) return invalid();
    const marketing = row.marketing.map(record);
    if (
      marketing.length !== 3 ||
      new Set(marketing.map((r) => r.influence_scope)).size !== 3 ||
      marketing.some(
        (r) =>
          !["LIFETIME", "ACQUISITION", "REPEAT_PURCHASE"].includes(
            String(r.influence_scope),
          ),
      )
    )
      return invalid();
    result = {
      profile,
      journey,
      marketing,
      health_score: null,
      health_status: null,
      health_policy: "NOT_DEFINED",
      ltv_complete: null,
    };
  } else if (resource === "performance") {
    result = record(value);
    for (const k of [
      "meta_spend",
      "influenced_orders",
      "influenced_customers",
      "requested_revenue_influenced",
      "fulfilled_revenue_influenced",
      "roas_requested",
      "roas_fulfilled",
      "new_customers_influenced",
      "cac_new_customer",
    ])
      if (!(k in result)) return invalid();
    if ("series" in result) {
      if (!Array.isArray(result.series) || result.series.length > 366)
        return invalid();
      const dates = new Set<string>();
      for (const raw of result.series) {
        const row = record(raw);
        if (
          typeof row.date !== "string" ||
          !/^\d{4}-\d{2}-\d{2}$/.test(row.date) ||
          dates.has(row.date)
        )
          return invalid();
        dates.add(row.date);
        for (const k of [
          "spend",
          "impressions",
          "clicks",
          "influenced_orders",
          "requested_revenue_influenced",
          "fulfilled_revenue_influenced",
        ])
          if (!(k in row)) return invalid();
      }
    }
  } else {
    if (!Array.isArray(value)) return invalid();
    result = value.map(record);
    const identifiers: Partial<Record<IntelligenceResource, string[]>> = {
      campaigns: ["campaign_id"],
      customerCampaigns: ["campaign_id"],
      campaign: ["campaign_id"],
      campaignCustomers: ["campaign_id", "customer_id"],
      campaignOrders: ["campaign_id", "customer_id", "order_id"],
      influencedCustomers: ["customer_id"],
      influencedOrders: ["customer_id", "order_id"],
      customerProducts: ["product_key"],
      timeline: ["event_name", "record_type"],
    };
    for (const row of result) {
      for (const key of identifiers[resource] ?? []) {
        if (typeof row[key] !== "string" || !row[key].trim()) return invalid();
      }
      if (
        resource === "timeline" &&
        (typeof row.occurred_at !== "string" ||
          !Number.isFinite(Date.parse(row.occurred_at)))
      )
        return invalid();
      if (
        resource === "customerProducts" &&
        row.product_id !== null &&
        typeof row.product_id !== "string"
      )
        return invalid();
      if (
        ["influencedCustomers", "influencedOrders"].includes(resource) &&
        row.influence_scope !== "LIFETIME"
      )
        return invalid();
    }
    if (
      ["campaignCustomers", "campaignOrders", "campaign"].includes(resource) &&
      result.some((r) => r.campaign_id !== entity)
    )
      return invalid();
  }
  // Every value was validated above. This cast selects the concrete parser result, never a raw response.
  return result as IntelligenceResourceMap[K];
}
