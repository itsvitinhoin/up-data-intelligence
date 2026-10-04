# CHANGE 18.4G — Recurring backend activation

## Scope and acceptance gates

This change preserves the completed MX installation plan and its 45 work-unit IDs.
It does not manufacture lifetime proof. `history_complete=false` remains unchanged.
Operational acceptance requires the manual normal Control Plane cycle to succeed,
a cumulative certified dashboard window, and exactly five approved schedulers enabled.
Until those live gates pass, the backend must not be described as activated.

## Recurring windows and cost

UP Zero and Meta use the previous closed local day. Analytics and Intelligence
resolve a valid Analytics HEAD and its linked completed RECEIPT. The receipt's
`report_from` is authoritative, including legacy HEADs with NULL report dates.
The next policy preserves that start and uses the new closed-day cutoff. Both
`report_to` and `as_of` must be nondecreasing. Missing or inconsistent publication
fails with `recurring_publication_required`; regression fails before publishing.

Example: `[2026-09-01,2026-10-03)` becomes `[2026-09-01,2026-10-04)`.
Repeating that cutoff keeps the same window. It never becomes a one-day HEAD.
Full refresh is retained to reduce semantic risk. Incremental read models/caching
are future optimizations, not part of this change. Query/execution ceilings remain
1 GiB / 128 GiB; source slices remain 20 pages / 600 seconds. No timeout increase.

UP Zero successful ingestion proves contiguous complete checkpoint/run evidence
and a fresh unfiltered Customers scan. Coverage stops at the first gap using the
shared `prefix` algorithm. Registry coverage is saved by CAS under the store lease.
Failures never advance it. An ambiguous Registry write retains the lease; no retry.

Meta Insights remain daily requests. Intelligence accepts their contiguous union
when store, connection, account snapshot and the complete Insights definition match,
ignoring only `since` and `until`. Each interval requires a completed linked run,
zero core failures and no pending RAW. Extra intervals outside the request are allowed.
Catalog freshness remains separately required. The evidence hash sorts the compatible
checkpoint set deterministically. Missing one day blocks publication.

## Automatic onboarding and activation

Explicit `--dispatch --all-stores --auto-activate` is the only global auto-activation
mode. Plan-only/create-plan/workers require single-store scope and confirmation.
Global onboarding preparation reads only bounded INSTALLING operations without plans,
orders deterministically, uses canonical Planner V2, and never creates duplicate plans.
Definitive invalid metadata receives a BLOCKED CAS receipt; other brands can proceed.
Ambiguous writes/launches stop and preserve durable outcomes rather than retrying.

Only complete plans, all complete work units, active required sources, certified
publication and complete source evidence can activate. A transaction CAS updates
Registry READY -> ACTIVE, sync false -> true, and the associated onboarding operation
INSTALLING -> READY/current_step ACTIVE. MX activation uses canonical StoreAdmin and
does not require a fabricated onboarding operation. Installation State remains READY
for a completed, healthy ACTIVE store, including later cumulative publications.

## Scheduler and IAM design

Both `control_plane_scheduler_paused` and `installation_scheduler_paused` default true.
The new `up-installation-dispatch` runs every minute with explicit global arguments.
The existing scheduler service account can invoke only the installation orchestrator,
not its workers. Global/store leases and durable reservation prevent concurrent work
on one store. Each tick adds bounded ledger queries and a no-op Job cost even when no
installation is pending; the frequency can be revisited after measured usage.

Necessary metadata grants are table scoped: UP Zero needs Registry write for coverage
CAS; the installation orchestrator needs onboarding-operation write for finalization
and Meta binding read for the activation guard. No new business table, dataset, secret,
service account, bucket, or Foundation scheduler change is required.

Stage 1 must deploy one digest to all five Control Plane and four Installation Jobs,
create the installation scheduler paused and only these necessary IAM bindings.
Stage 2 may change only `paused` on the four Control Plane dispatch schedulers and the
new installation scheduler. Foundation schedulers remain paused.

## Operational sequence / rollback

1. Audit clean source, live Registry/plan/work, sources/binding, HEAD/RECEIPT, pending
   RAW, executions, leases, all scheduler states and eligible-store inventory.
