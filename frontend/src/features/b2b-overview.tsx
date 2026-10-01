"use client";
import { LeadCards } from "@/components/lead-cards";
import dynamic from "next/dynamic";
import type { Metric, Overview } from "@/types/domain";
import { MetricCard, Panel, Notice } from "@/components/ui-kit";
import type { PreviewOverview } from "@/services/api/overview-presenter";
const OverviewChart = dynamic(
  () => import("@/components/overview-charts").then((m) => m.OverviewChart),
  { ssr: false },
);
const Gauge = dynamic(
  () => import("@/components/charts").then((m) => m.Gauge),
  { ssr: false },
);
type Data = NonNullable<Overview["b2b"]> | PreviewOverview["data"];
function Metrics({ title, items }: { title: string; items: Metric[] }) {
  return (
    <section
      aria-label={`Indicadores de ${title}`}
      className="overview-metrics"
    >
      <div className="metrics">
        {items.map((item, index) => (
          <MetricCard key={item.label} item={item} index={index} />
        ))}
      </div>
    </section>
  );
}
export function B2BOverview({
  data,
  goal,
  preview = false,
}: {
  data: Data;
  goal: Overview["goal"] | PreviewOverview["goal"];
  preview?: boolean;
}) {
  return (
    <div className="b2b-overview">
      <Metrics title="Receita" items={data.revenue} />
      {preview ? (
        <Notice>
          Cadastros e aprovação ainda não estão disponíveis nesta geração de
          dados.
        </Notice>
      ) : (
        <LeadCards />
      )}
      <section className="overview-revenue-row">
        <Panel
          title="Solicitado × Atendido por período"
          subtitle="Valores comerciais; atendimento não confirma pagamento"
        >
          <OverviewChart
            data={data.series}
            kind="revenue"
            currencyDigits={preview ? 2 : 0}
          />
        </Panel>
        <Panel
          title="Eficiência de Atendimento"
          subtitle="Atendido em relação ao solicitado"
        >
          <Gauge {...goal} />
        </Panel>
      </section>
      <Metrics title="Pedidos" items={data.orders} />
      <Metrics title="Clientes" items={data.customers} />
      <Panel
        title="Novos × Recorrentes por período"
        subtitle="Recorrentes observados por dia. Novos dependem da confirmação do histórico; ausência de dado não é zero."
      >
        {preview ? (
          <Notice>
            Série diária de novos e recorrentes ainda não disponível nesta
            publicação.
          </Notice>
        ) : (
          <OverviewChart data={data.series} kind="customers" />
        )}
      </Panel>
      <Metrics title="Relacionamento" items={data.relationship} />
    </div>
  );
}
