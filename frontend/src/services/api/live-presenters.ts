/** Certified transport → original UI. Unknown values remain null. */
import type {
  Customer,
  Order,
  OrderDetail,
  Product,
  Campaign,
  TimelineEvent,
  Geography,
  Lifecycle,
  RetentionSummary,
} from "@/types/domain";
import type {
  LiveCustomer,
  LiveOrder,
  LiveProduct,
  LiveRetention,
  ReadMetadata,
} from "./http";
import type {
  LiveOrderDetail,
  LiveProductDetail,
  LiveGeography,
} from "./product-contracts";
import type { IntelligenceRow } from "./intelligence";
import { ApiError } from "./access";
export const unavailable = () =>
  new ApiError(424, "Cobertura ainda não certificada.");
export function rowText(r: IntelligenceRow, key: string): string | null {
  const v = r[key];
  if (v === null || v === undefined) return null;
  if (typeof v !== "string")
    throw new ApiError(502, "Projeção textual inválida.");
  return v;
}
export function rowCount(r: IntelligenceRow, key: string): number | null {
  const v = r[key];
  if (v === null || v === undefined) return null;
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < 0)
    throw new ApiError(502, "Projeção quantitativa inválida.");
  return v;
}
export function rowFlag(r: IntelligenceRow, key: string): boolean | null {
  const v = r[key];
  if (v === null || v === undefined) return null;
  if (typeof v !== "boolean")
    throw new ApiError(502, "Projeção de cobertura inválida.");
  return v;
}
export function requiredText(r: IntelligenceRow, key: string): string {
  const v = rowText(r, key);
  if (!v) throw new ApiError(502, "Identidade não comprovada.");
  return v;
}
export function decimalQuantity(v: string | null): number | null {
  if (v === null) return null;
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > Number.MAX_SAFE_INTEGER)
    throw new ApiError(502, "Quantidade inválida.");
  return n;
}
/** Conversion to number is restricted to visual chart/ratio coordinates, never monetary transport or aggregation. */
export const chartValue = (v: string | null) => (v === null ? null : Number(v));
export function customerView(r: LiveCustomer): Customer {
  return {
    id: r.customer_id,
    name: r.name,
    city: r.city,
    state: r.state,
    orders: r.purchases_observed,
    requested: r.requested_lifetime_observed,
    fulfilled: r.fulfilled_lifetime_observed ?? null,
    firstPurchase: r.first_purchase_at_observed,
    lastPurchase: r.last_purchase_at_observed ?? null,
    segment:
      r.purchases_observed === null
        ? null
        : r.purchases_observed > 1
          ? "Recorrente"
          : "Primeira observada",
    paid: null,
  };
}
export function orderView(r: LiveOrder): Order {
  return {
    id: r.order_id,
    customer_id: r.customer_id,
    date: r.created_at,
    requested: r.requested_total,
    fulfilled: r.fulfilled_total,
    requestedQuantity: r.requested_items_qty,
    fulfilledQuantity: r.fulfilled_items_qty,
    status: r.order_status,
    paid: null,
  };
}
export function orderDetailView(r: LiveOrderDetail): OrderDetail {
  return {
    order: orderView(r.order),
    customer:
      r.customer === null
        ? null
        : { ...r.customer, id: r.customer.customer_id },
    items: r.items.map((i) => ({
      product_id: i.product_id,
      product_key: i.product_key,
      name: i.name,
      sku: i.sku,
      reference: i.reference,
      image: i.image,
      color: i.color,
      size: i.size,
      unitPrice: i.unit_price,
      requestedQuantity: decimalQuantity(i.requested_quantity),
      fulfilledQuantity: decimalQuantity(i.fulfilled_quantity),
      requested: i.requested_value,
      fulfilled: i.fulfilled_value,
    })),
    reconciliation: {
      requestedOrderAdjustment: r.reconciliation.requested_order_adjustment,
      fulfilledOrderAdjustment: r.reconciliation.fulfilled_order_adjustment,
      quantityReconciled: r.reconciliation.quantity_reconciled,
    },
  };
}
export function productView(r: LiveProduct | LiveProductDetail): Product {
  return {
    id: r.product_key,
    canonicalProductId: r.product_id,
    reference: r.reference ?? null,
    catalog: r.catalog ?? null,
    name: r.name,
    sku: r.sku,
    variantId: "variant_id" in r ? r.variant_id : null,
    image: "image" in r ? r.image : null,
    requested: r.requested_revenue,
    fulfilled: r.fulfilled_revenue,
    units: decimalQuantity(r.units_requested),
    orders: r.orders_observed,
    customers: r.buyers_unique,
    share: null,
    sizes: null,
    abc: null,
    views: null,
    cart: null,
    checkout: null,
    stock: "stock" in r ? decimalQuantity(r.stock) : null,
    variants:
      "variants" in r && r.variants
        ? r.variants.map((v) => ({
            color: v.color,
            size: v.size,
            sku: v.sku,
            stock: decimalQuantity(v.stock),
            hex: v.color_hex,
          }))
        : "size" in r && r.size && r.catalog
          ? [
              {
                color: r.color ?? null,
                size: r.size,
                sku: r.sku,
                stock: decimalQuantity(r.stock),
                hex: r.color_hex ?? null,
              },
            ]
          : undefined,
    variantSales:
      "variants" in r && r.variants
        ? r.variants.map((v) => ({
            color: v.color,
            size: v.size,
            units: decimalQuantity(v.units_fulfilled),
          }))
        : undefined,
    variantSalesBasis:
      "variants" in r && r.variants
        ? "observed_line_gross_current_catalog"
        : undefined,
    sellThrough: null,
    turnover: null,
    coverage: null,
    color: "color" in r ? (r.color ?? null) : null,
    active: "active" in r ? (r.active ?? null) : null,
    salePrice: "sale_price" in r ? (r.sale_price ?? null) : null,
    category: null,
    colorHex: "color_hex" in r ? (r.color_hex ?? null) : null,
  };
}
export function campaignView(r: IntelligenceRow): Campaign {
  return {
    id: requiredText(r, "campaign_id"),
    name: rowText(r, "campaign_name"),
    spend: rowText(r, "spend"),
    customers: rowCount(r, "influenced_customers"),
    newCustomers: null,
    orders: rowCount(r, "influenced_orders"),
    requested: rowText(r, "requested_revenue_influenced"),
    fulfilled: rowText(r, "fulfilled_revenue_influenced"),
    roasRequested: rowText(r, "roas_requested"),
    roasFulfilled: rowText(r, "roas_fulfilled"),
    cac: null,
  };
}
export function intelligenceOrderView(r: IntelligenceRow): Order {
  return {
    id: requiredText(r, "order_id"),
    customer_id: rowText(r, "customer_id"),
    date: requiredText(r, "created_at"),
    status: rowText(r, "order_status"),
    requested: rowText(r, "requested_total"),
    fulfilled: rowText(r, "fulfilled_total"),
    requestedQuantity: decimalQuantity(rowText(r, "requested_items_qty")),
    fulfilledQuantity: decimalQuantity(rowText(r, "fulfilled_items_qty")),
    paid: rowFlag(r, "paid_media_influenced"),
  };
}
export function timelineView(
  r: IntelligenceRow,
  customerId: string,
  m: ReadMetadata,
): TimelineEvent {
  const type = requiredText(r, "event_name");
  return {
    id: requiredText(r, "record_key"),
    customer_id: customerId,
    store_id: m.store_id,
    type,
    date: requiredText(r, "occurred_at"),
    title:
      (
        {
          register_submitted: "Cadastro enviado",
          register_approved: "Cadastro aprovado",
          session: "Sessão observada",
          product_view: "Produto visualizado",
          add_to_cart: "Produto adicionado ao carrinho",
          cart_created: "Carrinho criado",
          checkout_started: "Checkout iniciado",
          order_created: "Pedido criado",
          order_status_change: "Status do pedido atualizado",
          purchase: "Compra observada",
          repeat_purchase: "Recompra observada",
          purchase_item: "Item de compra observado",
          paid_touch: "Touchpoint de mídia observado",
        } as Record<string, string>
      )[type] ?? type,
    orderId: rowText(r, "order_id"),
    productId: rowText(r, "product_id"),
    variantId: rowText(r, "variant_id"),
    campaignId: rowText(r, "campaign_id"),
    adsetId: rowText(r, "adset_id"),
    adId: rowText(r, "ad_id"),
    detail: [
      rowText(r, "channel"),
      rowText(r, "order_status"),
      ...["campaign_id", "adset_id", "ad_id"].flatMap((key) => {
        const value = rowText(r, key);
        const label = {
          campaign_id: "Campanha",
          adset_id: "Conjunto",
          ad_id: "Anúncio",
        }[key];
        return value ? [`${label}: ${value}`] : [];
      }),
    ]
      .filter((v) => v !== null)
      .join(" · "),
    evidence: r.confidence_type === "DIRECT" ? "DIRECT" : "SUPPORTED",
  };
}
export function customerProductView(
  r: IntelligenceRow,
  metadata: ReadMetadata,
): Product {
  return productView({
    store_id: metadata.store_id,
    product_key: requiredText(r, "product_key"),
    product_id: rowText(r, "product_id"),
    name: null,
    sku: rowText(r, "sku"),
    requested_revenue: rowText(r, "requested_revenue"),
    fulfilled_revenue: rowText(r, "fulfilled_revenue"),
    units_requested: rowText(r, "requested_quantity"),
    units_fulfilled: rowText(r, "fulfilled_quantity"),
    orders_observed: rowCount(r, "orders_count"),
    buyers_unique: null,
  });
}
export function geographyView(r: LiveGeography): Geography[] {
  return r.states.map((s) => {
    return {
      uf: s.state,
      name: s.state,
      customers: s.customers,
      orders: s.orders,
      requested: s.requested_revenue,
      fulfilled: s.fulfilled_revenue,
      averageTicket: chartValue(s.average_ticket_requested),
      newCustomers: null,
      influencedCustomers: null,
      approvedWithoutPurchase: null,
      conversionRate: null,
      cities: s.top_cities.map((c) => {
        return {
          name: c.city ?? "Cidade indisponível",
          customers: c.customers,
          orders: c.orders,
          requested: c.requested_revenue,
          fulfilled: c.fulfilled_revenue,
        };
      }),
    };
  });
}
export function retentionSummaryView(r: LiveRetention): RetentionSummary {
  if (!r.series) throw unavailable();
  const series = r.series.map((p) => ({
    date: p.date,
    buyers: p.buyers_observed,
    recurring: p.recurring_buyers_observed,
    rate:
      p.retention_observed === null ? null : Number(p.retention_observed) * 100,
    ticket: p.retention_ticket_observed,
  }));
  return {
    buyers: r.buyers_observed,
    recurring: r.recurring_buyers_observed,
    rate:
      r.retention_observed === null ? null : Number(r.retention_observed) * 100,
    ticket: r.retention_ticket_observed,
    series,
    weekly: series,
  };
}
export const conversionUnavailable: Lifecycle["conversion"] = {
  buckets: [
    "Mesmo dia",
    "Até 3 dias",
    "Até 7 dias",
    "Até 14 dias",
    "Até 30 dias",
    "Até 60 dias",
    "Mais de 60",
  ].map((label) => ({ label, count: null, percent: null })),
  buyers: null,
  excluded: null,
  mean: null,
  median: null,
  withinWeek: null,
  withinMonth: null,
};
export function lifecycleView(r: LiveRetention): Lifecycle {
  if (!r.purchase_stages) throw unavailable();
  const groups = new Map<string, Lifecycle["cohorts"][number]>();
  for (const c of r.cohorts) {
    const month = c.cohort_month.slice(0, 7);
    let group = groups.get(month);
    if (!group) {
      if (c.buyers_observed === null) throw unavailable();
      group = {
        month,
        customers: c.buyers_observed,
        rates: [null, null, null, null],
      };
      groups.set(month, group);
    }
    if (c.month !== null && c.month < 4)
      group.rates[c.month] =
        c.observed_rate === null ? null : Number(c.observed_rate) * 100;
  }
  return {
    stages: r.purchase_stages.map((s) => ({
      stage: s.stage,
      customers: s.buyers_observed,
      share: s.share_observed === null ? null : Number(s.share_observed) * 100,
      continuation:
        s.continuation_observed === null
          ? null
          : Number(s.continuation_observed) * 100,
      revenue: s.requested_revenue_observed,
      accumulated: s.accumulated_requested_revenue_observed,
      meanDays: s.mean_days_observed,
    })),
    cohorts: [...groups.values()],
    conversion: conversionUnavailable,
  };
}
