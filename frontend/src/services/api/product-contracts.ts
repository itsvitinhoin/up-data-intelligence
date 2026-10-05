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
export type CatalogEvidence = {
  basis: "current_source_snapshot";
  snapshot_as_of: string;
  evidence_hash: string;
};
export function parseCatalogEvidence(value: unknown): CatalogEvidence | null {
  if (value === null) return null;
  const row = object(value);
  const stamp = text(row.snapshot_as_of);
  if (
    row.basis !== "current_source_snapshot" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      stamp,
    ) ||
    !Number.isFinite(Date.parse(stamp))
  )
    invalid();
  return {
    basis: "current_source_snapshot",
    snapshot_as_of: stamp,
    evidence_hash: key(row.evidence_hash),
  };
}
function catalogDimensions(row: Record<string, unknown>) {
  const catalog =
    row.catalog === undefined ? null : parseCatalogEvidence(row.catalog);
  const color = nullableText(row.color ?? null),
    size = nullableText(row.size ?? null);
  if (!catalog && (color !== null || size !== null)) invalid();
  return { color, size, ...(row.catalog === undefined ? {} : { catalog }) };
}
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
      ...catalogDimensions(i),
      ...(i.reference === undefined
        ? {}
        : { reference: nullableText(i.reference) }),
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
  const dimensions = catalogDimensions(row);
  const stock = decimal(row.stock);
  const active = flag(row.active ?? null),
    salePrice = decimal(row.sale_price ?? null);
  const colorHex = nullableText(row.color_hex ?? null);
  if (colorHex !== null && !/^#[a-fA-F0-9]{6}$/.test(colorHex)) invalid();
  if (stock !== null && Number(stock) < 0) invalid();
  if (
    !dimensions.catalog &&
    (stock !== null ||
      active !== null ||
      salePrice !== null ||
      colorHex !== null)
  )
    invalid();
  let variants = undefined;
  if (row.variants !== undefined) {
    variants =
      row.variants === null
        ? null
        : array(row.variants).map((value) => {
            const v = object(value),
              dimensions = catalogDimensions(v);
            const stock = decimal(v.stock),
              salePrice = decimal(v.sale_price),
              hex = nullableText(v.color_hex);
            if (
              !dimensions.catalog ||
              !product.catalog ||
              dimensions.catalog.evidence_hash !==
                product.catalog.evidence_hash ||
              dimensions.catalog.snapshot_as_of !==
                product.catalog.snapshot_as_of ||
              v.product_id !== product.product_id ||
              (stock !== null && Number(stock) < 0) ||
              (hex !== null && !/^#[a-fA-F0-9]{6}$/.test(hex))
            )
              invalid();
            return {
              variant_id: text(v.variant_id),
              product_id: nullableText(v.product_id),
              sku: nullableText(v.sku),
              ...dimensions,
              stock,
              sale_price: salePrice,
              color_hex: hex,
              active: flag(v.active),
              requested_revenue: decimal(v.requested_revenue),
              fulfilled_revenue: decimal(v.fulfilled_revenue),
              units_requested: decimal(v.units_requested),
              units_fulfilled: decimal(v.units_fulfilled),
              orders_observed: count(v.orders_observed),
              buyers_observed: count(v.buyers_observed),
            };
          });
    if (
      variants &&
      (variants.length > 1000 ||
        new Set(variants.map((v) => v.variant_id)).size !== variants.length ||
        row.variant_sales_basis !== "observed_line_gross_current_catalog")
    )
      invalid();
    if (variants === null && row.variant_sales_basis !== null) invalid();
  }
  return {
    ...product,
    ...(row.variants === undefined
      ? {}
      : {
          variants,
          variant_sales_basis: nullableText(row.variant_sales_basis),
        }),
    ...(row.catalog === undefined &&
    row.color === undefined &&
    row.size === undefined
      ? {}
      : dimensions),
    ...(row.active === undefined ? {} : { active }),
    ...(row.sale_price === undefined ? {} : { sale_price: salePrice }),
    ...(row.color_hex === undefined ? {} : { color_hex: colorHex }),
    variant_id: nullableText(row.variant_id),
    image: nullableText(row.image),
    stock,
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
