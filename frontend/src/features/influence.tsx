"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";
import dynamic from "next/dynamic";
import { ConversionVelocity } from "@/features/lifecycle";
import Link from "next/link";
import { OrderDialog } from "@/components/order-dialog";
import { money, number } from "@/lib/format";
import Image from "next/image";
import type { CampaignDetail, Metric } from "@/types/domain";
import type { MetaPeriodRow } from "@/services/api/meta-ads";
import { useState } from "react";
import { useResource, useCampaign } from "@/hooks/use-resource";
import { useWorkspace } from "@/features/providers";
import {
  PageHead,
  Panel,
  Loading,
  Failure,
  Notice,
  MetricCard,
  Choice,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { DataTable } from "@/components/data-table";
import {
  customerColumns,
  orderColumns,
  campaignColumns,
} from "@/components/business";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
const CommercialTrend = dynamic(
  () => import("@/components/charts").then((m) => m.RevenueChart),
  { ssr: false },
);
function PerformanceTrend() {
  const q = useResource("overview");
  return (
    <Panel
      title="Faturamento comercial por período"
      subtitle="Receita solicitada e atendida UP Zero; atendimento não comprova pagamento."
    >
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <CommercialTrend data={q.data.series} />
      )}
    </Panel>
  );
}
function DemoInfluencePage({
  acquisition = false,
  performance = false,
}: {
  acquisition?: boolean;
  performance?: boolean;
}) {
  const q = useResource("influence");
  return (
    <>
      <PageHead
        eyebrow={
          performance
            ? "B2B · Performance de mídia paga"
            : acquisition
              ? "Aquisição · histórico observado"
              : "Mídia · participação na jornada"
        }
        title={
          performance ? (
            <>
              Mídia paga e <em className="hl hl--up">resultado comercial.</em>
            </>
          ) : acquisition ? (
            "Aquisição e clientes influenciados"
          ) : (
            "Clientes, pedidos e campanhas participantes"
          )
        }
        description="A relação entre mídia e resultado comercial, sem atribuição exclusiva."
      />
      <FiltersBar />
      <Notice>
        {acquisition
          ? "Primeira compra observada não confirma cliente novo. CAC e reativação dependem de cobertura e policy."
          : "Totais calculados pela união dos pedidos. A participação de várias campanhas não multiplica a receita."}
      </Notice>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <div className="metrics">
            {q
              .compare((data) => {
                if (data.metrics)
                  return performance ? data.metrics : data.metrics.slice(0, 4);
                const previousSpend = data.campaigns.reduce(
                  (sum, campaign) => sum + Number(campaign.spend),
                  0,
                );
                return [
                  {
                    hint: "Deduplicado na operação selecionada",
                    label: "Clientes influenciados",
                    value: String(data.customers.length),
                    format: "number" as const,
                  },
                  {
                    label: "Pedidos influenciados",
                    value: String(data.orders.length),
                    format: "number" as const,
                  },
                  {
                    label: "Receita Solicitada Influenciada",
                    value: data.requested,
                    format: "currency" as const,
                  },
                  {
                    label: "Receita Atendida Influenciada",
                    value: data.fulfilled,
                    format: "currency" as const,
                  },
                  ...(performance
                    ? [
                        {
                          label: "Investimento em mídias",
                          value: String(previousSpend),
                          format: "currency" as const,
                        },
                        {
                          label: "ROAS solicitado influenciado",
                          value:
                            previousSpend > 0
                              ? String(Number(data.requested) / previousSpend)
                              : null,
                          format: "ratio" as const,
                        },
                        {
                          label: "ROAS atendido influenciado",
                          value:
                            previousSpend > 0
                              ? String(Number(data.fulfilled) / previousSpend)
                              : null,
                          format: "ratio" as const,
                        },
                        {
                          label: "ROI",
                          value: null,
                          format: "percent" as const,
                        },
                      ]
                    : []),
                ].map((m) => ({
                  ...m,
                  hint: "Deduplicado na operação selecionada",
                }));
              })
              .map((m) => (
                <MetricCard
                  key={m.label}
                  item={{ ...m, hint: "Deduplicado na operação selecionada" }}
                />
              ))}
          </div>
          {performance && <PerformanceTrend />}
          {acquisition && <ConversionVelocity />}
          <Panel title="Clientes influenciados">
            <DataTable data={q.data.customers} columns={customerColumns} />
          </Panel>
          <Panel title="Pedidos influenciados">
            <DataTable data={q.data.orders} columns={orderColumns} />
          </Panel>
          {performance && (
            <Link className="btn btn--glass w-fit" href="/campaigns">
              Explorar campanhas e criativos →
            </Link>
          )}
          <Panel title="Campanhas participantes">
            <DataTable data={q.data.campaigns} columns={campaignColumns} />
          </Panel>
        </>
      )}
    </>
  );
}
function MetaCampaignDetail({
  report,
}: {
  report: NonNullable<CampaignDetail["meta"]>;
}) {
  const campaign = report.campaign;
  const metrics: Omit<Metric, "hint">[] = [
    { label: "Investimento Meta", value: campaign.spend, format: "currency" },
    {
      label: "Compras reportadas pelo Meta",
      value: campaign.meta_reported_purchases,
      format: "number",
    },
    {
      label: "Valor de compras reportado pelo Meta",
      value: campaign.meta_reported_purchase_value,
      format: "currency",
    },
    { label: "ROAS Meta", value: campaign.roas, format: "ratio" },
    { label: "CPA Meta", value: campaign.cpa, format: "currency" },
    {
      label: "Alcance Meta",
      value: campaign.reach === null ? null : String(campaign.reach),
      format: "number",
    },
    { label: "Frequência Meta", value: campaign.frequency, format: "decimal" },
    { label: "CTR Meta", value: campaign.ctr, format: "percent" },
  ];
  const columns = (entity: "adset" | "ad") => [
    {
      accessorKey: entity + "_name",
      header: entity === "adset" ? "Conjunto" : "Anúncio",
    },
    { accessorKey: entity + "_status", header: "Status" },
    {
      accessorKey: "spend",
      header: "Investimento",
      cell: ({ row }: { row: { original: MetaPeriodRow } }) =>
        money(row.original.spend),
    },
    {
      accessorKey: "meta_reported_purchases",
      header: "Compras Meta",
      cell: ({ row }: { row: { original: MetaPeriodRow } }) =>
        number(
          row.original.meta_reported_purchases === null
            ? null
            : Number(row.original.meta_reported_purchases),
        ),
    },
    {
      accessorKey: "meta_reported_purchase_value",
      header: "Valor de compras Meta",
      cell: ({ row }: { row: { original: MetaPeriodRow } }) =>
        money(row.original.meta_reported_purchase_value),
    },
    {
      accessorKey: "cpa",
      header: "CPA Meta",
      cell: ({ row }: { row: { original: MetaPeriodRow } }) =>
        money(row.original.cpa),
    },
    ...(entity === "ad"
      ? [
          {
            id: "preview",
            header: "Criativo atual",
            cell: ({ row }: { row: { original: MetaPeriodRow } }) =>
              row.original.preview_url ? (
                <Image
                  src={row.original.preview_url}
                  width={100}
                  height={120}
                  unoptimized
                  alt="Prévia oficial Meta"
                />
              ) : (
                <span className="muted">Prévia não fornecida pelo Meta</span>
              ),
          },
        ]
      : []),
  ];
  return (
    <>
      <Link href="/campaigns" className="back-link">
        ← Meta Ads
      </Link>
      <PageHead
        eyebrow="Meta Ads · Campanha"
        title={campaign.campaign_name ?? "Campanha Meta"}
        description="Métricas oficiais da plataforma no período selecionado."
      />
      <FiltersBar />
      <Notice>
        Compras e valores reportados pelo Meta. Não representam receita
        comercial UP Zero nem atribuição de pedidos. Prévia e status são do
        catálogo atual.
      </Notice>
      <div className="metrics">
        {metrics.map((item) => (
          <MetricCard
            key={item.label}
            item={{
              ...item,
              hint: "Relatório oficial Meta all_days; família de compras certificada.",
            }}
            decorativeTrend={false}
          />
        ))}
      </div>
      <Panel title="Conjuntos de anúncios">
        <DataTable data={report.adsets} columns={columns("adset")} />
      </Panel>
      <Panel title="Anúncios e criativos">
        <DataTable data={report.ads} columns={columns("ad")} />
      </Panel>
    </>
  );
}
function DemoCampaignDetailPage({ id }: { id: string }) {
  const q = useCampaign(id);
  const [tab, setTab] = useState("customers");
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  const d = q.data;
  if (d.meta) return <MetaCampaignDetail report={d.meta} />;
  const orders = d.orders.map((o) => ({
    ...o,
    customer_name:
      d.customers.find((c) => c.id === o.customer_id)?.name ?? o.customer_id,
    campaign_name: d.campaign.name,
  }));
  return (
    <>
      <Link href="/campaigns" className="back-link">
        ← Campanhas
      </Link>
      <PageHead
        eyebrow="Performance · Campanha"
        title={d.campaign.name}
        description="Campanha participou da jornada."
      />
      <Notice>
        Pedidos e clientes distintos dentro desta campanha. Não some receita
        entre campanhas.
      </Notice>
      <div className="metrics">
        {q
          .compare((data) => [
            {
              label: "Spend",
              value: data.campaign.spend,
              format: "currency" as const,
              hint: "Campanha no recorte",
            },
            {
              label: "Receita Solicitada",
              value: data.requested,
              format: "currency" as const,
              hint: "Campanha no recorte",
            },
            {
              label: "Receita Atendida",
              value: data.fulfilled,
              format: "currency" as const,
              hint: "Campanha no recorte",
            },
          ])
          .map((m) => (
            <MetricCard
              key={m.label}
              item={{
                ...m,
                format: "currency",
                hint: "Influência observada, sem atribuição exclusiva",
              }}
            />
          ))}
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="tab-list glass">
          <TabsTrigger value="customers">Clientes influenciados</TabsTrigger>
          <TabsTrigger value="orders">Pedidos influenciados</TabsTrigger>
        </TabsList>
        <TabsContent value="customers">
          <Panel title="Clientes influenciados">
            <DataTable
              data={d.customers}
              columns={customerColumns.filter(
                (c) =>
                  "accessorKey" in c &&
                  ["name", "orders", "requested", "fulfilled"].includes(
                    String(c.accessorKey),
                  ),
              )}
            />
          </Panel>
        </TabsContent>
        <TabsContent value="orders">
          <Panel title="Pedidos influenciados">
            <DataTable
              data={orders}
              columns={[
                {
                  accessorKey: "id",
                  header: "Pedido",
                  cell: ({ row }) => <OrderDialog id={row.original.id} />,
                },
                {
                  accessorKey: "customer_name",
                  header: "Cliente",
                  cell: ({ row }) => (
                    <Link href={`/customers/${row.original.customer_id}`}>
                      {row.original.customer_name}
                    </Link>
                  ),
                },
                { accessorKey: "campaign_name", header: "Campanha" },
                {
                  accessorKey: "requested",
                  header: "Solicitado",
                  cell: (i) => money(i.getValue<string>()),
                },
                {
                  accessorKey: "fulfilled",
                  header: "Atendido",
                  cell: (i) => money(i.getValue<string>()),
                },
              ]}
            />
          </Panel>
        </TabsContent>
      </Tabs>
    </>
  );
}
function DemoCommercialPage({ revenue = false }: { revenue?: boolean }) {
  const q = useResource("orders");
  const overview = useResource("overview");
  const { scope } = useWorkspace();
  const [status, setStatus] = useState("all");
  return (
    <>
      <PageHead
        eyebrow={`${scope?.operation} · ${revenue ? "Receita" : "Pedidos"}`}
        title={
          revenue
            ? "Receita comercial e confirmação financeira"
            : "Pedidos no período"
        }
        description="Valores solicitados, atendidos e quantidades preservados por pedido."
      />
      <FiltersBar />
      {overview.data && (
        <div className="metrics">
          {overview.data.metrics
            .filter((m) =>
              revenue ? m.group === "Receita" : m.group === "Pedidos",
            )
            .map((m) => (
              <MetricCard key={m.label} item={m} />
            ))}
        </div>
      )}
      <Panel
        title="Pedidos no recorte"
        action={
          <Choice
            label="Status do pedido"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "Todos" },
              { value: "CANCELED", label: "Cancelado" },
              { value: "CONFIRMED", label: "Confirmado" },
              { value: "SHIPPED", label: "Enviado" },
              { value: "DELIVERED", label: "Entregue" },
              { value: "INVOICED", label: "Faturado" },
            ]}
          />
        }
      >
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <Failure retry={() => void q.refetch()} />
        ) : (
          <DataTable
            key={status}
            data={q.data.filter(
              (row) => status === "all" || row.status === status,
            )}
            columns={orderColumns}
          />
        )}
      </Panel>
    </>
  );
}

export function InfluencePage(props: {
  acquisition?: boolean;
  performance?: boolean;
}) {
  return (
    <B2BReadBoundary>
      <DemoInfluencePage {...props} />
    </B2BReadBoundary>
  );
}
export function CommercialPage(props: { revenue?: boolean }) {
  return (
    <B2BReadBoundary>
      <DemoCommercialPage {...props} />
    </B2BReadBoundary>
  );
}

export function CampaignDetailPage({ id }: { id: string }) {
  return (
    <B2BReadBoundary>
      <DemoCampaignDetailPage id={id} />
    </B2BReadBoundary>
  );
}
