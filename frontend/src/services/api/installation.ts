import { ApiError } from "./access";
import { dateRange, inclusiveToExclusive, validDate } from "@/lib/period";
import type { Filters } from "@/types/domain";
import type {
  Installation,
  InstallationCoverage,
  InstallationEnvelope,
} from "@/types/installation";

const invalid = () => new ApiError(502, "Estado de instalação inválido.");
const obj = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw invalid();
  return value as Record<string, unknown>;
};
function exact(value: unknown, keys: string[]) {
  const row = obj(value);
  if (
    Object.keys(row).some((key) => !keys.includes(key)) ||
    keys.some((key) => !(key in row))
  )
    throw invalid();
  return row;
}
function text(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > 250 ||
    /[\r\n]/.test(value)
  )
    throw invalid();
  return value;
}
function nullableText(value: unknown) {
  return value === null ? null : text(value);
}
function flag(value: unknown): boolean {
  if (typeof value !== "boolean") throw invalid();
  return value;
}
function nullableFlag(value: unknown) {
  return value === null ? null : flag(value);
}
function count(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw invalid();
  return value;
}
function timestamp(value: unknown): string {
  const s = text(value);
  if (
    !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(s) ||
    !Number.isFinite(Date.parse(s))
  )
    throw invalid();
  return s;
}
function nullableTimestamp(value: unknown) {
  return value === null ? null : timestamp(value);
}
function list(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw invalid();
  return value;
}
function choice<T extends string>(value: unknown, allowed: readonly T[]): T {
  if (!allowed.includes(value as T)) throw invalid();
  return value as T;
}
function code(value: unknown): string | null {
  if (value === null) return null;
  return choice(value, [
    "source_not_configured",
    "source_inactive",
    "source_status_unknown",
    "sync_requires_review",
  ]);
}
function coverage(value: unknown): InstallationCoverage | null {
  if (value === null) return null;
  const r = exact(value, ["from", "to", "reason", "resources"]);
  const from = text(r.from),
    to = text(r.to);
  if (!validDate(from) || !validDate(to) || from >= to) throw invalid();
  return {
    from,
    to,
    reason: text(r.reason),
    resources: list(r.resources).map(text),
  };
}
export function parseInstallation(
  value: unknown,
  expectedStore?: string,
): InstallationEnvelope {
  const e = exact(value, ["data", "pagination", "metadata"]);
  const r = exact(e.data, [
    "store_id",
    "overall_state",
    "updated_at",
    "history_complete",
    "facts_complete",
    "facts_coverage_from",
    "facts_coverage_to",
    "sources",
    "resources",
    "available_window",
    "recommended_preview_window",
    "progress",
    "limitations",
  ]);
  const m = exact(e.metadata, [
    "contract_version",
    "store_id",
    "snapshot_at",
    "generation",
    "policy_hash",
    "reporting_timezone",
    "currency",
  ]);
  const store = text(r.store_id);
  if (
    e.pagination !== null ||
    m.contract_version !== "installation.v1" ||
    m.store_id !== store ||
    (expectedStore && store !== expectedStore)
  )
    throw invalid();
  const p = exact(r.progress, [
    "kind",
    "percent",
    "processed",
    "total",
    "eta_seconds",
  ]);
  const processed = count(p.processed),
    total = count(p.total);
  const percent = p.percent;
  if (
    percent !== null &&
    (typeof percent !== "number" ||
      !Number.isFinite(percent) ||
      percent < 0 ||
      percent > 100 ||
      processed === null ||
      total === null ||
      total === 0 ||
      Math.abs(percent - (processed / total) * 100) > 0.000001)
  )
    throw invalid();
  const resourceStates = [
    "PENDING",
    "RUNNING",
    "PARTIAL",
    "COMPLETE",
    "BLOCKED",
  ] as const;
  const available = coverage(r.available_window),
    recommended = coverage(r.recommended_preview_window);
  if (
    recommended &&
    (!available ||
      recommended.from < available.from ||
      recommended.to > available.to ||
      recommended.resources.some((s) => !available.resources.includes(s)))
  )
    throw invalid();
  const generation = count(m.generation),
    policyHash = nullableText(m.policy_hash);
  if (
    (generation === null) !== (policyHash === null) ||
    (generation !== null && generation < 1) ||
    (policyHash !== null && !/^[a-f0-9]{64}$/.test(policyHash)) ||
    (available && generation === null)
  )
    throw invalid();
  const data: Installation = {
    store_id: store,
    overall_state: choice(r.overall_state, [
      "INSTALLING",
      "PARTIAL",
      "READY",
      "BLOCKED",
    ]),
    updated_at: timestamp(r.updated_at),
    history_complete: nullableFlag(r.history_complete),
    facts_complete: nullableFlag(r.facts_complete),
    facts_coverage_from: nullableTimestamp(r.facts_coverage_from),
    facts_coverage_to: nullableTimestamp(r.facts_coverage_to),
    sources: list(r.sources).map((value) => {
      const s = exact(value, [
        "source",
        "connection_id",
        "configured",
        "active",
        "state",
        "last_success_at",
        "last_error_code",
      ]);
      return {
        source: text(s.source),
        connection_id: nullableText(s.connection_id),
        configured: flag(s.configured),
        active: nullableFlag(s.active),
        state: choice(s.state, resourceStates),
        last_success_at: nullableTimestamp(s.last_success_at),
        last_error_code: code(s.last_error_code),
      };
    }),
    resources: list(r.resources).map((value) => {
      const s = exact(value, [
        "source",
        "connection_id",
        "resource",
        "state",
        "latest_run_id",
        "latest_run_status",
        "mode",
        "records_read",
        "records_processed",
        "records_failed",
        "pending_raw",
        "coverage_from",
        "coverage_to",
        "updated_at",
        "last_success_at",
        "last_error_code",
      ]);
      return {
        source: text(s.source),
        connection_id: nullableText(s.connection_id),
        resource: text(s.resource),
        state: choice(s.state, resourceStates),
        latest_run_id: nullableText(s.latest_run_id),
        latest_run_status:
          s.latest_run_status === null
            ? null
            : choice(s.latest_run_status, [
                "running",
                "completed",
                "completed_with_errors",
                "failed",
              ] as const),
        mode:
          s.mode === null
            ? null
            : choice(s.mode, [
                "backfill",
                "incremental",
                "open_orders",
                "replay",
              ] as const),
        records_read: count(s.records_read),
        records_processed: count(s.records_processed),
        records_failed: count(s.records_failed),
        pending_raw: nullableFlag(s.pending_raw),
        coverage_from: nullableTimestamp(s.coverage_from),
        coverage_to: nullableTimestamp(s.coverage_to),
        updated_at: nullableTimestamp(s.updated_at),
        last_success_at: nullableTimestamp(s.last_success_at),
        last_error_code: code(s.last_error_code),
      };
    }),
    available_window: available,
    recommended_preview_window: recommended,
    progress: {
      kind: choice(p.kind, ["RECORDS", "TIME_COVERAGE", "CHUNKS", "UNKNOWN"]),
      percent,
      processed,
      total,
      eta_seconds: count(p.eta_seconds),
    },
    limitations: list(r.limitations).map(text),
  };
  if (
    data.overall_state === "READY" &&
    (data.history_complete !== true ||
      data.facts_complete !== true ||
      !available ||
      !data.sources.length ||
      data.sources.some(
        (s) => s.state !== "COMPLETE" || !s.configured || s.active !== true,
      ) ||
      !data.resources.length ||
      data.resources.some(
        (r) => r.state !== "COMPLETE" || r.pending_raw === true,
      ))
  )
    throw invalid();
  return {
    data,
    pagination: null,
    metadata: {
      contract_version: "installation.v1",
      store_id: store,
      snapshot_at: timestamp(m.snapshot_at),
      generation,
      policy_hash: policyHash,
      reporting_timezone: text(m.reporting_timezone),
      currency: nullableText(m.currency),
    },
  };
}
export function installationPollingInterval(data?: Installation) {
  return data && ["INSTALLING", "PARTIAL"].includes(data.overall_state)
    ? 30000
    : false;
}
export function installationPeriodAvailable(
  data: Installation,
  filters: Filters,
  resource = "overview",
) {
  const window = data.available_window,
    range = dateRange(filters);
  return (
    !!window &&
    window.resources.includes(resource) &&
    range.from >= window.from &&
    inclusiveToExclusive(range.to) <= window.to
  );
}
export const partialInstallationMessage =
  "Histórico ainda está sendo processado. Os dados exibidos correspondem ao período atualmente certificado.";
