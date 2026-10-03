# CHANGE #18.4D — Installation runtime DEV

**Latest continuation (#18.4D.3, authorized resumption): MX PLAN PERSISTED —
READY FOR FIRST CONTROLLED DISPATCH. The legacy MX lease was reconciled and
removed once with its exact generation precondition. One canonical create-plan
execution succeeded; the persisted plan matches the approved semantic hash.
No dispatch or business work unit was executed.**

The seven-resource deployment and all four help smokes succeeded. The single MX
inspection stopped at source connection metadata validation, before calculating
a plan. The subsequent explicitly authorized metadata diagnosis identified the
missing Meta connection. Its one repair transaction aborted before INSERT due to
timestamp precision loss in the inspection output. Those historical attempts are
retained below. The latest acceptance sprint is recorded at the end of this file.

## Baseline and scope

- Branch: `change-18-4d-installation-runtime`, created exactly from
  `79e962eea2dd3264a30cfa0bcbd077174e531836`.
- Project: `up-data-intelligence-dev`; region: `southamerica-east1`.
- Qualified Installation image:
  `southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:5e9b3d0752cd78abfabf580b39c69eedf487dd72b086c3e62f6f593ccc2288f0`.
- Existing Control Plane image remains
  `foundation@sha256:47e4ce9ecd849642950fecff6e0a6ab88756e9cba04c9729c20dacbcd9dfcd2e`;
  Meta secret version reference remains `1` (reference only, no value read).
- `dev.tfvars` only appends the three approved live inputs:
  `control_plane_image`, `control_plane_meta_secret_version`, `installation_image`.
- The existing Terraform preservation test permits only the exact additional
  lines; all original content and other existing Terraform files remain hashed
  against their earlier approved baseline.

## Validation and single gate

Terraform formatting and validate passed locally and in Cloud Shell.
`git diff --check` passed. **837 focused Installation/Terraform tests passed**.
The modified preservation test also passed after formatting; no frontend or full
application suite was needed because runtime source code is unchanged.

A single plan using only `-var-file=environments/dev.tfvars` was saved as
`/tmp/change18-4d-runtime.plan` (private Cloud Shell file, excluded from Git).
Its JSON has exactly **7 CREATEs, 0 updates, 0 deletes, 0 replacements**:

- `google_cloud_run_v2_job.installation_orchestrator[0]`
- `google_cloud_run_v2_job.installation_worker["upzero"]`
- `google_cloud_run_v2_job.installation_worker["meta"]`
- `google_cloud_run_v2_job.installation_worker["analytics"]`
- `google_cloud_run_v2_job_iam_member.installation_run["upzero"]`
- `google_cloud_run_v2_job_iam_member.installation_run["meta"]`
- `google_cloud_run_v2_job_iam_member.installation_run["analytics"]`

All four Jobs use the qualified digest, command
`python -m src.installation.cli`, and `max_retries=0`.
The three bindings use existing custom role
`projects/up-data-intelligence-dev/roles/upControlPlaneRun_dev` for
`up-install-orchestrator-dev@up-data-intelligence-dev.iam.gserviceaccount.com`,
scoped to the three worker Jobs. No existing Job, Scheduler, BigQuery table/schema,
other IAM grant or image is changed. Plan warnings: **0**.

The first JSON verifier used incorrect expected spellings for the existing role
and SA. These were corrected to the names in the unchanged Terraform source;
the same saved plan was then certified without running another plan.

The browser policy requires action-time confirmation for security-sensitive
access changes. The user explicitly confirmed applying only the audited saved plan once, with no
regeneration, extra variables or automatic retry. Its SHA256 is
`38a3c8ad493064635041e5c1ef2f0aff088b3fbe08f63cadb499fbf52c7ed8e7`.
The checksum was rechecked immediately before the single Terraform invocation.

## Authorized follow-up and stop boundary

After a successful single apply, perform one post-plan, verify the four Job images
and preserved existing runtime/Schedulers, and run each new Job once with only
`--help`. Inspect MX once via the orchestrator using `--plan-only --adopt` and the
explicit target `2026-10-03T03:00:00+00:00` (closure of 02 October in
`America/Sao_Paulo`). Preserve budgets of 1 GiB/query and 128 GiB/execution.

Source inspection confirms argparse handles `--help` before any external IO.
`--plan-only` reads registry/connection/checkpoint/run/publication metadata but
uses no lease and calls neither plan persistence nor worker dispatch.

Do not execute `create-plan`, dispatch, business workers, source APIs, secret-value
reads, BigQuery DML, checkpoint/RAW/CORE/publication/registry/connection mutation.
Do not create a PR or merge. Commit/push the consolidated change only after the
permitted deployment and inspection results have been recorded.


## Runtime deployment — completed

The saved plan was applied exactly once with no added variables or regenerated
pre-apply plan: **7 added / 0 changed / 0 destroyed; exit code 0; warnings 0**.
One post-plan used only `environments/dev.tfvars` and returned **No changes**,
exit code 0, warnings 0. All four Jobs have the exact qualified digest and the
expected Python Installation CLI command. The nine existing Job images remain
unchanged. Scheduler inventory and states are unchanged; Installation Schedulers
remain **0**.

A local guard-script syntax error was corrected before any Terraform apply was
invoked. Absence of both the apply-attempt marker and apply log was checked before
proceeding. This was not a failed or repeated Terraform apply.

## Four safe smoke executions — completed

Each Job was executed once with the complete argument override `--args=--help`,
using `--wait`. All four returned successful Completed conditions and zero failed
tasks. The argparse help path executes no source API, BigQuery query/DML,
Secret Manager read, lease reservation or dispatch.

| Job | Successful execution |
| --- | --- |
| `up-installation-orchestrator` | `up-installation-orchestrator-2dmm6` |
| `up-installation-upzero-worker` | `up-installation-upzero-worker-mjxzs` |
| `up-installation-meta-worker` | `up-installation-meta-worker-nhfk4` |
| `up-installation-analytics-worker` | `up-installation-analytics-worker-tjn28` |

The worker Jobs were used only for CLI help, not business processing. No default
Job arguments were executed. Deployment creates manual Jobs; it does not start
installation or enable a Scheduler.


## Plan-only submission syntax

The installed Cloud SDK uses `ArgList` plus `UpdateAction` for `--args` and rejects
repeated standalone values such as the store/confirmation ID or repeated budget
numbers. The initial separated `--flag,value` command exited locally with code 2
and produced no Execution JSON; no MX Cloud Run execution had been created.
The SDK's installed source was inspected read-only. The equivalent `--flag=value`
form avoids duplicate entries and preserves every approved argument/value.
No Job configuration was updated, and no runtime execution was retried.

The authorized override uses:

```bash
MX_ARGS='--plan-only,--adopt,--store-id=mx-fashion,--confirm-store=mx-fashion,--target-as-of=2026-10-03T03:00:00+00:00,--live,--project=up-data-intelligence-dev,--confirm-project=up-data-intelligence-dev,--project-number=876521886531,--location=southamerica-east1,--lease-bucket=up-data-intelligence-dev-876521886531-leases,--maximum-bytes-billed=1073741824,--maximum-total-bytes-billed=137438953472,--page-budget=20,--soft-time-budget-seconds=600,--max-parallel-stores=2,--max-stores=10,--max-dispatches=20'
gcloud run jobs execute up-installation-orchestrator \
  --project=up-data-intelligence-dev --region=southamerica-east1 \
  --args="$MX_ARGS" --wait --format=json
```

This records the command used for the single inspection, not authorization to
repeat it or execute `create-plan`.


## MX plan-only — blocked, no retry

The one actual Cloud Run inspection was:

- Execution: `up-installation-orchestrator-wtfbj`.
- Mode: `--plan-only --adopt`; store and confirmation: `mx-fashion`.
- Target: `2026-10-03T03:00:00+00:00`, the complete closure of 02 October 2026
  in `America/Sao_Paulo`.
- Query budgets: `1073741824` per query and `137438953472` total.
- Complete approved CLI arguments and the qualified image were verified against
  execution metadata; neither default dispatch nor worker mode was present.
- Result: Cloud Run `NonZeroExitCode`, one failed task; gcloud wait exit code 1.
- Exact safe event: `job_failed`, code `source_verification_required`,
  store `mx-fashion`.
- Three log entries were retrieved for this exact execution; none contained the
  stdout plan/units JSON. No runtime execution was repeated.

### What the blocker proves

The source metadata guard in `src/installation/cli.py` requires exactly one
`source_connections` row for the configured store/connection/system with status
`active` or `pending`. It raised before `Planner.calculate()`, in the enabled
source-validation loop. Thus the adoption planner was not reached.

The sanitized event does not identify the failing system or distinguish a
missing row, duplicate matching rows or an unacceptable status. It is not evidence
of an invalid API token: no token value was read and no source API was probed.
Do not infer UP Zero versus Meta, repair metadata, change credentials or retry
from this result. Those require the next explicit review.

### Requested adoption summary

| Field | Evidence / result |
| --- | --- |
| Plan ID / status / config hash / registry revision | Unavailable: no plan stdout produced |
| Total/required units, pipeline/resource/kind/status counts | Unavailable: graph not calculated; not zero workload |
| Legacy checkpoint/run adoption / LEGACY_RESUME | Unavailable: source validation stopped the flow before adoption |
| Existing coverage / gaps / pending RAW / needs_review / ambiguous states | Not assessed by planner; do not claim clean or empty |
| Estimated pages/records/daily windows/first date/final date | Unavailable; target argument above is verified |
| Publication milestones / certified coverage / first/final new publication | Unavailable; no publication operation executed |
| Progress numerator / denominator / percent | Unavailable (`null`), not 0% |
| Concrete blocker | `source_verification_required` |

**MX PLAN-ONLY BLOCKED — REVIEW REQUIRED**

Deployment is successful; the MX adoption gate is not approvable from this
inspection. The next review must resolve enabled-source connection metadata
without inferring the missing cause from a generic sanitized code.

## Operations deliberately not executed

```text
create-plan: NO
dispatch: NO
business worker: NO
UP Zero API: NO
Meta API: NO
Secret value read: NO
BigQuery DML: NO
lease reservation: NO
checkpoint/RAW/CORE/publication mutation: NO
registry/source connection mutation: NO
Installation Scheduler: NO
PR/merge: NO
```

Four worker/orchestrator smoke executions and one orchestrator read-only inspection
are the only Cloud Run executions in this change. The term business worker above
excludes the approved `--help` smoke. Infrastructure state/Job creation and
Cloud Run execution/log records are expected platform changes; no business-data
or installation-ledger mutation was performed.

Raw logs, execution metadata, Terraform state/plans and temporary helper files
remain private outside Git under `/tmp`. Only this sanitized consolidated report,
the three additive DEV inputs and the corresponding preservation-test adjustment
are published on `change-18-4d-installation-runtime`.

## Authorized metadata continuation — 03 October 2026

Baseline: `13b55000f2f0fc7305c138046f22c1daf3d028a2`, same branch,
initial working tree clean. This continuation explicitly permitted metadata-only
inspection, at most one guarded missing-row repair, one verification read and a
new plan-only inspection only after a successful repair/valid source inventory.
It did not authorize `create-plan`, dispatch or business processing.

### Canonical tables and diagnosis

The requested table names placed source connections/bindings in `up_ops`.
The existing active catalog and Terraform manifest instead place both in
`up_core`; the Installation runtime reads these canonical tables. No table was
created, moved or renamed. Registry remains `up_ops.store_runtime_config`.
All metadata queries filtered `store_id=@store` and selected only the permitted
fields, with a 1 GiB query ceiling. No secret value or customer data was read.

Registry is unique, `ACTIVE`, revision **3**, `sync_enabled=true`, with both
UP Zero and Meta enabled; capabilities remain B2B=true/B2C=false. Reporting
timezone/currency remain `America/Sao_Paulo`/`BRL`; history starts
`2026-09-01T00:00:00Z`.

| Source | Enabled | Expected connection | Rows found | Status | Result |
| --- | --- | --- | --- | --- | --- |
| UP Zero | true | `mx-fashion-upzero` | 1 | active | OK |
| Meta | true | `mx-fashion-meta` | 0 | absent | MISSING |

The only existing source row is the expected UP Zero connection, with a numeric
version-2 pinned secret reference. Its key matches the existing digest contract.
There is exactly one MX Meta binding. Store/connection/account/API version match
Registry, and its timezone/currency match as well. No duplicate, different-source
connection or migration row was found in the inspected MX source inventory.
The missing Meta source row explains the historical `source_verification_required`.

### One repair attempt; transaction aborted before INSERT

Repair performed: **NO**. Successful BigQuery data mutations: **0**.

One parameterized transaction attempted to insert only a Meta source row with
`store_id=mx-fashion`, `connection_id=mx-fashion-meta`, `source_system=meta`,
`secret_resource_name=NULL`, `status=pending`, and identical UTC creation/update
timestamps. The row key was generated by importing the existing
`src.utils.data.digest(["mx-fashion", connection_id])`; no alternate hash was used.

Before INSERT, ASSERTs checked unique Registry and every selected Registry field,
including revision, flags and connections; unique/exact Meta binding; unchanged
MX source inventory and exact UP Zero row; absence of Meta source/connection/key
collisions. No UPDATE, DELETE or credential change was included.

BigQuery job `bqjob_r3fe30809f582063c_000001a103538fad_1` failed with
`Query error: binding_changed at [6:1]`; CLI exit code **1**. This ASSERT precedes
the INSERT, so no INSERT was reached. The transaction was not repeated.

One subsequent combined metadata read confirmed unique Registry revision 3,
one UP Zero active row, zero Meta rows and one compatible Meta binding. Comparing
the initial binding result with an explicit `CAST(configured_at AS STRING)`
showed the sole representation difference:

```text
initial bq prettyjson: 2026-10-01 22:06:09
exact TIMESTAMP:       2026-10-01 22:06:09.917+00
```

The temporary repair helper used the first representation for exact timestamp
comparison. Losing its fractional seconds caused a false guard mismatch. This is
an inspection/repair-helper precision error, not evidence that the binding
actually changed or that the deployed Installation runtime is faulty. The
post-read verifies the Meta row is still absent. Any future newly authorized
repair must capture timestamps losslessly before constructing CAS parameters;
do not weaken the guard or silently retry the attempted transaction.

### Plan-only and adoption result

No new Cloud Run execution was submitted because repair did not complete and
the required Meta connection is still absent. Last actual MX inspection remains
`up-installation-orchestrator-wtfbj`, with `source_verification_required`.
Target remains `2026-10-03T03:00:00+00:00`; budgets remain 1 GiB/query and
128 GiB/execution. No image/runtime/registry change was made.

| Requested result | Current evidence |
| --- | --- |
| New plan execution / plan ID / status / config hash | Not available: new plan-only not submitted |
| Registry revision | 3, observed in both inspections |
| Total/required units and pipeline/resource/kind/status counts | Not calculated; unknown, not zero |
| LEGACY_RESUME, adopted checkpoints/runs, coverage, pending RAW | Not evaluated by adoption planner |
| needs_review / ambiguous legacy states | Unknown; not asserted absent |
| First/last workload date, daily windows, pages/records estimates | Unknown; only history start and requested target are known |
| Certified publication, new publication milestones/first/final | Not assessed |
| Progress numerator/denominator/percentage | Unknown (`null`) |
| Immediate blocker | Repair ASSERT `binding_changed` due to lost timestamp precision |
| Remaining runtime blocker | Missing `mx-fashion-meta` source row |

**MX PLAN-ONLY BLOCKED — binding_changed**

Stop boundary respected: no repair retry, new plan-only, create-plan, dispatch,
business worker, UP Zero API, Meta API, secret-value read, checkpoint/RAW/CORE
business-data/publication mutation, Terraform operation or deployment. The only
write attempt was the aborted source-metadata transaction; no source row was
created. Query job/log records and private `/tmp` audit files are expected
operational artifacts and are excluded from Git. Only this existing runbook is
updated for publication on the same branch.

Local documentation validation: `git diff --check` passed; the unchanged
Installation suite passed **88 tests** (`.venv/bin/pytest -q tests/installation`).
The publication diff contains only this runbook, no helper scripts, raw metadata,
credentials, state, plans or runtime changes.

## CHANGE #18.4D.2 — MX adoption acceptance sprint (2026-10-03)

**MX ADOPTION BLOCKED — `store_busy_or_lease_unavailable`.**
The metadata handoff and plan-only acceptance succeeded. The single authorized
create-plan attempt failed acquiring the existing MX store lease, before any
installation persistence. Stop without retry, lease deletion/reset or dispatch.
This is a category C ownership/evidence blocker, not an established code bug.

### Baseline, precheck and lossless pre-simulation

Local and Cloud Shell checkouts were on `change-18-4d-installation-runtime` at
`e282da0dcb6bc9e414b4d6f455608fc03ae7ee4c`, clean. No branch/reset or runtime code
change was needed. All four Installation Jobs retained image digest
`sha256:5e9b3d0752cd78abfabf580b39c69eedf487dd72b086c3e62f6f593ccc2288f0`.
The nine normal Control Plane/Foundation Jobs were preserved. The nine specified
Control Plane/Installation Jobs had no active executions before mutation.
All seven normal Schedulers were PAUSED; Installation Schedulers were absent.

Private `/tmp/mx-adoption-18-4d2` helpers captured authorized metadata only:
Registry, source connections, Meta binding, checkpoints/runs and certified
publication evidence. No customer row, RAW payload, credential or secret value
was captured. All queries used the existing budget guards: 1,073,741,824 bytes
per query, 137,438,953,472 per execution. Runtime limits stayed pages=20,
soft time=600s, parallel stores=2, max stores=10, max dispatches=20.
Target stayed `2026-10-03T03:00:00+00:00` throughout.

CAS timestamp inputs were INT64 `UNIX_MICROS`, including Registry updated_at,
UP Zero source created_at/updated_at and Meta binding configured_at. BigQuery
computed SHA256 fingerprints of JSON STRUCTs with timestamp microseconds for
Registry, UP Zero source, Meta binding and ordered MX source inventory. No
prettyjson timestamp was used as a CAS source. Meta row_key came directly from
`src.utils.data.digest(["mx-fashion", "mx-fashion-meta"])`.

Canonical adoption inspection saw 97 checkpoints and 111 runs: 33 complete
Orders, 29 complete Facts, 25 complete Customers, four recovered Customers,
one running Facts checkpoint, and five complete legacy Meta resource checkpoints.
There was no needs_review, ambiguous adoption or ignored pending RAW.
The pre-simulation changed only sync_enabled to false in memory, retaining
ACTIVE/revision 3. It used canonical `Planner.calculate(adopt=True)`, adoption
inspection and publication availability. Result: RUNNING, 45 units, no blocker.
The completed pre-simulation ledger settled 31,457,280 billed bytes for ten
queries; that figure is not a total for every read in the sprint.

Temporary helper corrections handled DATE serialization, scheduler name matching
and canonical JSON comparison of tuple/list representations. None changed the
runtime, planner guards or historical evidence. There was no code fix, build,
image update, Terraform operation, redeploy or new help smoke in this sprint.

### Single guarded metadata handoff — committed

BigQuery job:
`mx_handoff_d835333aaf69024ce3cf7e95bc09b28669cfe31c2b60f68f7eda42883c7bec54`.

One transaction checked exact unique rows, lossless timestamp guards, server-side
fingerprints and source inventory. It asserted Registry revision 3/ACTIVE/sync
true and the approved flags/connection IDs; exact active UP Zero connection;
exact compatible Meta binding; zero Meta source; and absence of connection,
row-key, duplicate-source and cross-store collisions before any write.

The transaction inserted exactly one `up_core.source_connections` row for
`mx-fashion-meta`, source meta, status pending, secret_resource_name NULL.
It updated exactly one Registry row: sync_enabled=false, revision=4, updated_at.
One server-side repair_at timestamp was shared by that update and both new
source timestamps. Row-count ASSERTs guarded each write; no retry occurred.

| Metadata | Before | Verified after handoff and failed create-plan |
| --- | --- | --- |
| Registry | revision 3 / ACTIVE / sync true | revision 4 / ACTIVE / sync false |
| UP Zero | 1 active source | 1 active source, identical fingerprint |
| Meta | 0 source rows | 1 pending source, secret reference NULL |
| Meta binding | 1 compatible row | 1 row, identical fingerprint |
| Installation plans/work units | 0 / 0 | 0 / 0 |

All other Registry fields were identical, including history_complete=false.
Canonical `eligible("upzero"/"meta"/"analytics"/"intelligence")` returned false
for all four pipelines after handoff, and again at final reconciliation.

### Accepted plan-only and semantic audit

Only one post-handoff plan-only execution was submitted:
`up-installation-orchestrator-sbwrb`, exit 0. Its exact args, budgets, fixed target
and immutable image matched the approved invocation. This path performed no
persistence, source API, source probe, dispatch or work-unit execution.

| Plan field | Value |
| --- | --- |
| plan_id | `67ac3f1baed4d7fc8ea055a6c90c265a4a7f4b4b1b21c21d37d983c77fc04a15` |
| status / registry revision / planner_version | RUNNING / 4 / 1.0.0 |
| config_hash | `2e91000a8c229e772a1f1d86bf63f445fd4359a2bad09bf7c73e23fce9048c38` |
| semantic_plan_sha256 | `b0c522d697abbd9640170ab36a2348fbb365271325909c221ad1aa35a781975a` |
| units / required / optional | 45 / 43 / 2 |
| logical progress | CHUNKS, 0 complete / 43 required, 0% |
| eta_seconds | null; no three comparable completed logical units |
| legacy records / pages | 344,000 / 344, separate from logical progress |

The semantic hash used the canonical digest and the requested plan fields plus
unit fields ordered by work_unit_id, excluding created_at/updated_at. It also
excluded nested adopted_coverage.publication.snapshot_at: this field is the
volatile metadata-read instant attached by `available()`, not the certified
receipt's as_of. Publication ID, generation, policy and report window remained
included. This normalization was applied only to the private audit signature;
neither plan/evidence nor runtime comparisons were modified.

| Source / pipeline | Units |
| --- | ---: |
| upzero | 5 |
| meta | 38 |
| analytics | 2 |

| Resource | Units |
| --- | ---: |
| verification | 2 |
| analytics_facts | 2 |
| customers | 1 |
| orders | 1 |
| accounts / campaigns / adsets / ads | 1 each |
| insights | 33 |
| publication | 2 |

| Unit kind | Units |
| --- | ---: |
| VERIFY_SOURCE | 2 |
| LEGACY_RESUME | 1 |
| SYNC_SNAPSHOT | 1 |
| SYNC_WINDOW | 2 |
| META_CATALOG | 4 |
| META_INSIGHTS | 33 |
| PUBLISH_ANALYTICS | 2 |

All 45 units were PENDING. All acceptance checks passed: present config hash,
exactly one pending-Facts LEGACY_RESUME, unchanged refs/filters, no overlap or
ambiguous evidence, no ignored pending RAW, reused completed coverage, Meta
planning without an API call, and coherent publication milestones.

### Legacy adoption, coverage and publication

The single analytics_facts LEGACY_RESUME preserved:

- run_id `0264739c-d3c6-4984-b88e-74fb5554bd58`;
- checkpoint_plan_key `9a1ab3d71e25c60c73f0edc40c8e10af4dc7e867fc01cfb142726ea33fd2fbec`;
- mode incremental and original filters: from `2026-09-01T00:00:00+00:00`,
  to `2026-10-02T03:00:00+00:00`, limit 1000;
- persisted counters 344,000 records / 344 pages;
- cursor ownership through the unchanged checkpoint; cursor not disclosed;
- pending_raw_id null; no RAW envelope skipped or deleted.

Four historical recovered Customers did not cause replay and did not certify
freshness. The plan contains one Customers SYNC_SNAPSHOT (incremental, limit 200).

| Adopted evidence | Contiguous union, half-open UTC interval | New gap only |
| --- | --- | --- |
| Orders: 33 complete intervals | `[2026-08-31T03:00Z, 2026-10-02T03:00Z)` | local 02 October, start_date=end_date=2026-10-02 |
| Facts: 29 complete intervals | `[2026-09-01T00:00Z, 2026-09-29T00:00Z)` | `[2026-10-02T03:00Z, 2026-10-03T03:00Z)` after the legacy pending interval |

These are unions checked for gaps, not MIN/MAX across missing coverage. The
legacy pending Facts interval was not declared complete. No new analytics_facts
window overlapped it. New UP Zero daily windows start/end on local 02 October.
The 33 Meta insights daily windows run from the partial first local day,
31 August, through 02 October; they do not establish historical completeness.

Certified existing HEAD/RECEIPT remained generation 1, policy hash
`3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c`, publication
`6a70891ac41d0cc2a8441888aa31b7f41ed6835fbc4728c2b06dadbe2c559d74`.
Its report window remains `[2026-09-01, 2026-09-28)` (local 01–27 September),
as_of `2026-09-28T03:00:00Z`. No publication was altered or executed.
Existing certified milestones were reused; two future publication units remain:

1. report_from 2026-09-01, exclusive report_to 2026-09-29,
   as_of 2026-09-29T03:00Z, facts_complete=false.
2. report_from 2026-09-01, exclusive report_to 2026-10-03,
   as_of 2026-10-03T03:00Z, facts_complete=true.

These flags describe planned units only; no stored coverage was changed.

### One create-plan attempt — lease blocked, no persistence

The pre-create combined read verified revision 4/ACTIVE/sync false, exact source
and binding fingerprints, zero MX plans, unchanged checkpoints/runs and the same
adoption evidence. Source inspection confirmed create-plan does not probe sources,
run workers, mutate checkpoints/RAW/CORE/publication or dispatch. Its canonical
path acquires global and store leases before calculating and persisting a plan.

The single authorized execution `up-installation-orchestrator-xpsg2` used the
same target/budgets/digest and `--create-plan --adopt`. It exited 1 with structured
`job_failed`, code `store_busy_or_lease_unavailable`. No retry was submitted.

Read-only reconciliation confirmed exactly zero MX installation_plans and zero
installation_work_units. Registry stayed revision 4/ACTIVE/sync false; expected
canonical revision 5/DRAFT was not reached. Consequently there is no persisted
plan ID/signature comparison or persisted INSTALLING/CHUNKS state to report.
The accepted in-memory plan remains the evidence above, not a persisted plan.

Object metadata only (not lease contents) showed an existing MX lease in bucket
`up-data-intelligence-dev-876521886531-leases`:

- key `leases/fa7e7671aca22a7663014f31f0124d4f70f4401aafea3afa5e895359e6f850c5`;
- generation `1790967367875706`, size 36 bytes;
- created/updated `2026-10-02T18:56:07.883000+00:00`;
- global Installation lease absent after the failed execution.

Existing bucket IAM and the unchanged lease-writer role were read, not changed.
The canonical global coordination lease can be acquired/released by create-plan;
this does not mean the pre-existing MX lease was removed or reset. No such
cleanup was performed. The helper maps acquisition errors to the safe code above;
its collision evidence does not establish the previous owner's outcome or prove
a lease abandoned merely from age. Lease recovery requires a separate ownership
and outcome audit/authorization; do not delete it automatically.

Final checks found no active execution in the three legacy Foundation Jobs either.
The referenced Facts sync_run still records running, 344,000 records/344 pages,
zero failed records; an operational execution's absence does not turn that
historical run into completed. All 97 checkpoints and 111 sync_runs were unchanged.
All 13 Job specs were identical; all seven Schedulers remained PAUSED and
Installation Schedulers remained absent.

### Safety, tests and publication boundary

UP Zero API: NO. Meta API: NO. Secret value read: NO. Business workers: NO.
Dispatch: NO. RAW mutation: NO. CORE business-data mutation: NO. Checkpoint
mutation: NO. Sync-run mutation: NO. Publication mutation: NO.
history_complete changed: NO. Normal scheduler state changed: NO.
The sole committed business-metadata transaction was the authorized handoff:
one source metadata INSERT and one Registry UPDATE. The canonical create-plan
attempt failed before its persistence transaction. No image/IAM/Terraform change.

Local validation of the unchanged runtime:

- `.venv/bin/pytest -q tests/installation`: **88 passed**, 15.79s.
- `.venv/bin/pytest -q`: **2052 passed**, 127.10s.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: **270 files already formatted**.
- `.venv/bin/mypy src`: passed, **150 source files**.
- `git diff --check`: passed after this documentation update.

Only this runbook is published; private helpers, snapshots, logs and screenshots
remain outside Git. No credentials, customer data, Terraform state/plan or cache
is included. Same branch, a separate documentation commit, no PR or merge.
Stop before lease recovery, another create-plan attempt or any dispatch.

## CHANGE #18.4D.3 — initial access gate (2026-10-03)

**MX ADOPTION BLOCKED — `cloud_session_authorization_required`.**
This label identifies the local access/approval gate, not a SafeError emitted by
Cloud Run. No ownership determination or lease recovery was made this round.

### Confirmed local baseline and access blocker

The checkout was exactly `change-18-4d-installation-runtime`, HEAD
`7557efeed9e728a8bd4f3dd2c329e322ac92e397`, clean. No branch switch or reset.
No runtime, frontend, policy, schema, Terraform or image file changed.

The previous Cloud Shell browser tab was no longer available. A new tab for the
specified DEV project opened under a different signed-in Google session. The
automatic approval review rejected switching to the previously used UP session
because the current request did not explicitly identify/authorize that account.
Explicit authorization was requested and remained pending. No workaround,
alternative credentials or cloud SDK operation was used to bypass the rejection.

Opening the Cloud Shell UI is not evidence of successful project access. No GCP
metadata query, execution listing, lease metadata GET/body read, business-data
read, delete, create-plan or Terraform operation was performed in this round.

### Recovery/persistence gates remain unexecuted

The approved historical lease key/generation, Registry revision 4, 97 checkpoints,
111 runs, zero plans/work units and accepted semantic plan signature are retained
in the preceding section as historical evidence only. They are not a substitute
for current reconciliation. No claim is made that the lease is currently orphaned,
absent or safe to delete, or that current execution/scheduler state is unchanged.

After session access is explicitly authorized, the remaining sequence is:

1. Audit full candidate execution metadata around 2026-10-02 18:45–20:15Z,
   including the five normal workers/dispatcher and applicable Foundation Jobs.
2. Reconcile current executions, seven PAUSED Schedulers/no Installation
   Scheduler, Registry/source/binding, zero plans/units and exact legacy
   run/checkpoint evidence against the private previous snapshot. Stop if any
   ownership/outcome or business-state criterion cannot be proved.
3. Re-read lease metadata immediately before the only authorized deletion.
   Require generation `1790967367875706`, canonical MX key and unchanged
   creation/update time. Use that exact generation precondition, never a generic
   delete, body read, expiry assumption or automatic retry.
4. Reconcile absence of MX/global leases; repeat pre-create state/image guards.
   Submit create-plan once with the fixed approved target and budgets.
5. Reconcile persisted plan/45 PENDING units/Registry and compare the approved
   semantic signature, preserving legacy IDs, filters, counters and checkpoints.
   Read the actual Installation State without forcing INSTALLING; audit final
   leases and unchanged certified window/history/coverage.
6. Stop before dispatch or any business worker. Any unknown outcome stops retries.

No new create-plan execution/exit, persisted signature, current Registry,
Installation State or lease-delete outcome exists to report for #18.4D.3.
These remain unverified rather than defaulting to the expected values.

### Local validation and publication

- `.venv/bin/pytest -q tests/installation`: **88 passed**, 16.75s.
- `.venv/bin/pytest -q`: **2052 passed**, 133.87s.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: **270 files already formatted**.
- `.venv/bin/mypy src`: passed, **150 source files**.
- `git diff --check`: passed after this documentation update.

UP Zero API: NO. Meta API: NO. Secret value read: NO. Dispatch: NO.
Business workers: NO. RAW mutation: NO. CORE business mutation: NO.
Checkpoint mutation: NO. Sync-run mutation: NO. Publication mutation: NO.
history_complete changed: NO. Schedulers changed: NO. Terraform: NO.
Lease delete: NO. Create-plan attempt: NO.

Only this existing runbook is committed/pushed on the same branch. No private
metadata, lease body, credentials, state/plan, temporary artifact, PR or merge.
Stop at the session-authorization gate; lease recovery is not yet certified.

## CHANGE #18.4D.3 — authorized lease recovery and plan persistence

**MX PLAN PERSISTED — READY FOR FIRST CONTROLLED DISPATCH.**
The user subsequently authorized the intended UP Google session. The earlier
access rejection was resolved through that authorization, without a workaround.
This section supersedes the initial access-gate outcome, preserving its history.

### Baseline, runtime and ownership reconciliation

The local and Cloud Shell checkouts remained on
`change-18-4d-installation-runtime`, HEAD
`717a53a3dbe8d04e92dff025116c0b27deeb181e`, clean. This is the documentation-only
continuation of required baseline `7557efeed9e728a8bd4f3dd2c329e322ac92e397`;
only this runbook differs. No branch switch, reset or runtime modification.

All 13 Cloud Run Job specs matched the preceding audit. All four Installation
Jobs retained digest
`sha256:5e9b3d0752cd78abfabf580b39c69eedf487dd72b086c3e62f6f593ccc2288f0`.
The execution inventory covered all nine required normal/Installation Jobs and
three existing Foundation Jobs. None was active immediately before recovery.
Seven existing Schedulers were PAUSED; Installation Schedulers were absent.

Full candidate execution metadata in the historical 18:45–20:15Z window showed:

| Execution | Start (UTC) | Completion (UTC) | Terminal evidence |
| --- | --- | --- | --- |
| `up-store-dispatcher-zww44` | 2026-10-02 18:55:45.749367 | 2026-10-02 19:56:22.153419 | failedCount=1, Completed=False, NonZeroExitCode |
| `up-upzero-worker-97khw` | 2026-10-02 18:55:59.749307 | 2026-10-02 19:56:16.159085 | failedCount=1, Completed=False, configured timeout reached |

The worker args identified MX/upzero. Its structured sync_started event at
18:58:17.856944Z identified legacy run
`0264739c-d3c6-4984-b88e-74fb5554bd58`. The dispatcher subsequently emitted
`worker_execution_outcome_unknown` at 19:56:19.160045Z. This connects the preserved
lease to an ended legacy attempt and its ambiguous dispatcher result; it does
not infer ownership merely from object age or a lease UUID.

All 479 BigQuery write job IDs recorded by that worker were reconciled through
job metadata: DONE, zero errors, zero pending/running jobs. There were no
INSERT/UPDATE/DELETE/MERGE/SCRIPT jobs after the preceding reconciliation cutoff
2026-10-03T20:43:09.121039Z and before this round's authorized persistence.
The full 97 checkpoint rows and 111 sync-run rows matched the private preceding
snapshot, including the legacy run/checkpoint, filters, mode and cursor ownership.
Source connections and Meta binding also matched. No customer rows, RAW payload,
secret value or query text was fetched for this audit.

Before recovery: Registry revision 4/ACTIVE/sync_enabled=false, zero MX plans and
zero MX work units. UP Zero remained active, Meta pending with secret reference
NULL, and the binding unchanged. All four normal pipeline eligibility checks
were false. Canonical read-only planning reproduced the approved plan/hash before
recovery; no code fix, build, image update or Terraform action was required.

### Generation-guarded recovery

Only metadata was read for the canonical `digest("mx-fashion")` object:

- Bucket: `up-data-intelligence-dev-876521886531-leases`.
- Key: `leases/fa7e7671aca22a7663014f31f0124d4f70f4401aafea3afa5e895359e6f850c5`.
- Generation: `1790967367875706`.
- Creation/update: `2026-10-02T18:56:07.883000+00:00`; size 36 bytes.

A fresh metadata GET immediately before deletion confirmed that exact generation,
creation/update time and size. SDK deletion ran once with
`if_generation_match=1790967367875706`, `retry=None`, timeout 30 seconds.
Result: SUCCESS. Subsequent metadata GETs proved both the MX lease and the global
Installation lease absent. No body/UUID was read and no other lease was removed.
Recovery rested on terminal executions, settled writes, unchanged durable
business evidence, paused schedulers and no current owner, not automatic expiry.

### Single canonical create-plan and reconciliation

Fresh pre-create reads proved revision 4/ACTIVE/sync=false, zero plans/units,
exact UP Zero/Meta source and binding metadata, unchanged legacy evidence,
absent leases and unchanged runtime Job specs.

The one authorized create-plan execution was
`up-installation-orchestrator-pf4bk`, exit 0, succeededCount=1, Completed=True
(start 2026-10-03T21:39:54.740865Z, completion 21:40:21.227431Z). It used the existing immutable
Installation image, explicit `--create-plan --adopt`, MX store/confirmation,
fixed target `2026-10-03T03:00:00+00:00`, DEV project/confirmation/number/region,
and the approved lease bucket. Budgets remained 1,073,741,824 bytes/query,
137,438,953,472 bytes/execution, pages 20, soft time 600s, parallel stores 2,
max stores 10 and max dispatches 20. No --dispatch or implicit business mode.

The canonical create transaction
`installation_bac237425380e75d43623a12387f353862fe5d05536a8647fe853b07c0d9e71f`
and its child statements were DONE without errors. Its source code and job
metadata limit writes to Registry, installation_plans and installation_work_units.
No automatic repetition occurred.

| Persisted identity | Verified value |
| --- | --- |
| Plan ID | `67ac3f1baed4d7fc8ea055a6c90c265a4a7f4b4b1b21c21d37d983c77fc04a15` |
| planner_version | `1.0.0` |
| config_hash | `2e91000a8c229e772a1f1d86bf63f445fd4359a2bad09bf7c73e23fce9048c38` |
| semantic_plan_sha256 | `b0c522d697abbd9640170ab36a2348fbb365271325909c221ad1aa35a781975a` |
| Plan status / Registry revision | RUNNING / 5 |
| Plans / total / required / optional units | 1 / 45 / 43 / 2 |
| Unit state | all 45 PENDING, attempt_count=0, execution_name/dispatch_token=NULL |

The same semantic normalization as the accepted plan-only excluded created_at,
updated_at and adopted publication snapshot_at only. Full normalized plan/unit
comparison also matched IDs, sources/resources/kinds, original filters,
dependencies, required flags and legacy references. No missing or added unit.

| Source | Units |
| --- | ---: |
| upzero | 5 |
| meta | 38 |
| analytics | 2 |

| Kind | Units |
| --- | ---: |
| VERIFY_SOURCE | 2 |
| LEGACY_RESUME | 1 |
| SYNC_SNAPSHOT | 1 |
| SYNC_WINDOW | 2 |
| META_CATALOG | 4 |
| META_INSIGHTS | 33 |
| PUBLISH_ANALYTICS | 2 |

Resource counts: verification 2, analytics_facts 2, customers 1, orders 1,
accounts 1, campaigns 1, adsets 1, ads 1, insights 33, publication 2.
The only LEGACY_RESUME remains the exact Facts run/checkpoint recorded above:
344,000 records, 344 pages, pending_raw_id=NULL; incremental mode and original
filters/cursor ownership preserved. No new Facts window overlaps its pending
interval. The four recovered Customers neither caused replay nor established
freshness; the one Customers snapshot remains planned.

Orders reuse the 33 complete intervals, contiguous union
[2026-08-31T03:00Z, 2026-10-02T03:00Z), with only local 02 October newly planned.
Facts reuse the 29 complete intervals, contiguous union
[2026-09-01T00:00Z, 2026-09-29T00:00Z). The pending legacy Facts work is preserved;
the sole new gap is [2026-10-02T03:00Z, 2026-10-03T03:00Z). These are checked
unions, not MIN/MAX across gaps. Meta retains one VERIFY_SOURCE, four catalog
units and 33 insights units (partial local 31 August through 02 October), all
unexecuted.

Existing certified generation 1, policy/publication IDs and the local
[2026-09-01, 2026-09-28) window above were revalidated unchanged through canonical
HEAD/RECEIPT/coverage reads. Both future publication milestones above matched:
exclusive report_to 29 September/facts_complete=false and 03 October/true.
Neither was published; planned coverage does not modify stored coverage.

### Final Registry, Installation State and immutability

| Field | Before | After |
| --- | --- | --- |
| revision | 4 | 5 |
| status | ACTIVE | DRAFT |
| sync_enabled | false | false |
| analytics_enabled | true | true |
| history_complete | false | false |

Only revision, status and updated_at changed in the full Registry comparison.
Analytics was already enabled, so it was preserved rather than counted as a
change. All other fields, sources and Meta binding matched exactly. UP Zero
remained active and Meta pending with secret_resource_name=NULL.
StoreConfig eligibility for upzero/meta/analytics/intelligence is false for all.

Canonical InstallationReader, using an explicitly scoped administrative local
audit principal, returned the actual state PARTIAL, plan RUNNING, CHUNKS 0/43
(0%), ETA null. Separately it reports 344,000 legacy records and 344 pages.
Available window remains local 01–27 September (exclusive report_to 28 September),
history_complete=false. No state was forced to INSTALLING and no claim of new
coverage or progress was made.

Checkpoint count remained 97 -> 97; sync-run count 111 -> 111. Full row digests
matched, including legacy IDs, filters, mode, pending RAW and cursor ownership.
Both MX and global Installation leases were absent after completion.
The final inventory again proved zero active executions, seven PAUSED Schedulers
and no Installation Scheduler. Comparing inventories showed exactly one new
execution, the orchestrator create-plan, and no new normal/Foundation/Installation
business worker execution. All 13 Job specs remained identical; execution args
and the image digest exactly matched the approved submission.

### Validation, safety and stop boundary

The unchanged runtime was validated during the initial part of this same change:
Installation suite 88 passed (16.75s); full suite 2052 passed (133.87s);
Ruff passed; formatting check 270 files already formatted; mypy passed for 150
source files. No runtime code changed during this resumption. Private audit
helpers were corrected for Registry expectations (analytics already true) and
local principal composition; they did not change source code or durable evidence.
Git diff whitespace validation is repeated for this documentation-only update.

UP Zero API: NO. Meta API: NO. Secret value read: NO. Dispatch: NO.
Business workers: NO. RAW mutation: NO. CORE business mutation: NO.
Checkpoint mutation: NO. Sync-run mutation: NO. Publication mutation: NO.
history_complete changed: NO. Schedulers changed: NO. Terraform: NO.

Only the reconciled generation-matched legacy lease deletion and the canonical
create-plan metadata transaction were performed. No source probe, business
worker, image/build/deploy, repeated create-plan or other recovery mutation.
Private snapshots/logs/helpers and screenshots remain outside Git. Only this
runbook is committed/pushed on the existing branch, no PR or merge.
**STOP: do not dispatch or execute a business work unit in this change.**
