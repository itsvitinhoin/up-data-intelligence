/** Strict drill-down DTOs. Uncertified inventory/contact data is explicitly null. */
import { ApiError } from "./access";
import type { LiveOrder, LiveProduct, LiveScope } from "./http";
const invalid = (): never => {
  throw new ApiError(502, "Contrato de detalhe inválido.");
};
const object = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : invalid();
const text = (v: unknown): string =>
  typeof v === "string" && v.length > 0 ? v : invalid();
const nullableText = (v: unknown) => (v === null ? null : text(v));
const absent = (v: unknown): null => (v === null ? null : invalid());
const decimal = (v: unknown): string | null =>
  v === null
    ? null
    : typeof v === "string" && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(v)
      ? v
      : invalid();
const count = (v: unknown): number | null =>
  v === null
    ? null
    : typeof v === "number" && Number.isSafeInteger(v) && v >= 0
      ? v
      : invalid();
const requiredCount = (v: unknown) => count(v) ?? invalid();
const flag = (v: unknown): boolean | null =>
  v === null ? null : typeof v === "boolean" ? v : invalid();
const array = (v: unknown): unknown[] => (Array.isArray(v) ? v : invalid());
const key = (v: unknown): string =>
  typeof v === "string" && /^[a-f0-9]{64}$/.test(v) ? v : invalid();
export function parseOrderDetail(
  value: unknown,
  scope: LiveScope,
  id: string,
  parseOrder: (v: unknown, scope: LiveScope) => LiveOrder,
) {
  const row = object(value),
    order = parseOrder(row.order, scope);
  if (order.order_id !== id) invalid();
  const profile = row.customer === null ? null : object(row.customer);
  if (profile && profile.customer_id !== order.customer_id) invalid();
  const items = array(row.items).map((value) => {
    const i = object(value);
    if (!["active", "attended", "removed"].includes(text(i.status))) invalid();
    return {
      item_id: text(i.item_id),
      product_key: key(i.product_key),
      product_id: nullableText(i.product_id),
      asset_id: nullableText(i.asset_id),
      variant_id: nullableText(i.variant_id),
      name: nullableText(i.name),
      sku: nullableText(i.sku),
      image: nullableText(i.image),
      color: absent(i.color),
      size: absent(i.size),
      status: text(i.status),
      requested_quantity: decimal(i.requested_quantity),
      fulfilled_quantity: decimal(i.fulfilled_quantity),
      unit_price: decimal(i.unit_price),
      requested_value: decimal(i.requested_value),
      fulfilled_value: decimal(i.fulfilled_value),
    };
  });
  if (new Set(items.map((r) => r.item_id)).size !== items.length) invalid();
  const r = object(row.reconciliation);
  if (r.item_value_basis !== "line_gross_at_current_unit_price") invalid();
  return {
    order,
    customer:
      profile === null
        ? null
        : {
            customer_id: text(profile.customer_id),
            name: nullableText(profile.name),
            state: nullableText(profile.state),
            city: nullableText(profile.city),
            cnpj: absent(profile.cnpj),
            email: absent(profile.email),
            phone: absent(profile.phone),
          },
    items,
    reconciliation: {
      item_value_basis: "line_gross_at_current_unit_price" as const,
      gross_requested: decimal(r.gross_requested),
      gross_fulfilled: decimal(r.gross_fulfilled),
      requested_order_adjustment: decimal(r.requested_order_adjustment),
      fulfilled_order_adjustment: decimal(r.fulfilled_order_adjustment),
      quantity_reconciled: flag(r.quantity_reconciled),
    },
  };
}
export function parseProductDetail(
  value: unknown,
  scope: LiveScope,
  id: string,
  parseProduct: (v: unknown, scope: LiveScope) => LiveProduct,
) {
  const row = object(value),
    product = parseProduct(value, scope);
  if (
    key(product.product_key) !== id ||
    row.revenue_basis !== "line_gross_at_current_unit_price"
  )
    invalid();
  return {
    ...product,
    variant_id: nullableText(row.variant_id),
    image: nullableText(row.image),
    stock: absent(row.stock),
    sizes: absent(row.sizes),
    colors: absent(row.colors),
    abc: absent(row.abc),
    sell_through: absent(row.sell_through),
    revenue_basis: "line_gross_at_current_unit_price" as const,
  };
}
export function parseGeography(value: unknown) {
  const row = object(value),
    c = object(row.coverage);
  if (c.basis !== "order_shipping_location") invalid();
  const states = array(row.states).map((value) => {
    const r = object(value),
      state = text(r.state);
    if (
      !"AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO"
        .split(" ")
        .includes(state)
    )
      invalid();
    return {
      state,
      customers: count(r.customers),
      orders: requiredCount(r.orders),
      requested_revenue: decimal(r.requested_revenue),
      fulfilled_revenue: decimal(r.fulfilled_revenue),
      average_ticket_requested: decimal(r.average_ticket_requested),
      new_customers: absent(r.new_customers),
      influenced_customers: absent(r.influenced_customers),
      approved_without_purchase: absent(r.approved_without_purchase),
      conversion_rate: absent(r.conversion_rate),
      top_cities: array(r.top_cities).map((value) => {
        const city = object(value);
        return {
          city: nullableText(city.city),
          customers: count(city.customers),
          orders: count(city.orders),
          requested_revenue: decimal(city.requested_revenue),
          fulfilled_revenue: decimal(city.fulfilled_revenue),
        };
      }),
    };
  });
  const coverage = {
    basis: "order_shipping_location" as const,
    orders_observed: requiredCount(c.orders_observed),
    mapped_orders: requiredCount(c.mapped_orders),
    unmapped_orders: requiredCount(c.unmapped_orders),
    orders_without_customer: requiredCount(c.orders_without_customer),
  };
  if (
    new Set(states.map((r) => r.state)).size !== states.length ||
    states.reduce((sum, r) => sum + r.orders, 0) !== coverage.mapped_orders ||
    coverage.mapped_orders + coverage.unmapped_orders !==
      coverage.orders_observed ||
    coverage.orders_without_customer > coverage.orders_observed
  )
    invalid();
  return { states, coverage };
}
export type LiveOrderDetail = ReturnType<typeof parseOrderDetail>;
export type LiveProductDetail = ReturnType<typeof parseProductDetail>;
export type LiveGeography = ReturnType<typeof parseGeography>;