2. Run all offline checks. Commit clean source before one immutable image build.
3. Audit the saved Stage 1 plan JSON, hash the binary, apply once, require no changes.
4. Nine `--help` smokes; inventory onboarding; one global no-op test (zero dispatches).
5. Canonical StoreAdmin activation for MX, then sequential normal UP Zero, Meta,
   Analytics and Intelligence dispatcher runs with previous-closed-day and one store.
6. Verify cumulative dashboard, history-sensitive NULLs, READY installation and leases.
7. Audit an exact five-scheduler Stage 2 saved plan, hash, apply once; post-plan clean.
8. Stop. Do not claim a future cron has executed before observing it.

Any unknown mutation outcome stops globally. Reconcile durable metadata, Cloud Run
operations/executions and leases before another action. Never delete stale leases
without a separate ownership audit and generation-matched recovery authorization.
On definitive manual-cycle failure, keep all schedulers paused and use StoreAdmin
pause/validate to restore READY/sync=false after proving safety. No manual RAW/CORE,
checkpoint, or publication DML; no credential or Meta-binding edits.

## Validation record

Initial read-only audit: MX READY/revision 9/sync=false, complete plan 45/45,
required progress 43/43, pending RAW 0, 132 checkpoints and 147 sync runs.
Legacy Facts completed with the original run/checkpoint at 429,911 records/430 pages.
Both sources active; normal eligibility false. Runtime/schedulers remain unchanged.

Offline acceptance: 2,103 Python tests passed; Ruff lint/format and mypy (152 source
files) passed. Frontend: 230 tests, ESLint, TypeScript and Prettier passed. Next
production build passed outside the sandbox after the restricted attempt stalled.
Offline Playwright: onboarding 1/1 and B2B/Installation 11/11 passed using installed
Chrome. Terraform recursive fmt-check and validation passed (provider IPC needed
the unrestricted validation process). No suite failure was ignored.

Live build, deployment, activation and scheduler enablement are not yet performed.
Their exact evidence must be appended before operational completion is declared.

### Immutable build and audited Stage 1 plan

Runtime source commit: `79eaa98f5b70530607fa27ffd4a7276b193927ad`.
Qualified Cloud Build: `3c6045c3-5f92-4584-a842-eb6ee6b44692`, SUCCESS.
Build and Artifact Registry agree on
`sha256:0157e83cd704c12fe071c523d841faf8021bbc6c86570cd22002c5488395f99a`.
The build context contained 239 allowlisted files, no credentials or customer data.
Container smokes ran without network. The first build attempt
`6a93eb77-8c13-4da8-b623-b73f5c074a8d` failed definitively before publishing an image:
private staging permissions under umask 077 prevented the non-root container from
reading source files. Correcting staging readability and the private smoke entrypoint
resolved it; runtime source, Dockerfile and repository build configuration were unchanged.

The Stage 1 saved plan, `/tmp/mx-activation-18-4g/stage1.plan` in Cloud Shell, has SHA256
`10159f053faea4b93e85849d2b663793661f8b0fcda18c88c6678406ad52c5a3`.
An exact resource/path guard passed: nine image-only updates, five creates, no deletes
or replacements. Creates are the paused Installation Scheduler, its scoped invocation
binding and the three table-scoped metadata grants described above. All other resource
changes are absent; 36 provider-computed drift entries passed the existing benign-drift
allowlist. Because the three metadata grants exceed the initial two-create estimate,
explicit approval of this concrete saved plan was requested before apply.

Read-only preflight confirmed only MX in Registry, no onboarding operations, the
certified generation 3 window `[2026-09-01,2026-10-03)`, contiguous Facts coverage through
`2026-10-03T03:00:00Z`, and 33 compatible Meta Insights checkpoints. Existing Meta
catalog runs are complete but older than the requested cutoff; the normal Meta cycle
must refresh them before Intelligence preflight. The freshness guard is unchanged.

At this checkpoint, no Stage 1 apply, live smoke, activation, recurring cycle or
scheduler enablement has occurred. MX remains READY/sync=false and all seven existing
schedulers remain PAUSED. Operational completion is still pending.
