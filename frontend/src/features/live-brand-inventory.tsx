"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Search, ArrowRight } from "lucide-react";
import { useWorkspace } from "./providers";
import { catalogCompanies } from "@/services/auth/catalog";
import {
  readBrandSummaries,
  type BrandSummary,
} from "@/services/api/brand-integrations";
import { readInstallation, installationKey } from "@/hooks/use-installation";
import { BrandHistory } from "./brand-history";
import { BrandHealth } from "./brand-health";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { PageHead, Panel, Loading, Failure, Empty } from "@/components/ui-kit";
import { ListExport } from "@/components/exports";
import { date } from "@/lib/format";
import { ProviderSettings } from "./provider-settings";
import type { Company, Scope } from "@/types/domain";

const statuses: Record<BrandSummary["status"], string> = {
  ACTIVE: "Ativa",
  READY: "Pronta",
  DRAFT: "Instalando",
  PAUSED: "Pausada",
  ERROR: "Bloqueada",
  DISABLED: "Desativada",
};
const normalize = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
function scopeFor(summary: BrandSummary): Scope {
  return {
    tenant_id: summary.tenant_id,
    workspace_operation_id: summary.workspace_operation_id,
    store_id: summary.workspace_operation_id,
    operation: summary.operation,
  };
}
function coverage(summary: BrandSummary) {
  return summary.coverage_from && summary.coverage_to
    ? `${date(summary.coverage_from)} → ${date(summary.coverage_to)} (fim exclusivo)`
    : "Cobertura não comprovada";
}

