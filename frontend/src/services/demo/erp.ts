import type { RequestContext } from "@/types/domain";
import type {
  ErpData,
  ErpOrderRow,
  ErpProductRow,
  Breakdown,
} from "@/types/erp";
import { dateRange, DEMO_TODAY, periodDays } from "@/lib/period";
import { hasDemoData, ordersFor } from "./business";
import { orderDetailFor, variantsFor } from "./details";
import * as fixtures from "./fixtures";
const round = (n: number) => Math.round(n * 100) / 100;
const sum = <T>(rows: T[], value: (row: T) => number) =>
  round(rows.reduce((s, row) => s + value(row), 0));
const ratio = (n: number, d: number) => (d ? (n / d) * 100 : 0);
export const stockTurnover = (units: number, stock: number) =>
  ratio(Math.max(0, units), Math.max(0, units) + Math.max(0, stock));
export const stockCoverage = (units: number, stock: number, days: number) =>
  units > 0 ? Math.max(0, stock) / (units / Math.max(1, days)) : null;
function breakdown(
  rows: ErpOrderRow[],
  key: "seller" | "store" | "state" | "status" | "paymentMethod",
): Breakdown[] {
  return [...new Set(rows.map((o) => o[key] ?? "Não identificado"))]
    .map((label) => {
      const selected = rows.filter(
        (o) => (o[key] ?? "Não identificado") === label,
      );
      return {
        label,
        orders: selected.length,
        revenue: sum(selected, (o) => o.netAmount),
        customers: new Set(selected.map((o) => o.customerId)).size,
      };
    })
    .sort((a, b) => b.revenue - a.revenue);
}
export function erpFor(context: RequestContext): ErpData {
  const { from, to: end, days } = dateRange(context.filters);
  const to = end < DEMO_TODAY ? end : DEMO_TODAY;
  // Independent ERP demonstration ledger. Discounts, returns, costs, stores and sellers are synthetic, not inferred source facts.
  const c = {
    ...context,
    filters: {
      ...context.filters,
      from: "2000-01-01",
      to,
      channel: "all",
      collection: "all",
      search: "",
      state: "all",
      segment: "all",
      media: "all",
    },
  };
  const history: ErpOrderRow[] = ordersFor(c).map((base) => {
    const i = fixtures.orders.findIndex((o) => o.id === base.id);
    const detail = orderDetailFor(base.id, c)!;
    const cancelled = i % 17 === 16;
    const items = detail.items.map((item, j) => {
      const product = fixtures.products.find((p) => p.id === item.product_id)!;
      const grossAmount = Number(item.requested);
      const discountAmount = round(grossAmount * (i % 3 === 0 ? 0.05 : 0));
      return {
        id: `${base.id}-${j}`,
        sku: `${item.sku}-${item.color}-${item.size}`,
        productId: item.product_id,
        name: item.name,
        category: ["Vestidos", "Conjuntos", "Calças", "Blusas", "Macacões"][
          fixtures.products.findIndex((p) => p.id === product.id)
        ],
        color: item.color,
        size: item.size,
        quantity: item.requestedQuantity,
        unitPrice: round(grossAmount / item.requestedQuantity),
        costPrice: round((grossAmount / item.requestedQuantity) * 0.45),
        discountAmount,
        grossAmount,
        netAmount: round(grossAmount - discountAmount),
      };
    });
    const grossAmount = sum(items, (x) => x.grossAmount),
      discountAmount = sum(items, (x) => x.discountAmount);
    const returnedQuantity = !cancelled && i % 11 === 10 ? 2 : 0;
    const returnAmount = round(
      (returnedQuantity * (grossAmount - discountAmount)) /
        base.requestedQuantity,
    );
    return {
      id: `ERP-${base.id}`,
      createdAt: base.date,
      customerId: base.customer_id,
      customerName: detail.customer.name,
      company: detail.customer.name,
      document: detail.customer.cnpj,
      seller: ["Equipe Ana", "Equipe Bruno", "Equipe Clara"][i % 3],
      store: ["Matriz", "Showroom"][i % 2],
      paymentMethod: ["PIX", "Boleto", "Cartão"][i % 3],
      freightAmount: 0,
      channel: context.scope.operation,
      status: cancelled ? "CANCELADO" : "FATURADO",
      requestedQuantity: base.requestedQuantity,
      fulfilledQuantity: cancelled
        ? 0
        : base.requestedQuantity - returnedQuantity,
      returnedQuantity,
      grossAmount,
      discountAmount,
      returnAmount,
      netAmount: cancelled
        ? 0
        : round(grossAmount - discountAmount - returnAmount),
      state: detail.customer.state,
      city: detail.customer.city,
      utmSource: base.paid ? "meta" : null,
      utmMedium: base.paid ? "paid_social" : null,
      utmCampaign: base.paid ? "Coleção · demo" : null,
      attributed: base.paid,
      items,
    };
  });
  const orders = history.filter((o) => o.createdAt >= from);
  const sold = orders.filter((o) => o.status !== "CANCELADO");
  const validHistory = history
    .filter((o) => o.status !== "CANCELADO")
    .sort(
      (a, b) =>
        a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id),
    );
  const customers: ErpData["customers"] = [
    ...new Set(sold.map((o) => o.customerId)),
  ].map((id) => {
    const all = validHistory.filter((o) => o.customerId === id),
      period = sold.filter((o) => o.customerId === id),
      last = all.at(-1)!;
    const observedLifetimeValue = sum(all, (o) => o.netAmount),
      totalSpent = sum(period, (o) => o.netAmount);
    const recurring = all.some((o) => o.createdAt < from) || period.length > 1;
    return {
      id: id!,
      name: last.customerName,
      company: last.company,
      document: last.document,
      email: `${id}@clientes.example`,
      phone: "(00) 00000-0000 · fictício",
      city: last.city,
      state: last.state,
      seller: last.seller,
      orders: period.length,
      totalSpent,
      averageTicket: period.length ? totalSpent / period.length : 0,
      historicalOrders: all.length,
      lifetimeValue: null,
      observedLifetimeValue,
      buyerType: recurring ? "RETURNING" : "NEW",
      daysSinceLastOrder:
        (Date.parse(to) - Date.parse(last.createdAt)) / 86400000,
      segment:
        all.length >= 6
          ? "CHAMPION"
          : all.length >= 3
            ? "LOYAL"
            : all.length > 1
              ? "POTENTIAL"
              : "AT_RISK",
      firstOrderAt: all[0].createdAt,
      lastOrderAt: last.createdAt,
      utmSource: last.utmSource,
      utmMedium: last.utmMedium,
      utmCampaign: last.utmCampaign,
      attributed: period.some((o) => o.attributed),
    };
  });
  const products: ErpProductRow[] = (hasDemoData(c) ? fixtures.products : [])
    .map((product, pi) => {
      const variants = variantsFor(product).map((v, vi) => {
        const matches = sold.flatMap((o) =>
          o.items
            .filter(
              (item) =>
                item.productId === product.id &&
                item.color === v.color &&
                item.size === v.size,
            )
            .map((item) => ({ o, item })),
        );
        const units = sum(matches, ({ item }) => item.quantity);
        // Allocate return value proportionally so catalogue revenue reconciles with ERP net sales.
        const revenue = sum(
          matches,
          ({ o, item }) =>
            item.netAmount -
            (o.returnAmount * item.netAmount) /
              (o.grossAmount - o.discountAmount),
        );
        const costAmount = sum(
          matches,
          ({ item }) => item.costPrice * item.quantity,
        );
        const catalogPrice = 120 + pi * 15;
        const stock = pi === 0 && vi === 0 ? -2 : v.stock;
        return {
          id: v.sku,
          sku: v.sku,
          color: v.color,
          size: v.size,
          units,
          revenue,
          averagePrice: units ? revenue / units : 0,
          catalogPrice,
          stock,
          turnoverPct: stockTurnover(units, stock),
          salesPower: Math.max(0, stock) * catalogPrice,
          costAmount,
          grossProfit: round(revenue - costAmount),
          grossMarginPct: ratio(revenue - costAmount, revenue),
          coverageDays: stockCoverage(units, stock, days),
        };
      });
      const units = sum(variants, (v) => v.units),
        revenue = sum(variants, (v) => v.revenue),
        stock = sum(variants, (v) => v.stock),
        costAmount = sum(variants, (v) => v.costAmount);
      return {
        id: product.id,
        name: product.name,
        category: ["Vestidos", "Conjuntos", "Calças", "Blusas", "Macacões"][
          fixtures.products.findIndex((p) => p.id === product.id)
        ],
        units,
        revenue,
        averagePrice: units ? revenue / units : 0,
        stock,
        turnoverPct: stockTurnover(units, stock),
        salesPower: sum(variants, (v) => v.salesPower),
        costAmount,
        grossProfit: round(revenue - costAmount),
        grossMarginPct: ratio(revenue - costAmount, revenue),
        coverageDays: stockCoverage(units, stock, days),
        variantCount: variants.length,
        outOfStockCount: variants.filter((v) => v.stock === 0).length,
        variants,
      };
    })
    .sort((a, b) => b.revenue - a.revenue);
  const allVariants = products.flatMap((p) => p.variants);
  const totalRevenue = sum(products, (p) => p.revenue),
    totalUnits = sum(products, (p) => p.units),
    totalStock = sum(products, (p) => p.stock),
    totalCost = sum(products, (p) => p.costAmount);
  const grossRevenue = sum(sold, (o) => o.grossAmount),
    netRevenue = sum(sold, (o) => o.netAmount),
    discountAmount = sum(sold, (o) => o.discountAmount),
    returnAmount = sum(sold, (o) => o.returnAmount),
    returningCustomers = customers.filter(
      (c) => c.buyerType === "RETURNING",
    ).length;
  const series = periodDays(context.filters);
  const first = new Map<string, string>();
  for (const o of validHistory)
    if (!first.has(o.customerId!)) first.set(o.customerId!, o.createdAt);
  return {
    orders,
    history,
    customers,
    dashboard: {
      kpis: {
        grossRevenue,
        netRevenue,
        discountAmount,
        orders: sold.length,
        totalQuantity: sum(sold, (o) => o.requestedQuantity),
        returnedQuantity: sum(sold, (o) => o.returnedQuantity),
        uniqueCustomers: customers.length,
        newCustomers: null,
        returningCustomers,
        retentionPct: ratio(returningCustomers, customers.length),
        cancelledOrders: orders.length - sold.length,
        cancelledAmount: sum(
          orders.filter((o) => o.status === "CANCELADO"),
          (o) => o.grossAmount,
        ),
        avgTicket: sold.length ? netRevenue / sold.length : 0,
        returnAmount,
        avgItemsPerOrder: sold.length
          ? sum(sold, (o) => o.requestedQuantity) / sold.length
          : 0,
        returnRatePct: ratio(returnAmount, grossRevenue),
        discountRatePct: ratio(discountAmount, grossRevenue),
      },
      revenueOverTime: series.map((date) => ({
        date,
        value: sum(
          sold.filter((o) => o.createdAt === date),
          (o) => o.netAmount,
        ),
      })),
      ordersOverTime: series.map((date) => ({
        date,
        value: sold.filter((o) => o.createdAt === date).length,
      })),
      newCustomersOverTime: series.map((date) => ({
        date,
        value: new Set(
          sold
            .filter(
              (o) => o.createdAt === date && first.get(o.customerId!) === date,
            )
            .map((o) => o.customerId),
        ).size,
      })),
      returningCustomersOverTime: series.map((date) => ({
        date,
        value: new Set(
          sold
            .filter(
              (o) => o.createdAt === date && first.get(o.customerId!)! < date,
            )
            .map((o) => o.customerId),
        ).size,
      })),
      attribution: {
        attributedCustomers: customers.filter((c) => c.attributed).length,
        unattributedCustomers: customers.filter((c) => !c.attributed).length,
        attributedRevenue: sum(
          sold.filter((o) => o.attributed),
          (o) => o.netAmount,
        ),
        unattributedRevenue: sum(
          sold.filter((o) => !o.attributed),
          (o) => o.netAmount,
        ),
      },
      breakdowns: {
        statuses: breakdown(orders, "status"),
        payments: breakdown(sold, "paymentMethod"),
        sellers: breakdown(sold, "seller"),
        stores: breakdown(sold, "store"),
        states: breakdown(sold, "state"),
      },
    },
    products: {
      rows: products,
      total: products.length,
      totalSkus: allVariants.length,
      filteredTotal: products.length,
      totalRevenue,
      totalUnits,
      totalStock,
      outOfStockCount: allVariants.filter((v) => v.stock === 0).length,
      turnoverPct: stockTurnover(totalUnits, totalStock),
      salesPower: sum(products, (p) => p.salesPower),
      totalCost,
      grossProfit: round(totalRevenue - totalCost),
      grossMarginPct: ratio(totalRevenue - totalCost, totalRevenue),
      negativeStockCount: allVariants.filter((v) => v.stock < 0).length,
      coverageDays: stockCoverage(totalUnits, totalStock, days),
      breakdowns: {
        categories: [...new Set(products.map((p) => p.category))].map(
          (label) => ({
            label: label ?? "Sem categoria",
            units: sum(
              products.filter((p) => p.category === label),
              (p) => p.units,
            ),
            revenue: sum(
              products.filter((p) => p.category === label),
              (p) => p.revenue,
            ),
            salesPower: sum(
              products.filter((p) => p.category === label),
              (p) => p.salesPower,
            ),
          }),
        ),
        colors: [...new Set(allVariants.map((v) => v.color))].map((label) => ({
          label: label ?? "Sem cor",
          units: sum(
            allVariants.filter((v) => v.color === label),
            (v) => v.units,
          ),
          revenue: sum(
            allVariants.filter((v) => v.color === label),
            (v) => v.revenue,
          ),
        })),
        sizes: [...new Set(allVariants.map((v) => v.size))].map((label) => ({
          label: label ?? "Sem tamanho",
          units: sum(
            allVariants.filter((v) => v.size === label),
            (v) => v.units,
          ),
          revenue: sum(
            allVariants.filter((v) => v.size === label),
            (v) => v.revenue,
          ),
        })),
      },
    },
  };
}
