import { ApiError } from "./access";

export type BrandSummary = {
  tenant_id: string;
  brand_id: string;
  workspace_operation_id: string;
  operation: "B2B" | "B2C";
  status: "DRAFT" | "READY" | "ACTIVE" | "PAUSED" | "ERROR" | "DISABLED";
  sync_enabled: boolean;
  created_at: string | null;
  coverage_from: string | null;
  coverage_to: string | null;
  active_connections: number;
  pending_connections: number;
  attention_connections: number;
  sources: {
    provider: "upzero" | "meta";
    status: string;
    credential_configured: boolean;
  }[];
};
const invalid = () => new ApiError(502, "Resumo de marcas inválido.");
function exact(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw invalid();
  const row = value as Record<string, unknown>;
  if (
    Object.keys(row).length !== keys.length ||
    keys.some((key) => !(key in row))
  )
    throw invalid();
  return row;
}
function text(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > 128 ||
    /[\r\n]/.test(value)
  )
    throw invalid();
  return value;
}
function timestamp(value: unknown): string | null {
  if (value === null) return null;
  const v = text(value);
  if (
    !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) ||
    !Number.isFinite(Date.parse(v))
  )
    throw invalid();
  return v;
}
function flag(value: unknown): boolean {
  if (typeof value !== "boolean") throw invalid();
  return value;
}
function count(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw invalid();
  return value;
}
function choice<T extends string>(value: unknown, choices: readonly T[]): T {
  if (!choices.includes(value as T)) throw invalid();
  return value as T;
}
export function parseBrandSummaries(value: unknown) {
  const root = exact(value, ["data", "metadata"]);
  const meta = exact(root.metadata, ["as_of", "basis"]);
  if (meta.basis !== "operational_metadata" || !timestamp(meta.as_of))
    throw invalid();
  if (!Array.isArray(root.data) || root.data.length > 1000) throw invalid();
  const seen = new Set<string>();
  const data: BrandSummary[] = root.data.map((value) => {
    const r = exact(value, [
      "tenant_id",
      "brand_id",
      "workspace_operation_id",
      "operation",
      "status",
      "sync_enabled",
      "created_at",
      "coverage_from",
      "coverage_to",
      "active_connections",
      "pending_connections",
      "attention_connections",
      "sources",
    ]);
    const key = JSON.stringify([r.tenant_id, r.workspace_operation_id]);
    if (seen.has(key) || !Array.isArray(r.sources)) throw invalid();
    seen.add(key);
    const providers = new Set<string>();
    const sources = r.sources.map((s) => {
      const row = exact(s, ["provider", "status", "credential_configured"]);
      const provider = choice(row.provider, ["upzero", "meta"] as const);
      if (providers.has(provider)) throw invalid();
      providers.add(provider);
      return {
        provider,
        status: choice(row.status, [
          "active",
          "pending",
          "disabled",
          "inactive",
          "error",
        ] as const),
        credential_configured: flag(row.credential_configured),
      };
    });
    const active = count(r.active_connections),
      pending = count(r.pending_connections),
      attention = count(r.attention_connections);
    if (
      active !== sources.filter((s) => s.status === "active").length ||
      pending !== sources.filter((s) => s.status === "pending").length ||
      attention !== sources.filter((s) => s.status === "error").length
    )
      throw invalid();
    return {
      tenant_id: text(r.tenant_id),
      brand_id: text(r.brand_id),
      workspace_operation_id: text(r.workspace_operation_id),
      operation: choice(r.operation, ["B2B", "B2C"] as const),
      status: choice(r.status, [
        "DRAFT",
        "READY",
        "ACTIVE",
        "PAUSED",
        "ERROR",
        "DISABLED",
      ] as const),
      sync_enabled: flag(r.sync_enabled),
      created_at: timestamp(r.created_at),
      coverage_from: timestamp(r.coverage_from),
      coverage_to: timestamp(r.coverage_to),
      active_connections: active,
      pending_connections: pending,
      attention_connections: attention,
      sources,
    };
  });
  return {
    data,
    metadata: {
      as_of: timestamp(meta.as_of)!,
      basis: "operational_metadata" as const,
    },
  };
}
export async function readBrandSummaries(
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
) {
  const response = await fetcher("/api/admin/brands", {
    cache: "no-store",
    credentials: "same-origin",
    signal,
  });
  if (!response.ok)
    throw new ApiError(
      response.status,
      "Não foi possível consultar as marcas.",
    );
  return parseBrandSummaries(await response.json());
}

