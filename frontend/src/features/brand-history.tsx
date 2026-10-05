"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Choice, Loading, Failure } from "@/components/ui-kit";
import { date } from "@/lib/format";
import { readHistory, requestHistory } from "@/services/api/history";
import type { BrandSummary } from "@/services/api/brand-integrations";

export function HistoryProgress({ summary }: { summary: BrandSummary }) {
  const q = useQuery({
    queryKey: [
      "admin-history",
      summary.tenant_id,
      summary.workspace_operation_id,
    ],
    queryFn: ({ signal }) => readHistory(summary, signal),
    retry: false,
    refetchInterval: (q) =>
      q.state.data?.data.some((p) => ["RUNNING", "PARTIAL"].includes(p.status))
        ? 15000
        : false,
  });
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  return (
    <div>
      {q.data.data.length === 0 && <p>Nenhuma extração solicitada.</p>}
      {q.data.data.map((p) => (
        <section key={p.plan_id} className="integration-editor">
          <strong>
            {p.provider === "upzero" ? "UP Zero" : "Meta Ads"} ·{" "}
            {p.purpose === "HISTORY_EXTENSION" ? "Histórico" : "Enriquecimento"}
          </strong>
          <p>
            <span className="badge">{p.status}</span> · {date(p.requested_from)}{" "}
            → {date(p.target_as_of)} (fim exclusivo)
          </p>
          <p>
            {p.progress.processed === null
              ? "Progresso indisponível"
              : `${p.progress.processed}/${p.progress.total} unidades · ${p.progress.percent?.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}
          </p>
          {p.error_code && <p role="status">{p.error_code}</p>}
          <details>
            <summary>Recursos</summary>
            {p.resources.map((r) => (
              <p key={r.resource}>
                {r.resource} · {r.complete}/{r.total}
              </p>
            ))}
          </details>
        </section>
      ))}
    </div>
  );
}
export function BrandHistory({ summary }: { summary: BrandSummary }) {
  const [provider, setProvider] = useState<"upzero" | "meta">("upzero"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => requestHistory(summary, { provider, from, to }),
    retry: false,
    onSuccess: () =>
      void client.invalidateQueries({
        queryKey: [
          "admin-history",
          summary.tenant_id,
          summary.workspace_operation_id,
        ],
      }),
  });
  const configured = summary.sources.some(
    (s) => s.provider === provider && s.status === "active",
  );
  return (
    <>
      <p>
        Cobertura atual:{" "}
        {summary.coverage_from && summary.coverage_to
          ? `${date(summary.coverage_from)} → ${date(summary.coverage_to)} (fim exclusivo)`
          : "Não comprovada"}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <Choice
          label="Fonte"
          value={provider}
          onChange={(v) => setProvider(v as "upzero" | "meta")}
          options={[
            { value: "upzero", label: "UP Zero" },
            { value: "meta", label: "Meta Ads" },
          ]}
        />
        <div className="form-grid">
          <label className="form-field">
            Período inicial
            <Input
              type="date"
              required
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label className="form-field">
            Período final (inclusivo)
            <Input
              type="date"
              required
              min={from || undefined}
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
        </div>
        <p className="muted">
          Recupera e persiste apenas a história ausente em unidades limitadas.
          Dias futuros são recusados no fuso da marca. A janela certificada
          atual continua disponível; este pedido não comprova histórico de vida
          completo.
        </p>
        {from && to && (
          <p>
            Nova janela solicitada: {date(from)} → {date(to)}
          </p>
        )}
        <Button
          type="submit"
          disabled={
            !configured || !from || !to || from > to || mutation.isPending
          }
        >
          {mutation.isPending ? "Preparando…" : "Solicitar extração"}
        </Button>
        {!configured && <p>Fonte ativa necessária.</p>}
        {mutation.isError && <p role="alert">{mutation.error.message}</p>}
        {mutation.isSuccess && (
          <p role="status">Plano persistido. Acompanhe o progresso abaixo.</p>
        )}
      </form>
      <HistoryProgress summary={summary} />
    </>
  );
}
