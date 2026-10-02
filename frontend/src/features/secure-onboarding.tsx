"use client";
import { useEffect, useRef, useState } from "react";
import { submitOnboarding } from "@/services/api/onboarding";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui-kit";
import type { OnboardingRequest, OnboardingResult } from "@/types/onboarding";

export function SecureOnboardingForm({
  tenant,
  onCreated,
}: {
  tenant: string;
  onCreated: (result: OnboardingResult) => void;
}) {
  const [upzero, setUpzero] = useState(false),
    [meta, setMeta] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const idempotency = useRef<string | null>(null),
    credential = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      abort.current?.abort();
    },
    [],
  );
  return (
    <form
      className="form-grid no-print"
      onSubmit={async (event) => {
        event.preventDefault();
        if (busy) return;
        const form = event.currentTarget,
          values = new FormData(form);
        const get = (key: string) => String(values.get(key) ?? "");
        const request: OnboardingRequest = {
          tenant_id: tenant,
          store: {
            name: get("name"),
            slug: get("slug"),
            operation_b2b: values.get("b2b") === "on",
            operation_b2c: values.get("b2c") === "on",
            timezone: get("timezone"),
            currency: get("currency"),
            history_from: get("history_from"),
          },
          sources: {
            upzero: {
              enabled: upzero,
              credential: upzero ? get("credential") : null,
              store_identifier: upzero ? get("store_identifier") || null : null,
            },
            meta: {
              enabled: meta,
              account_id: meta ? get("account_id") : null,
              api_version: meta ? get("api_version") : null,
            },
          },
        };
        values.delete("credential");
        if (credential.current) credential.current.value = "";
        idempotency.current ??= crypto.randomUUID();
        abort.current = new AbortController();
        setBusy(true);
        setError(null);
        try {
          const result = await submitOnboarding(
            request,
            idempotency.current,
            abort.current.signal,
          );
          onCreated(result);
          form.reset();
          idempotency.current = null;
        } catch {
          setError(
            "Cadastro não concluído. Reinsira a mesma credencial para retomar com a mesma configuração. Nenhuma ingestão foi iniciada.",
          );
        } finally {
          request.sources.upzero.credential = null;
          if (credential.current) credential.current.value = "";
          abort.current = null;
          setBusy(false);
        }
      }}
    >
      <Notice>
        Onboarding DEV explícito. O login demo não é autenticação de produção. A
        marca será DRAFT, sem ingestão.
      </Notice>
      <label className="form-field">
        Nome da marca
        <Input
          name="name"
          required
          maxLength={120}
          disabled={busy}
          autoComplete="off"
        />
      </label>
      <label className="form-field">
        Slug técnico
        <Input
          name="slug"
          required
          maxLength={80}
          pattern="[a-z][a-z0-9-]*"
          disabled={busy}
          autoComplete="off"
        />
      </label>
      <label className="form-field">
        Operação B2B
        <input name="b2b" type="checkbox" defaultChecked disabled={busy} />
      </label>
      <label className="form-field">
        Operação B2C
        <input name="b2c" type="checkbox" disabled={busy} />
      </label>
      <label className="form-field">
        Timezone
        <Input
          name="timezone"
          defaultValue="America/Sao_Paulo"
          required
          maxLength={100}
          disabled={busy}
        />
      </label>
      <label className="form-field">
        Moeda
        <Input
          name="currency"
          defaultValue="BRL"
          required
          maxLength={3}
          disabled={busy}
        />
      </label>
      <label className="form-field">
        Início do histórico
        <Input name="history_from" type="date" required disabled={busy} />
      </label>
      <label className="integration-toggle">
        <input
          type="checkbox"
          checked={upzero}
          disabled={busy}
          onChange={(event) => {
            setUpzero(event.target.checked);
            if (credential.current) credential.current.value = "";
          }}
        />
        UP Zero
      </label>
      {upzero && (
        <>
          <label className="form-field">
            Chave/API Key UP Zero
            <Input
              ref={credential}
              name="credential"
              type="password"
              required
              maxLength={8192}
              autoComplete="new-password"
              spellCheck={false}
              disabled={busy}
              data-1p-ignore
              data-lpignore="true"
            />
          </label>
          <label className="form-field">
            Identificador UP Zero (opcional)
            <Input
              name="store_identifier"
              maxLength={120}
              autoComplete="off"
              disabled={busy}
            />
          </label>
        </>
      )}
      <label className="integration-toggle">
        <input
          type="checkbox"
          checked={meta}
          disabled={busy}
          onChange={(event) => setMeta(event.target.checked)}
        />
        Meta Ads
      </label>
      {meta && (
        <>
          <label className="form-field">
            Conta Meta
            <Input
              name="account_id"
              required
              inputMode="numeric"
              pattern="[0-9]+"
              maxLength={32}
              disabled={busy}
            />
          </label>
          <label className="form-field">
            Versão API Meta
            <Input
              name="api_version"
              required
              pattern="v[0-9]+\.0"
              maxLength={16}
              disabled={busy}
            />
          </label>
          <p className="muted">
            Token global exclusivamente server-side. Conta ainda não verificada.
          </p>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <Button type="submit" className="btn" disabled={busy}>
        {busy ? "Criando configuração..." : "Criar marca com segurança"}
      </Button>
    </form>
  );
}
