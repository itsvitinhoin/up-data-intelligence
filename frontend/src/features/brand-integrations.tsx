"use client";
import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings2, Plug, KeyRound, ArrowRight, Search } from "lucide-react";
import { useWorkspace } from "@/features/providers";
import { adminApi, authorizedTenants } from "@/services/api";
import {
  platforms,
  erps,
  type Company,
  type BrandIntegration,
} from "@/types/domain";
import {
  PageHead,
  Panel,
  Loading,
  Failure,
  Choice,
  Empty,
} from "@/components/ui-kit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ListExport } from "@/components/exports";
import { date } from "@/lib/format";
import { verifiedConnectionCount } from "@/lib/brand-connection";
const providers: BrandIntegration["provider"][] = [
  "Plataforma",
  "Meta Ads",
  "Google Ads",
  "TikTok Ads",
  "ERP",
];
function connections(brand: Company): BrandIntegration[] {
  return providers.map(
    (provider) =>
      brand.integrations?.find((i) => i.provider === provider) ?? {
        provider,
        enabled: provider === "Meta Ads" && !!brand.meta_account_id,
        accountId: provider === "Meta Ads" ? (brand.meta_account_id ?? "") : "",
      },
  );
}
const searchableName = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
function BrandDashboard({ brand }: { brand: Company }) {
  const { session, select } = useWorkspace();
  const router = useRouter();
  const operations = (session ? authorizedTenants(session) : []).flatMap(
    (tenant) =>
      tenant.brands
        .filter((item) => item.id === brand.id)
        .flatMap((item) =>
          item.operations.map((operation) => ({
            tenantId: tenant.id,
            storeId: operation.id,
            type: operation.type,
          })),
        ),
  );
  const [storeId, setStoreId] = useState(operations[0]?.storeId ?? "");
  const selected =
    operations.find((item) => item.storeId === storeId) ?? operations[0];
  return (
    <div className="brand-dashboard-access">
      {operations.length > 1 && (
        <Choice
          label={`Operação de ${brand.name}`}
          value={selected?.storeId ?? ""}
          onChange={setStoreId}
          options={operations.map((item) => ({
            value: item.storeId,
            label: item.type,
          }))}
        />
      )}
      <Button
        className="btn"
        disabled={!selected}
        aria-label={`Ver Dashboard de ${brand.name}`}
        onClick={() => {
          if (!selected) return;
          select({
            tenant_id: selected.tenantId,
            store_id: selected.storeId,
            operation: selected.type,
          });
          router.push("/" + selected.type.toLowerCase());
        }}
      >
        Ver Dashboard <ArrowRight size={15} />
      </Button>
    </div>
  );
}
export function BrandIntegrationsPage({
  createAction,
}: {
  createAction?: React.ReactNode;
}) {
  const { session, refreshAccess } = useWorkspace();
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["up-admin", "brands"],
    queryFn: () => adminApi.brands(session!),
  });
  const meta = useQuery({
    queryKey: ["up-admin", "meta"],
    queryFn: () => adminApi.meta(session!),
  });
  const [draft, setDraft] = useState<Company | null>(null);
  const [credential, setCredential] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const save = useMutation({
    mutationFn: (brand: Company) => adminApi.saveBrand(brand, session!),
    onSuccess: () => {
      setDraft(null);
      refreshAccess();
      void client.invalidateQueries({ queryKey: ["up-admin"] });
    },
  });
  const load = useMutation({
    mutationFn: () => adminApi.configureMetaDemo(session!),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["up-admin", "meta"] }),
  });
  function patch(
    provider: BrandIntegration["provider"],
    change: Partial<BrandIntegration>,
  ) {
    if (!draft) return;
    const integrations = connections(draft).map((i) =>
      i.provider === provider ? { ...i, ...change } : i,
    );
    const m = integrations.find((i) => i.provider === "Meta Ads")!;
    setDraft({
      ...draft,
      integrations,
      meta_account_id: m.enabled && m.accountId ? m.accountId : null,
    });
  }
  const visibleBrands = q.data?.filter((brand) =>
    searchableName(brand.name).includes(searchableName(search)),
  );
  return (
    <>
      <PageHead
        eyebrow="UP Admin · Marcas"
        title={
          <>
            Controle de <em className="hl hl--up">marcas.</em>
          </>
        }
        description="Cadastre marcas, acompanhe conexões e acesse cada dashboard em um só lugar. Ambiente demonstrativo."
        action={createAction}
      />
      <div className="brand-search">
        <Search size={17} aria-hidden="true" />
        <Input
          aria-label="Pesquisar marca"
          placeholder="Pesquisar marca pelo nome"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {q.data && (
          <span className="brand-search-count">
            {visibleBrands?.length ?? 0} de {q.data.length} marcas
          </span>
        )}
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <ListExport
            rows={(visibleBrands ?? []).flatMap((b) =>
              connections(b).map((i) => ({
                marca: b.name,
                criada_em: b.createdAt ?? "Data não informada",
                conexoes_ativas: verifiedConnectionCount(b),
                integracao: i.provider,
                solicitada: i.enabled,
                conta: i.accountId,
                status: i.enabled
                  ? "Pendente de conexão segura"
                  : "Não configurada",
              })),
            )}
            name="integracoes-por-marca"
          />
          {visibleBrands?.length ? (
            <div className="workspace-grid brand-integrations">
              {visibleBrands.map((brand) => (
                <Panel
                  key={brand.id}
                  title={
                    <span className="brand-card-heading">
                      <span
                        className={`connection-dot ${verifiedConnectionCount(brand) ? "connection-dot--active" : ""}`}
                        role="img"
                        aria-label={
                          verifiedConnectionCount(brand)
                            ? `Conexão ativa de ${brand.name}`
                            : `Sem conexão ativa de ${brand.name}`
                        }
                      />
                      {brand.logo && (
                        <Image
                          className="brand-card-logo"
                          src={brand.logo}
                          alt={`Logo de ${brand.name}`}
                          width={36}
                          height={36}
                          unoptimized
                        />
                      )}
                      <span className="brand-card-identity">
                        <strong>{brand.name}</strong>
                        <small>
                          {brand.createdAt
                            ? `Criada em ${date(brand.createdAt)}`
                            : "Data de criação não informada"}
                        </small>
                      </span>
                    </span>
                  }
                  subtitle={`Operação ${brand.operation} · ${brand.segment}`}
                >
                  <div className="integration-summary">
                    <Plug size={16} />
                    <span>
                      {verifiedConnectionCount(brand)} integrações ativas ·{" "}
                      {connections(brand).filter((i) => i.enabled).length}{" "}
                      preparadas
                    </span>
                  </div>
                  <div className="brand-card-meta">
                    <Choice
                      label={`Plataforma de ${brand.name}`}
                      value={brand.platform ?? "none"}
                      onChange={(value) =>
                        save.mutate({
                          ...brand,
                          platform:
                            value === "none"
                              ? null
                              : (value as Company["platform"]),
                        })
                      }
                      options={[
                        { value: "none", label: "Não informado" },
                        ...platforms.map((value) => ({ value, label: value })),
                      ]}
                    />
                    <Choice
                      label={`ERP de ${brand.name}`}
                      value={brand.erp ?? "none"}
                      onChange={(value) =>
                        save.mutate({
                          ...brand,
                          erp:
                            value === "none" ? null : (value as Company["erp"]),
                        })
                      }
                      options={[
                        { value: "none", label: "Não informado" },
                        ...erps.map((value) => ({ value, label: value })),
                      ]}
                    />
                  </div>
                  <div className="brand-card-actions">
                    <Button
                      className="btn btn--glass"
                      onClick={() => {
                        save.reset();
                        setDraft({
                          ...brand,
                          integrations: connections(brand),
                        });
                      }}
                      aria-label={`Editar integração de ${brand.name}`}
                    >
                      <Settings2 size={15} />
                      Editar integração
                    </Button>
                    <BrandDashboard brand={brand} />
                  </div>
                  <ul className="integration-statuses">
                    {connections(brand).map((i) => (
                      <li key={i.provider}>
                        <span>{i.provider}</span>
                        <span
                          className={`badge ${i.enabled ? "badge--up" : ""}`}
                        >
                          {i.enabled
                            ? "Pendente de conexão"
                            : "Não configurada"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              ))}
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
        open={!!draft}
        onOpenChange={(open) => {
          if (!open) {
            setDraft(null);
            setCredential(null);
          }
        }}
      >
        <DialogContent className="glass brand-integration-dialog">
          <DialogTitle>Integrações · {draft?.name}</DialogTitle>
          <DialogDescription>
            Selecione as integrações desta marca. As configurações ficam nesta
            sessão de demonstração.
          </DialogDescription>
          {draft && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                save.mutate(draft);
              }}
            >
              <div className="form-grid">
                <Choice
                  label="Plataforma da marca"
                  value={draft.platform ?? "none"}
                  onChange={(v) =>
                    setDraft({
                      ...draft,
                      platform:
                        v === "none" ? null : (v as Company["platform"]),
                    })
                  }
                  options={[
                    { value: "none", label: "Não informado" },
                    ...platforms.map((value) => ({ value, label: value })),
                  ]}
                />
                <Choice
                  label="ERP da marca"
                  value={draft.erp ?? "none"}
                  onChange={(v) =>
                    setDraft({
                      ...draft,
                      erp: v === "none" ? null : (v as Company["erp"]),
                    })
                  }
                  options={[
                    { value: "none", label: "Não informado" },
                    ...erps.map((value) => ({ value, label: value })),
                  ]}
                />
              </div>
              {connections(draft).map((i) => (
                <section key={i.provider} className="integration-editor">
                  <label className="integration-toggle">
                    <input
                      type="checkbox"
                      checked={i.enabled}
                      onChange={(e) =>
                        patch(i.provider, { enabled: e.target.checked })
                      }
                    />
                    <strong>{i.provider}</strong>
                    <span className="badge">
                      {i.enabled ? "Preparar conexão" : "Desativada"}
                    </span>
                  </label>
                  {i.enabled && (
                    <>
                      {i.provider === "Meta Ads" ? (
                        <>
                          <Choice
                            label="Conta de anúncio Meta"
                            value={i.accountId || "none"}
                            onChange={(id) =>
                              patch(i.provider, {
                                accountId: id === "none" ? "" : id,
                              })
                            }
                            options={[
                              { value: "none", label: "Selecionar conta" },
                              ...(meta.data?.accounts
                                .filter(
                                  (a) =>
                                    a.status === "AVAILABLE" ||
                                    a.meta_account_id ===
                                      q.data?.find((b) => b.id === draft.id)
                                        ?.meta_account_id,
                                )
                                .map((a) => ({
                                  value: a.meta_account_id,
                                  label: a.account_name,
                                })) ?? []),
                            ]}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={load.isPending}
                            onClick={() => load.mutate()}
                          >
                            Carregar contas demonstrativas
                          </Button>
                        </>
                      ) : (
                        <label className="form-field">
                          {i.provider === "Plataforma" || i.provider === "ERP"
                            ? "Identificador da loja (opcional)"
                            : "ID da conta de anúncio"}
                          <Input
                            value={i.accountId}
                            maxLength={120}
                            autoComplete="off"
                            onChange={(e) =>
                              patch(i.provider, { accountId: e.target.value })
                            }
                          />
                        </label>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setCredential(i.provider)}
                      >
                        <KeyRound size={14} />
                        Gerenciar credencial · {i.provider}
                      </Button>
                      {credential === i.provider && (
                        <div className="credential-placeholder">
                          <label className="form-field">
                            Chave de API · {i.provider}
                            <Input
                              type="password"
                              disabled
                              placeholder="Disponível após conectar o serviço seguro"
                              autoComplete="off"
                            />
                          </label>
                          <p className="muted">
                            A edição de chaves reais requer o backend de
                            credenciais. Este protótipo não recebe nem armazena
                            API Keys no navegador.
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </section>
              ))}
              {(save.isError || load.isError) && (
                <p role="alert">{save.error?.message ?? load.error?.message}</p>
              )}
              <Button className="btn" type="submit" disabled={save.isPending}>
                Salvar configurações da marca
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