function BrandCard({
  brand,
  summary,
  open,
}: {
  brand: Company;
  summary: BrandSummary;
  open: (kind: "settings" | "health" | "history") => void;
}) {
  const { session, select } = useWorkspace();
  const router = useRouter(),
    client = useQueryClient();
  const [opening, setOpening] = useState(false),
    [error, setError] = useState<string | null>(null);
  async function dashboard() {
    if (opening) return;
    setOpening(true);
    setError(null);
    try {
      const scope = scopeFor(summary);
      const result = await client.fetchQuery({
        queryKey: installationKey(session, scope),
        queryFn: ({ signal }) => readInstallation(scope, signal),
        staleTime: 0,
      });
      if (!result?.data.recommended_preview_window)
        throw new Error("Nenhuma janela certificada disponível.");
      select(scope, result.data.recommended_preview_window);
      router.push("/" + summary.operation.toLowerCase());
    } catch {
      setError(
        "Não foi possível verificar a janela certificada. Tente novamente.",
      );
    } finally {
      setOpening(false);
    }
  }
  return (
    <Panel
      title={
        <span className="brand-card-heading">
          <span
            className={`connection-dot ${summary.active_connections > 0 ? "connection-dot--active" : ""}`}
            role="img"
            aria-label={`${summary.active_connections > 0 ? "Conexão ativa" : "Sem conexão ativa"} de ${brand.name}`}
          />
          <span className="brand-card-identity">
            <strong>{brand.name}</strong>
            <small>
              {summary.created_at
                ? `Criada em ${date(summary.created_at)}`
                : "Data de criação não informada"}
            </small>
          </span>
        </span>
      }
      subtitle={`Operação ${summary.operation}`}
    >
      <span className="badge badge--up">{statuses[summary.status]}</span>
      <p>
        {summary.active_connections} ativas · {summary.pending_connections}{" "}
        pendentes · {summary.attention_connections} com atenção
      </p>
      <p className="muted">Cobertura: {coverage(summary)}</p>
      <div className="brand-dashboard-access">
        <Button
          className="btn"
          aria-label={`Ver Dashboard de ${brand.name}`}
          disabled={opening || summary.operation !== "B2B"}
          onClick={() => void dashboard()}
        >
          {opening ? "Verificando…" : "Ver Dashboard"} <ArrowRight size={15} />
        </Button>
      </div>
      <div className="brand-admin-actions">
        <Button variant="ghost" onClick={() => open("settings")}>
          Configurar Integrações
        </Button>
        <Button variant="ghost" onClick={() => open("health")}>
          Saúde das Integrações
        </Button>
        <Button variant="ghost" onClick={() => open("history")}>
          Extrair Histórico
        </Button>
      </div>
      {error && <p role="status">{error}</p>}
    </Panel>
  );
}
export function LiveBrandInventory({
  createAction,
  children,
}: {
  createAction?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const { session, tenants } = useWorkspace();
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState<{
    kind: "settings" | "health" | "history";
    brand: Company;
    summary: BrandSummary;
  } | null>(null);
  const query = useQuery({
    queryKey: [
      "up-admin",
      "brand-summaries",
      session?.id,
      session?.role,
      tenants,
    ],
    queryFn: ({ signal }) => readBrandSummaries(signal),
    retry: false,
  });
  const brands = catalogCompanies(tenants).filter((b) =>
    normalize(b.name).includes(normalize(search)),
  );
  const title =
    dialog?.kind === "health"
      ? "Saúde das Integrações"
      : dialog?.kind === "history"
        ? "Extrair Histórico"
        : "Configurar Integrações";
  return (
    <>
      <PageHead
        eyebrow="UP Admin · Marcas"
        title={
          <>
            Controle de <em className="hl hl--up">marcas.</em>
          </>
        }
        description="Cadastre marcas, acompanhe conexões e acesse cada dashboard em um só lugar. DEV · Acesso interno."
        action={createAction}
      />
      <div className="brand-search">
        <Search size={17} aria-hidden="true" />
        <Input
          aria-label="Pesquisar marca"
          placeholder="Pesquisar marca pelo nome"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="brand-search-count">{brands.length} marcas</span>
      </div>
      {children}
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <Failure retry={() => void query.refetch()} />
      ) : (
        <>
          <ListExport<Record<string, string | number | boolean | null>>
            rows={brands.map((brand) => {
              const summary = query.data.data.find(
                (s) =>
                  s.brand_id === brand.id && s.tenant_id === brand.tenant_id,
              );
              return {
                marca: brand.name,
                operacao: summary?.operation ?? brand.operation,
                status: summary ? statuses[summary.status] : "Indisponível",
                conexoes_ativas: summary?.active_connections ?? null,
                criada_em: summary?.created_at ?? null,
              };
            })}
            name="marcas"
          />
          {brands.length ? (
            <div className="workspace-grid brand-integrations">
              {brands.map((brand) => {
                const summary =
                  query.data.data.find(
                    (s) =>
                      s.brand_id === brand.id &&
                      s.tenant_id === brand.tenant_id &&
                      s.operation === "B2B",
                  ) ??
                  query.data.data.find(
                    (s) =>
                      s.brand_id === brand.id &&
                      s.tenant_id === brand.tenant_id,
                  );
                return summary ? (
                  <BrandCard
                    key={`${brand.tenant_id}/${brand.id}`}
                    brand={brand}
                    summary={summary}
                    open={(kind) => setDialog({ kind, brand, summary })}
                  />
                ) : (
                  <Panel
                    key={`${brand.tenant_id}/${brand.id}`}
                    title={brand.name}
                  >
                    <p role="status">Resumo autorizado indisponível.</p>
                  </Panel>
                );
              })}
            </div>
          ) : (
            <Empty
              title="Nenhuma marca encontrada"
              description="Tente outro nome para localizar a marca."
            />
          )}
        </>
      )}
      <Dialog
        open={!!dialog}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <DialogContent className="glass brand-integration-dialog">
          <DialogTitle>
            {title} · {dialog?.brand.name}
          </DialogTitle>
          <DialogDescription>
            {dialog?.kind === "history"
              ? "A extração recupera e persiste história ausente; não altera apenas o filtro do Dashboard."
              : "Detalhes operacionais da marca selecionada."}
          </DialogDescription>
          {dialog?.kind === "health" && (
            <BrandHealth summary={dialog.summary} />
          )}
          {dialog?.kind === "settings" && (
            <ProviderSettings summary={dialog.summary} />
          )}
          {dialog?.kind === "history" && (
            <BrandHistory summary={dialog.summary} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
