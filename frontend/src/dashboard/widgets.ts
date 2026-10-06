import type { ReadResource } from "@/services/api/http";
import type { GapCategory } from "./bindings";
export type WidgetBinding = {
  resources: ReadResource[];
  metricIds: string[];
  category: GapCategory;
  reason: string;
};
const binding = (
  resources: ReadResource[],
  metricIds: string[] = [],
  category: GapCategory = "A",
  reason = "GENERATION_PINNED_READ_MODEL",
): WidgetBinding => ({ resources, metricIds, category, reason });
export const WidgetBindings: Readonly<Record<string, WidgetBinding>> = {
  "commercial-trend": binding(["overview"]),
  "paid-media-trend": binding(
    ["performance"],
    ["meta_spend", "revenue_paid"],
    "D",
    "PAYMENT_SOURCE_NOT_CERTIFIED · Meta spend existe; receita paga não é receita atendida.",
  ),
  "acquisition-retention": binding(
    ["acquisition", "retention"],
    [
      "new_requested_observed",
      "new_orders_observed",
      "recurring_fulfilled_observed",
      "recurring_orders_observed",
    ],
  ),
  funnel: binding(
    ["funnel", "performance", "overview", "acquisition"],
    [
      "meta_impressions",
      "meta_clicks",
      "meta_link_clicks",
      "meta_reach_campaign_day_sum",
      "sessions",
      "facts_product_views",
      "registrations",
      "approved_registrations",
      "add_to_cart",
      "checkout_started",
      "facts_purchase",
      "facts_purchase_items",
      "approval_rate",
      "session_to_cart_rate",
      "cart_to_checkout_rate",
      "checkout_to_sale_rate",
    ],
  ),
  "new-revenue-ticket": binding(
    ["acquisition"],
    ["new_requested_observed", "new_ticket_observed"],
  ),
  "new-sales-customers": binding(
    ["acquisition"],
    ["new_orders_observed", "new_customers"],
  ),
  "investment-cac": binding(
    ["performance"],
    ["meta_spend", "cac"],
    "C",
    "REQUIRES_HISTORICAL_BACKFILL · CAC definitivo exige novos clientes lifetime.",
  ),
  "approved-conversion": binding(
    ["acquisition"],
    ["approved_registrations", "approved_conversion"],
    "A",
    "REGISTRATION_CUSTOMER_IDENTITY_NOT_CERTIFIED",
  ),
  "registration-cohort": binding(
    [],
    [],
    "A",
    "REGISTRATION_CUSTOMER_IDENTITY_NOT_CERTIFIED · contagens operacionais não são cohort de cadastro.",
  ),
  "repeat-revenue-ticket": binding(
    ["retention"],
    ["recurring_fulfilled_observed", "recurring_ticket_observed"],
  ),
  "recurring-reactivated": binding(
    ["retention"],
    ["recurring_customers", "reactivated_customers"],
    "C",
    "REQUIRES_HISTORICAL_BACKFILL · reativação definitiva exige histórico e definição de inatividade.",
  ),
  "repurchase-cohort": binding(["retention"]),
  "purchase-progression": binding(["retention"]),
  "journey-guidance": binding([
    "customers",
    "customer360",
    "timeline",
    "customerCampaigns",
  ]),
  "monthly-history": binding(["overview", "performance", "funnel"]),
  "provider-unavailable": binding(
    [],
    [],
    "D",
    "REQUIRES_NEW_CONNECTOR · ERP/WhatsApp não conectados.",
  ),
  "retail-overview": binding(
    [],
    [],
    "D",
    "B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE",
  ),
  "retail-retention": binding(
    [],
    [],
    "D",
    "B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE",
  ),
  "retail-platforms": binding(
    [],
    [],
    "D",
    "B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE",
  ),
  "retail-funnel": binding([], [], "D", "B2C_EXPLICIT_LOCAL_SYNTHETIC_FIXTURE"),
  forecast: binding([], [], "A", "FORECAST_BUSINESS_CONTRACT_NOT_CERTIFIED"),
};

/** Reused V1 bodies have certified read resources and on-demand detail boundaries. */
export const BodyBindings: Readonly<
  Record<
    string,
    {
      resources: ReadResource[];
      fields: string[];
      privateDetailFields?: string[];
    }
  >
> = {
  overview: {
    resources: ["overview", "acquisition", "retention"],
    fields: [
      "requested_revenue",
      "fulfilled_revenue",
      "fulfillment_rate",
      "fulfillment_gap",
      "leads_generated",
      "leads_approved",
      "lead_qualification_rate",
      "approved_conversion_rate",
      "purchase_frequency_observed",
      "ltv_complete",
      "series",
    ],
  },
  orders: {
    resources: ["orders", "order"],
    fields: [
      "order_id",
      "created_at",
      "order_status",
      "payment_status",
      "requested_total",
      "fulfilled_total",
      "requested_items_qty",
      "fulfilled_items_qty",
      "items",
    ],
    privateDetailFields: ["order_snapshot", "current_core_profile"],
  },
  customers: {
    resources: ["customers", "customer360", "timeline"],
    fields: [
      "customer_id",
      "purchases_observed",
      "requested_lifetime_observed",
      "fulfilled_lifetime_observed",
      "first_purchase_at_observed",
      "last_purchase_at_observed",
      "timeline",
    ],
    privateDetailFields: ["current_core_profile"],
  },
  products: {
    resources: ["products", "product"],
    fields: [
      "name",
      "reference",
      "requested_revenue",
      "fulfilled_revenue",
      "units_requested",
      "units_fulfilled",
      "orders",
      "buyers_unique",
      "catalog",
      "image",
    ],
  },
  stock: {
    resources: ["products", "product"],
    fields: [
      "catalog.current_stock",
      "catalog.variants",
      "catalog.grade",
      "catalog.color_hex",
    ],
  },
  geography: {
    resources: ["geography"],
    fields: [
      "state",
      "cities",
      "customers",
      "orders",
      "requested_revenue",
      "fulfilled_revenue",
      "requested_ticket",
    ],
  },
  campaigns: {
    resources: ["campaigns", "creatives"],
    fields: [
      "campaign_id",
      "campaign_name",
      "spend",
      "impressions",
      "clicks",
      "ctr",
      "cpc",
      "cpm",
      "preview",
      "actions",
      "frequency",
    ],
  },
  "retail-orders": {
    resources: [],
    fields: ["demo.orders", "demo.captured", "demo.approved", "demo.cancelled"],
  },
  "retail-products": {
    resources: [],
    fields: ["demo.products", "demo.stock", "demo.color", "demo.size"],
  },
  "retail-stock": {
    resources: [],
    fields: ["demo.products", "demo.stock", "demo.color", "demo.size"],
  },
};
