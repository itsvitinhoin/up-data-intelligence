"use client";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { useState, type ReactNode, type ComponentType } from "react";
import { useWorkspace } from "@/features/providers";
import { B2BReadBoundary, useDashboardRead } from "@/hooks/use-dashboard-read";
import { usePageSource } from "@/hooks/use-page-source";
import { usePublicationMetadata } from "@/hooks/publication-context";
import {
  MetricCard,
  PageHead,
  Panel,
  Choice,
  Empty,
  Loading,
  Failure,
} from "@/components/ui-kit";
import { DataTable } from "@/components/data-table";
import { useTemplate } from "./provider";
import {
  managerPage,
  MetricRegistry,
  FilterRegistry,
  WidgetRegistry,
  type ManagerPage,
} from "./registry";
import { validatedPagePreference } from "./preferences";
import { managerMetrics, divideDecimal } from "./presenters";
import { WidgetBindings } from "./widgets";
import { PageDataCoverage } from "./coverage";
import { MetricBindings } from "./bindings";
import {
  managerDemoMetrics,
  managerDemoValues,
} from "@/services/demo/manager-v2";
import { useRequestContext } from "@/hooks/use-resource";
const bodies: Record<string, ComponentType> = {
  overview: dynamic(() =>
    import("@/features/overview").then((m) => m.OverviewPage),
  ),
  orders: dynamic(() =>
    import("@/features/influence").then(
      (m) =>
        function CommercialPageBody() {
          return <m.CommercialPage />;
        },
    ),
  ),
  customers: dynamic(() =>
    import("@/features/customer-pages").then((m) => m.CustomersPage),
  ),
  products: dynamic(() =>
    import("@/features/commerce").then(
      (m) =>
        function ProductsPageBody() {
          return <m.ProductsPage />;
        },
    ),
  ),
  stock: dynamic(() =>
    import("@/features/commerce").then(
      (m) =>
        function ProductsPageStock() {
          return <m.ProductsPage inventory />;
        },
    ),
  ),
  geography: dynamic(() =>
    import("@/features/geography").then((m) => m.GeographyPage),
  ),
  campaigns: dynamic(() =>
    import("@/features/campaigns").then(
      (m) =>
        function CampaignsPageBody() {
          return <m.CampaignsPage />;
        },
    ),
  ),
  "retail-orders": dynamic(() =>
    import("@/features/retail-orders").then((m) => m.RetailOrdersPage),
  ),
  "retail-products": dynamic(() =>
    import("@/features/retail-products").then(
      (m) =>
        function RetailProductsPageBody() {
          return <m.RetailProductsPage />;
        },
    ),
  ),
  "retail-stock": dynamic(() =>
    import("@/features/retail-products").then(
      (m) =>
        function RetailProductsPageStock() {
          return <m.RetailProductsPage inventory />;
        },
    ),
  ),
};
const Retention = dynamic(() =>
  import("@/features/lifecycle").then((m) => m.RetentionDashboard),
);
const Retail = dynamic(() =>
  import("@/features/retail").then((m) => m.RetailOverview),
);
const RetailPerformance = dynamic(() =>
  import("@/features/retail").then((m) => m.RetailPerformance),
);
const RevenueChart = dynamic(
  () => import("@/components/charts").then((m) => m.RevenueChart),
  { ssr: false },
);

