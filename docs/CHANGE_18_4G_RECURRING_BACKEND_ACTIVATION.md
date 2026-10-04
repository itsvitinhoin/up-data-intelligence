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

The initial offline checkpoint preceded build/deployment. The operational record below
is authoritative for live progress; activation and scheduler enablement remain gated.

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

This was the pre-approval checkpoint. The approved Stage 1 was subsequently applied
and its acceptance evidence is recorded below. Operational completion is still pending.

### Approved Stage 1 — deployed and verified

The user explicitly approved the exact saved binary, including all three additional
metadata grants. Its SHA256 was rechecked immediately before apply and matched
`10159f053faea4b93e85849d2b663793661f8b0fcda18c88c6678406ad52c5a3`.
The original saved plan was applied exactly once, without regeneration or extra variables.
Exit 0: **5 added, 9 changed, 0 destroyed**. The complete apply output was captured
privately in Cloud Shell. Both immediate and final post-plans returned exit 0 / **No changes**.
All nine approved Jobs use the qualified `0157e83c…95f99a` digest. No Foundation Job
changed. The new Installation Scheduler exists and remains PAUSED.

Exactly one help-only smoke per updated Job succeeded:

| Job | Help execution | Result |
| --- | --- | --- |
| up-store-dispatcher | up-store-dispatcher-qhnms | SUCCESS |
| up-upzero-worker | up-upzero-worker-qlxfj | SUCCESS |
| up-meta-worker | up-meta-worker-kfdvs | SUCCESS |
| up-analytics-worker | up-analytics-worker-zdj2s | SUCCESS |
| up-intelligence-worker | up-intelligence-worker-gtv8t | SUCCESS |
| up-installation-orchestrator | up-installation-orchestrator-bmrvz | SUCCESS |
| up-installation-upzero-worker | up-installation-upzero-worker-rrhcr | SUCCESS |
| up-installation-meta-worker | up-installation-meta-worker-h87tc | SUCCESS |
| up-installation-analytics-worker | up-installation-analytics-worker-5wd6d | SUCCESS |

These executions used only `--help`: no source, secret-value or business IO.

### Global Installation no-op — passed

Inventory contained only MX and no onboarding operations. Global execution
`up-installation-orchestrator-kf4tg` used explicit
`--dispatch --all-stores --auto-activate`, parallel/store/dispatch limits all 1,
page budget 20 and soft budget 600 seconds. It completed successfully at
`2026-10-04T02:09:23.057704Z`. Structured output proved `dispatches=0`.
No installation worker was launched by that execution, no plan/work unit was created,
and no onboarding operation was changed.

Server-side full-row fingerprints before/after were identical for Registry,
installation plans/work units, checkpoints, sync runs, onboarding and Analytics
publications. MX remains revision 9 / READY / sync=false. The plan is COMPLETE,
45/45 units COMPLETE, required progress 43/43 (100%, ETA 0), Installation State READY,
history_complete=false and facts_complete=true. Analytics generation 3 remains
`[2026-09-01,2026-10-03)`, as_of `2026-10-03T03:00:00Z`, publication
`daf35780acf6259b69ed7cb542db09d2a0799e1d03aed1a96dc3a71a6749d4d7`.
Legacy Facts remain completed at 429,911 records / 430 core pages under the original
run/checkpoint. Counts remain 132 checkpoints / 147 sync runs; zero pending RAW or
pending checkpoints. The canonical activation/configuration guard passed, and all
four normal eligible-store inventories were empty.

### Safety stop — normal dispatcher global lease

**BACKEND ACTIVATION STOPPED SAFELY — store_dispatch_global_lease_present**

The broader immediate pre-activation audit found the canonical normal Control Plane
lease. Installation/store leases are absent, but this existing object blocks normal
dispatch. It was not created by this change:

- Bucket: `up-data-intelligence-dev-876521886531-leases`.
- Key: `leases/1766ac512643efd281e46471d1cadbc43244d41c4a751c4d2571503510c7b47c`,
  verified using canonical `digest("store-dispatch-global")`.
- Generation: `1790967353906003`.
- Created/updated: `2026-10-02T18:55:53.975000+00:00`.
- Size: 36 bytes. **Body was not read. Object was not deleted or modified.**

Historical candidate metadata (temporal correlation, not exact ownership proof):

| Execution | Start UTC | Completion UTC | Result |
| --- | --- | --- | --- |
| up-store-dispatcher-zww44 | 2026-10-02T18:55:45.749367Z | 2026-10-02T19:56:22.153419Z | FAILED / NON_ZERO_EXIT_CODE |
| up-upzero-worker-97khw | 2026-10-02T18:55:59.749307Z | 2026-10-02T19:56:16.159085Z | FAILED |

Full candidate execution metadata was inspected. No matching structured terminal
application events or object storage audit entries were returned by the historical
queries (zero log entries returned for either historical candidate). Therefore exact
lease ownership/cause is not asserted. The current inventory inspected 13 Jobs and
147 executions, with no active execution; project-wide BigQuery running-job inventory
is empty. Durable MX evidence is complete and unchanged, including the recovered legacy
run/checkpoint and certified publication. Object age alone was not used as recovery proof.

`cloud_lease` intentionally does not expire on ambiguous outcomes or process death.
The current authorization does not permit automatic stale-lease deletion. Recovery
requires a separate ownership/outcome review and explicit generation-matched removal
scope, rechecking metadata immediately before any deletion. Never delete without a
precondition, never retry an unknown delete, and never silently adopt a new generation.

**Activation was not executed. No normal recurring pipeline was started. Stage 2 was
not generated or applied.** No rollback was needed: MX never left READY/sync=false.
All eight schedulers remain PAUSED:

| Scheduler | State |
| --- | --- |
| up-upzero-dispatch | PAUSED |
| up-meta-dispatch | PAUSED |
| up-analytics-dispatch | PAUSED |
| up-intelligence-dispatch | PAUSED |
| up-installation-dispatch | PAUSED |
| up-foundation-dev-sync | PAUSED |
| up-foundation-dev-reconcile | PAUSED |
| up-foundation-dev-quality | PAUSED |

There is no ambiguous outcome from a mutation performed in this round: Stage 1 and
the global no-op are proved complete. The historical lease remains an unresolved
recovery gate. Backend automation is **not** declared complete or enabled.

### Final checks at the safety boundary

After live Stage 1/no-op: full pytest **2,103 passed in 128.23s**; Ruff lint/format,
mypy (152 files), git diff-check, Terraform recursive fmt-check and validate passed.
Frontend: **230 tests / 21 files**, lint, typecheck, format-check and production build
passed (45 static pages). Offline E2E: onboarding **1 passed**; B2B/Installation
**11 passed**. Next-generated development type/config changes were restored to their
original repository content and typecheck/format-check were repeated. No generated
files, caches, credentials, raw metadata or customer data are included in Git.
The existing Terraform-preservation test now recognizes only the exact approved
Stage 2 paused-variable pair, preserving the Foundation baseline checks.

Safety: exact Stage 1 apply YES; unexpected IAM/infra NO; activation NO; normal
business workers NO; UP Zero/Meta API NO; secret-value read NO; manual RAW/CORE DML NO;
checkpoint/publication repair NO; MX replan NO; new secret version/credential change NO;
history_complete forced NO; any scheduler enabled NO. Stop before lease recovery,
activation, recurring processing and scheduler enablement.
