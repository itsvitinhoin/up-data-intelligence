import { ApiError } from "./access";

import { historyScope } from "./history";
import type { BrandSummary } from "./brand-integrations";
export type ProviderConnection = {
  provider: "upzero" | "meta";
  status: string;
  credential_configured: boolean;
  connection_id: string | null;
  store_identifier: string | null;
  account_id: string | null;
  api_version: string | null;
};
function exact(value: unknown, keys: string[]): Record<string, unknown> {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((k) => !(k in value))
  )
    throw new ApiError(502, "Configuração de integração inválida.");
  return value as Record<string, unknown>;
}
function text(value: unknown): string | null {
  if (value === null) return null;
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 128 ||
    /[\r\n]/.test(value)
  )
    throw new ApiError(502, "Configuração de integração inválida.");
  return value;
}
export function parseConnections(value: unknown) {
  const root = exact(value, ["data"]),
    r = exact(root.data, ["tenant_id", "workspace_operation_id", "providers"]);
  if (!Array.isArray(r.providers) || r.providers.length !== 2)
    throw new ApiError(502, "Configuração de integração inválida.");
  const providers = r.providers.map((value) => {
    const p = exact(value, [
      "provider",
      "status",
      "credential_configured",
      "connection_id",
      "store_identifier",
      "account_id",
      "api_version",
    ]);
    if (
      !["upzero", "meta"].includes(String(p.provider)) ||
      ![
        "active",
        "pending",
        "disabled",
        "inactive",
        "error",
        "not_configured",
      ].includes(String(p.status)) ||
      typeof p.credential_configured !== "boolean"
    )
      throw new ApiError(502, "Configuração de integração inválida.");
    return {
      provider: p.provider as "upzero" | "meta",
      status: p.status as string,
      credential_configured: p.credential_configured,
      connection_id: text(p.connection_id),
      store_identifier: text(p.store_identifier),
      account_id: text(p.account_id),
      api_version: text(p.api_version),
    };
  });
  if (
    new Set(providers.map((p) => p.provider)).size !== 2 ||
    !text(r.tenant_id) ||
    !text(r.workspace_operation_id)
  )
    throw new ApiError(502, "Configuração de integração inválida.");
  return {
    data: {
      tenant_id: text(r.tenant_id)!,
      workspace_operation_id: text(r.workspace_operation_id)!,
      providers,
    },
  };
}
export function parseConnectionResult(value: unknown) {
  const root = exact(value, ["data"]),
    r = exact(root.data, [
      "operation_id",
      "provider",
      "action",
      "status",
      "error_code",
      "updated_at",
    ]);
  if (
    !/^[a-f0-9]{64}$/.test(String(r.operation_id)) ||
    !["upzero", "meta"].includes(String(r.provider)) ||
    !["rotate", "disable", "enable", "add"].includes(String(r.action)) ||
    r.status !== "COMPLETE" ||
    r.error_code !== null ||
    typeof r.updated_at !== "string" ||
    !Number.isFinite(Date.parse(r.updated_at))
  )
    throw new ApiError(502, "Alteração não confirmada.");
  return {
    data: {
      operation_id: r.operation_id as string,
      provider: r.provider as "upzero" | "meta",
      action: r.action as "rotate" | "disable" | "enable" | "add",
      status: "COMPLETE" as const,
      error_code: null,
      updated_at: r.updated_at,
    },
  };
}
export async function readConnections(
  summary: BrandSummary,
  signal?: AbortSignal,
) {
  const res = await fetch(
    `/api/admin/integrations/configuration?${historyScope(summary)}`,
    { cache: "no-store", credentials: "same-origin", signal },
  );
  if (!res.ok)
    throw new ApiError(
      res.status,
      "Não foi possível consultar as configurações.",
    );
  const value = parseConnections(await res.json());
  if (
    value.data.tenant_id !== summary.tenant_id ||
    value.data.workspace_operation_id !== summary.workspace_operation_id
  )
    throw new ApiError(502, "Escopo de integração inválido.");
  return value;
}
/** Credential is a function-local value, never Query mutation variables or client storage. */
export async function changeConnection(
  summary: BrandSummary,
  provider: "upzero" | "meta",
  action: "rotate" | "disable" | "enable",
  credential: string | null,
  key: string,
) {
  const { csrf } = await import("@/services/auth/client");
  const token = await csrf();
  const res = await fetch(
    `/api/admin/integrations/configuration?${historyScope(summary)}`,
    {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-UP-CSRF": token,
        "Idempotency-Key": key,
      },
      body: JSON.stringify({ provider, action, credential }),
    },
  );
  if (!res.ok)
    throw new ApiError(
      res.status,
      "Alteração não confirmada. Não reenviamos credenciais automaticamente; verifique a operação antes de tentar novamente.",
    );
  return parseConnectionResult(await res.json());
}

/** Adds only a Meta connection; credentials remain global and server-owned. */
export async function addMetaConnection(
  summary: BrandSummary,
  accountId: string,
  apiVersion: string,
  key: string,
) {
  const { csrf } = await import("@/services/auth/client");
  const token = await csrf();
  const res = await fetch(
    `/api/admin/integrations/configuration?${historyScope(summary)}`,
    {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-UP-CSRF": token,
        "Idempotency-Key": key,
      },
      body: JSON.stringify({
        provider: "meta",
        action: "add",
        account_id: accountId,
        api_version: apiVersion,
      }),
    },
  );
  if (!res.ok)
    throw new ApiError(
      res.status,
      "Adição não confirmada. Não repetimos a verificação automaticamente; consulte a saúde da integração.",
    );
  return parseConnectionResult(await res.json());
}
