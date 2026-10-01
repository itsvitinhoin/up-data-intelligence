"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";
import { RealRetention } from "./b2b-read-pages";

import { ListExport } from "@/components/exports";
import { RetentionMetrics } from "@/features/retention-metrics";
import { useResource } from "@/hooks/use-resource";
import {
  PageHead,
  Panel,
  Loading,
  Failure,
  Notice,
  Empty,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { money, number } from "@/lib/format";
const decimal = (value: number | null) =>
  value === null
    ? "—"
    : value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
const percent = (value: number | null) =>
  value === null ? "—" : `${decimal(value)}%`;
function DemoRetentionDashboard() {
  const q = useResource("lifecycle");
  return (
    <>
      <PageHead
        eyebrow="Relacionamentos que permanecem"
        title={
          <>
            Da primeira à <em className="hl hl--up">próxima compra.</em>
          </>
        }
        description="Evolução da base e retenção mensal por primeira compra observada."
      />
      <FiltersBar />
      <RetentionMetrics />
      <Notice>
        Histórico incompleto: primeira compra observada não confirma aquisição
        histórica. Base selecionada pela primeira compra observada no período;
        acompanhamento até a data de fim.
      </Notice>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : !q.data.cohorts.length ? (
        <Empty title="Sem compradores nesta janela" />
      ) : (
        <>
          <Panel
            title="Progressão de recompra"
            action={
              <ListExport rows={q.data.stages} name="progressao-recompra" />
            }
            subtitle="Evolução da base · compra 1 → 2 → 3 → 4 → 5+"
          >
            <div className="purchase-progression">
              {q.data.stages.map((stage, i) => (
                <section
                  key={stage.stage}
                  aria-label={`Compra ${stage.stage}${stage.stage === 5 ? "+" : ""}`}
                  className="purchase-stage"
                >
                  <div className="progression-track">
                    <span />
                    {i < 4 && (
                      <small>
                        {percent(q.data.stages[i + 1].continuation)} seguem
                      </small>
                    )}
                  </div>
                  <h3>
                    Compra {stage.stage}
                    {stage.stage === 5 ? "+" : ""}
                  </h3>
                  <div className="progression-count num">
                    {number(stage.customers)}{" "}
                    <small>{percent(stage.share)}</small>
                  </div>
                  <p>
                    <strong>{money(stage.revenue)}</strong> em receita
                  </p>
                  <p>
                    <strong>{money(stage.accumulated)}</strong> acumulados
                  </p>
                  <div className="progression-bar">
                    <span style={{ width: `${stage.share ?? 0}%` }} />
                  </div>
                  {i > 0 && (
                    <small className="muted">
                      {decimal(stage.meanDays)} dias em média desde a compra
                      anterior
                    </small>
                  )}
                </section>
              ))}
            </div>
            <p className="metric-hint mt-4">
              Receita atendida por etapa. Compra 5+ reúne pedidos da quinta
              compra em diante; compradores contados uma vez por etapa.
            </p>
          </Panel>
          <Panel
            title="Retenção por janela"
            action={
              <ListExport
                rows={q.data.cohorts.map((c) => ({
                  mes: c.month,
                  compradores: c.customers,
                  mes_0: c.rates[0],
                  mes_1: c.rates[1],
                  mes_2: c.rates[2],
                  mes_3: c.rates[3],
                }))}
                name="coortes"
              />
            }
            subtitle="Coortes mensais · retorno no mês, não cumulativo"
          >
            <div className="table-scroll">
              <table className="retention-matrix">
                <thead>
                  <tr>
                    <th>Primeira compra observada</th>
                    {[0, 1, 2, 3].map((month) => (
                      <th key={month}>Mês {month}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {q.data.cohorts.map((cohort) => (
                    <tr key={cohort.month}>
                      <th>
                        {new Date(
                          cohort.month + "-01T12:00:00Z",
                        ).toLocaleDateString("pt-BR", {
                          month: "long",
                          year: "numeric",
                          timeZone: "America/Sao_Paulo",
                        })}
                        <small>{cohort.customers} lojistas</small>
                      </th>
                      {cohort.rates.map((rate, i) => (
                        <td key={i}>
                          <div
                            className={
                              rate === null
                                ? "cohort-unknown"
                                : i === 0
                                  ? "cohort-base"
                                  : "cohort-rate"
                            }
                            style={
                              rate !== null && i > 0
                                ? {
                                    backgroundColor: `hsl(${Math.min(rate / 30, 1) * 155} 42% 24%)`,
                                  }
                                : undefined
                            }
                            title={
                              rate === null
                                ? "Janela não madura ou sem cobertura"
                                : `${percent(rate)} dos compradores da coorte`
                            }
                          >
                            {percent(rate)}
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="cohort-legend">
              Menor retenção <span /> Maior retenção
            </div>
            <p className="metric-hint">
              Mês 0 é o mês da primeira compra observada. Cada célula mostra a
              parcela que comprou novamente naquele mês. Traço indica janela não
              madura ou sem cobertura; 0% indica mês completo sem recompra
              observada.
            </p>
          </Panel>
        </>
      )}
    </>
  );
}
export function ConversionVelocity() {
  const q = useResource("lifecycle");
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  const c = q.data.conversion;
  const max = Math.max(1, ...c.buckets.map((b) => b.percent ?? 0));
  return (
    <section aria-label="Velocidade de conversão">
      <div className="marketing-section-head">
        <div>
          <h2 className="card-title">Velocidade de conversão</h2>
          <p className="card-sub">
            Em quanto tempo o lojista aprovado faz o primeiro pedido
            qualificante observado.
          </p>
        </div>
      </div>
      <div className="conversion-layout">
        <Panel
          title="Distribuição de compradores"
          subtitle={`Aprovação → primeiro pedido · base: ${c.buyers} compradores · ${c.excluded} excluídos por data ausente ou inválida`}
        >
          {!c.buyers ? (
            <Empty title="Sem datas suficientes para calcular" />
          ) : (
            <div className="conversion-bars">
              {c.buckets.map((bucket) => (
                <div key={bucket.label} className="conversion-bin">
                  <strong className="num">{percent(bucket.percent)}</strong>
                  <div className="conversion-bar-space">
                    <div
                      style={{
                        height: `${((bucket.percent ?? 0) / max) * 100}%`,
                      }}
                    />
                  </div>
                  <span>{bucket.label}</span>
                  <small>{bucket.count} lojistas</small>
                </div>
              ))}
            </div>
          )}
          <p className="metric-hint mt-5">
            Intervalos exclusivos, em dias corridos. Aprovações sintéticas;
            status comercial não confirma pagamento.
          </p>
        </Panel>
        <div className="conversion-summary">
          {[
            {
              label: "Compram na primeira semana",
              value: percent(c.buyers ? (c.withinWeek / c.buyers) * 100 : null),
              detail: `${c.withinWeek} lojistas`,
            },
            {
              label: "Compram em até 30 dias",
              value: percent(
                c.buyers ? (c.withinMonth / c.buyers) * 100 : null,
              ),
              detail: `${c.withinMonth} lojistas`,
            },
            {
              label: "Mediana até o pedido",
              value: `${decimal(c.median)} dias`,
              detail: `Média de ${decimal(c.mean)} dias`,
            },
          ].map((item) => (
            <Panel key={item.label} title={item.label}>
              <strong className="conversion-number num">{item.value}</strong>
              <p className="card-sub">{item.detail}</p>
            </Panel>
          ))}
        </div>
      </div>
    </section>
  );
}

export function RetentionDashboard() {
  return (
    <B2BReadBoundary real={(metadata) => <RealRetention metadata={metadata} />}>
      <DemoRetentionDashboard />
    </B2BReadBoundary>
  );
}
