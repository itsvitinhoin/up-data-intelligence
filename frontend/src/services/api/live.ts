/** Real DataApi for the approved original feature tree. No fixture imports. */
import type {
  DataApi,
  RequestContext,
  Resource,
  ResourceMap,
  Customer,
  CustomerDetail,
  Overview,
  Metric,
} from "@/types/domain";
import type {
  ReadMetadata,
  ReadResource,
  ReadResourceMap,
  ReadEnvelope,
} from "./http";
import { decodeOverviewEnvelope } from "./http";
import { readDashboard } from "./read-client";
import { assertAccess, ApiError } from "./access";
import { exclusiveToInclusive } from "@/lib/period";
import { presentLiveOverview } from "./overview-presenter";
import {
  customerView,
  orderView,
  orderDetailView,
  productView,
  campaignView,
  intelligenceOrderView,
  timelineView,
  customerProductView,
  geographyView,
  retentionSummaryView,
  lifecycleView,
  rowCount,
  rowText,
  requiredText,
  rowFlag,
  chartValue,
  unavailable,
} from "./live-presenters";
type ListResource =
  | "orders"
  | "customers"
  | "products"
  | "customerOrders"
  | "timeline"
  | "customerProducts"
  | "influencedOrders"
  | "influencedCustomers"
  | "campaigns"
  | "campaign"
  | "campaignCustomers"
  | "campaignOrders";