function PerformanceFilters() {
  const { filters, setFilters } = useWorkspace();
  return (
    <Panel
      title="Filtros de Performance"
      subtitle="Filtros sem capacidade certificada permanecem indisponíveis."
    >
      <div className="flex flex-wrap gap-3">
        {Object.entries(FilterRegistry).map(([id, filter]) => (
          <Choice
            key={id}
            label={filter.label}
            disabled={!filter.supported}
            value={
              id === "comparison" && filters.compare === false
                ? "Sem comparação"
                : filter.values[0]
            }
            options={filter.values.map((value) => ({ value, label: value }))}
            onChange={(value) =>
              setFilters({ ...filters, compare: value !== "Sem comparação" })
            }
          />
        ))}
      </div>
    </Panel>
  );
}
const months = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
];
function HistoricalPerformance() {
  const { dataMode } = useWorkspace();
  const metadata = usePublicationMetadata();
  if (dataMode !== "demo" && metadata)
    return <LiveHistorical metadata={metadata} />;
  return <DemoHistorical />;
}
function DemoHistorical() {
  const context = useRequestContext();
  const groups: Record<string, string[]> = {
    Vendas: [
      "revenue_captured",
      "revenue_approved",
      "revenue_cancelled",
      "approval_rate",
      "average_ticket",
      "orders_generated",
      "orders_paid",
      "cost_per_sale",
    ],
    Clientes: [
      "new_customers",
      "recurring_customers",
      "repurchase_rate",
      "cac",
    ],
    Mídia: [
      "meta_spend",
      "google_spend",
      "tiktok_spend",
      "total_media_spend",
      "roas_captured",
      "roas_approved",
    ],
    Sessões: ["sessions", "cost_per_session", "final_conversion_rate"],
    Carrinho: ["add_to_cart", "cost_per_add_to_cart", "session_to_cart_rate"],
    Checkout: [
      "checkout_started",
      "cost_per_checkout",
      "cart_to_checkout_rate",
      "checkout_to_sale_rate",
    ],
  };
  return (
    <>
      {Object.entries(groups).map(([group, ids]) => (
        <Panel
          key={group}
          title={group}
          subtitle="B2C · DADOS DEMONSTRATIVOS · setembro/2026; demais meses fora do cenário."
        >
          <DataTable
            pageSize={12}
            data={ids.map((id) => ({
              metric: MetricRegistry[id].label,
              ...Object.fromEntries(
                months.map((month) => [
                  month,
                  month === "Set"
                    ? (managerDemoValues({
                        ...context,
                        filters: {
                          ...context.filters,
                          from: "2026-09-01",
                          to: "2026-09-30",
                        },
                      })[id] ?? null)
                    : null,
                ]),
              ),
            }))}
            columns={[
              { accessorKey: "metric", header: "Métrica" },
              ...months.map((month) => ({
                accessorKey: month,
                header: month,
                cell: ({
                  row,
                }: {
                  row: { original: Record<string, unknown> };
                }) => String(row.original[month] ?? "—"),
              })),
            ]}
          />
        </Panel>
      ))}
    </>
  );
}
function LiveHistorical({
  metadata,
}: {
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  const overview = useDashboardRead("overview", metadata);
  const funnel = useDashboardRead("funnel", metadata);
  const performance = useDashboardRead("performance", metadata);
  if (overview.isError)
    return (
      <Failure
        retry={() => {
          void overview.refetch();
          void funnel.refetch();
          void performance.refetch();
        }}
      />
    );
  if (!overview.data) return <Loading />;
  type Monthly = Record<string, string | number | null>;
  const buckets = new Map<string, Monthly>();
  const add = (
    month: string,
    field: string,
    v: string | number | null | undefined,
  ) => {
    const r = buckets.get(month) ?? {};
    r[field] =
      v == null || r[field] === null
        ? null
        : typeof v === "number"
          ? Number(r[field] ?? 0) + v
          : decimalSum(String(r[field] ?? "0"), v);
    buckets.set(month, r);
  };
  for (const r of overview.data.data.series) {
    const month = r.date.slice(0, 7);
    add(month, "requested", r.requested);
    add(month, "fulfilled", r.fulfilled);
    add(month, "orders", r.orders);
    add(month, "cancelled", r.cancelled_requested);
  }
  for (const r of overview.data.data.monthly_customers ?? []) {
    const m = r.month.slice(0, 7),
      values = buckets.get(m) ?? {};
    values.buyers = r.buyers_observed;
    values.recurring = r.recurring_buyers_observed;
    buckets.set(m, values);
  }
  for (const r of funnel.data?.data.days ?? []) {
    const m = r.date.slice(0, 7);
    for (const k of [
      "sessions",
      "add_to_cart",
      "checkout_started",
      "sessions_with_cart",
      "sessions_cart_then_checkout",
      "sessions_cart_checkout_purchase",
      "sessions_with_purchase",
    ])
      add(m, k, r[k]);
  }
  const media = performance.data?.data.series;
  if (Array.isArray(media))
    for (const item of media)
      if (
        item &&
        typeof item === "object" &&
        !Array.isArray(item) &&
        typeof item.date === "string"
      )
        add(
          item.date.slice(0, 7),
          "meta_spend",
          typeof item.spend === "string" ? item.spend : null,
        );
  const ratio = (r: Monthly, a: string, b: string, scale = 1) =>
    r[a] == null || r[b] == null
      ? null
      : divideDecimal(String(r[a]), String(r[b]), scale);
  const groups: Record<
    string,
    {
      label: string;
      field?: string;
      value?: (r: Monthly) => string | null;
      reason?: string;
    }[]
  > = {
    Vendas: [
      { label: "Receita solicitada", field: "requested" },
      { label: "Receita atendida", field: "fulfilled" },
      { label: "Receita cancelada solicitada", field: "cancelled" },
      { label: "Faturamento pago", reason: "PAYMENT_SOURCE_NOT_CERTIFIED" },
      {
        label: "Ticket solicitado",
        value: (r) => ratio(r, "requested", "orders"),
      },
      { label: "Pedidos", field: "orders" },
      { label: "Pedidos pagos", reason: "PAYMENT_SOURCE_NOT_CERTIFIED" },
      {
        label: "Custo por venda paga",
        reason: "PAID_SALES_AND_TOTAL_MEDIA_CONNECTORS_REQUIRED",
      },
    ],
    Clientes: [
      { label: "Compradores observados", field: "buyers" },
      { label: "Recorrentes observados", field: "recurring" },
      {
        label: "% recorrentes observado",
        value: (r) => ratio(r, "recurring", "buyers", 100),
      },
      { label: "CAC definitivo", reason: "REQUIRES_HISTORICAL_BACKFILL" },
    ],
    Mídia: [
      { label: "Investimento Meta", field: "meta_spend" },
      { label: "Investimento Google", reason: "GOOGLE_ADS_CONNECTOR_REQUIRED" },
      { label: "Investimento TikTok", reason: "TIKTOK_ADS_CONNECTOR_REQUIRED" },
      {
        label: "Investimento total",
        reason: "MEDIA_PLATFORM_COVERAGE_INCOMPLETE",
      },
      {
        label: "ROAS captado geral",
        reason: "MEDIA_PLATFORM_COVERAGE_INCOMPLETE",
      },
      { label: "ROAS pago", reason: "PAYMENT_SOURCE_NOT_CERTIFIED" },
    ],
    Sessões: [
      { label: "Sessões", field: "sessions" },
      {
        label: "Custo por sessão geral",
        reason: "MEDIA_PLATFORM_COVERAGE_INCOMPLETE",
      },
      {
        label: "Sessões com compra (%)",
        value: (r) => ratio(r, "sessions_with_purchase", "sessions", 100),
      },
    ],
    Carrinho: [
      { label: "Eventos de carrinho", field: "add_to_cart" },
      {
        label: "Custo por carrinho geral",
        reason: "MEDIA_PLATFORM_COVERAGE_INCOMPLETE",
      },
      {
        label: "Sessão → carrinho (%)",
        value: (r) => ratio(r, "sessions_with_cart", "sessions", 100),
      },
    ],
    Checkout: [
      { label: "Eventos de checkout", field: "checkout_started" },
      {
        label: "Custo por checkout geral",
        reason: "MEDIA_PLATFORM_COVERAGE_INCOMPLETE",
      },
      {
        label: "Carrinho → checkout (%)",
        value: (r) =>
          ratio(r, "sessions_cart_then_checkout", "sessions_with_cart", 100),
      },
      {
        label: "Checkout → compra (%)",
        value: (r) =>
          ratio(
            r,
            "sessions_cart_checkout_purchase",
            "sessions_cart_then_checkout",
            100,
          ),
      },
    ],
  };
  return (
    <>
      {Object.entries(groups).map(([group, rows]) => (
        <Panel
          key={group}
          title={group}
          subtitle="Janela certificada; meses nas bordas podem ser parciais. Atendido não confirma pagamento; clientes são distintos dentro de cada mês."
        >
          <DataTable
            pageSize={12}
            data={rows.map((row) => ({
              metric: row.label,
              reason: row.reason ?? "",
              ...Object.fromEntries(
                [...buckets].map(([month, r]) => [
                  month,
                  row.field
                    ? (r[row.field] ?? null)
                    : row.value
                      ? row.value(r)
                      : null,
                ]),
              ),
            }))}
            columns={[
              { accessorKey: "metric", header: "Métrica" },
              ...[...buckets.keys()].map((month) => ({
                accessorKey: month,
                header: month,
                cell: ({
                  row,
                }: {
                  row: { original: Record<string, unknown> };
                }) => (
                  <span
                    title={String(
                      row.original.reason || "Campo certificado no mês",
                    )}
                  >
                    {String(row.original[month] ?? "—")}
                  </span>
                ),
              })),
            ]}
          />
        </Panel>
      ))}
    </>
  );
}
function decimalSum(a: string, b: string): string {
  const [ai, af = ""] = a.split("."),
    [bi, bf = ""] = b.split("."),
    length = Math.max(af.length, bf.length),
    scale = 10n ** BigInt(length);
  const v =
    BigInt(ai) * scale +
    BigInt(af.padEnd(length, "0") || "0") +
    BigInt(bi) * scale +
    BigInt(bf.padEnd(length, "0") || "0");
  return `${v / scale}${length ? "." + (v % scale).toString().padStart(length, "0") : ""}`;
}
function UnavailableWidget({ id }: { id: string }) {
  const title = WidgetRegistry[id]?.label ?? "Cobertura ainda não certificada";
  const columns =
    id === "registration-cohort"
      ? [
          "Mês cadastro",
          "Aprovados",
          "Até 30D",
          "Até 60D",
          "Até 90D",
          "Até hoje",
        ]
      : id === "repurchase-cohort"
        ? [
            "Até 7D",
            "Até 30D",
            "Até 60D",
            "Até 90D",
            "Até 180D",
            "+180D",
            "Até hoje",
          ]
        : id === "purchase-progression"
          ? [
              "1ª compra",
              "2ª compra",
              "3ª compra",
              "4ª compra",
              "5ª compra",
              "6ª compra",
            ]
          : [];
  return (
    <Panel
      title={title}
      subtitle={
        WidgetBindings[id]?.reason ??
        "SELLER_PERIOD_READ_NOT_CERTIFIED · associação vendedor/pedido ainda não projetada."
      }
    >
      {columns.length ? (
        <>
          <div className="table-scroll">
            <table className="list num">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  {columns.map((column) => (
                    <td key={column}>—</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted mt-3">
            Janelas sem maturidade ou evidência não recebem zero.
          </p>
        </>
      ) : (
        <Empty
          title="Indisponível"
          description={
            WidgetBindings[id]?.reason ?? "SELLER_PERIOD_READ_NOT_CERTIFIED"
          }
        />
      )}
    </Panel>
  );
}
function Widget({ id, page }: { id: string; page: ManagerPage }) {
  const { dataMode } = useWorkspace();
  if (id === "journey-guidance") {
    const Body = bodies.customers;
    return <Body />;
  }
  if (WidgetBindings[id]?.metricIds.length && id !== "funnel")
    return <BoundMetricWidget id={id} />;
  if (id === "repurchase-cohort") return <Retention />;
  if (id === "monthly-history") return <HistoricalPerformance />;
  if (id === "retail-platforms") return <RetailPlatformViews />;
  if (id === "commercial-trend" && dataMode !== "demo")
    return <CertifiedTrend />;
  if (id === "commercial-trend" && dataMode === "demo") {
    const Body = bodies.overview;
    return <Body />;
  }
  if (id === "retail-overview" && dataMode === "demo") return <Retail />;
  if (id === "retail-retention" && dataMode === "demo") return <Retention />;
  if (id === "retail-funnel" && dataMode === "demo")
    return <RetailPerformance />;
  if (id === "funnel") return <ManagerFunnel />;
  if (id === "purchase-progression") return <ManagerProgression />;
  if (id === "content" && page.body && bodies[page.body]) {
    const Body = bodies[page.body];
    return <Body />;
  }
  return <UnavailableWidget id={id} />;
}
function BoundMetricWidget({ id }: { id: string }) {
  const metadata = usePublicationMetadata();
  const ids = WidgetBindings[id].metricIds;
  if (!metadata) return <UnavailableWidget id={id} />;
  return (
    <Panel
      title={WidgetRegistry[id].label}
      subtitle={WidgetBindings[id].reason}
    >
      <section className="metrics">
        {ids.map((metricId, index) =>
          MetricBindings[metricId].resource ? (
            <ReadMetricSlot
              key={metricId}
              id={metricId}
              index={index}
              metadata={metadata}
            />
          ) : (
            <MetricCard
              key={metricId}
              item={managerMetrics([metricId], "overview", null, metadata)[0]}
              decorativeTrend={false}
            />
          ),
        )}
      </section>
    </Panel>
  );
}
function RetailPlatformViews() {
  const [platform, setPlatform] = useState("Total");
  const { dataMode } = useWorkspace();
  const context = useRequestContext();
  const ids =
    platform === "Total"
      ? ["total_media_spend", "roas_captured", "cost_per_sale"]
      : [
          platform === "Meta"
            ? "meta_spend"
            : platform === "Google"
              ? "google_spend"
              : "tiktok_spend",
        ];
  return (
    <Panel
      title="Mídia e conversão"
      action={
        <Choice
          label="Plataforma"
          value={platform}
          options={["Total", "Meta", "Google", "TikTok"].map((value) => ({
            value,
            label: value,
          }))}
          onChange={setPlatform}
        />
      }
    >
      {dataMode === "demo" ? (
        <div className="metrics">
          {managerDemoMetrics(ids, context).map((item, i) => (
            <MetricCard key={item.label} item={item} index={i} />
          ))}
        </div>
      ) : (
        <p>Indisponível · cobertura ainda não certificada.</p>
      )}
    </Panel>
  );
}
function CertifiedTrend() {
  const metadata = usePublicationMetadata();
  if (!metadata) return <UnavailableWidget id="commercial-trend" />;
  return <ReadTrend metadata={metadata} />;
}
function ReadTrend({
  metadata,
}: {
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  const q = useDashboardRead("overview", metadata);
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  if (q.isPending || !q.data) return <Loading />;
  return (
    <Panel
      title="Receita comercial observada por período"
      subtitle="Solicitado e atendido são estados separados; atendimento não confirma pagamento."
    >
      <RevenueChart
        data={q.data.data.series.map((row) => ({
          date: row.date,
          requested: row.requested === null ? null : Number(row.requested),
          fulfilled: row.fulfilled === null ? null : Number(row.fulfilled),
          orders: row.orders,
        }))}
      />
    </Panel>
  );
}
function ManagerFunnel() {
  const metadata = usePublicationMetadata();
  if (!metadata) return <UnavailableWidget id="funnel" />;
  return <ReadFunnel metadata={metadata} />;
}
function ReadFunnel({
  metadata,
}: {
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  const q = useDashboardRead("funnel", metadata);
  const p = useDashboardRead("performance", metadata),
    overview = useDashboardRead("overview", metadata),
    leads = useDashboardRead("acquisition", metadata);
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  if (q.isPending || !q.data) return <Loading />;
  const d = q.data.data;
  const media = p.data?.data;
  const stages = [
    ["Impressões", media?.impressions ?? null],
    [
      "Alcance observado · soma campanha/dia",
      media?.reach_campaign_day_sum ?? null,
    ],
    ["Cliques no Link", media?.link_clicks ?? null],
    ["Visitas / Sessões", d.totals.sessions ?? null],
    ["Cadastros concluídos", leads.data?.data.leads_generated ?? null],
    ["Cadastros aprovados", leads.data?.data.leads_approved ?? null],
    ["Visualizações de produto", d.totals.product_views ?? null],
    ["Adições ao carrinho", d.totals.add_to_cart ?? null],
    ["Checkouts", d.totals.checkout_started ?? null],
    ["Compras · eventos observados", d.totals.purchase ?? null],
    ["Itens comprados · eventos observados", d.totals.purchase_item ?? null],
    ["Faturamento solicitado", overview.data?.data.requested_revenue ?? null],
    ["Faturamento pago", null],
  ] as const;
  const rates = [
    ["Frequência", null],
    ["CTR", media?.ctr ?? null],
    ["CPC", media?.cpc ?? null],
    ["Connect Rate", null],
    ["Taxa de cadastro", null],
    ["Taxa de aprovação", leads.data?.data.lead_qualification_rate ?? null],
    ["Taxa de carrinho", d.session_to_cart_rate],
    ["Taxa de checkout", d.cart_to_checkout_rate],
    ["Checkout → compra observada", d.checkout_to_purchase_rate],
    ["Taxa de pagamento", null],
  ] as const;
  return (
    <>
      <Panel
        title="Funil de Conversão"
        subtitle="Etapas sem evidência compatível de fonte e período permanecem indisponíveis."
      >
        <DataTable
          pageSize={15}
          data={stages.map(([stage, value]) => ({ stage, value }))}
          columns={[
            { accessorKey: "stage", header: "Etapa" },
            {
              accessorKey: "value",
              header: "Valor",
              cell: ({ row }) => row.original.value ?? "—",
            },
          ]}
        />
      </Panel>
      <Panel
        title="Transições do funil"
        subtitle="Checkout → compra é evento observado; não confirma pagamento."
      >
        <DataTable
          pageSize={12}
          data={rates.map(([stage, value]) => ({ stage, value }))}
          columns={[
            { accessorKey: "stage", header: "Transição" },
            {
              accessorKey: "value",
              header: "Taxa certificada",
              cell: ({ row }) => row.original.value ?? "—",
            },
          ]}
        />
      </Panel>
    </>
  );
}
function ManagerProgression() {
  const metadata = usePublicationMetadata();
  if (!metadata) return <UnavailableWidget id="purchase-progression" />;
  return <ReadProgression metadata={metadata} />;
}
function ReadProgression({
  metadata,
}: {
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  const q = useDashboardRead("retention", metadata);
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  if (q.isPending || !q.data) return <Loading />;
  const stages = q.data.data.purchase_stages ?? [];
  return (
    <>
      <Panel
        title="Progressão de recompra"
        subtitle="Histórico observado. O contrato atual agrupa 5+; quinta e sexta compras separadas aguardam certificação."
      >
        <div className="purchase-progression">
          {Array.from({ length: 6 }, (_, i) => i + 1).map((stage) => {
            const row =
              stage <= 5 ? stages.find((s) => s.stage === stage) : undefined;
            return (
              <section key={stage} className="purchase-stage">
                <div className="progression-track">
                  <span />
                </div>
                <h3>{stage === 5 ? "5+ compras" : `${stage}ª compra`}</h3>
                <div className="progression-count num">
                  {row?.buyers_observed ?? "—"}
                </div>
                <p>{row?.share_observed ?? "—"}% da base observada</p>
              </section>
            );
          })}
        </div>
      </Panel>
      <Retention />
    </>
  );
}
function LiveMetrics({ page }: { page: ManagerPage }) {
  const metadata = usePublicationMetadata();
  if (!metadata) return <MetricGrid page={page} />;
  return <ReadMetrics page={page} metadata={metadata} />;
}
function ReadMetrics({
  page,
  metadata,
}: {
  page: ManagerPage;
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  return (
    <section className="metrics" aria-label="Indicadores de gestão">
      {page.metricIds.map((id, index) =>
        MetricBindings[id].resource ? (
          <ReadMetricSlot key={id} id={id} index={index} metadata={metadata} />
        ) : (
          <MetricCard
            key={id}
            item={managerMetrics([id], page.resource, null, metadata)[0]}
            index={index}
            decorativeTrend={false}
          />
        ),
      )}
    </section>
  );
}
function ReadMetricSlot({
  id,
  index,
  metadata,
}: {
  id: string;
  index: number;
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  const resource = MetricBindings[id].resource!;
  const q = useDashboardRead(resource, metadata);
  const item =
    q.compare((data) =>
      managerMetrics([id], resource, data, q.data?.metadata),
    )[0] ?? managerMetrics([id], resource, null, metadata)[0];
  return (
    <MetricCard
      item={{
        ...item,
        hint: q.isError
          ? "API_READ_FAILED · leitura indisponível; nenhum dado demo foi usado."
          : item.hint,
      }}
      index={index}
      decorativeTrend={false}
    />
  );
}
function MetricGrid({ page }: { page: ManagerPage }) {
  const context = useRequestContext();
  const { dataMode } = useWorkspace();
  const metrics =
    dataMode === "demo" && context.scope.operation === "B2C"
      ? managerDemoMetrics(page.metricIds, context)
      : managerMetrics(page.metricIds, page.resource, null);
  return (
    <section className="metrics" aria-label="Indicadores de gestão">
      {metrics.map((item, index) => (
        <MetricCard
          key={page.metricIds[index]}
          item={item}
          index={index}
          decorativeTrend={false}
        />
      ))}
    </section>
  );
}
function ManagerContents({ page }: { page: ManagerPage }) {
  const { preference } = useTemplate(),
    { dataMode } = useWorkspace();
  const pref = validatedPagePreference(page.path, preference.pages[page.path]);
  return (
    <>
      <PageHead
        eyebrow={`${page.path.startsWith("/b2b") ? "B2B" : "B2C"} · ${page.group}`}
        title={page.title}
        description="Decisões com dados certificados e cobertura explícita."
      />
      {page.group === "Performance" && page.path.startsWith("/b2b") && (
        <PerformanceFilters />
      )}
      <PageDataCoverage page={page} />
      {!page.body && !page.widgets.length && !page.metricIds.length && (
        <UnavailableWidget id="sellers" />
      )}
      <div className="manager-widgets">
        {pref.order
          .filter((id) => !pref.hidden.includes(id))
          .map((id) => (
            <section
              key={id}
              className={`manager-widget manager-widget--${pref.sizes[id] ?? "full"}`}
              data-widget={id}
            >
              {id === "metrics" ? (
                dataMode !== "demo" && page.path.startsWith("/b2b") ? (
                  <LiveMetrics page={page} />
                ) : (
                  <MetricGrid page={page} />
                )
              ) : (
                <div className="manager-content">
                  <Widget id={id} page={page} />
                </div>
              )}
            </section>
          ))}
      </div>
    </>
  );
}
export function ManagerBoundary({ children }: { children: ReactNode }) {
  const path = usePathname(),
    { enabled } = useTemplate(),
    { dataMode } = useWorkspace(),
    page = managerPage(path);
  if (!enabled || !page) return children;
  // Unsupported sources stay visible without executing unrelated business reads.
  if (
    page.group === "ERP" ||
    page.group === "WhatsApp" ||
    (dataMode === "live" && path.startsWith("/b2c"))
  )
    return <UnavailableTemplate page={page} />;
  return page.path.startsWith("/b2b") ? (
    <B2BReadBoundary>
      <ManagerContents page={page} />
    </B2BReadBoundary>
  ) : (
    <ManagerContents page={page} />
  );
}

function UnavailableTemplate({ page }: { page: ManagerPage }) {
  const { dataMode } = useWorkspace();
  usePageSource(dataMode === "demo" ? "demo" : "unavailable-real");
  return <ManagerContents page={page} />;
}
