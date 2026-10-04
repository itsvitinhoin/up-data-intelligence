import { parseInstallation } from "./installation";
/** Secret submission deliberately avoids React Query, Company and persistent browser storage. */
import { ApiError } from "./access";
import type { OnboardingRequest, OnboardingResult } from "@/types/onboarding";
const invalid = () => new ApiError(502, "Resposta administrativa inválida.");
function record(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw invalid();
  const result = value as Record<string, unknown>;
  if (
    Object.keys(result).some((key) => !keys.includes(key)) ||
    keys.some((key) => !(key in result))
  )
    throw invalid();
  return result;
}
function text(value: unknown) {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > 250 ||
    /[\r\n]/.test(value)
  )
    throw invalid();
  return value;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw invalid();
  return value;
}
export function parseOnboarding(value: unknown): OnboardingResult {
  const hasInstallation =
    !!value && typeof value === "object" && "installation" in value;
  const r = record(value, [
    ...(hasInstallation ? ["installation"] : []),
    "operation_id",
    "store_id",
    "brand_id",
    "name",
    "tenant_id",
    "workspace_operations",
    "status",
    "current_step",
    "error_code",
    "created_at",
    "updated_at",
    "sources",
  ]);
  const statuses = [
    "RESERVED",
    "SECRET_PENDING",
    "SECRET_READY",
    "FINALIZING",
    "INSTALLING",
    "READY",
    "BLOCKED",
  ] as const;
  if (!statuses.includes(r.status as OnboardingResult["status"]))
    throw invalid();
  const store = text(r.store_id),
    brand = text(r.brand_id),
    operationId = text(r.operation_id);
  if (
    !/^[a-z][a-z0-9-]{0,79}$/.test(store) ||
    brand !== `brand-${store}` ||
    !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(operationId)
  )
    throw invalid();
  const workspace = array(r.workspace_operations).map<
    OnboardingResult["workspace_operations"][number]
  >((value) => {
    const w = record(value, ["id", "operation"]);
    if (
      (w.operation !== "B2B" && w.operation !== "B2C") ||
      w.id !== `${store}-${w.operation.toLowerCase()}`
    )
      throw invalid();
    return { id: text(w.id), operation: w.operation };
  });
  if (
    !workspace.length ||
    new Set(workspace.map((w) => w.id)).size !== workspace.length
  )
    throw invalid();
  const sources = array(r.sources).map<OnboardingResult["sources"][number]>(
    (value) => {
      const s = record(value, ["source", "state"]);
      if (
        (s.source !== "upzero" && s.source !== "meta") ||
        (r.status === "READY" ? s.state !== "ACTIVE" : s.state !== "PENDING")
      )
        throw invalid();
      return {
        source: s.source,
        state: r.status === "READY" ? "ACTIVE" : "PENDING",
      };
    },
  );
  for (const t of [r.created_at, r.updated_at])
    if (!Number.isFinite(Date.parse(text(t)))) throw invalid();
  const errorCode = r.error_code === null ? null : text(r.error_code);
  if (errorCode !== null && !/^[a-z_]{1,100}$/.test(errorCode)) throw invalid();
  return {
    ...(hasInstallation
      ? { installation: parseInstallation(r.installation, store) }
      : {}),
    operation_id: operationId,
    store_id: store,
    brand_id: brand,
    name: text(r.name),
    tenant_id: text(r.tenant_id),
    workspace_operations: workspace,
    status: r.status as OnboardingResult["status"],
    current_step: text(r.current_step),
    error_code: errorCode,
    created_at: text(r.created_at),
    updated_at: text(r.updated_at),
    sources,
  };
}
export async function submitOnboarding(
  payload: OnboardingRequest,
  key: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<OnboardingResult> {
  let body = JSON.stringify(payload);
  try {
    const response = await fetcher("/api/admin/onboarding", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body,
      signal,
    });
    if (!response.ok)
      throw new ApiError(
        response.status,
        "Cadastro não concluído. Consulte a operação ou repita com a mesma chave e configuração; não crie uma segunda operação.",
      );
    return parseOnboarding(await response.json());
  } finally {
    payload.sources.upzero.credential = null;
    body = ""; // Best effort only; JS strings cannot be reliably zeroized.
  }
}

export async function readOnboarding(
  operationId: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<OnboardingResult> {
  if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(operationId))
    throw invalid();
  const response = await fetcher(`/api/admin/onboarding/${operationId}`, {
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });
  if (!response.ok)
    throw new ApiError(
      response.status,
      "Não foi possível verificar a instalação da marca.",
    );
  return parseOnboarding(await response.json());
}
