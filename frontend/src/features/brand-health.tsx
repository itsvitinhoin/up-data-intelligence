"use client";
import { useState } from "react";
import { HistoryProgress } from "./brand-history";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "./providers";
import { useInstallation } from "@/hooks/use-installation";
import {
  readIntegrationHealth,
  type BrandSummary,
} from "@/services/api/brand-integrations";
import { InstallationStatus } from "@/components/installation-state";
import { Button } from "@/components/ui/button";
import { Panel, Loading, Failure } from "@/components/ui-kit";
import { date } from "@/lib/format";
const healthLabels = {
  HEALTHY: "Saudável",
  SYNCING: "Sincronizando",
  PARTIAL: "Parcial",
  STALE: "Desatualizada",
  ERROR: "Requer revisão",
  DISABLED: "Desativada",
  NOT_CONFIGURED: "Não configurada",
};
const resourceNames: Record<string, string> = {
  customers: "Clientes",
  orders: "Pedidos",
  analytics_facts: "Eventos observados",
  products: "Produtos",
  variants: "Variantes",
  inventory: "Estoque",
  attributes: "Atributos",
  meta_live_accounts: "Contas",
  meta_live_campaigns: "Campanhas",
  meta_live_adsets: "Conjuntos",
  meta_live_ads: "Anúncios",
  meta_live_insights_daily: "Insights",
  meta_creative_insights_daily: "Criativos · anúncio/dia",
};
export function BrandHealth({ summary }: { summary: BrandSummary }) {
  const { session } = useWorkspace();
  const [tab, setTab] = useState("general");
  const installation = useInstallation({
    tenant_id: summary.tenant_id,
    workspace_operation_id: summary.workspace_operation_id,
    store_id: summary.workspace_operation_id,
    operation: summary.operation,
  });
  const query = useQuery({
    queryKey: [
      "integration-health",
      session?.id,
      summary.tenant_id,
      summary.workspace_operation_id,
    ],
    queryFn: ({ signal }) => readIntegrationHealth(summary, signal),
    retry: false,
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <Failure retry={() => void query.refetch()} />;
  const health = query.data.data;
  const source = health.sources.find((source) => source.provider === tab);
  return (
    <>
      <HistoryProgress summary={summary} />
      <div
        className="brand-admin-actions"
        role="group"
        aria-label="Seções de saúde"
      >
        <Button
          variant="ghost"
          aria-pressed={tab === "general"}
          onClick={() => setTab("general")}
        >
          Geral
        </Button>
        {health.sources.map((source) => (
          <Button
            variant="ghost"
            key={source.provider}
            aria-pressed={tab === source.provider}
            onClick={() => setTab(source.provider)}
          >
            {source.provider === "upzero" ? "UP Zero" : "Meta Ads"}
          </Button>
        ))}
      </div>
      {tab === "general" ? (
        <>
          <p className="muted">
            Saúde diária e instalação são evidências distintas. Ledger em
            execução não confirma um worker ativo.
          </p>
          <div className="stats-grid">
            <Panel title="Saúde diária">
              <span>
                {health.health_evidence_current
                  ? health.blocking_findings === 0
                    ? "Sem falhas bloqueantes"
                    : "Requer revisão"
                  : "Verificação desatualizada"}
              </span>
            </Panel>
            <Panel title="Verificação de saúde">
              <span>
                {health.health_checked_at
                  ? date(health.health_checked_at)
                  : "Não comprovada"}
              </span>
            </Panel>
            <Panel title="Próxima sincronização">
              <span>
                {health.next_sync_at
                  ? date(health.next_sync_at)
                  : "Não comprovada"}
              </span>
            </Panel>
            <Panel title="Alertas atuais">
              <span>
                {health.blocking_findings ?? "—"} bloqueantes ·{" "}
                {health.warning_findings ?? "—"} avisos
              </span>
            </Panel>
          </div>
          <details>
            <summary>Instalação · detalhes avançados</summary>
            {installation.isPending ? (
              <Loading />
            ) : installation.isError ? (
              <Failure retry={() => void installation.refetch()} />
            ) : installation.data ? (
              <InstallationStatus data={installation.data.data} details />
            ) : (
              <p>Contrato de instalação indisponível.</p>
            )}
          </details>
        </>
      ) : (
        source && (
          <>
            <span className="badge">{healthLabels[source.health]}</span>
            <p>
              Último sync de recurso confirmado:{" "}
              {source.last_success_at
                ? date(source.last_success_at)
                : "Não comprovado"}
            </p>
            <p className="muted">
              Última tentativa:{" "}
              {source.last_attempt_at
                ? date(source.last_attempt_at)
                : "Não informada"}
            </p>
            <p>
              Cobertura diária:{" "}
              {source.coverage_certified
                ? "Certificada no cutoff esperado"
                : "Não comprovada"}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Recurso</th>
                    <th>Status do ledger</th>
                    <th>Último sync confirmado</th>
                    <th>Registros</th>
                    <th>Páginas</th>
                    <th>Falhas</th>
                  </tr>
                </thead>
                <tbody>
                  {source.resources.map((row) => (
                    <tr key={row.resource}>
                      <td>{resourceNames[row.resource] ?? row.resource}</td>
                      <td>{row.ledger_status}</td>
                      <td>
                        {row.last_success_at
                          ? date(row.last_success_at)
                          : "Não comprovado"}
                      </td>
                      <td>{row.records_processed ?? "—"}</td>
                      <td>{row.pages_processed ?? "—"}</td>
                      <td>{row.failed_records ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      )}
    </>
  );
}
