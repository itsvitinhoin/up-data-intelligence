"use client";
import { RetailOverview } from "@/features/retail";
import { B2BOverview } from "@/features/b2b-overview";
import { useWorkspace } from "@/features/providers";
import { useResource } from "@/hooks/use-resource";
import { PageHead, Loading, Failure } from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
export function OverviewPage() {
  const { scope } = useWorkspace();
  const q = useResource("overview");
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
      <FiltersBar />
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : b2b && q.data.b2b ? (
        <B2BOverview data={q.data.b2b} goal={q.data.goal} />
      ) : (
        <RetailOverview />
      )}
    </>
  );
}
