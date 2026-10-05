/** Synthetic HTTP contracts for offline functional parity; never used by deployed live acceptance. */
export const metadata = {
  contract_version: "1.0.0",
  store_id: "synthetic-store",
  generation: 6,
  policy_hash: "a".repeat(64),
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-10-05T03:00:00Z",
  report_from: "2026-09-01",
  report_to: "2026-10-05",
  history_complete: false,
  facts_complete: true,
  limitations: [],
};
export const intelligenceMetadata = {
  ...metadata,
  publication_domain: "intelligence",
  generation: 4,
  analytics_generation: 6,
  publication_id: "b".repeat(64),
  meta_complete: true,
  influence_complete: false,
  customer_intelligence_complete: true,
  performance_complete: true,
};
export const customer = {
  store_id: metadata.store_id,
  customer_id: "synthetic-customer",
  customer_type: "B2B",
  name: "Comprador sintético",
  state: "SP",
  city: "Cidade sintética",
  purchases_observed: 1,
  first_purchase_at_observed: "2026-09-02T12:00:00Z",
  last_purchase_at_observed: "2026-09-02T12:00:00Z",
  requested_lifetime_observed: "50.01",
  fulfilled_lifetime_observed: null,
  ltv_complete: null,
};
export const order = {
  store_id: metadata.store_id,
  customer_id: customer.customer_id,
  order_id: "synthetic-order",
  created_at: "2026-09-02T12:00:00Z",
  order_status: "CONFIRMED",
  payment_status: "unpaid",
  requested_total: "50.01",
  fulfilled_total: null,
  requested_items_qty: 2,
  fulfilled_items_qty: null,
};
export const product = {
  store_id: metadata.store_id,
  product_key: "d".repeat(64),
  product_id: null,
  sku: "SKU-sintético",
  name: null,
  requested_revenue: "50.01",
  fulfilled_revenue: null,
  units_requested: "2",
  units_fulfilled: null,
  orders_observed: 1,
  buyers_unique: 1,
};
export const campaign = {
  record_key: "campaign-synthetic",
  campaign_id: "campaign-synthetic",
  campaign_name: "Campanha sintética",
  campaign_status: "ACTIVE",
  spend: "100.01",
  observed_spend: "100.01",
  impressions: 1000,
  clicks: 10,
  ctr: "1",
  cpc: "10.001",
  cpm: "100.01",
  influenced_customers: 1,
  influenced_orders: 1,
  requested_revenue_influenced: "50.01",
  fulfilled_revenue_influenced: null,
  roas_requested: null,
  roas_fulfilled: null,
};
export const performance = {
  meta_spend: "100.01",
  influenced_orders: 1,
  influenced_customers: 1,
  requested_revenue_influenced: "50.01",
  fulfilled_revenue_influenced: null,
  roas_requested: null,
  roas_fulfilled: null,
  new_customers_influenced: null,
  cac_new_customer: null,
  ctr: "1",
  cpc: "10.001",
  cpm: "100.01",
  impressions: 1000,
  clicks: 10,
  series: [
    {
      date: "2026-09-02",
      spend: "100.01",
      impressions: 1000,
      clicks: 10,
      influenced_orders: 1,
      requested_revenue_influenced: "50.01",
      fulfilled_revenue_influenced: null,
    },
  ],
};
export const overview = {
  requested_revenue: "50.01",
  fulfilled_revenue: null,
  fulfillment_gap: null,
  fulfillment_rate: null,
  cancelled_requested_revenue: "0.00",
  orders_requested: 1,
  orders_cancelled: 0,
  buyers_observed: 1,
  recurring_buyers_observed: 0,
  purchase_frequency_observed: "1",
  new_customers_confirmed: null,
  ltv_complete: null,
  cac: null,
  revenue_paid: null,
  series: [
    {
      date: "2026-09-02",
      requested: "50.01",
      fulfilled: null,
      orders: 1,
      new_customers_confirmed: null,
    },
  ],
};
export const retention = {
  buyers_observed: 1,
  recurring_buyers_observed: 0,
  retention_observed: "0",
  retention_ticket_observed: null,
  frequency_observed: "1",
  purchase_stages: [1, 2, 3, 4, 5].map((stage) => ({
    stage,
    buyers_observed: stage === 1 ? 1 : 0,
    share_observed: stage === 1 ? "1" : "0",
    continuation_observed: stage === 2 ? "0" : null,
    requested_revenue_observed: stage === 1 ? "50.01" : "0",
    accumulated_requested_revenue_observed: "50.01",
    mean_days_observed: null,
  })),
  series: [
    {
      date: "2026-09-02",
      buyers_observed: 1,
      recurring_buyers_observed: 0,
      retention_observed: "0",
      retention_ticket_observed: null,
    },
  ],
  progression: [1, 2, 3, 4].map((from_purchase) => ({
    from_purchase,
    to_purchase: from_purchase === 4 ? "5+" : String(from_purchase + 1),
    customers_reached_observed: 0,
    continuation_observed: from_purchase === 1 ? "0" : null,
    mean_days_observed: null,
    median_days_observed: null,
  })),
  cohorts: [
    {
      cohort_month: "2026-09-01",
      reporting_month: "2026-09-01",
      month: 0,
      buyers_observed: 1,
      rate: null,
      observed_rate: null,
      period_complete: false,
    },
  ],
};
export const orderDetail = {
  order,
  customer: {
    customer_id: customer.customer_id,
    name: customer.name,
    city: customer.city,
    state: customer.state,
    cnpj: null,
    email: null,
    phone: null,
  },
  items: [
    {
      item_id: "item-synthetic",
      product_key: product.product_key,
      product_id: null,
      asset_id: null,
      variant_id: "variant-synthetic",
      name: null,
      sku: product.sku,
      image: null,
      color: null,
      size: null,
      status: "active",
      requested_quantity: "2",
      fulfilled_quantity: null,
      unit_price: "25.005",
      requested_value: "50.010",
      fulfilled_value: null,
    },
  ],
  reconciliation: {
    item_value_basis: "line_gross_at_current_unit_price" as const,
    gross_requested: "50.010",
    gross_fulfilled: null,
    requested_order_adjustment: "0.000",
    fulfilled_order_adjustment: null,
    quantity_reconciled: null,
  },
};
export const productDetail = {
  ...product,
  variant_id: "variant-synthetic",
  image: null,
  stock: null,
  sizes: null,
  colors: null,
  abc: null,
  sell_through: null,
  revenue_basis: "line_gross_at_current_unit_price",
};
export const customerDetail = {
  profile: customer,
  commercial: {
    qualifying_orders_observed: 1,
    requested_revenue_observed: "50.01",
    fulfilled_revenue_observed: null,
    first_purchase_at_observed: customer.first_purchase_at_observed,
    last_purchase_at_observed: customer.last_purchase_at_observed,
    ltv_complete: null,
  },
};
export const customer360 = {
  profile: { customer_id: customer.customer_id },
  journey: {
    first_paid_touch_at: "2026-09-01T12:00:00Z",
    last_paid_touch_at: "2026-09-01T12:00:00Z",
  },
  marketing: ["LIFETIME", "ACQUISITION", "REPEAT_PURCHASE"].map(
    (influence_scope) => ({
      influence_scope,
      paid_media_influenced: influence_scope === "LIFETIME" ? true : null,
    }),
  ),
  health_score: null,
  health_status: null,
  health_policy: "NOT_DEFINED",
  ltv_complete: null,
};
export const timeline = [
  {
    record_key: "event-synthetic",
    event_name: "paid_touch",
    record_type: "FACT",
    occurred_at: "2026-09-01T12:00:00Z",
    channel: "meta",
    order_status: null,
    confidence_type: "DIRECT",
  },
];
export const customerProducts = [
  {
    record_key: "product-synthetic",
    product_key: product.product_key,
    product_id: null,
    sku: product.sku,
    requested_revenue: "50.01",
    fulfilled_revenue: null,
    requested_quantity: "2",
    fulfilled_quantity: null,
    orders_count: 1,
  },
];
export const campaignCustomers = [
  {
    record_key: "participation-customer-synthetic",
    campaign_id: campaign.campaign_id,
    customer_id: customer.customer_id,
    orders_influenced: 1,
    requested_revenue: "50.01",
    fulfilled_revenue: null,
  },
];
export const campaignOrders = [
  {
    record_key: "participation-order-synthetic",
    campaign_id: campaign.campaign_id,
    customer_id: customer.customer_id,
    order_id: order.order_id,
  },
];
export const influencedOrders = [
  {
    ...order,
    requested_items_qty: "2",
    fulfilled_items_qty: null,
    record_key: "influenced-order-synthetic",
    influence_scope: "LIFETIME",
    paid_media_influenced: true,
  },
];
export const geography = {
  states: [
    {
      state: "SP",
      customers: 1,
      orders: 1,
      requested_revenue: "50.01",
      fulfilled_revenue: null,
      average_ticket_requested: "50.01",
      new_customers: null,
      influenced_customers: null,
      approved_without_purchase: null,
      conversion_rate: null,
      top_cities: [
        {
          city: customer.city,
          customers: 1,
          orders: 1,
          requested_revenue: "50.01",
          fulfilled_revenue: null,
        },
      ],
    },
  ],
  coverage: {
    basis: "order_shipping_location" as const,
    orders_observed: 1,
    mapped_orders: 1,
    unmapped_orders: 0,
    orders_without_customer: 0,
  },
};
export function envelope(
  data: unknown,
  intelligence = false,
  cursor: string | null = null,
) {
  return {
    data,
    pagination: Array.isArray(data)
      ? { page_size: 100, cursor, has_more: cursor !== null }
      : null,
    metadata: intelligence ? intelligenceMetadata : metadata,
  };
}
