"use client";
import dynamic from "next/dynamic";
import { useResource } from "@/hooks/use-resource";
import { Panel, MetricCard, Loading, Failure } from "@/components/ui-kit";
import type { Metric } from "@/types/domain";
const RetentionTrend = dynamic(
  () => import("@/components/retention-trend").then((m) => m.RetentionTrend),
  { ssr: false },
);
export function RetentionMetrics() {
  const q = useResource("retention_summary");
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  const d = q.data;
  const metrics: Metric[] = q.compare((data) => [
    {
      label: "Compradores",
      value: data.buyers === null ? null : String(data.buyers),
      format: "number",
      hint: "Clientes distintos com compra qualificante no período.",
    },
    {
      label: "Compradores Recorrentes",
      value: data.recurring === null ? null : String(data.recurring),
      format: "number",
      hint: "Compradores com recompra no período e uma compra anterior observada, inclusive antes do recorte.",
    },
    {
      label: "% de Retenção",
      value: data.rate === null ? null : String(data.rate),
      format: "percent",
      hint: "Compradores recorrentes / compradores do período. Não é retenção por coorte.",
    },
    {
      label: "Ticket Médio de Retenção",
      value: data.ticket === null ? null : String(data.ticket),
      format: "currency",
      hint: "Receita atendida de recompras / pedidos de recompra no período; não confirma pagamento.",
    },
  ]);
  return (
    <>
      <section className="metrics" aria-label="Indicadores de Retenção">
        {metrics.map((item) => (
          <MetricCard key={item.label} item={item} />
        ))}
      </section>
      <Panel
        title="% de Retenção por período"
        subtitle="Recorrentes / compradores distintos em cada período da série selecionada. Semanas sem compradores ficam sem taxa; histórico observado parcial."
      >
        <RetentionTrend data={d.weekly} />
      </Panel>
    </>
  );
}
