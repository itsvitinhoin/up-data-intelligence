export const brandSummariesFixture = () => ({
  data: [
    {
      tenant_id: "synthetic-tenant",
      brand_id: "synthetic-brand",
      workspace_operation_id: "synthetic-workspace",
      operation: "B2B",
      status: "ACTIVE",
      sync_enabled: true,
      created_at: null,
      coverage_from: "2026-09-01T03:00:00Z",
      coverage_to: "2026-10-05T03:00:00Z",
      active_connections: 2,
      pending_connections: 0,
      attention_connections: 0,
      sources: [
        { provider: "upzero", status: "active", credential_configured: true },
        { provider: "meta", status: "active", credential_configured: false },
      ],
    },
  ],
  metadata: { as_of: "2026-10-05T12:00:00Z", basis: "operational_metadata" },
});
export const integrationHealthFixture = () => ({
  data: {
    tenant_id: "synthetic-tenant",
    brand_id: "synthetic-brand",
    workspace_operation_id: "synthetic-workspace",
    next_sync_at: null,
    expected_cutoff: "2026-10-05T03:00:00Z",
    health_checked_at: "2026-10-05T07:00:00Z",
    health_evidence_current: true,
    blocking_findings: 0,
    warning_findings: 0,
    sources: [
      {
        provider: "upzero",
        connection_status: "active",
        health: "HEALTHY",
        last_success_at: "2026-10-05T03:05:00Z",
        last_attempt_at: "2026-10-05T03:01:00Z",
        coverage_certified: true,
        resources: [
          {
            resource: "customers",
            ledger_status: "completed",
            last_attempt_at: "2026-10-05T03:01:00Z",
            last_success_at: "2026-10-05T03:05:00Z",
            records_processed: 12,
            pages_processed: 1,
            failed_records: 0,
          },
        ],
      },
    ],
  },
  metadata: {
    as_of: "2026-10-05T12:00:00Z",
    basis: "durable_operational_evidence",
  },
});

export const connectionConfigurationFixture = () => ({
  data: {
    tenant_id: "synthetic-tenant",
    workspace_operation_id: "synthetic-workspace",
    providers: [
      {
        provider: "upzero",
        status: "active",
        credential_configured: true,
        connection_id: "synthetic-upzero",
        store_identifier: "synthetic-store",
        account_id: null,
        api_version: null,
      },
      {
        provider: "meta",
        status: "active",
        credential_configured: true,
        connection_id: "synthetic-meta",
        store_identifier: null,
        account_id: "act_synthetic",
        api_version: "v24.0",
      },
    ],
  },
});

export const historyPlanFixture = () => ({
  plan_id: "a".repeat(64),
  purpose: "HISTORY_EXTENSION",
  provider: "upzero",
  status: "RUNNING",
  requested_from: "2026-08-01T03:00:00Z",
  target_as_of: "2026-09-01T03:00:00Z",
  requested_at: "2026-10-05T12:00:00Z",
  error_code: null,
  progress: {
    kind: "CHUNKS",
    processed: 0,
    total: 63,
    percent: 0,
    eta_seconds: null,
  },
  work: { pending: 63, running: 0, complete: 0, blocked: 0, ambiguous: 0 },
  resources: [
    { resource: "orders", total: 31, complete: 0 },
    { resource: "analytics_facts", total: 31, complete: 0 },
    { resource: "publication", total: 1, complete: 0 },
  ],
});
