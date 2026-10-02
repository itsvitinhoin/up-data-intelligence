"use client";
import { useResource } from "@/hooks/use-resource";
import { Failure, Loading, MetricCard } from "@/components/ui-kit";
import type { Metric } from "@/types/domain";
export function LeadCards() {
  const q = useResource("leads");
  const metrics: Metric[] = q.compare((data) => [
    {
      label: "Leads",
      value: String(data.leads),
      format: "number",
      hint: "Cadastros únicos da marca no período, de todas as origens. Base demonstrativa; independe de canal e coleção.",
    },
    {
      label: "Leads aprovados",
      value: String(data.approved),
      format: "number",
      hint: "Dos leads cadastrados no período, quantos foram aprovados até o fim do recorte.",
    },
    {
      label: "Qualificação de leads",
      value:
        data.qualificationRate === null ? null : String(data.qualificationRate),
      format: "percent",
      hint: "Leads aprovados / leads cadastrados no período × 100.",
    },
    {
      label: "Taxa de conversão",
      value: data.conversionRate === null ? null : String(data.conversionRate),
      format: "percent",
      hint: "Leads aprovados com compra qualificante após aprovação / leads aprovados × 100, até o fim do período. Cada lead conta uma vez; não confirma pagamento.",
    },
  ]);
  return (
    <section aria-label="Indicadores de Leads" className="overview-metrics">
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <div className="metrics">
          {metrics.map((item, index) => (
            <MetricCard key={item.label} item={item} index={index} />
          ))}
        </div>
      )}
    </section>
  );
}
