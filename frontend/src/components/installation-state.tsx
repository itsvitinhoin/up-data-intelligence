"use client";
import { CheckCircle2, Circle, LoaderCircle, AlertCircle } from "lucide-react";
import { usePageSource } from "@/hooks/use-page-source";
import { isB2BReadPage } from "@/lib/dashboard-source";
import { usePathname } from "next/navigation";
import { useInstallation } from "@/hooks/use-installation";
import { useWorkspace } from "@/features/providers";
import {
  installationPeriodAvailable,
  partialInstallationMessage,
} from "@/services/api/installation";
import { displayRange, exclusiveToInclusive } from "@/lib/period";
import { Notice, Empty, Failure, Loading } from "@/components/ui-kit";
import type {
  Installation,
  InstallationProgress,
  InstallationResourceState,
  InstallationState,
} from "@/types/installation";

export const installationLabels: Record<InstallationState, string> = {
  INSTALLING: "Instalando",
  PARTIAL: "Dados parciais disponíveis",
  READY: "Pronto",
  BLOCKED: "Bloqueado",
};
const resourceLabels: Record<InstallationResourceState, string> = {
  PENDING: "Pendente",
  RUNNING: "Processando",
  PARTIAL: "Parcial",
  COMPLETE: "Disponível",
  BLOCKED: "Requer revisão",
};
const name = (value: string) =>
  ({
    upzero: "UP Zero",
    customers: "Clientes",
    orders: "Pedidos",
    analytics_facts: "Analytics Facts",
  })[value] ?? value;
export function InstallationProgressView({
  progress,
}: {
  progress: InstallationProgress;
}) {
  return (
    <div className="installation-progress">
      <p>
        {progress.percent !== null
          ? `${progress.percent.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
          : progress.processed !== null
            ? `${progress.processed.toLocaleString("pt-BR")} registros processados nas últimas execuções por recurso`
            : "Calculando progresso..."}
      </p>
      {progress.percent !== null && (
        <progress
          aria-label="Progresso comprovado da instalação"
          max={100}
          value={progress.percent}
        />
      )}
      <small className="muted">
        {progress.eta_seconds === null
          ? "Calculando tempo estimado..."
          : `Tempo estimado: ${progress.eta_seconds.toLocaleString("pt-BR")} segundos`}
      </small>
    </div>
  );
}
export function InstallationStatus({
  data,
  details = false,
}: {
  data: Installation;
  details?: boolean;
}) {
  return (
    <section
      className="installation-status"
      aria-label={`Instalação de ${data.store_id}`}
    >
      <span
        className={`badge ${data.overall_state === "BLOCKED" ? "badge--warn" : "badge--up"}`}
      >
        {installationLabels[data.overall_state]}
      </span>
      {data.sources.map((source) => (
        <div key={`${source.source}/${source.connection_id}`}>
          <strong>{name(source.source)}</strong>{" "}
          <span className="muted">
            {source.configured
              ? source.active === true
                ? "Conexão ativa"
                : source.active === false
                  ? "Conexão inativa"
                  : "Conexão não verificada"
              : "Não configurada"}{" "}
            · {resourceLabels[source.state]}
          </span>
          <ul className="integration-statuses">
            {data.resources
              .filter(
                (r) =>
                  r.source === source.source &&
                  r.connection_id === source.connection_id,
              )
              .map((r) => {
                const Icon =
                  r.state === "COMPLETE"
                    ? CheckCircle2
                    : r.state === "RUNNING"
                      ? LoaderCircle
                      : r.state === "BLOCKED"
                        ? AlertCircle
                        : Circle;
                return (
                  <li key={r.resource}>
                    <span>
                      <Icon size={14} aria-hidden="true" /> {name(r.resource)}
                    </span>
                    <span>{resourceLabels[r.state]}</span>
                    {details && (
                      <div className="installation-detail">
                        <small>
                          Execução: {r.latest_run_status ?? "Desconhecida"} ·{" "}
                          {r.mode ?? "Modo desconhecido"}
                        </small>
                        <small>
                          Lidos: {r.records_read ?? "—"} · Processados:{" "}
                          {r.records_processed ?? "—"} · Rejeitados na execução:{" "}
                          {r.records_failed ?? "—"}
                        </small>
                        <small>
                          RAW pendente:{" "}
                          {r.pending_raw === null
                            ? "Desconhecido"
                            : r.pending_raw
                              ? "Sim"
                              : "Não"}
                        </small>
                        <small>
                          Cobertura desta execução:{" "}
                          {r.coverage_from && r.coverage_to
                            ? `${r.coverage_from} — ${r.coverage_to} (fim exclusivo)`
                            : "Não comprovada"}
                        </small>
                        <small>
                          Atualização: {r.updated_at ?? "Não informada"}
                        </small>
                        {r.last_error_code && (
                          <small>Bloqueio: {r.last_error_code}</small>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
          </ul>
          {source.last_error_code && (
            <p className="muted">{source.last_error_code}</p>
          )}
        </div>
      ))}
      <InstallationProgressView progress={data.progress} />
      {data.recommended_preview_window && (
        <p className="muted">
          Período certificado:{" "}
          {displayRange(
            data.recommended_preview_window.from,
            exclusiveToInclusive(data.recommended_preview_window.to),
          )}
        </p>
      )}
      {details && (
        <p className="muted">
          Atualização da leitura: {data.updated_at}. Histórico completo:{" "}
          {data.history_complete === null
            ? "Desconhecido"
            : data.history_complete
              ? "Sim"
              : "Não"}
          . Contadores não representam total único do histórico.
        </p>
      )}
    </section>
  );
}
export function InstallationBoundary({
  children,
}: {
  children: React.ReactNode;
}) {
  const { filters, scope } = useWorkspace();
  const path = usePathname();
  const q = useInstallation(isB2BReadPage(path) ? scope : null);
  // Published V1 commercial windows do not claim Intelligence/Meta/geography coverage.
  const resource = (
    {
      "/b2b": "overview",
      "/b2b/commercial": "orders",
      "/b2b/acquisition": "overview",
      "/b2b/retention": "retention",
      "/b2b/customers": "customers",
      "/b2b/products": "products",
    } as Record<string, string>
  )[path];
  const unavailable =
    !!resource &&
    !!q.data &&
    (!q.data.data.available_window ||
      (!!filters.from &&
        !!filters.to &&
        !installationPeriodAvailable(q.data.data, filters, resource)));
  usePageSource(
    q.isError
      ? "error-real"
      : unavailable
        ? "unavailable-real"
        : "loading-real",
    undefined,
    !q.enabled || (!q.isError && !q.isPending && !unavailable),
  );
  if (!q.enabled) return children;
  if (q.isPending) return <Loading />;
  if (q.isError)
    return (
      <Failure
        retry={() => void q.refetch()}
        description="Não foi possível verificar a cobertura de instalação. Nenhum dado demo foi usado."
      />
    );
  if (!q.data) return children; // Server confirmed that this workspace has no live binding.
  const data = q.data.data;
  if (unavailable)
    return (
      <Empty
        title="Histórico deste período ainda está sendo processado."
        description="Selecione um período com cobertura publicada. Ausência de dados não representa zero."
      />
    );
  return (
    <>
      {["INSTALLING", "PARTIAL"].includes(data.overall_state) && (
        <Notice>{partialInstallationMessage}</Notice>
      )}
      {children}
    </>
  );
}
