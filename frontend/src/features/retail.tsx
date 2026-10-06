"use client";
import dynamic from "next/dynamic";
import { useWorkspace } from "./providers";
import { useResource } from "@/hooks/use-resource";
import {
  Panel,
  PageHead,
  MetricCard,
  Loading,
  Failure,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { ListExport } from "@/components/exports";
const Revenue = dynamic(
  () => import("@/components/retail-charts").then((m) => m.RetailRevenueChart),
  { ssr: false },
);
const Gauge = dynamic(
  () => import("@/components/retail-charts").then((m) => m.PaidGauge),
  { ssr: false },
);
export function RetailOverview() {
  const { dataMode } = useWorkspace();
  const q = useResource("retail");
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  return (
    <>
      <section className="metrics" aria-label="Indicadores B2C">
        {q.data.overview.map((item) => (
          <MetricCard key={item.label} item={item} />
        ))}
      </section>
      <section className="row-a">
        <Panel
          title="Faturamento por período"
          subtitle={
            dataMode === "demo"
              ? "Captado × aprovado · B2C DADOS DEMONSTRATIVOS"
              : "Captado × aprovado · aprovado aguarda fonte financeira"
          }
        >
          <Revenue data={q.data.series} />
        </Panel>
        <Panel
          title="Porcentagem de vendas pagas"
          subtitle="Pedidos com pagamento confirmado / pedidos captados"
        >
          <Gauge rate={q.data.paidRate} />
        </Panel>
      </section>
    </>
  );
}
export function RetailPerformance() {
  const q = useResource("retail");
  return (
    <>
      <PageHead
        eyebrow="B2C · Performance"
        title={
          <>
            Mídia e conversão, <em className="hl hl--up">juntas.</em>
          </>
        }
        description="Investimento por plataforma, retorno e jornada até o pedido."
      />
      <FiltersBar />
      {q.isPending ? (
        <Loading page />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <section
            className="metrics"
            aria-label="Indicadores de Performance B2C"
          >
            {q.data.performance.map((item) => (
              <MetricCard key={item.label} item={item} />
            ))}
          </section>
          <Panel
            title="Funil de conversão"
            subtitle="Etapas demonstrativas no recorte selecionado"
            action={<ListExport rows={q.data.funnel} name="funil-b2c" />}
          >
            <div className="funnel">
              {q.data.funnel.map((r) => (
                <div className="funnel-row" key={r.label}>
                  <span>{r.label}</span>
                  <div>
                    <i
                      style={{
                        width: `${q.data.funnel[0].value ? Math.max(1, (r.value / q.data.funnel[0].value) * 100) : 0}%`,
                      }}
                    />
                  </div>
                  <strong>{r.value.toLocaleString("pt-BR")}</strong>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
