# Backend data platform — operational architecture

Operational activation evidence is maintained in
[CHANGE 18.4G](CHANGE_18_4G_RECURRING_BACKEND_ACTIVATION.md).
This architecture document is not itself proof that live activation has completed.

Current acceptance status: **STOPPED SAFELY — store_dispatch_global_lease_present**.
The approved Stage 1 is deployed (nine image-only updates, five approved creates),
post-plan is clean, nine help smokes passed and the global Installation no-op proved
zero dispatches with unchanged metadata. MX remains READY/revision 9/sync=false,
Installation COMPLETE/READY with 43/43 required units, and certified generation 3
coverage `[2026-09-01,2026-10-03)`. All eight schedulers are PAUSED. No normal recurring
cycle or Stage 2 activation has occurred. The old normal dispatcher global lease
requires separate guarded recovery approval; it was not removed automatically.
**Backend data platform operational completion has not yet been achieved.**

## Data and lifecycle

Secure server-side onboarding persists configuration and pinned secret references,
then INSTALLING operations feed the bounded Installation V2 scheduler. Deterministic
plans and work units verify sources, ingest RAW before CORE, resume certified
checkpoints, and publish Analytics through atomic HEAD/RECEIPT. A completed installation
can activate Registry atomically with its onboarding receipt. Multi-store authorization,
store leases, CAS revisions and per-execution budgets remain boundaries throughout.

Recurring jobs follow UP Zero at 03 UTC, Meta at 04 UTC, Analytics at 05 UTC,
and Intelligence at 06 UTC. Source windows are daily; analytic publication windows
are cumulative from the existing certified receipt. Contiguous checkpoint coverage
is required; no MIN/MAX across gaps. NULL remains unknown, requested differs from
fulfilled, fulfilled does not prove paid, and influence is not attribution.

READY means the installation contract is complete. ACTIVE/sync=true additionally
admits recurring dispatch. Neither establishes lifetime history. Daily ingestion
can extend facts coverage without changing `history_complete`.

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

## Still outside Product Go-Live

Backend automation does not deliver production HTTP authentication, public Read/Admin
API serving or cutover, frontend production binding, or client-facing deployment.
Those are separate Product Go-Live changes. The frontend demo and server-side preview
boundaries remain explicit until that rollout is authorized.
