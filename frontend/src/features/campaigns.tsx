"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";
import { ListExport } from "@/components/exports";
import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import dynamic from "next/dynamic";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowUpRight, MousePointer2, Target, Users } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import { useWorkspace } from "@/features/providers";
import {
  PageHead,
  Panel,
  MetricCard,
  Notice,
  Loading,
  Failure,
  Empty,
  Choice,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { DataTable } from "@/components/data-table";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { money, number, metric } from "@/lib/format";
import { rankCreatives, ratio } from "@/lib/marketing";
import type { Marketing, MarketingCreative, Metric } from "@/types/domain";
const MarketingChart = dynamic(
  () => import("@/components/marketing-charts").then((m) => m.MarketingChart),
  { ssr: false },
);
const sumCreatives = (
  rows: MarketingCreative[],
  key: "spend" | "leads" | "approved" | "purchases" | "clicks" | "impressions",
) =>
  rows.some((row) => row[key] === null)
    ? null
    : rows.reduce((sum, row) => sum + row[key]!, 0);
const times = (value: number | null, factor: number) =>
  value === null ? null : value * factor;
const cost = (r: MarketingCreative, b2c: boolean) =>
  ratio(r.spend, b2c ? r.purchases : r.leads);
const pct = (value: number | null) =>
  value === null
    ? "—"
    : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const statusLabel = (value: string | null) =>
  value === null
    ? "Indisponível"
    : value === "ACTIVE"
      ? "Ativa"
      : value === "PAUSED"
        ? "Pausada"
        : value;

function CreativePreview({
  creative,
  large = false,
}: {
  creative: MarketingCreative;
  large?: boolean;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  return (
    <div className={large ? "creative-preview large" : "creative-preview"}>
      {creative.preview && failedUrl !== creative.preview ? (
        <Image
          src={creative.preview}
          alt={`${creative.source === "real" ? "Prévia Meta" : "Prévia ilustrativa"}: ${creative.name}`}
          width={480}
          height={600}
          unoptimized
          onError={() => setFailedUrl(creative.preview)}
        />
      ) : (
        <p className="muted text-sm">Prévia indisponível</p>
      )}
      <span>
        {creative.format} · {creative.source === "real" ? "Meta" : "demo"}
      </span>
    </div>
  );
}
function CreativeRank({
  title,
  kind,
  rows,
  b2c,
  onSelect,
}: {
  title: string;
  kind: "ctr" | "cost" | "results";
  rows: MarketingCreative[];
  b2c: boolean;
  onSelect: (creative: MarketingCreative) => void;
}) {
  const Icon =
    kind === "ctr" ? MousePointer2 : kind === "cost" ? Target : Users;
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Icon size={16} />
          {title}
        </span>
      }
      subtitle="Top 3 do recorte selecionado"
      action={<ListExport rows={rows} name={`criativos-${kind}`} />}
    >
      <div className="creative-ranking">
        {rows.length ? (
          rows.map((ad, i) => (
            <button
              type="button"
              className="creative-rank"
              key={ad.id}
              onClick={() => onSelect(ad)}
              aria-label={`Ver criativo ${ad.name} — ${title}`}
            >
              <CreativePreview creative={ad} />
              <div className="creative-rank-copy">
                <small>
                  0{i + 1} · {ad.placement}
                </small>
                <strong>{ad.name}</strong>
                <span>{ad.campaign_name}</span>
                <div className="creative-result num">
                  {kind === "ctr"
                    ? pct(ratio(times(ad.clicks, 100), ad.impressions))
                    : kind === "cost"
                      ? money(cost(ad, b2c))
                      : number(b2c ? ad.purchases : ad.leads)}
                  <ArrowUpRight size={14} />
                </div>
                <small>
                  {money(ad.spend)} investidos · {number(ad.impressions)}{" "}
                  impressões
                </small>
              </div>
            </button>
          ))
        ) : (
          <p className="muted text-sm">
            Criativos indisponíveis ou sem resultados elegíveis neste ranking.
          </p>
        )}
      </div>
    </Panel>
  );
}
export function marketingMetrics(data: Marketing): Metric[] {
  if (data.metrics) return data.metrics;
  const sum = (
    key:
      "spend" | "leads" | "approved" | "purchases" | "clicks" | "impressions",
  ) => sumCreatives(data.creatives, key);
  const spend = sum("spend"),
    purchases = sum("purchases");
  // The series contains deduplicated order revenue; campaign revenue is not additive.

  const kpi = (
    label: string,
    value: number | null,
    format: Metric["format"],
    hint: string,
  ): Metric => ({
    label,
    value: value === null ? null : String(value),
    format,
    hint,
  });
  const metrics = [
    kpi(
      "Investimento em mídia",
      spend,
      "currency",
      "Gasto da plataforma Meta Ads no período.",
    ),
    kpi(
      "Faturamento atribuído",
      null,
      "currency",
      "Atribuição de pedidos à plataforma não confirmada; influência observada não é atribuição exclusiva.",
    ),
    kpi(
      "ROAS",
      null,
      "ratio",
      "Faturamento atribuído / investimento em mídia. Depende da regra de atribuição e cobertura de pedidos.",
    ),
    kpi(
      "CTR médio",
      ratio(times(sum("clicks"), 100), sum("impressions")),
      "percent",
      "Cliques / impressões × 100, ponderado pelo volume.",
    ),
    kpi(
      "CPM",
      ratio(times(spend, 1000), sum("impressions")),
      "currency",
      "Investimento / impressões × 1.000.",
    ),
    kpi(
      "Frequência",
      null,
      "decimal",
      "Impressões / alcance único. Alcance não está disponível no dado demonstrativo.",
    ),
    kpi(
      "CPC",
      ratio(spend, sum("clicks")),
      "currency",
      "Investimento / cliques.",
    ),
    kpi(
      "Custo por compra",
      ratio(spend, purchases),
      "currency",
      "Investimento / compras reportadas pela plataforma, sem conciliação com pedidos.",
    ),
  ];

  return metrics;
}
function MarketingContent({
  data,
  b2c,
  compare,
}: {
  data: Marketing;
  b2c: boolean;
  compare: (select: (data: Marketing) => Metric[]) => Metric[];
}) {
  const [selected, setSelected] = useState<MarketingCreative | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const metrics = compare(marketingMetrics);
  const sum = (key: "spend" | "leads" | "clicks" | "impressions") =>
    sumCreatives(data.creatives, key);
  const spend = data.summary ? data.summary.spend : sum("spend"),
    leads = data.summary ? data.summary.leads : sum("leads");
  type Row = Marketing["campaigns"][number];
  const columns: ColumnDef<Row>[] = [
    {
      accessorKey: "name",
      header: "Campanha",
      cell: ({ row }) => (
        <Link className="customer-link" href={`/campaigns/${row.original.id}`}>
          {row.original.name} <ArrowUpRight size={13} />
        </Link>
      ),
    },
    { accessorKey: "platform", header: "Plataforma" },
    {
      accessorKey: "status",
      header: "Status",
      cell: (c) => (
        <span className="pill">{statusLabel(c.getValue<string>())}</span>
      ),
    },
    {
      accessorKey: "spend",
      header: "Investimento",
      cell: (c) => money(c.getValue<string>()),
    },
    {
      accessorKey: "fulfilled",
      header: "Receita influenciada",
      cell: (c) => money(c.getValue<string>()),
    },
    {
      accessorKey: "roasFulfilled",
      header: "ROAS",
      cell: (c) => metric(c.getValue<string>(), "ratio"),
    },
    {
      accessorKey: "leads",
      header: "Leads",
      cell: (c) => number(c.getValue<number | null>()),
    },
    {
      accessorKey: b2c ? "purchases" : "approved",
      header: b2c ? "Compras Meta" : "Aprovados",
      cell: (c) => number(c.getValue<number | null>()),
    },
    {
      id: "cost",
      header: b2c ? "Custo/compra" : "CPL",
      accessorFn: (row) =>
        ratio(
          row.spend === null ? null : Number(row.spend),
          b2c ? row.purchases : row.leads,
        ),
      cell: (c) => money(c.getValue<number | null>()),
    },
    ...(!b2c
      ? [
          {
            id: "cpa",
            header: "CPA aprovado",
            accessorFn: (row: Row) =>
              ratio(
                row.spend === null ? null : Number(row.spend),
                row.approved,
              ),
            cell: (c: { getValue: () => unknown }) =>
              money(c.getValue() as number | null),
          },
        ]
      : []),
    { accessorKey: "clicks", header: "Cliques" },
    {
      id: "ctr",
      header: "CTR",
      accessorFn: (row) =>
        ratio(row.clicks === null ? null : row.clicks * 100, row.impressions),
      cell: (c) => pct(c.getValue<number | null>()),
    },
  ];
  const campaigns = data.campaigns.filter(
    (row) =>
      (status === "all" || row.status === status) &&
      (row.name ?? "")
        .toLocaleLowerCase("pt-BR")
        .includes(search.toLocaleLowerCase("pt-BR")),
  );
  return (
    <>
      <section aria-label="Indicadores de Marketing" className="metrics">
        {metrics.map((item, i) => (
          <MetricCard key={item.label} item={item} index={i} />
        ))}
      </section>
      <section aria-label="Criativos em destaque">
        <div className="marketing-section-head">
          <div>
            <h2 className="card-title">Criativos em destaque</h2>
            <p className="card-sub">
              Compare atenção, eficiência e volume. Clique para inspecionar o
              anúncio.
            </p>
          </div>
          <span className="pill">
            {data.source === "real"
              ? data.creatives.length
                ? "Meta Ads · métricas por anúncio"
                : "Meta Ads · cobertura de criativos indisponível"
              : "Meta Ads · demonstração"}
          </span>
        </div>
        <div className="marketing-rankings">
          <CreativeRank
            title="Maior CTR"
            kind="ctr"
            rows={rankCreatives(data.creatives, "ctr", true)}
            b2c={true}
            onSelect={setSelected}
          />
          <CreativeRank
            title="Menor CPA · custo por compra"
            kind="cost"
            rows={rankCreatives(data.creatives, "cost", true)}
            b2c={true}
            onSelect={setSelected}
          />
          <CreativeRank
            title="Mais compras"
            kind="results"
            rows={rankCreatives(data.creatives, "results", true)}
            b2c={true}
            onSelect={setSelected}
          />
        </div>
      </section>
      <section className="marketing-trends">
        <Panel
          title={b2c ? "Investimento × Compras" : "Investimento × Leads"}
          subtitle={
            data.source === "real"
              ? "Investimento diário certificado; leads não disponíveis"
              : "Volume e investimento por dia · série sintética"
          }
        >
          <MarketingChart series={data.series} kind="results" b2c={b2c} />
        </Panel>
        <Panel
          title="ROAS ao longo do período"
          subtitle="Receita influenciada / investimento"
        >
          <MarketingChart series={data.series} kind="roas" b2c={b2c} />
        </Panel>
      </section>
      <Panel
        title="Investimento × Receita"
        subtitle="Receita atendida dos pedidos com influência de mídia, sem duplicação"
      >
        <MarketingChart series={data.series} kind="revenue" b2c={b2c} />
      </Panel>
      <section className="marketing-breakdowns">
        <Panel
          title="Performance por plataforma"
          subtitle="Mesma base dos indicadores gerais"
        >
          <div className="platform-summary">
            <span className="pill">Meta Ads</span>
            <strong className="num">{money(spend)}</strong>
            <small>
              {data.source === "real"
                ? "Investimento da plataforma Meta nesta publicação"
                : "100% do investimento deste cenário"}
            </small>
          </div>
          <dl className="detail-list">
            <div>
              <dt>Leads</dt>
              <dd>{number(leads)}</dd>
            </div>
            <div>
              <dt>Cliques</dt>
              <dd>
                {number(data.summary ? data.summary.clicks : sum("clicks"))}
              </dd>
            </div>
            <div>
              <dt>CTR ponderado</dt>
              <dd>
                {data.summary
                  ? metric(data.summary.ctr, "percent")
                  : pct(ratio(times(sum("clicks"), 100), sum("impressions")))}
              </dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Performance por região" subtitle="ROAS por estado">
          <p className="muted text-sm leading-relaxed">
            O recorte de investimento por estado ainda não está disponível. O
            ranking regional será exibido quando receita e investimento puderem
            ser comparados na mesma base.
          </p>
          <Link
            className="btn btn--glass mt-5 w-fit"
            href={b2c ? "/b2c/customers" : "/b2b/geography"}
          >
            Explorar {b2c ? "clientes" : "geografia comercial"}{" "}
            <ArrowUpRight size={14} />
          </Link>
        </Panel>
      </section>
      <Panel
        title="Performance por campanha"
        subtitle="Clique na campanha para ver os clientes e pedidos participantes. Receitas de campanhas podem se sobrepor."
      >
        <div className="marketing-table-filters">
          <Input
            aria-label="Buscar campanha"
            placeholder="Buscar campanha…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Choice
            label="Status da campanha"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "Todos os status" },
              { value: "ACTIVE", label: "Ativas" },
              { value: "PAUSED", label: "Pausadas" },
            ]}
          />
        </div>
        <DataTable
          key={`${search}:${status}`}
          data={campaigns}
          columns={columns}
        />
      </Panel>
      <Sheet
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="detail-sheet">
          {selected && (
            <>
              <SheetTitle>{selected.name}</SheetTitle>
              <SheetDescription>
                {selected.source === "real"
                  ? "Métricas reportadas pelo Meta por anúncio. A prévia e o status são do catálogo atual; não representam atribuição comercial."
                  : "Prévia ilustrativa · métricas sintéticas · nenhum anúncio real conectado."}
              </SheetDescription>
              <CreativePreview creative={selected} large />
              {selected.source === "real" && selected.previewObservedAt && (
                <p className="muted text-sm">
                  Prévia/status observados em{" "}
                  {new Date(selected.previewObservedAt).toLocaleString("pt-BR")}{" "}
                  · links de mídia podem expirar.
                </p>
              )}
              <p className="muted text-sm">
                {selected.placement} · {selected.format} ·{" "}
                {statusLabel(selected.status)}
              </p>
              <dl className="detail-list">
                {[
                  ["Investimento", money(selected.spend)],
                  ["Impressões", number(selected.impressions)],
                  ["Cliques", number(selected.clicks)],
                  [
                    "CTR",
                    pct(
                      ratio(times(selected.clicks, 100), selected.impressions),
                    ),
                  ],
                  [
                    b2c || selected.source === "real"
                      ? "Compras Meta"
                      : "Leads",
                    number(
                      b2c || selected.source === "real"
                        ? selected.purchases
                        : selected.leads,
                    ),
                  ],
                  [
                    b2c || selected.source === "real"
                      ? "Custo por compra"
                      : "CPL",
                    money(cost(selected, b2c || selected.source === "real")),
                  ],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd className="num">{value}</dd>
                  </div>
                ))}
              </dl>
              <Link
                className="btn btn--glass"
                href={`/campaigns/${selected.campaign_id}`}
              >
                Explorar campanha <ArrowUpRight size={14} />
              </Link>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
export type CampaignPlatform =
  "Meta Ads" | "Google Ads" | "Pinterest Ads" | "TikTok Ads";
function MetaContent() {
  const { scope, filters } = useWorkspace();
  const q = useResource("marketing");
  return q.isPending ? (
    <Loading />
  ) : q.isError ? (
    <Failure retry={() => void q.refetch()} />
  ) : (
    <MarketingContent
      key={`${scope?.store_id}:${JSON.stringify(filters)}`}
      data={q.data}
      compare={q.compare}
      b2c={scope?.operation === "B2C"}
    />
  );
}
function DemoCampaignsPage({
  platform = "Meta Ads",
}: {
  platform?: CampaignPlatform;
}) {
  const { scope, dataMode } = useWorkspace();
  const labels = [
    "Investimento em mídia",
    "Faturamento atribuído",
    "ROAS",
    "CTR médio",
    "CPM",
    "Frequência",
    "CPC",
    "Custo por compra",
  ] as const;
  return (
    <>
      <PageHead
        eyebrow={`${scope?.operation} · Campanhas · ${platform}`}
        title={
          <>
            Campanhas <em className="hl hl--up">{platform}.</em>
          </>
        }
        description="Investimento, criativos e resultado por plataforma no período selecionado."
      />
      <FiltersBar showChannel={false} />
      <Notice>
        {platform === "Meta Ads"
          ? `${dataMode === "demo" ? "Dados sintéticos Meta." : "Dados reais Meta; criativos ainda não certificados."} Receita influenciada e faturamento atribuído têm significados diferentes; a atribuição não está confirmada.`
          : `A integração ${platform} ainda não fornece métricas nesta operação. Ausência de dados não representa zero.`}
      </Notice>
      {platform === "Meta Ads" ? (
        <MetaContent />
      ) : (
        <>
          <section
            className="metrics"
            aria-label={`Indicadores de ${platform}`}
          >
            {labels.map((label) => (
              <MetricCard
                key={label}
                item={{
                  label,
                  value: null,
                  format: [
                    "Faturamento atribuído",
                    "Investimento em mídia",
                    "CPM",
                    "CPC",
                    "Custo por compra",
                  ].includes(label)
                    ? "currency"
                    : label === "CTR médio"
                      ? "percent"
                      : label === "ROAS"
                        ? "ratio"
                        : "decimal",
                  hint: `${platform}: fonte de dados ainda não conectada.`,
                }}
              />
            ))}
          </section>
          <Empty
            title={`Sem campanhas de ${platform}`}
            description="Aguardando integração da plataforma para exibir criativos e rankings desta fonte."
          />
        </>
      )}
    </>
  );
}

export function CampaignsPage(props: { platform?: CampaignPlatform }) {
  return (
    <B2BReadBoundary>
      <DemoCampaignsPage {...props} />
    </B2BReadBoundary>
  );
}
