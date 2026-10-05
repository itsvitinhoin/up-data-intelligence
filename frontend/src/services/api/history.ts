import { ApiError } from "./access";
import type { BrandSummary } from "./brand-integrations";

export type HistoryPlan = {
  plan_id: string;
  purpose:
    | "HISTORY_EXTENSION"
    | "CATALOG_SNAPSHOT"
    | "META_CREATIVE_COVERAGE"
    | "META_SOURCE_ADDITION";
  provider: "upzero" | "meta";
  status: "RUNNING" | "PARTIAL" | "COMPLETE" | "BLOCKED" | "OUTCOME_UNKNOWN";
  requested_from: string;
  target_as_of: string;
  requested_at: string;
  error_code: string | null;
  progress: {
    kind: "CHUNKS" | "UNKNOWN";
    processed: number | null;
    total: number | null;
    percent: number | null;
    eta_seconds: number | null;
  };
  work: {
    pending: number;
    running: number;
    complete: number;
    blocked: number;
    ambiguous: number;
  };
  resources: { resource: string; total: number; complete: number }[];
};
const invalid = () => new ApiError(502, "Resposta de histórico inválida.");
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw invalid();
  const r = value as Record<string, unknown>;
  if (Object.keys(r).length !== keys.length || keys.some((k) => !(k in r)))
    throw invalid();
  return r;
}
function text(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 128 ||
    /[\r\n]/.test(value)
  )
    throw invalid();
  return value;
}
function stamp(value: unknown) {
  const v = text(value);
  if (
    !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) ||
    !Number.isFinite(Date.parse(v))
  )
    throw invalid();
  return v;
}
function number(value: unknown, nullable = false): number | null {
  if (nullable && value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
    throw invalid();
  return value;
}
function count(value: unknown): number {
  const n = number(value)!;
  if (!Number.isSafeInteger(n)) throw invalid();
  return n;
}
function choice<T extends string>(value: unknown, options: readonly T[]): T {
  if (!options.includes(value as T)) throw invalid();
  return value as T;
}
export function parseHistoryPlan(value: unknown): HistoryPlan {
  const r = object(value, [
    "plan_id",
    "purpose",
    "provider",
    "status",
    "requested_from",
    "target_as_of",
    "requested_at",
    "error_code",
    "progress",
    "work",
    "resources",
  ]);
  const id = text(r.plan_id);
  if (!/^[a-f0-9]{64}$/.test(id)) throw invalid();
  const p = object(r.progress, [
    "kind",
    "processed",
    "total",
    "percent",
    "eta_seconds",
  ]);
  const w = object(r.work, [
    "pending",
    "running",
    "complete",
    "blocked",
    "ambiguous",
  ]);
  const processed = p.processed === null ? null : count(p.processed),
    total = p.total === null ? null : count(p.total),
    percent = number(p.percent, true);
  if (
    total === 0 ||
    (processed === null) !== (total === null) ||
    (processed !== null &&
      total !== null &&
      (processed > total ||
        percent === null ||
        Math.abs(percent - (processed / total) * 100) > 1e-8)) ||
    (percent !== null && percent > 100)
  )
    throw invalid();
  if (!Array.isArray(r.resources) || r.resources.length > 10) throw invalid();
  const seen = new Set<string>();
  const resources = r.resources.map((value) => {
    const row = object(value, ["resource", "total", "complete"]);
    const resource = text(row.resource),
      total = count(row.total),
      complete = count(row.complete);
    if (seen.has(resource) || complete > total) throw invalid();
    seen.add(resource);
    return { resource, total, complete };
  });
  const from = stamp(r.requested_from),
    to = stamp(r.target_as_of);
  if (Date.parse(from) >= Date.parse(to)) throw invalid();
  return {
    plan_id: id,
    purpose: choice(r.purpose, [
      "HISTORY_EXTENSION",
      "CATALOG_SNAPSHOT",
      "META_CREATIVE_COVERAGE",
      "META_SOURCE_ADDITION",
    ] as const),
    provider: choice(r.provider, ["upzero", "meta"] as const),
    status: choice(r.status, [
      "RUNNING",
      "PARTIAL",
      "COMPLETE",
      "BLOCKED",
      "OUTCOME_UNKNOWN",
    ] as const),
    requested_from: from,
    target_as_of: to,
    requested_at: stamp(r.requested_at),
    error_code: r.error_code === null ? null : text(r.error_code),
    progress: {
      kind: choice(p.kind, ["CHUNKS", "UNKNOWN"] as const),
      processed,
      total,
      percent,
      eta_seconds: number(p.eta_seconds, true),
    },
    work: {
      pending: count(w.pending),
      running: count(w.running),
      complete: count(w.complete),
      blocked: count(w.blocked),
      ambiguous: count(w.ambiguous),
    },
    resources,
  };
}
export function parseHistory(value: unknown, single = false) {
  const root = object(value, ["data"]);
  if (single) return { data: [parseHistoryPlan(root.data)] };
  if (!Array.isArray(root.data) || root.data.length > 1000) throw invalid();
  const data = root.data.map(parseHistoryPlan);
  if (new Set(data.map((p) => p.plan_id)).size !== data.length) throw invalid();
  return { data };
}
export function historyScope(summary: BrandSummary) {
  return new URLSearchParams({
    tenant_id: summary.tenant_id,
    workspace_operation_id: summary.workspace_operation_id,
    operation: summary.operation,
  });
}
export async function readHistory(summary: BrandSummary, signal?: AbortSignal) {
  const res = await fetch(
    `/api/admin/integrations/history?${historyScope(summary)}`,
    { cache: "no-store", credentials: "same-origin", signal },
  );
  if (!res.ok)
    throw new ApiError(res.status, "Não foi possível consultar as extrações.");
  return parseHistory(await res.json());
}
export async function requestHistory(
  summary: BrandSummary,
  value: { provider: "upzero" | "meta"; from: string; to: string },
) {
  const csrf = await fetch("/api/auth/csrf", {
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!csrf.ok)
    throw new ApiError(csrf.status, "Não foi possível verificar a sessão.");
  const token = (await csrf.json()).data?.csrf_token;
  if (typeof token !== "string" || !/^[a-f0-9]{64}$/.test(token))
    throw invalid();
  const res = await fetch(
    `/api/admin/integrations/history?${historyScope(summary)}`,
    {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-UP-CSRF": token },
      body: JSON.stringify(value),
    },
  );
  if (!res.ok)
    throw new ApiError(
      res.status,
      "A extração não foi confirmada. Consulte a saúde antes de reenviar; não há repetição automática.",
    );
  return parseHistory(await res.json(), true);
}
