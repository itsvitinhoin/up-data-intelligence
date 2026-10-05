"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading, Failure } from "@/components/ui-kit";
import {
  readConnections,
  changeConnection,
  addMetaConnection,
  type ProviderConnection,
} from "@/services/api/connections";
import type { BrandSummary } from "@/services/api/brand-integrations";
import { integrationProviders } from "./integration-providers";

function ConnectionEditor({
  connection,
  summary,
}: {
  connection: ProviderConnection;
  summary: BrandSummary;
}) {
  const [edit, setEdit] = useState(false),
    [busy, setBusy] = useState(false),
    [blocked, setBlocked] = useState(false),
    [message, setMessage] = useState<string | null>(null),
    [disable, setDisable] = useState(false);
  const client = useQueryClient();
  async function perform(
    action: "rotate" | "disable" | "enable",
    credential: string | null,
  ) {
    if (busy || blocked) return;
    setBusy(true);
    setMessage(null);
    try {
      await changeConnection(
        summary,
        connection.provider,
        action,
        credential,
        crypto.randomUUID(),
      );
      setMessage("Configuração confirmada.");
      setEdit(false);
      setDisable(false);
      await client.invalidateQueries({
        queryKey: [
          "connection-configuration",
          summary.tenant_id,
          summary.workspace_operation_id,
        ],
      });
      await client.invalidateQueries({
        queryKey: ["up-admin", "brand-summaries"],
      });
    } catch {
      setBlocked(true);
      setMessage(
        "Alteração não confirmada. A referência anterior não é substituída sem verificação. Consulte a saúde da integração; não há repetição automática.",
      );
    } finally {
      setBusy(false);
    }
  }
  const active = connection.status === "active";
  return (
    <section className="integration-editor">
      <strong>
        {connection.provider === "upzero" ? "UP Zero" : "Meta Ads"}
      </strong>
      <p>
        Conexão:{" "}
        {active
          ? "Ativa"
          : connection.status === "disabled"
            ? "Desativada"
            : connection.status === "not_configured"
              ? "Não configurada"
              : "Pendente"}
      </p>
      <p>
        Credencial:{" "}
        {connection.provider === "meta"
          ? "Global · gerenciada no servidor"
          : connection.credential_configured
            ? "Configurada"
            : "Não configurada"}
      </p>
      {connection.provider === "upzero" ? (
        <>
          <p>
            Identificador da loja:{" "}
            {connection.store_identifier ?? "Não informado"}
          </p>
          <p>Conexão: {connection.connection_id ?? "Não configurada"}</p>
        </>
      ) : (
        <>
          <p>Conta Meta: {connection.account_id ?? "Não informada"}</p>
          <p>Versão da API: {connection.api_version ?? "Não informada"}</p>
          <p className="muted">
            A identidade da conta é preservada. Trocar a conta histórica exige
            adoção explícita; nenhum token por marca é solicitado.
          </p>
        </>
      )}
      {connection.status === "not_configured" ? (
        connection.provider === "meta" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (busy || blocked) return;
              const form = e.currentTarget,
                values = new FormData(form);
              const account = String(values.get("account_id") ?? ""),
                version = String(values.get("api_version") ?? "");
              form.reset();
              setBusy(true);
              setMessage(null);
              void addMetaConnection(
                summary,
                account,
                version,
                crypto.randomUUID(),
              )
                .then(async () => {
                  setMessage(
                    "Conta verificada. O catálogo e os insights serão processados em unidades limitadas, preservando os dados certificados.",
                  );
                  await client.invalidateQueries({
                    queryKey: [
                      "connection-configuration",
                      summary.tenant_id,
                      summary.workspace_operation_id,
                    ],
                  });
                  await client.invalidateQueries({
                    queryKey: ["up-admin", "brand-summaries"],
                  });
                })
                .catch(() => {
                  setBlocked(true);
                  setMessage(
                    "Adição não confirmada. Consulte a saúde da integração antes de tentar novamente.",
                  );
                })
                .finally(() => setBusy(false));
            }}
          >
            <label className="form-field">
              Conta de anúncio Meta
              <Input
                name="account_id"
                required
                pattern="[0-9]+"
                maxLength={128}
                autoComplete="off"
              />
            </label>
            <label className="form-field">
              Versão da API aprovada
              <Input
                name="api_version"
                required
                pattern="v[0-9]+\.0"
                maxLength={16}
                autoComplete="off"
              />
            </label>
            <p className="muted">
              O servidor verifica o acesso com a credencial global da UP. A
              adição cria apenas trabalho desta fonte para a janela já
              certificada; não reinstala UP Zero.
            </p>
            <Button type="submit" disabled={busy || blocked}>
              {busy ? "Verificando…" : "Verificar e adicionar Meta"}
            </Button>
          </form>
        ) : (
          <p className="muted">
            A adição de UP Zero a uma marca sem dados comerciais certificados
            exige adoção própria. Nenhuma credencial é coletada neste fluxo.
          </p>
        )
      ) : (
        <>
          {connection.provider === "upzero" && !edit && (
            <Button
              variant="ghost"
              disabled={busy || blocked}
              onClick={() => setEdit(true)}
            >
              {active
                ? "Substituir credencial"
                : "Reativar com nova credencial"}
            </Button>
          )}
          {edit && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const credential = String(
                  new FormData(form).get("credential") ?? "",
                );
                form.reset();
                void perform(active ? "rotate" : "enable", credential);
              }}
            >
              <label className="form-field">
                Nova credencial UP Zero
                <Input
                  type="password"
                  name="credential"
                  required
                  maxLength={8192}
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
              <p className="muted">
                O servidor cria uma versão, verifica a fonte e só então troca a
                referência. A versão anterior é preservada. O campo não é
                preenchido nem armazenado nesta sessão.
              </p>
              <Button type="submit" disabled={busy || blocked}>
                {busy ? "Verificando…" : "Verificar e salvar"}
              </Button>
            </form>
          )}
          {connection.provider === "meta" && !active && (
            <Button
              disabled={busy || blocked}
              onClick={() => void perform("enable", null)}
            >
              Verificar e reativar conta atual
            </Button>
          )}
          {active && (
            <Button
              variant="ghost"
              disabled={busy || blocked}
              onClick={() => setDisable(true)}
            >
              Desativar conexão
            </Button>
          )}
          {disable && (
            <div>
              <p>
                A desativação interrompe esta fonte e seus pipelines
                dependentes. O histórico e as publicações são preservados.
              </p>
              <Button
                disabled={busy || blocked}
                onClick={() => void perform("disable", null)}
              >
                Confirmar desativação
              </Button>
              <Button variant="ghost" onClick={() => setDisable(false)}>
                Manter ativa
              </Button>
            </div>
          )}
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
export function ProviderSettings({ summary }: { summary: BrandSummary }) {
  const q = useQuery({
    queryKey: [
      "connection-configuration",
      summary.tenant_id,
      summary.workspace_operation_id,
    ],
    queryFn: ({ signal }) => readConnections(summary, signal),
    retry: false,
  });
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  return (
    <div className="integration-statuses">
      {integrationProviders.map((provider) =>
        provider.implemented ? (
          <ConnectionEditor
            key={provider.id}
            summary={summary}
            connection={q.data.data.providers.find(
              (p) => p.provider === provider.id,
            )!}
          />
        ) : (
          <section className="integration-editor" key={provider.id}>
            <strong>{provider.label}</strong>{" "}
            <span className="badge">{provider.category}</span>
            <p>Disponível em breve · conector ainda não implementado</p>
            <Button disabled>Disponível em breve</Button>
          </section>
        ),
      )}
    </div>
  );
}
