import type {
  InstallationEnvelope,
  InstallationState,
} from "@/types/installation";
export function installationFixture(
  state: InstallationState = "PARTIAL",
  window = true,
): InstallationEnvelope {
  const available = window
    ? {
        from: "2026-09-01",
        to: "2026-09-28",
        reason: "analytics_head_receipt_certified",
        resources: ["overview", "customers", "orders", "retention", "products"],
      }
    : null;
  return {
    data: {
      store_id: "mx-fashion",
      overall_state: state,
      updated_at: "2026-09-30T00:00:00Z",
      history_complete: state === "READY",
      facts_complete: state === "READY",
      facts_coverage_from: null,
      facts_coverage_to: null,
      sources: [
        {
          source: "upzero",
          connection_id: "synthetic-connection",
          configured: true,
          active: true,
          state:
            state === "READY"
              ? "COMPLETE"
              : state === "BLOCKED"
                ? "BLOCKED"
                : "RUNNING",
          last_success_at: "2026-09-29T00:00:00Z",
          last_error_code: state === "BLOCKED" ? "sync_requires_review" : null,
        },
      ],
      resources: ["customers", "orders", "analytics_facts"].map((resource) => ({
        source: "upzero",
        connection_id: "synthetic-connection",
        resource,
        state:
          state === "READY" || resource !== "analytics_facts"
            ? "COMPLETE"
            : state === "BLOCKED"
              ? "BLOCKED"
              : "RUNNING",
        latest_run_id: "synthetic-run",
        latest_run_status:
          resource === "analytics_facts" && state !== "READY"
            ? "running"
            : "completed",
        mode: "backfill",
        records_read: 120,
        records_processed: 100,
        records_failed: 0,
        pending_raw: resource === "analytics_facts" && state !== "READY",
        coverage_from: null,
        coverage_to: null,
        updated_at: "2026-09-30T00:00:00Z",
        last_success_at: null,
        last_error_code: null,
      })),
      available_window: available,
      recommended_preview_window: available ? structuredClone(available) : null,
      progress: {
        kind: "RECORDS",
        processed: 300,
        total: null,
        percent: null,
        eta_seconds: null,
      },
      limitations:
        state === "READY"
          ? []
          : ["history_incomplete", "facts_incomplete", "eta_unknown"],
    },
    pagination: null,
    metadata: {
      contract_version: "installation.v1",
      store_id: "mx-fashion",
      snapshot_at: "2026-09-30T00:00:00Z",
      generation: window ? 7 : null,
      policy_hash: window ? "a".repeat(64) : null,
      reporting_timezone: "America/Sao_Paulo",
      currency: "BRL",
    },
  };
}
