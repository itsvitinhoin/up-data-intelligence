"use client";
import { LeadCards } from "@/components/lead-cards";
import dynamic from "next/dynamic";
import type { Metric, Overview } from "@/types/domain";
import { MetricCard, Panel } from "@/components/ui-kit";
const OverviewChart = dynamic(
  () => import("@/components/overview-charts").then((m) => m.OverviewChart),
  { ssr: false },
);
const Gauge = dynamic(
  () => import("@/components/charts").then((m) => m.Gauge),
  { ssr: false },
);
type Data = NonNullable<Overview["b2b"]>;
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
}: {
  data: Data;
  goal: Overview["goal"];
}) {
  return (
    <div className="b2b-overview">
      <Metrics title="Receita" items={data.revenue} />
      <LeadCards />
      <section className="overview-revenue-row">
        <Panel
          title="Solicitado × Atendido por período"
          subtitle="Valores comerciais; atendimento não confirma pagamento"
        >
          <OverviewChart data={data.series} kind="revenue" />
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
        <OverviewChart data={data.series} kind="customers" />
      </Panel>
      <Metrics title="Relacionamento" items={data.relationship} />
    </div>
  );
}
