import { periodDays } from "@/lib/period";
import { managerDemoRetail } from "./manager-v2";
import { retailFor } from "./retail";
import { erpFor } from "./erp";
import { retentionSummaryFor } from "./retention-summary";
import { leadsFor, geographyWithLeads } from "./leads";
import { acquisitionFor } from "./acquisition";
import { lifecycleFor } from "./lifecycle";
import { variantsFor, variantSalesFor, orderDetailFor } from "./details";
import { marketingFor } from "./marketing";
import type {
  DataApi,
  RequestContext,
  Resource,
  ResourceMap,
} from "@/services/demo/types";
import { assertAccess, ApiError } from "@/services/api/access";
import { tenants } from "@/config/tenants";
import { adminApi, assertUp } from "./admin";
import * as fixtures from "./fixtures";
import {
  hasDemoData,
  factor,
  customersFor,
  ordersFor,
  allOrdersFor,
  overviewFor,
  campaignsFor,
  campaignFor,
  influenceFor,
  retentionFor,
  timelineFor,
} from "./business";
function partition(c: RequestContext) {
  assertAccess(c);
  const tenant = tenants.find((t) => t.id === c.scope.tenant_id);
  if (
    !tenant?.brands.some(
      (b) =>
        (c.session.role === "ADMIN" || b.id === c.session.brand_id) &&
        b.operations.some(
          (o) => o.id === c.scope.store_id && o.type === c.scope.operation,
        ),
    )
  )
    throw new ApiError(403, "Operação não autorizada.");
}
async function wait(signal?: AbortSignal) {
  await new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, 100);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
export const demoApi: DataApi = {
  async read<K extends Resource>(
    resource: K,
    c: RequestContext,
  ): Promise<ResourceMap[K]> {
    partition(c);
    await wait(c.signal);
    let result: unknown;
    switch (resource) {
      case "retail":
        result =
          c.scope.operation === "B2C" ? managerDemoRetail(c) : retailFor(c);
        break;
      case "erp":
        result = erpFor(c);
        break;
      case "retention_summary":
        result = retentionSummaryFor(c);
        break;
      case "leads":
        result = leadsFor(c);
        break;
      case "acquisition":
        result = acquisitionFor(c);
        break;
      case "lifecycle":
        result = lifecycleFor(c);
        break;
      case "marketing":
        result = marketingFor(c);
        break;
      case "overview":
        result = overviewFor(c);
        break;
      case "customers":
        result = customersFor(c);
        break;
      case "order_history":
        result = allOrdersFor(c);
        break;
      case "orders":
        result = ordersFor(c);
        break;
      case "inventory_products":
      case "products": {
        const historical = resource === "inventory_products";
        const days = historical
          ? 30
          : periodDays(c.filters).filter(
              (day) => day >= "2026-09-01" && day <= "2026-09-30",
            ).length;
        const basis = historical
          ? {
              ...c,
              filters: { ...c.filters, channel: "all", collection: "all" },
            }
          : c;
        const weight = (factor(basis) * days) / 30;
        result = (hasDemoData(c) && days ? fixtures.products : []).map((p) => {
          const product = {
            ...p,
            units: Math.round(p.units * weight),
            requested: (Number(p.requested) * weight).toFixed(2),
            fulfilled: (Number(p.fulfilled) * weight).toFixed(2),
          };
          return {
            ...product,
            variants: variantsFor(product),
            variantSales: variantSalesFor(product),
          };
        });
        break;
      }
      case "campaigns":
      case "performance":
        result = campaignsFor(c);
        break;
      case "influence":
        result = influenceFor(c);
        break;
      case "geography":
        result = geographyWithLeads(c);
        break;
      case "retention":
        result = retentionFor(c);
        break;
      case "funnel":
        result = [
          ["Sessões", 32000],
          ["Usuários", 24500],
          ["Produto visto", 18000],
          ["Carrinho", 4200],
          ["Checkout", 2200],
          ["Compra", fixtures.orders.length],
        ].map(([label, value]) => ({
          label: String(label),
          value: hasDemoData(c) ? Math.round(Number(value) * factor(c)) : 0,
        }));
        break;
      case "companies":
        result = await adminApi.brands(c.session);
        break;
      case "users":
        result = await adminApi.users(c.session);
        break;
      case "integrations":
        assertUp(c.session);
        result = fixtures.integrations.filter((i) => i.type !== "Meta Ads");
        break;
    }
    return structuredClone(result) as ResourceMap[K];
  },
  async customer(id, c) {
    partition(c);
    await wait(c.signal);
    if (c.scope.operation === "B2C") {
      const historyContext = {
        ...c,
        filters: {
          ...c.filters,
          from: "2000-01-01",
          to: "2100-01-01",
          channel: "all",
          collection: "all",
          search: "",
          state: "all",
          segment: "all",
          media: "all",
        },
      };
      const customer = customersFor(historyContext).find((r) => r.id === id);
      if (!customer) throw new ApiError(404, "Cliente não encontrado.");
      return {
        customer,
        orders: allOrdersFor(c).filter((order) => order.customer_id === id),
        products: [],
        timeline: [],
        campaigns: [],
        history_complete: false,
      };
    }
    const customer = customersFor({
      ...c,
      filters: {
        ...c.filters,
        search: "",
        state: "all",
        segment: "all",
        media: "all",
      },
    }).find((r) => r.id === id);
    if (!customer) throw new ApiError(404, "Cliente não encontrado.");
    return {
      customer,
      orders: ordersFor(c).filter((o) => o.customer_id === id),
      products: (await this.read("products", c)).slice(0, 3).map((p, i) => ({
        ...p,
        requested: (Number(customer.requested) * [0.5, 0.3, 0.2][i]).toFixed(2),
        fulfilled: (Number(customer.fulfilled) * [0.5, 0.3, 0.2][i]).toFixed(2),
        customers: 1,
        orders: customer.orders,
        share: [50, 30, 20][i],
        units: Math.round(customer.orders * 48 * [0.5, 0.3, 0.2][i]),
        variantSales: variantSalesFor({
          ...p,
          units: Math.round(customer.orders * 48 * [0.5, 0.3, 0.2][i]),
        }),
      })),
      timeline: timelineFor(customer, c),
      campaigns: campaignsFor(c).filter((p) =>
        campaignFor(p.id, c)?.orders.some((o) => o.customer_id === id),
      ),
      history_complete: false,
    };
  },
  async campaign(id, c) {
    partition(c);
    await wait(c.signal);
    const detail = campaignFor(id, c);
    if (!detail) throw new ApiError(404, "Campanha não encontrada.");
    return structuredClone(detail);
  },
  async saveCompany(v, c) {
    return adminApi.saveBrand(v, c.session);
  },
  async order(id, c) {
    partition(c);
    await wait(c.signal);
    const detail = orderDetailFor(id, c);
    if (!detail)
      throw new ApiError(
        404,
        "Pedido não encontrado nesta operação e período.",
      );
    return detail;
  },
  async saveUser(v, c) {
    return adminApi.saveUser(v, c.session);
  },
  async saveIntegration(_v, c) {
    assertUp(c.session);
    throw new ApiError(400, "Use o fluxo global de integrações da UP.");
  },
};
