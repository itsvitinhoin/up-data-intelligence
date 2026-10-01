"use client";
import { RetailOverview } from "@/features/retail";
import { B2BOverview } from "@/features/b2b-overview";
import { useWorkspace } from "@/features/providers";
import { useOverviewData } from "@/hooks/use-overview-data";
import { PageHead, Loading, Failure, Notice } from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
export function OverviewPage() {
  const { scope } = useWorkspace();
  const q = useOverviewData();
  const b2b = scope?.operation === "B2B";
  return (
    <>
      <PageHead
        eyebrow={`${scope?.operation} · Overview`}
        title={
          <>
            Sua operação em <em className="hl hl--up">perspectiva.</em>
          </>
        }
        description={
          b2b
            ? "Receita, pedidos e relacionamento com os clientes da marca."
            : "Receita, pedidos, clientes e mídia — com definições comerciais explícitas."
        }
      />
      {!b2b && <FiltersBar />}
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure
          retry={() => void q.refetch()}
          description={q.error?.message}
        />
      ) : b2b && q.data.source === "real" ? (
        <>
          {(!q.data.overview.metadata.history_complete ||
            !q.data.overview.metadata.facts_complete) && (
            <Notice>
              Cobertura parcial. Indicadores que dependem de cobertura completa
              permanecem indisponíveis.
            </Notice>
          )}
          <B2BOverview
            data={q.data.overview.data}
            goal={q.data.overview.goal}
            preview
          />
        </>
      ) : b2b && q.data.source === "demo" && q.data.overview.b2b ? (
        <B2BOverview data={q.data.overview.b2b} goal={q.data.overview.goal} />
      ) : (
        <RetailOverview />
      )}
    </>
  );
}
