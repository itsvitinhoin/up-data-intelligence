import { metaCampaignView } from "./meta-ads";
import { creativeView } from "./creatives";
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
import { groupJourney } from "@/lib/journey";
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
  | "customerCampaigns"
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
        case "leads": {
          const leads = (await request("acquisition", c, m)).data;
          result = {
            leads: leads.leads_generated ?? null,
            approved: leads.leads_approved ?? null,
            converted: leads.approved_converted ?? null,
            qualificationRate:
              leads.lead_qualification_rate === undefined ||
              leads.lead_qualification_rate === null
                ? null
                : Number(leads.lead_qualification_rate),
            conversionRate:
              leads.approved_conversion_rate === undefined ||
              leads.approved_conversion_rate === null
                ? null
                : Number(leads.approved_conversion_rate),
          };
          break;
        }
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
          const [platform, creativesResponse] = await Promise.all([
            request("metaAds", c, m),
            request("creatives", c, m).catch((error: unknown) => {
              if (error instanceof ApiError && error.status === 424)
                return null;
              throw error;
            }),
          ]);
          const p = platform.data.summary;
          const kpi = (
            label: string,
            value: string | number | null,
            format: Metric["format"],
            hint: string,
          ): Metric => ({ label, value: scalar(value), format, hint });
          result = {
            source: "real",
            creatives: creativesResponse?.data.map(creativeView) ?? [],
            summary: {
              spend: p.spend,
              leads: null,
              clicks: p.clicks,
              ctr: p.ctr,
            },
            campaigns: platform.data.campaigns.map((r) => ({
              ...metaCampaignView(r),
              impressions: r.impressions,
              clicks: r.clicks,
              leads: null,
              approved: null,
              purchases:
                r.meta_reported_purchases === null
                  ? null
                  : Number(r.meta_reported_purchases),
              platform: "Meta Ads",
              status: r.campaign_status,
              metaPurchaseValue: r.meta_reported_purchase_value,
              metaRoas: r.roas,
              metaCpa: r.cpa,
              metaCtr: r.ctr,
            })),
            seriesAvailable: platform.data.series !== null,
            series: (platform.data.series ?? []).map((r) => ({
              source: "real" as const,
              date: r.date,
              spend: r.spend,
              leads: null,
              purchases:
                r.meta_reported_purchases === null
                  ? null
                  : Number(r.meta_reported_purchases),
              revenue: r.meta_reported_purchase_value,
              roas: r.roas,
            })),
            metrics: [
              kpi(
                "Investimento Meta",
                p.spend,
                "currency",
                "Gasto oficial do Meta no período.",
              ),
              kpi(
                "Valor de compras reportado pelo Meta",
                p.meta_reported_purchase_value,
                "currency",
                "Action value da família de compras certificada; não é receita comercial UP Zero.",
              ),
              kpi(
                "ROAS Meta",
                p.roas,
                "ratio",
                "Valor de compras reportado / gasto Meta; não é atribuição comercial.",
              ),
              kpi(
                "Compras reportadas pelo Meta",
                p.meta_reported_purchases,
                "number",
                platform.data.purchase_action_type,
              ),
              kpi(
                "CTR Meta",
                p.ctr,
                "percent",
                "Cliques / impressões × 100; cálculo no backend.",
              ),
              kpi(
                "CPM Meta",
                p.cpm,
                "currency",
                "Gasto / impressões × 1.000; cálculo no backend.",
              ),
              kpi(
                "Frequência Meta",
                p.frequency,
                "decimal",
                "Frequência oficial all_days; não soma dias ou campanhas.",
              ),
              kpi(
                "CPC Meta",
                p.cpc,
                "currency",
                "Gasto / cliques; cálculo no backend.",
              ),
              kpi(
                "CPA Meta",
                p.cpa,
                "currency",
                "Gasto / compras reportadas pelo Meta.",
              ),
              kpi(
                "Impressões Meta",
                p.impressions,
                "number",
                "Relatório oficial do período.",
              ),
              kpi(
                "Alcance Meta",
                p.reach,
                "number",
                "Alcance único oficial do período all_days.",
              ),
              kpi(
                "Cliques no link Meta",
                p.link_clicks,
                "number",
                "inline_link_clicks do relatório oficial.",
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
      // customer360 pins Intelligence first; subsequent independent collections
      // share that generation. Campaign participation is one bounded resource,
      // never a scan of every campaign's customer list.
      const [orderRows, productRows, timelineRows, campaignRows] =
        await Promise.all([
          collection("customerOrders", full, m, { customerId: id }),
          collection("customerProducts", full, m, { customerId: id }),
          collection("timeline", full, m, { customerId: id }),
          collection("customerCampaigns", full, m, { customerId: id }),
        ]);
      const orders = orderRows.data.map(orderView);
      const products = productRows.data.map((r) => customerProductView(r, m));
      const timeline = groupJourney(
        timelineRows.data.map((r) => timelineView(r, id, m)),
      );
      const participating = campaignRows.data.map(campaignView);
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
      const m = await metadata(c);
      const report = (await request("metaAds", c, m)).data;
      const campaign = report.campaigns.find((r) => r.campaign_id === id);
      if (!campaign) throw new ApiError(404, "Campanha não encontrada.");
      return {
        campaign: metaCampaignView(campaign),
        campaigns: [metaCampaignView(campaign)],
        customers: [],
        orders: [],
        requested: null,
        fulfilled: null,
        meta: {
          campaign,
          adsets: report.adsets.filter((r) => r.campaign_id === id),
          ads: report.ads.filter((r) => r.campaign_id === id),
        },
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
