# Backend data platform — operational architecture

Operational activation evidence is maintained in
[CHANGE 18.4G](CHANGE_18_4G_RECURRING_BACKEND_ACTIVATION.md).
Current acceptance status: **COMPLETE — DEV backend data platform**, verified on
2026-10-04. MX is ACTIVE/revision 11/sync=true, history_complete=false,
facts_complete=true. The normal UP Zero → Meta → Analytics → Intelligence manual
equivalent cycle succeeded with schedulers paused. Analytics generation 4 is
certified for `[2026-09-01,2026-10-04)`, as_of `2026-10-04T03:00Z`; its initial
report_from was preserved. Intelligence generation 2 is committed against that base.
Installation remains READY, plan COMPLETE, 45/45 work units COMPLETE, 43/43 required.
The exact five-scheduler saved plan was applied once; post-plan returned No changes.

## Data and lifecycle

Secure server-side onboarding persists configuration and pinned secret references,
then INSTALLING operations feed the bounded Installation V2 scheduler. Deterministic
plans and work units verify sources, ingest RAW before CORE, resume certified
checkpoints, and publish Analytics through atomic HEAD/RECEIPT. A completed installation
can activate Registry atomically with its onboarding receipt. Multi-store authorization,
store leases, CAS revisions and per-execution budgets remain boundaries throughout.

Recurring jobs follow UP Zero at 03 UTC, Meta at 04 UTC, Analytics at 05 UTC,
and Intelligence at 06 UTC. UP Zero uses incremental collection/reconciliation with
canonical lookback; Meta collects the closed day. Analytics/Intelligence publication
windows are cumulative from the existing certified receipt. Contiguous checkpoint coverage
is required; no MIN/MAX across gaps. NULL remains unknown, requested differs from
fulfilled, fulfilled does not prove paid, and influence is not attribution.

READY means the installation contract is complete. ACTIVE/sync=true additionally
admits recurring dispatch. Neither establishes lifetime history. Daily ingestion
can extend facts coverage without changing `history_complete`.

Meta preflight accepts compatible daily checkpoint intervals only when their union
is contiguous over the required cumulative period. Configuration comparison excludes
only since/until; account identity, definition, attribution settings and linked
completed runs remain mandatory. Fresh catalogs are independently required.
Intelligence shares this coverage model and hashes the sorted evidence set.

Global Installation dispatch explicitly uses `--all-stores --auto-activate`.
It bounds deterministic onboarding preparation by max_stores, isolates definitive
per-store failures, preserves ambiguous-outcome stop semantics, and avoids duplicate
plans. Final activation requires completed work, active required sources, no pending
RAW/nonterminal relevant checkpoint and a valid final publication when required.
Registry READY → ACTIVE/sync=true and onboarding INSTALLING → READY/current_step
ACTIVE are persisted canonically with CAS. The legacy MX has no onboarding operation;
its activation used StoreAdmin. Generic future-brand lifecycle is proved with synthetic
tests and deployed configuration, without creating a second real brand.

## Operations, secrets and failures

Installation scheduling is one minute, bounded by global/store concurrency and
one active unit per store. Normal schedules and installation scheduling each have a
fail-closed paused default. Foundation/legacy schedules remain paused. Jobs receive
one approved immutable runtime digest, query/execution budgets and pinned references.
Secret values stay server-side; global Meta credentials are never copied per brand.

Definitive failures follow existing retry allowlists. Unknown mutation/launch outcomes
stop further orchestration and retain leases until reconciled. Durable checkpoints,
runs, reservations and receipts are authoritative, rather than a process exit alone.
No manual business DML or checkpoint repair is part of routine operation.

For acceptance, inventory all stores/executions/leases, validate sources and publication,
run a manual equivalent daily cycle with schedules paused, verify dashboard coverage,
then enable only the five named dispatch schedulers through an exact saved Terraform
plan. Record build provenance, saved-plan hashes, execution results and post-plans.
MX is the sole live pilot; future brands are tested synthetically without creating
an extra real store. See the change runbook for rollback and reconciliation boundaries.

| Scheduler | Enabled DEV schedule (UTC) |
| --- | --- |
| up-upzero-dispatch | 03:00 daily |
| up-meta-dispatch | 04:00 daily |
| up-analytics-dispatch | 05:00 daily |
| up-intelligence-dispatch | 06:00 daily |
| up-installation-dispatch | Every minute |

All three Foundation schedulers remain PAUSED. The minute Installation schedule
only prepares/dispatches bounded eligible work; complete legacy plans are excluded
from global selection. It adds orchestration/query overhead, so monitor execution
counts and billed bytes independently from business ingestion. There is no second
live-brand acceptance claim or claim that a future daily cron already ran.

Rollback: keep unknown outcomes fail-closed and reconcile durable state before any
retry. For a definite reconciled recurring failure, pause the five schedules with an
audited Terraform plan and use canonical StoreAdmin pause/validate lifecycle to return
the store to READY/sync=false. Never repair checkpoints/publications or delete a lease
just because it is old; recovery requires ownership evidence and generation preconditions.

Acceptance checks: Python 2,103 tests, frontend 230 tests, offline E2E 12 tests,
lint/format/type checks, production frontend build, Terraform fmt/validate and diff-check
passed. Six real B2B resource reads passed on generation 4; outside coverage was rejected.
No credentials or commercial rows are stored in these documents.

## Still outside Product Go-Live

Backend automation does not deliver production HTTP authentication, public Read/Admin
API serving or cutover, frontend production binding, or client-facing deployment.
Those are separate Product Go-Live changes. The frontend demo and server-side preview
boundaries remain explicit until that rollout is authorized.
