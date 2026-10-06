"use client";
import { useResource } from "@/hooks/use-resource";
import { Failure, Loading, MetricCard } from "@/components/ui-kit";
import type { Metric } from "@/types/domain";
export function LeadCards() {
  const q = useResource("leads");
  const metrics: Metric[] = q.compare((data) => [
    {
      label: "Leads",
      value: data.leads === null ? null : String(data.leads),
      format: "number",
      hint: "Eventos register_submitted realizados no período, deduplicados pela identidade canônica do evento. Não é contagem de pessoas lifetime.",
    },
    {
      label: "Leads aprovados",
      value: data.approved === null ? null : String(data.approved),
      format: "number",
      hint: "Aprovações register_approved realizadas no período, incluindo cadastros de períodos anteriores.",
    },
    {
      label: "Taxa de aprovação / qualificação",
      value:
        data.qualificationRate === null ? null : String(data.qualificationRate),
      format: "percent",
      hint: "Aprovações / cadastros no período × 100. Pode exceder 100% por backlog.",
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
