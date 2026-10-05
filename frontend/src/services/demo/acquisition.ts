import type { Acquisition, Order, RequestContext } from "@/services/demo/types";
import { dateRange, inPeriod, DEMO_TODAY } from "@/lib/period";
import { customersFor, ordersFor, total } from "./business";
export function acquisitionFor(context: RequestContext): Acquisition {
  // Acquisition includes all origins, regardless of an inherited media filter.
  const c = {
    ...context,
    filters: {
      ...context.filters,
      channel: "all",
      media: "all",
      search: "",
      state: "all",
      segment: "all",
    },
  };
  const { to } = dateRange(c.filters);
  const history = ordersFor({
    ...c,
    filters: {
      ...c.filters,
      from: "2000-01-01",
      to: to < DEMO_TODAY ? to : DEMO_TODAY,
    },
  });
  const first = new Map<string, Order>();
  history
    .filter((o) =>
      ["RESERVED", "CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED"].includes(
        o.status,
      ),
    )
    .toSorted(
      (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
    )
    .forEach((order) => {
      if (!first.has(order.customer_id)) first.set(order.customer_id, order);
    });
  const firstOrders = [...first.values()].filter((order) =>
    inPeriod(order.date, c.filters),
  );
  const ids = new Set(firstOrders.map((order) => order.customer_id));
  const buyers = customersFor(c);
  return {
    customers: buyers
      .filter((customer) => ids.has(customer.id))
      .map((customer) => ({
        ...customer,
        firstPurchase: first.get(customer.id)!.date,
        orders: 1,
        requested: first.get(customer.id)!.requested,
        fulfilled: first.get(customer.id)!.fulfilled,
      })),
    firstOrders,
    buyerCount: buyers.length,
    confirmedNewCustomers: null,
    requested: total(firstOrders, "requested"),
    fulfilled: total(firstOrders, "fulfilled"),
    historyComplete: false,
  };
}
