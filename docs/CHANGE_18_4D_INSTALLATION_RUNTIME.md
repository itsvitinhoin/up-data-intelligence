# CHANGE #18.4D — Installation runtime DEV

**Runtime provisioned; MX PLAN-ONLY BLOCKED — REVIEW REQUIRED.**

The seven-resource deployment and all four help smokes succeeded. The single MX
inspection stopped at source connection metadata validation, before calculating
a plan. No installation was initiated.

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
