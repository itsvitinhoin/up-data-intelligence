"use client";
import { useQueries } from "@tanstack/react-query";
import { useWorkspace } from "@/features/providers";
import { useRequestContext } from "@/hooks/use-resource";
import { usePublicationMetadata } from "@/hooks/publication-context";
import { dashboardReadKey } from "@/hooks/use-dashboard-read";
import { readDashboard } from "@/services/api/read-client";
import { exclusiveToInclusive } from "@/lib/period";
import { MetricBindings, bindingResources, readPath } from "./bindings";
import { WidgetBindings } from "./widgets";
import { MetricRegistry, type ManagerPage } from "./registry";

/** Internal read diagnostics. This is never client authorization or publication evidence. */
export function coverageSummary(
  ids: string[],
  values: Record<string, unknown>,
  historyComplete: boolean,
) {
  const counts = {
    available: 0,
    unavailable: 0,
    ingestion: 0,
    connector: 0,
    history: 0,
    identity: 0,
  };
  for (const id of ids) {
    const b = MetricBindings[id];
    if (!b) throw new Error("Orphan metric");
    const raw =
      b.resource && b.path ? readPath(values[b.resource], b.path) : null;
    if (raw !== null && raw !== undefined && (!b.history || historyComplete)) {
      counts.available++;
      continue;
    }
    counts.unavailable++;
    if (b.category === "B") counts.ingestion++;
    if (b.category === "C") counts.history++;
    if (b.category === "D") counts.connector++;
    if (b.category === "A") counts.identity++;
  }
  return counts;
}
export function PageDataCoverage({ page }: { page: ManagerPage }) {
  const { session, dataMode } = useWorkspace();
  const metadata = usePublicationMetadata();
  if (session?.role !== "ADMIN" || dataMode === "demo" || !metadata)
    return null;
  return <ReadCoverage page={page} metadata={metadata} />;
}
function ReadCoverage({
  page,
  metadata,
}: {
  page: ManagerPage;
  metadata: NonNullable<ReturnType<typeof usePublicationMetadata>>;
}) {
  const base = useRequestContext();
  const { dataMode } = useWorkspace();
  const context = {
    ...base,
    filters: {
      ...base.filters,
      from: base.filters.from ?? metadata.report_from,
      to: base.filters.to ?? exclusiveToInclusive(metadata.report_to),
    },
  };
  const ids = [
    ...new Set([
      ...page.metricIds,
      ...page.widgets.flatMap((id) => WidgetBindings[id].metricIds),
    ]),
  ];
  const resources = bindingResources(ids);
  const options = {
    policy_hash: metadata.policy_hash,
    publication_domain: metadata.publication_domain ?? "analytics-v1",
    intelligence_generation:
      metadata.publication_domain === "intelligence"
        ? metadata.generation
        : null,
    analytics_generation: metadata.analytics_generation ?? metadata.generation,
  };
  const queries = useQueries({
    queries: resources.map((resource) => ({
      queryKey: dashboardReadKey(
        dataMode,
        resource,
        context,
        metadata.generation,
        options,
      ),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        readDashboard(
          resource,
          context,
          metadata.analytics_generation ?? metadata.generation,
          { signal, expectedPolicyHash: metadata.policy_hash },
        ),
      retry: false,
    })),
  });
  const values = Object.fromEntries(
    resources.map((r, i) => [r, queries[i].data?.data]),
  );
  const counts = coverageSummary(ids, values, metadata.history_complete);
  return (
    <details className="no-print" data-testid="page-data-coverage">
      <summary>Cobertura de Dados · auditoria interna</summary>
      <p>
        {queries.some((q) => q.isPending) ? "Leituras em andamento · " : ""}
        Disponíveis: {counts.available} · Indisponíveis: {counts.unavailable} ·
        Ingestão: {counts.ingestion} · Conector: {counts.connector} · Histórico:{" "}
        {counts.history} · Ligação/identidade: {counts.identity}
      </p>
      <p className="muted">
        Contagem dos cards e métricas dos widgets; detalhes e tabelas são
        auditados na matriz versionada. Generation {metadata.generation} · até{" "}
        {metadata.report_to} exclusivo.
      </p>
      <div className="table-scroll">
        <table className="list">
          <thead>
            <tr>
              <th>Métrica</th>
              <th>Recurso / campo</th>
              <th>Diagnóstico</th>
            </tr>
          </thead>
          <tbody>
            {ids.map((id) => {
              const b = MetricBindings[id];
              const value =
                b.resource && b.path
                  ? readPath(values[b.resource], b.path)
                  : null;
              return (
                <tr key={id}>
                  <td>{MetricRegistry[id].label}</td>
                  <td>
                    {b.resource ?? "—"} / {b.path ?? "—"}
                  </td>
                  <td>
                    {value !== null && value !== undefined
                      ? "Campo recebido; regra de cobertura preservada"
                      : `${b.category} · ${b.reason}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
