export type InstallationState = "INSTALLING" | "PARTIAL" | "READY" | "BLOCKED";
export type InstallationResourceState =
  "PENDING" | "RUNNING" | "PARTIAL" | "COMPLETE" | "BLOCKED";
export type InstallationCoverage = {
  from: string;
  to: string;
  reason: string;
  resources: string[];
};
export type InstallationProgress = {
  kind: "RECORDS" | "TIME_COVERAGE" | "CHUNKS" | "UNKNOWN";
  percent: number | null;
  processed: number | null;
  total: number | null;
  eta_seconds: number | null;
};
export type InstallationSource = {
  source: string;
  connection_id: string | null;
  configured: boolean;
  active: boolean | null;
  state: InstallationResourceState;
  last_success_at: string | null;
  last_error_code: string | null;
};
export type InstallationResource = {
  source: string;
  connection_id: string | null;
  resource: string;
  state: InstallationResourceState;
  latest_run_id: string | null;
  latest_run_status:
    "running" | "completed" | "completed_with_errors" | "failed" | null;
  mode: "backfill" | "incremental" | "open_orders" | "replay" | null;
  records_read: number | null;
  records_processed: number | null;
  records_failed: number | null;
  pending_raw: boolean | null;
  coverage_from: string | null;
  coverage_to: string | null;
  updated_at: string | null;
  last_success_at: string | null;
  last_error_code: string | null;
};
export type Installation = {
  store_id: string;
  overall_state: InstallationState;
  updated_at: string;
  history_complete: boolean | null;
  facts_complete: boolean | null;
  facts_coverage_from: string | null;
  facts_coverage_to: string | null;
  sources: InstallationSource[];
  resources: InstallationResource[];
  available_window: InstallationCoverage | null;
  recommended_preview_window: InstallationCoverage | null;
  progress: InstallationProgress;
  limitations: string[];
};
export type InstallationEnvelope = {
  data: Installation;
  pagination: null;
  metadata: {
    contract_version: "installation.v1";
    store_id: string;
    snapshot_at: string;
    generation: number | null;
    policy_hash: string | null;
    reporting_timezone: string;
    currency: string | null;
  };
};
