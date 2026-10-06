/** B2C-only fixtures projected from the same order lines as the retail totals. */
import type { Product, RequestContext } from "./types";
import { allOrdersFor, hasDemoData, ordersFor } from "./business";
import { orderItemsFor, variantsFor } from "./details";
import { products } from "./fixtures";

const cents = (value: string) => BigInt(value.replace(".", ""));
const money = (value: bigint) =>
  `${value / 100n}.${String(value % 100n).padStart(2, "0")}`;

export function retailProductsFor(
  c: RequestContext,
  inventory = false,
): Product[] {
  if (!hasDemoData(c)) return [];
  const orders = inventory ? allOrdersFor(c) : ordersFor(c);
  if (!inventory && !orders.length) return [];
  const lines = orders.flatMap((order) =>
    orderItemsFor(order).map((item) => ({ order, item })),
  );
  const total = lines.reduce(
    (sum, { item }) => sum + cents(item.requested),
    0n,
  );
  return products.map((product, index) => {
    const selected = lines.filter(({ item }) => item.product_id === product.id);
    const requested = selected.reduce(
      (sum, { item }) => sum + cents(item.requested),
      0n,
    );
    const fulfilled = selected.reduce(
      (sum, { item }) => sum + cents(item.fulfilled),
      0n,
    );
    const units = selected.reduce(
      (sum, { item }) => sum + item.requestedQuantity,
      0,
    );
    const orderCount = new Set(selected.map(({ order }) => order.id)).size;
    const variants = variantsFor(product);
    // Synthetic traffic is declared separately from stock and reconciled to the
    // observed demo purchases, preserving risk/promising interactions.
    const views = orderCount * [100, 60, 50, 40, 30][index];
    return {
      ...product,
      requested: money(requested),
      fulfilled: money(fulfilled),
      units,
      orders: orderCount,
      customers: new Set(selected.map(({ order }) => order.customer_id)).size,
      share: total ? (Number(requested) / Number(total)) * 100 : 0,
      views,
      cart: Math.round(views * 0.15),
      checkout: Math.round(views * 0.1),
      variants,
      variantSales: variants.map((variant) => ({
        color: variant.color,
        size: variant.size,
        units: selected
          .filter(
            ({ item }) =>
              item.color === variant.color && item.size === variant.size,
          )
          .reduce((sum, { item }) => sum + item.requestedQuantity, 0),
      })),
    };
  });
}
