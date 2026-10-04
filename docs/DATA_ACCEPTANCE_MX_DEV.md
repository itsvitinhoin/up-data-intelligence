# CHANGE #19.0 — MX DEV data acceptance

## Status

IN PROGRESS. Product Go-Live remains prohibited until every live acceptance gate passes.
No public HTTP serving, production authentication or frontend binding is changed.

Audit ID: `8b214cbc-a3a8-40b0-ad02-14bef801e7e7`.
Logical cutoff: `2026-10-04T03:00:00Z`.
Certified local report window: `[2026-09-01,2026-10-04)` in America/Sao_Paulo.
Currency: BRL. Policy/identity remain Registry-driven. `history_complete=false`.
Source payloads, customer identifiers, credentials and cursors are excluded from this report.

## Exact comparison

`src/quality/data_accuracy.py` compares required identities before field values.
Duplicate, absent, missing and unexpected identities fail independently of aggregate totals.
Money uses Decimal; floats are rejected. NULL and booleans preserve their meanings.
The seven independent SQL reference models can pin every CORE input to the same
parameterized `source_snapshot_at`; ordinary compilation is unchanged.

Source/CORE results already observed at the approved cutoff:

| Check | Expected/source | Actual/CORE | Delta | Status |
|---|---:|---:|---:|---|
| Customers current unique identities | 1211 | 1211 | 0 | PASS |
| Orders in certified window | 22 | 22 | 0 | PASS |
| Order items in latest parent versions | 366 | 366 | 0 | PASS |
| Duplicate/missing/unexpected customer, order and item identities | 0 | 0 | 0 | PASS |
| Order money/quantities/status and item fields mismatched by identity | 0 | 0 | 0 | PASS |
| Invalid item parent version | 0 | 0 | 0 | PASS |

Remaining Facts, Meta, Analytics, Intelligence, Dashboard and freshness checks must
be completed quantitatively before acceptance. A missing check is not PASS.

## Real Scheduler invocation path

Normal schedulers had no attempt since activation, although ENABLED. Installation
had automatic no-op attempts. One explicit run-now per normal scheduler is authorized,
sequentially, guarded by absent leases, no active chain and only MX eligible.
UP Zero Scheduler → dispatcher `up-store-dispatcher-jrpxh` → worker
`up-upzero-worker-hj7x6` completed successfully. Source run core failures = 0;
pending RAW = 0. Meta Scheduler → dispatcher `up-store-dispatcher-splx4` → worker
`up-meta-worker-lb6vf` completed successfully, including all four fresh catalogs
and daily Insights. Same-cutoff reruns must not advance report_from or regress coverage.

## Durable daily health detector

`src/quality/data_health.py` checks sixteen aggregate rules without source clients,
Secret Manager access or business mutations: Registry active/sync, active sources,
pending RAW, nonterminal work, Customers freshness, contiguous Orders/Facts coverage,
Meta daily union/catalog freshness, valid Analytics HEAD/RECEIPT/current cutoff/
monotonic history, current Intelligence base, Dashboard publication resolution and
history semantics. Operational reads use one snapshot; source-disabled checks are
explicitly not applicable rather than evidence of freshness.

`src/quality/data_health_cli.py` requires explicit DEV confirmation, bounded store
inventory and query ceilings of 1 GiB/query and 128 GiB/execution. Blocking findings
persist and cause exit 1. Unknown reads/writes cause a sanitized failure, never green.
There is no automatic repair or retry of ambiguous writes.

Results use the existing `up_ops.quality_results`, `record_id=NULL`, aggregate counts,
and deterministic `digest([store,cutoff,rule])` keys. Same-cutoff reruns MERGE the same
logical checks. No new schema/table is needed.

Terraform prepares `up-data-health`, a dedicated SA, table-scoped READ on eight
necessary evidence tables and WRITE only on quality_results, query jobUser and
scoped existing Scheduler-SA invocation. No secret access or worker invocation.
`up-data-health-dispatch` uses `0 7 * * *` UTC and defaults PAUSED. Deployment/manual
acceptance/enablement are still pending; no health cron execution is claimed.
Cloud Run failed execution and quality_results are the operational failure authority.
No notification recipient/channel is invented.

Manual DEV command after audited deployment (Scheduler still PAUSED):

```bash
python -m src.quality.data_health_cli --live \
  --project up-data-intelligence-dev --confirm-project up-data-intelligence-dev \
  --location southamerica-east1 --store-id mx-fashion --confirm-store mx-fashion \
  --maximum-bytes-billed 1073741824 --maximum-total-bytes-billed 137438953472
```

Enablement requires zero blocking health failures and a saved Terraform plan limited
to the health scheduler paused-state change. Existing business schedulers are preserved.

## Intentional limitations

Observed first purchases/frequency and observed commercial totals may be correct
without lifetime proof. Definitive new-customer classification, lifetime LTV/CAC and
other lifetime-dependent metrics remain NULL/unavailable by design. Fulfilled does
not prove paid. Influence is separate from attribution. No incomplete metric may
be substituted with zero to pass parity.