const scalar = (v: string | number | null) => (v === null ? null : String(v));
export function filterCustomers(
  rows: Customer[],
  c: RequestContext,
): Customer[] {
  const search = c.filters.search?.trim().toLocaleLowerCase("pt-BR");
  return rows.filter(
    (r) =>
      (!search ||
        [r.name, r.city, r.state].some((v) =>
          v?.toLocaleLowerCase("pt-BR").includes(search),
        )) &&
      (!c.filters.state ||
        c.filters.state === "all" ||
        r.state === c.filters.state) &&
      (!c.filters.segment ||
        c.filters.segment === "all" ||
        r.segment === c.filters.segment) &&
      (!c.filters.media ||
        c.filters.media === "all" ||
        r.paid === (c.filters.media === "yes")),
  );
}
export function createLiveDataApi(
  publication?: ReadMetadata,
  fetcher: typeof fetch = fetch,
): DataApi {
  let pinnedIntelligenceGeneration: number | undefined;
  async function metadata(c: RequestContext): Promise<ReadMetadata> {
    assertAccess(c);
    if (c.scope.operation !== "B2B") throw unavailable();
    if (publication) return publication;
    const p = new URLSearchParams({
      tenant_id: c.scope.tenant_id,
      workspace_operation_id:
        c.scope.workspace_operation_id ?? c.scope.store_id,
      operation: c.scope.operation,
    });
    const r = await fetcher(`/api/dashboard/overview?${p}`, {
      cache: "no-store",
      signal: c.signal,
    });
    if (!r.ok) throw new ApiError(r.status, "Publicação real indisponível.");
    return decodeOverviewEnvelope(await r.json()).metadata;
  }
  async function request<K extends ReadResource>(
    r: K,
    c: RequestContext,
    m: ReadMetadata,
    options: {
      customerId?: string;
      cursor?: string;
      firstPurchase?: boolean;
      full?: boolean;
      intelligenceGeneration?: number;
    } = {},
  ) {
    const { full, intelligenceGeneration, ...transport } = options;
    const filters = full
      ? {
          ...c.filters,
          from: m.report_from,
          to: exclusiveToInclusive(m.report_to),
        }
      : {
          ...c.filters,
          from: c.filters.from ?? m.report_from,
          to: c.filters.to ?? exclusiveToInclusive(m.report_to),
        };
    const response = await readDashboard(
      r,
      { ...c, filters },
      m.analytics_generation ?? m.generation,
      {
        ...transport,
        signal: c.signal,
        pageSize: 100,
        expectedStoreId: m.store_id,
        expectedPolicyHash: m.policy_hash,
        expectedIntelligenceGeneration:
          intelligenceGeneration ?? pinnedIntelligenceGeneration,
      },
      fetcher,
    );
    if (
      response.metadata.as_of !== m.as_of ||
      response.metadata.report_from !== m.report_from ||
      response.metadata.report_to !== m.report_to
    )
      throw new ApiError(409, "Publicação mudou durante a leitura.");
    if (response.metadata.publication_domain === "intelligence") {
      if (
        pinnedIntelligenceGeneration !== undefined &&
        response.metadata.generation !== pinnedIntelligenceGeneration
      )
        throw new ApiError(409, "Inteligência mudou durante a leitura.");
      pinnedIntelligenceGeneration = response.metadata.generation;
    }
    return response;
  }
  async function collection<K extends ListResource>(
    r: K,
    c: RequestContext,
    m: ReadMetadata,
    options: {
      customerId?: string;
      firstPurchase?: boolean;
      full?: boolean;
    } = {},
  ): Promise<ReadEnvelope<ReadResourceMap[K]>> {
    let cursor: string | undefined;
    let first: ReadEnvelope<ReadResourceMap[K]> | undefined;
    const result: unknown[] = [],
      cursors = new Set<string>(),
      identities = new Set<string>();
    for (let page = 0; page < 100; page++) {
      const response = await request(r, c, m, {
        ...options,
        cursor,
        intelligenceGeneration:
          first?.metadata.publication_domain === "intelligence"
            ? first.metadata.generation
            : undefined,
      });
      if (!Array.isArray(response.data) || !response.pagination)
        throw new ApiError(502, "Lista paginada inválida.");
      if (
        first &&
        (response.metadata.as_of !== first.metadata.as_of ||
          response.metadata.generation !== first.metadata.generation ||
          response.metadata.report_from !== first.metadata.report_from ||
          response.metadata.report_to !== first.metadata.report_to)
      )
        throw new ApiError(409, "Publicação mudou durante a leitura.");
      first ??= response;
      for (const row of response.data) {
        const identity =
          "record_key" in row
            ? row.record_key
            : "order_id" in row
              ? row.order_id
              : "customer_id" in row
                ? row.customer_id
                : "product_key" in row
                  ? row.product_key
                  : null;
        if (typeof identity !== "string" || identities.has(identity))
          throw new ApiError(502, "Identidade duplicada ou ausente.");
        identities.add(identity);
        result.push(row);
      }
      if (!response.pagination.has_more) {
        // All pages were decoded and checked above; never cast a raw HTTP envelope into a view model.
        return {
          ...first,
          data: result as ReadResourceMap[K],
          pagination: { page_size: 100, cursor: null, has_more: false },
        };
      }
      const next = response.pagination.cursor;
      if (!next || cursors.has(next))
        throw new ApiError(502, "Cursor inválido.");
      cursors.add(next);
      cursor = next;
    }
    throw new ApiError(
      413,
      "A coleção excede o limite desta leitura. Nenhuma exportação parcial foi produzida.",
    );
  }
  async function customers(
    c: RequestContext,
    m: ReadMetadata,
    full = false,
  ): Promise<Customer[]> {
    const base = await collection("customers", c, m, { full });
    return base.data.map(customerView);
  }
  function overview(
    response: ReadEnvelope<ReadResourceMap["overview"]>,
  ): Overview {
    const v = presentLiveOverview(response),
      b = v.data;
    const metrics = [
      ...b.revenue.map((x) => ({ ...x, group: "Receita" as const })),
      ...b.orders.map((x) => ({ ...x, group: "Pedidos" as const })),
    ];
    return {
      metrics,
      b2b: { ...b, media: [], attributedOrders: [] },
      series: response.data.series.map((p) => ({
        date: p.date,
        requested: chartValue(p.requested),
        fulfilled: chartValue(p.fulfilled),
        orders: p.orders,
      })),
      goal: {
        requested: chartValue(v.goal.requested),
        fulfilled: chartValue(v.goal.fulfilled),
      },
      week: [],
    };
  }
  const api: DataApi = {
    async read<K extends Resource>(
      resource: K,
      c: RequestContext,
    ): Promise<ResourceMap[K]> {
      const m = await metadata(c);
      if (c.filters.collection !== "all" || c.filters.channel !== "all")
        throw new ApiError(400, "Filtro ainda não certificado nesta leitura.");
      if (
        resource === "customers" &&
        ((c.filters.media && c.filters.media !== "all") ||
          ["Novo confirmado", "Reativado"].includes(c.filters.segment ?? ""))
      )
        throw new ApiError(400, "Classificação ainda não certificada.");
      let result: ResourceMap[Resource];
      switch (resource) {
        case "overview":
          result = overview(await request("overview", c, m));
          break;
        case "customers":
          result = filterCustomers(await customers(c, m), c);
          break;
        case "orders":
        case "order_history":
          result = (
            await collection("orders", c, m, {
              full: resource === "order_history",
            })
          ).data.map(orderView);
          break;
        case "products":
          result = (await collection("products", c, m)).data.map(productView);
          break;
        case "geography":
          result = geographyView((await request("geography", c, m)).data);
          break;
        case "leads":
          result = {
            leads: null,
            approved: null,
            converted: null,
            qualificationRate: null,
            conversionRate: null,
          };
          break;
        case "lifecycle":
          result = lifecycleView((await request("retention", c, m)).data);
          break;
        case "retention_summary":
          result = retentionSummaryView(
            (await request("retention", c, m)).data,
          );
          break;
        case "retention":
          result = (await request("retention", c, m)).data.progression.map(
            (p) => ({
              sequence: `${p.from_purchase} → ${p.to_purchase}`,
              customers: p.customers_reached_observed,
              mean: p.mean_days_observed,
              median: p.median_days_observed,
              rate:
                p.continuation_observed === null
                  ? null
                  : Number(p.continuation_observed) * 100,
              cohorts: [],
            }),
          );
          break;
        case "funnel": {
          const data = (await request("funnel", c, m)).data;
          result = [
            ["Sessões", "sessions"],
            ["Usuários", null],
            ["Produto visto", "product_views"],
            ["Carrinho", "add_to_cart"],
            ["Checkout", "checkout_started"],
            ["Compra", "purchase"],
          ].map(([label, key]) => ({
            label: label!,
            value: key === null ? null : data.totals[key],
          }));
          break;
        }
        case "acquisition": {
          const a = (await request("acquisition", c, m)).data,
            orders = (
              await collection("orders", c, m, { firstPurchase: true })
            ).data.map(orderView),
            all = await customers(c, m);
          const ids = new Set(orders.map((o) => o.customer_id));
          const first = all.filter((r) => ids.has(r.id));
          if (
            a.first_purchase_orders_observed !== orders.length ||
            a.first_purchase_customers_observed !== first.length
          )
            throw new ApiError(502, "Primeiras compras não reconciliadas.");
          result = {
            customers: first,
            firstOrders: orders,
            buyerCount: a.buyers_observed,
            confirmedNewCustomers: a.confirmed_new_customers,
            requested: a.requested_first_purchase_observed,
            fulfilled: a.fulfilled_first_purchase_observed,
            historyComplete: m.history_complete,
          };
          break;
        }
        case "campaigns":
        case "performance":
          result = (await collection("campaigns", c, m)).data.map(campaignView);
          break;
        case "influence": {
          const p = (await request("performance", c, m)).data;
          const orders = (await collection("influencedOrders", c, m)).data.map(
              intelligenceOrderView,
            ),
            rows = await customers(c, m, true),
            campaigns = (await collection("campaigns", c, m)).data.map(
              campaignView,
            );
          const ids = new Set(orders.map((o) => o.customer_id));
          const metric = (
            label: string,
            value: string | number | null,
            format: Metric["format"],
          ): Metric => ({
            label,
            value: scalar(value),
            format,
            hint: "Influência observada, sem atribuição exclusiva. Histórico parcial permanece protegido.",
          });
          result = {
            customers: rows
              .filter((r) => ids.has(r.id))
              .map((r) => ({ ...r, paid: true })),
            orders,
            campaigns,
            requested: rowText(p, "requested_revenue_influenced"),
            fulfilled: rowText(p, "fulfilled_revenue_influenced"),
            metrics: [
              metric(
                "Clientes influenciados",
                rowCount(p, "influenced_customers"),
                "number",
              ),
              metric(
                "Pedidos influenciados",
                rowCount(p, "influenced_orders"),
                "number",
              ),
              metric(
                "Receita Solicitada Influenciada",
                rowText(p, "requested_revenue_influenced"),
                "currency",
              ),
              metric(
                "Receita Atendida Influenciada",
                rowText(p, "fulfilled_revenue_influenced"),
                "currency",
              ),
              metric(
                "Investimento em mídias",
                rowText(p, "meta_spend"),
                "currency",
              ),
              metric(
                "ROAS solicitado influenciado",
                rowText(p, "roas_requested"),
                "ratio",
              ),
              metric(
                "ROAS atendido influenciado",
                rowText(p, "roas_fulfilled"),
                "ratio",
              ),
              metric("ROI", null, "percent"),
            ],
          };
          break;
        }
        case "marketing": {
          const p = (await request("performance", c, m)).data;
          if (!Array.isArray(p.series)) throw unavailable();
          const campaignRows = (await collection("campaigns", c, m)).data;
          const kpi = (
            label: string,
            value: string | number | null,
            format: Metric["format"],
            hint: string,
          ): Metric => ({ label, value: scalar(value), format, hint });
          result = {
            source: "real",
            creatives: [],
            summary: {
              spend: rowText(p, "meta_spend"),
              leads: null,
              clicks: rowCount(p, "clicks"),
              ctr: rowText(p, "ctr"),
            },
            campaigns: campaignRows.map((r) => ({
              ...campaignView(r),
              impressions: rowCount(r, "impressions"),
              clicks: rowCount(r, "clicks"),
              leads: null,
              approved: null,
              purchases: null,
              platform: "Meta Ads",
              status: rowText(r, "campaign_status"),
            })),
            series: p.series.map((raw) => {
              if (!raw || typeof raw !== "object" || Array.isArray(raw))
                throw new ApiError(502, "Série diária inválida.");
              return {
                date: requiredText(raw, "date"),
                spend: rowText(raw, "spend"),
                revenue: rowText(raw, "fulfilled_revenue_influenced"),
                leads: null,
                purchases: null,
              };
            }),
            metrics: [
              kpi(
                "Investimento em mídia",
                rowText(p, "meta_spend"),
                "currency",
                "Investimento Meta certificado no período.",
              ),
              kpi(
                "Faturamento atribuído",
                null,
                "currency",
                "Influência observada não comprova atribuição exclusiva.",
              ),
              kpi(
                "ROAS",
                null,
                "ratio",
                "Atribuição de faturamento ainda não certificada.",
              ),
              kpi(
                "CTR médio",
                rowText(p, "ctr"),
                "percent",
                "Cliques / impressões × 100, ponderado pelo volume.",
              ),
              kpi(
                "CPM",
                rowText(p, "cpm"),
                "currency",
                "Investimento / impressões × 1.000.",
              ),
              kpi(
                "Frequência",
                null,
                "decimal",
                "Alcance único agregado não certificado nesta publicação.",
              ),
              kpi(
                "CPC",
                rowText(p, "cpc"),
                "currency",
                "Investimento / cliques.",
              ),
              kpi(
                "Custo por compra",
                null,
                "currency",
                "Compras atribuídas não certificadas nesta projeção.",
              ),
            ],
          };
          break;
        }
        default:
          throw unavailable();
      }
      return result as ResourceMap[K];
    },
    async order(id, c) {
      const m = await metadata(c);
      return orderDetailView(
        (await request("order", c, m, { customerId: id })).data,
      );
    },
    async product(id, c) {
      const m = await metadata(c);
      return productView(
        (await request("product", c, m, { customerId: id })).data,
      );
    },
    async customer(id, c): Promise<CustomerDetail> {
      const m = await metadata(c),
        full = {
          ...c,
          filters: {
            ...c.filters,
            from: m.report_from,
            to: exclusiveToInclusive(m.report_to),
          },
        };
      const base = (await request("customer", full, m, { customerId: id }))
        .data;
      const intelligence = (
        await request("customer360", full, m, { customerId: id })
      ).data;
      const orders = (
        await collection("customerOrders", full, m, { customerId: id })
      ).data.map(orderView);
      const products = (
        await collection("customerProducts", full, m, { customerId: id })
      ).data.map((r) => customerProductView(r, m));
      const timeline = (
        await collection("timeline", full, m, { customerId: id })
      ).data
        .map((r) => timelineView(r, id, m))
        .sort(
          (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
        );
      const allCampaigns = (await collection("campaigns", full, m)).data;
      const participating = [];
      for (const campaign of allCampaigns) {
        const cid = requiredText(campaign, "campaign_id");
        const people = (
          await collection("campaignCustomers", full, m, { customerId: cid })
        ).data;
        if (people.some((r) => r.customer_id === id))
          participating.push(campaignView(campaign));
      }
      const influence = intelligence.marketing.find(
        (r) => r.influence_scope === "LIFETIME",
      );
      return {
        customer: {
          ...customerView(base.profile),
          fulfilled: base.commercial.fulfilled_revenue_observed,
          lastPurchase: base.commercial.last_purchase_at_observed,
          paid: influence ? rowFlag(influence, "paid_media_influenced") : null,
        },
        orders,
        products,
        timeline,
        campaigns: participating,
        marketingTouches: {
          first: rowText(intelligence.journey, "first_paid_touch_at"),
          last: rowText(intelligence.journey, "last_paid_touch_at"),
        },
        history_complete: m.history_complete,
      };
    },
    async campaign(id, c) {
      const m = await metadata(c),
        campaignRows = (await collection("campaign", c, m, { customerId: id }))
          .data;
      if (campaignRows.length !== 1)
        throw new ApiError(404, "Campanha não encontrada.");
      const r = campaignRows[0],
        orderRelations = (
          await collection("campaignOrders", c, m, { customerId: id })
        ).data;
      const allOrders = (await collection("orders", c, m)).data.map(orderView),
        orderIds = new Set(
          orderRelations.map((r) => requiredText(r, "order_id")),
        );
      const orders = allOrders
        .filter((r) => orderIds.has(r.id))
        .map((r) => ({ ...r, paid: true }));
      if (orders.length !== orderIds.size)
        throw new ApiError(502, "Pedidos participantes não reconciliados.");
      const people = (
          await collection("campaignCustomers", c, m, { customerId: id })
        ).data,
        ids = new Set(people.map((r) => requiredText(r, "customer_id")));
      const rows = await customers(c, m, true);
      return {
        campaign: campaignView(r),
        customers: rows
          .filter((r) => ids.has(r.id))
          .map((r) => ({ ...r, paid: true })),
        orders,
        campaigns: [campaignView(r)],
        requested: rowText(r, "requested_revenue_influenced"),
        fulfilled: rowText(r, "fulfilled_revenue_influenced"),
      };
    },
    async saveCompany() {
      throw unavailable();
    },
    async saveIntegration() {
      throw unavailable();
    },
    async saveUser() {
      throw unavailable();
    },
  };
  return api;
}