export function parseIntegrationHealth(value: unknown) {
  const root = exact(value, ["data", "metadata"]);
  const meta = exact(root.metadata, ["as_of", "basis"]);
  if (meta.basis !== "durable_operational_evidence" || !timestamp(meta.as_of))
    throw invalid();
  const row = exact(root.data, [
    "tenant_id",
    "brand_id",
    "workspace_operation_id",
    "next_sync_at",
    "expected_cutoff",
    "health_checked_at",
    "health_evidence_current",
    "blocking_findings",
    "warning_findings",
    "sources",
  ]);
  if (!Array.isArray(row.sources) || row.sources.length > 2) throw invalid();
  const seen = new Set<string>();
  const sources = row.sources.map((value) => {
    const r = exact(value, [
      "provider",
      "connection_status",
      "health",
      "last_success_at",
      "last_attempt_at",
      "coverage_certified",
      "resources",
    ]);
    const provider = choice(r.provider, ["upzero", "meta"] as const);
    if (
      seen.has(provider) ||
      !Array.isArray(r.resources) ||
      r.resources.length > 30
    )
      throw invalid();
    seen.add(provider);
    const resources = new Set<string>();
    return {
      provider,
      connection_status: text(r.connection_status),
      health: choice(r.health, [
        "HEALTHY",
        "SYNCING",
        "PARTIAL",
        "STALE",
        "ERROR",
        "DISABLED",
        "NOT_CONFIGURED",
      ] as const),
      last_success_at: timestamp(r.last_success_at),
      last_attempt_at: timestamp(r.last_attempt_at),
      coverage_certified: flag(r.coverage_certified),
      resources: r.resources.map((value) => {
        const row = exact(value, [
          "resource",
          "ledger_status",
          "last_attempt_at",
          "last_success_at",
          "records_processed",
          "pages_processed",
          "failed_records",
        ]);
        const resource = text(row.resource);
        if (resources.has(resource)) throw invalid();
        resources.add(resource);
        return {
          resource,
          ledger_status: text(row.ledger_status),
          last_attempt_at: timestamp(row.last_attempt_at),
          last_success_at: timestamp(row.last_success_at),
          records_processed:
            row.records_processed === null
              ? null
              : count(row.records_processed),
          pages_processed:
            row.pages_processed === null ? null : count(row.pages_processed),
          failed_records:
            row.failed_records === null ? null : count(row.failed_records),
        };
      }),
    };
  });
  return {
    data: {
      tenant_id: text(row.tenant_id),
      brand_id: text(row.brand_id),
      workspace_operation_id: text(row.workspace_operation_id),
      next_sync_at: timestamp(row.next_sync_at),
      expected_cutoff: timestamp(row.expected_cutoff)!,
      health_checked_at: timestamp(row.health_checked_at),
      health_evidence_current: flag(row.health_evidence_current),
      blocking_findings:
        row.blocking_findings === null ? null : count(row.blocking_findings),
      warning_findings:
        row.warning_findings === null ? null : count(row.warning_findings),
      sources,
    },
    metadata: {
      as_of: timestamp(meta.as_of)!,
      basis: "durable_operational_evidence" as const,
    },
  };
}
export async function readIntegrationHealth(
  summary: BrandSummary,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
) {
  const params = new URLSearchParams({
    tenant_id: summary.tenant_id,
    workspace_operation_id: summary.workspace_operation_id,
    operation: summary.operation,
  });
  const response = await fetcher(`/api/admin/integrations/health?${params}`, {
    cache: "no-store",
    credentials: "same-origin",
    signal,
  });
  if (!response.ok)
    throw new ApiError(
      response.status,
      "Não foi possível consultar a saúde das integrações.",
    );
  const envelope = parseIntegrationHealth(await response.json());
  if (
    envelope.data.tenant_id !== summary.tenant_id ||
    envelope.data.brand_id !== summary.brand_id ||
    envelope.data.workspace_operation_id !== summary.workspace_operation_id
  )
    throw invalid();
  return envelope;
}
