import type {
  OrderDetail,
  Order,
  Product,
  RequestContext,
} from "@/services/demo/types";
import * as fixtures from "./fixtures";
import { ordersFor, allOrdersFor, customersFor } from "./business";
export function variantsFor(product: Product) {
  const colors = [product.color, product.color === "Preto" ? "Areia" : "Preto"];
  const sizes = Object.keys(product.sizes);
  const rows = colors.flatMap((color) =>
    sizes.map((size) => ({
      color,
      size,
      sku: `${product.sku}-${color}-${size}`,
      stock: 0,
      hex:
        color === product.color
          ? (product.colorHex ?? null)
          : color === "Preto"
            ? "#1A1A1A"
            : "#C9B494",
    })),
  );
  const available = rows.filter((row) => product.sizes[row.size]);
  available.forEach((row, i) => {
    row.stock =
      Math.floor(product.stock / available.length) +
      (i < product.stock % available.length ? 1 : 0);
  });
  return rows;
}
export function orderDetailFor(
  id: string,
  c: RequestContext,
): OrderDetail | null {
  const order =
    ordersFor(c).find((row) => row.id === id) ??
    (c.scope.operation === "B2C"
      ? allOrdersFor(c).find((row) => row.id === id)
      : undefined);
  if (!order) return null;
  const customer = customersFor({
    ...c,
    filters: {
      ...c.filters,
      search: "",
      state: "all",
      segment: "all",
      media: "all",
      from: c.scope.operation === "B2C" ? "2000-01-01" : c.filters.from,
      to: c.scope.operation === "B2C" ? "2100-12-31" : c.filters.to,
    },
  }).find((row) => row.id === order.customer_id);
  if (!customer) return null;
  return {
    order,
    customer: {
      ...customer,
      cnpj: `DEMO-CNPJ-${customer.id.toUpperCase()}`,
      email: `${customer.id}@clientes.example`,
      phone: "(00) 00000-0000 · fictício",
    },
    items: orderItemsFor(order),
  };
}

/** The same synthetic lines feed order detail and B2C product aggregates. */
export function orderItemsFor(order: Order): OrderDetail["items"] {
  const index = fixtures.orders.findIndex((row) => row.id === order.id);
  const products = [
    fixtures.products[index % fixtures.products.length],
    fixtures.products[(index + 1) % fixtures.products.length],
  ];
  const split = (value: number, i: number) =>
    i === 0 ? Math.floor(value / 2) : value - Math.floor(value / 2);
  return products.map((product, i) => ({
    product_id: product.id,
    name: product.name,
    sku: product.sku,
    color: product.color,
    size: i === 0 ? "M" : "G",
    requestedQuantity: split(order.requestedQuantity, i),
    fulfilledQuantity: split(order.fulfilledQuantity, i),
    requested: (
      split(Math.round(Number(order.requested) * 100), i) / 100
    ).toFixed(2),
    fulfilled: (
      split(Math.round(Number(order.fulfilled) * 100), i) / 100
    ).toFixed(2),
  }));
}

/** Synthetic sold units, independent of current stock. Never inferred from availability. */
export function variantSalesFor(product: Product) {
  const variants = variantsFor(product);
  const weights = variants.map((_, i) => i + 1);
  const sum = weights.reduce((a, b) => a + b, 0);
  let remaining = product.units;
  return variants.map((v, i) => {
    const units =
      i === variants.length - 1
        ? remaining
        : Math.floor((product.units * weights[i]) / sum);
    remaining -= units;
    return { color: v.color, size: v.size, units };
  });
}
