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
import { managerMetrics } from "./presenters";
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
          subtitle="Histórico mensal aguarda publicação certificada por mês."
        >
          <DataTable
            pageSize={12}
            data={ids.map((id) => ({
              metric: MetricRegistry[id].label,
              ...Object.fromEntries(months.map((month) => [month, null])),
            }))}
            columns={[
              { accessorKey: "metric", header: "Métrica" },
              ...months.map((month) => ({
                accessorKey: month,
                header: month,
                cell: () => "—",
              })),
            ]}
          />
        </Panel>
      ))}
    </>
  );
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
      subtitle="Fonte ainda não disponível / cobertura ainda não certificada."
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
          description="Esta visualização requer evidência compatível de período e fonte."
        />
      )}
    </Panel>
  );
}
function Widget({ id, page }: { id: string; page: ManagerPage }) {
  const { dataMode } = useWorkspace();
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
function RetailPlatformViews() {
  const [platform, setPlatform] = useState("Total");
  const { dataMode } = useWorkspace();
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
      <p className="muted">
        {platform}:{" "}
        {dataMode === "demo"
          ? "Modo demonstrativo. Valores de plataforma ainda não vinculados neste template."
          : "Indisponível · cobertura ainda não certificada."}
      </p>
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
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  if (q.isPending || !q.data) return <Loading />;
  const d = q.data.data;
  const stages = [
    ["Impressões", null],
    ["Alcance", null],
    ["Cliques no Link", null],
    ["Visitas / Sessões", d.totals.sessions ?? null],
    ["Cadastros concluídos", null],
    ["Cadastros aprovados", null],
    ["Adições ao carrinho", d.totals.add_to_cart ?? null],
    ["Checkouts", d.totals.checkout_started ?? null],
    ["Faturamento solicitado", null],
    ["Faturamento pago", null],
  ] as const;
  const rates = [
    ["Frequência", null],
    ["CTR", null],
    ["CPC", null],
    ["Connect Rate", null],
    ["Taxa de cadastro", null],
    ["Taxa de aprovação", null],
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
          pageSize={12}
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
              stage < 5 ? stages.find((s) => s.stage === stage) : undefined;
            return (
              <section key={stage} className="purchase-stage">
                <div className="progression-track">
                  <span />
                </div>
                <h3>{stage}ª compra</h3>
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
  const q = useDashboardRead(page.resource, metadata);
  if (q.isPending) return <Loading />;
  if (q.isError)
    return (
      <Failure
        retry={() => void q.refetch()}
        description="Indicadores indisponíveis nesta publicação."
      />
    );
  return (
    <section className="metrics" aria-label="Indicadores de gestão">
      {q
        .compare((data) =>
          managerMetrics(page.metricIds, page.resource, data, q.data?.metadata),
        )
        .map((item, index) => (
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
function MetricGrid({ page }: { page: ManagerPage }) {
  return (
    <section className="metrics" aria-label="Indicadores de gestão">
      {managerMetrics(page.metricIds, page.resource, null).map(
        (item, index) => (
          <MetricCard
            key={page.metricIds[index]}
            item={item}
            index={index}
            decorativeTrend={false}
          />
        ),
      )}
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
