# CHANGE #18.4B — DEV Metadata/IAM Provisioning

## Summary and decision

**PROVISIONING CLEAN — READY FOR IMAGE QUALIFICATION**

One authorized saved-plan apply completed successfully: **32 added, 0 changed,
0 destroyed**. The post-apply plan returned **exit code 0 / no changes**.
Only metadata tables, one service account and the approved IAM bindings were
provisioned. This is not an MX Fashion installation or activation.

## Baseline and environment

- Exact baseline: `cb7905d79009d9dbf528d3f1dcb4e222505a7155`.
- Branch: `change-18-4b-dev-metadata-iam-provisioning`, created from that baseline.
- Initial working trees: clean, locally and in the authorized Cloud Shell.
- Project identity verified: `up-data-intelligence-dev`, number `876521886531`.
- Region/location: `southamerica-east1`.
- Terraform: `1.16.4`; workspace: `default`.
- Backend: `gs://up-data-intelligence-dev-876521886531-tfstate/foundation/dev/default.tfstate`.
- State before/after: **303 / 335** resources.
- Verification completed: `2026-10-03T04:54:45Z`.

Terraform, tfvars, schemas, Python, frontend and all existing image references
were preserved. Git changes are limited to this runbook and the appended
[authorized #18.4A continuation](CHANGE_18_4A_DEV_TERRAFORM_PLAN_AUDIT.md#authorized-cloud-shell-continuation).

## Pre-apply plan and exact allowlist comparison

A fresh #18.4B plan was generated; the historical #18.4A plan was not applied.

```bash
CONTROL_PLANE_IMAGE='southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:47e4ce9ecd849642950fecff6e0a6ab88756e9cba04c9729c20dacbcd9dfcd2e'
terraform -chdir=infra/terraform plan \
  -input=false -no-color -lock-timeout=60s \
  -var-file=environments/dev.tfvars \
  -var="control_plane_image=${CONTROL_PLANE_IMAGE}" \
  -var='control_plane_meta_secret_version=1' \
  -out=/tmp/change18-4b-dev.plan -detailed-exitcode
```

Result: **exit code 2; 32 add / 0 change / 0 destroy / 0 replacement**.
Material actions were extracted from saved-plan JSON and compared by exact
set equality with all 32 approved addresses below, including their `create`
action. The sorted expected/actual comparison had **no diff**.

```text
google_bigquery_table.tables["installation_plans"]
google_bigquery_table.tables["installation_work_units"]
google_bigquery_table.tables["onboarding_operations"]
google_bigquery_table.tables["workspace_store_bindings"]
google_bigquery_table_iam_member.installation["analytics/read/installation_plans"]
google_bigquery_table_iam_member.installation["analytics/read/installation_work_units"]
google_bigquery_table_iam_member.installation["analytics/write/installation_work_units"]
google_bigquery_table_iam_member.installation["meta/read/installation_plans"]
google_bigquery_table_iam_member.installation["meta/read/installation_work_units"]
google_bigquery_table_iam_member.installation["meta/write/installation_work_units"]
google_bigquery_table_iam_member.installation["meta/write/source_connections"]
google_bigquery_table_iam_member.installation["orchestrator/read/analytics_funnel_daily"]
google_bigquery_table_iam_member.installation["orchestrator/read/analytics_publications"]
google_bigquery_table_iam_member.installation["orchestrator/read/analytics_store_daily"]
google_bigquery_table_iam_member.installation["orchestrator/read/installation_plans"]
google_bigquery_table_iam_member.installation["orchestrator/read/installation_work_units"]
google_bigquery_table_iam_member.installation["orchestrator/read/onboarding_operations"]
google_bigquery_table_iam_member.installation["orchestrator/read/source_connections"]
google_bigquery_table_iam_member.installation["orchestrator/read/store_runtime_config"]
google_bigquery_table_iam_member.installation["orchestrator/read/sync_checkpoints"]
google_bigquery_table_iam_member.installation["orchestrator/read/sync_runs"]
google_bigquery_table_iam_member.installation["orchestrator/write/installation_plans"]
google_bigquery_table_iam_member.installation["orchestrator/write/installation_work_units"]
google_bigquery_table_iam_member.installation["orchestrator/write/store_runtime_config"]
google_bigquery_table_iam_member.installation["upzero/read/installation_plans"]
google_bigquery_table_iam_member.installation["upzero/read/installation_work_units"]
google_bigquery_table_iam_member.installation["upzero/write/installation_work_units"]
google_bigquery_table_iam_member.installation["upzero/write/source_connections"]
google_project_iam_member.installation_poll
google_project_iam_member.installation_query
google_service_account.installation_orchestrator
google_storage_bucket_iam_member.installation_lease
```

Explicit guards confirmed zero update/delete/replacement, zero Installation
Job instances, zero Scheduler material action, and `installation_image=null`.
Neither tfvars nor the shell supplied an Installation image. The five existing
Control Plane Jobs had the same approved digest before/after; all four Control
Plane Scheduler plans remained paused with their existing schedules.

## Authorized apply and state verification

The user confirmed application of this exact audited saved plan. Its recorded
SHA-256, checked again before application, was:

```text
7b41c70d9ef13d201f6c4803547dabb5ee0949aa93a34a90f05a5865ded21e399
```

An initial pre-command checksum guard stopped because its manually transcribed
comparison literal was incorrect. No Terraform apply command ran at that point.
The actual file checksum matched the recorded audit checksum, and the exact
32-address comparison still passed. The guard was corrected to compare directly
with the recorded checksum; the plan file was neither regenerated nor changed.

The following apply ran **once**, with no variables, implicit replanning or retry:

```bash
terraform -chdir=infra/terraform apply \
  -input=false /tmp/change18-4b-dev.plan
```

- Apply exit code: **0**.
- Terraform result: **32 added, 0 changed, 0 destroyed**.
- Creation completion records: **32**.
- State set comparison: before was a subset of after; exactly the authorized
  32 addresses were added, with **zero removed**.
- No provisioning failure or recovery apply occurred.

## BigQuery metadata verification

Only `bq show` metadata reads were performed; no query or business row read.
Schemas were compared with the versioned schema files, including field order,
name, type, mode and nested fields. The API represents the equivalent schema
aliases `INT64/INTEGER`, `FLOAT64/FLOAT` and `BOOL/BOOLEAN` differently; the
comparison canonicalized those aliases without editing any schema.

| Table in `up_ops` | Columns | Clustering | Partition | Metadata row count |
| --- | ---: | --- | --- | ---: |
| `installation_plans` | 17 | `store_id,status` | None | 0 |
| `installation_work_units` | 33 | `store_id,status,plan_id,resource` | None | 0 |
| `onboarding_operations` | 15 | `admin_subject_hash,idempotency_key,store_id` | None | 0 |
| `workspace_store_bindings` | 9 | `tenant_id,workspace_operation_id,store_id` | None | 0 |

All four table references and locations match DEV / `southamerica-east1`.
Schema and clustering comparisons passed. Terraform `deletion_protection=true`
was checked in the audited plan and again after provider refresh. This protection
is a Terraform guard, not an independent BigQuery API deletion-protection flag.
The metadata `numRows=0` verifies empty tables without selecting rows.

## IAM verification

The service account `up-install-orchestrator-dev` exists and is enabled in DEV.
The 27 new bindings comprise:

| Scope | Role | Bindings |
| --- | --- | ---: |
| Approved individual tables | `roles/bigquery.dataViewer` | 16 |
| Approved individual tables | `upControlPlaneDataWriter_dev` | 8 |
| DEV project | `roles/bigquery.jobUser` | 1 |
| DEV project | `upControlPlanePoll_dev` | 1 |
| DEV lease bucket only | `upFoundationLeaseWriter_dev` | 1 |

Custom roles are existing roles, not newly created roles. The table writer has
only `bigquery.tables.get`, `bigquery.tables.getData` and
`bigquery.tables.updateData`; the poll role has `run.operations.get`; the lease
role has `storage.objects.create/delete/get`. No Owner, Editor, broad
BigQuery dataEditor, Secret Manager accessor or worker RunJob binding was added.
Worker grants reuse the existing source-specific Control Plane service accounts.
All 27 bindings were refreshed by the provider in the post-apply plan and were
no-op; no separate IAM policy write or manual corrective operation was performed.

## Installation Jobs and Scheduler verification

Read-only Cloud Run Jobs metadata list confirmed **zero `up-installation-*`
Jobs**. The five existing Control Plane Jobs still use the approved `47e4…d2e`
immutable digest shown above.

Read-only Cloud Scheduler metadata list confirmed:

| Scheduler | State | Schedule |
| --- | --- | --- |
| `up-upzero-dispatch` | PAUSED | `0 3 * * *` |
| `up-meta-dispatch` | PAUSED | `0 4 * * *` |
| `up-analytics-dispatch` | PAUSED | `0 5 * * *` |
| `up-intelligence-dispatch` | PAUSED | `0 6 * * *` |

No Job or Scheduler was executed or activated.

## Post-apply plan

The same approved input values were used for a read-only plan. A private saved
post-plan was also produced solely to inspect the JSON; it was not applied.

```bash
terraform -chdir=infra/terraform plan \
  -input=false -no-color -lock-timeout=60s \
  -var-file=environments/dev.tfvars \
  -var="control_plane_image=${CONTROL_PLANE_IMAGE}" \
  -var='control_plane_meta_secret_version=1' \
  -out=/tmp/change18-4b-post.plan -detailed-exitcode \
  > /tmp/change18-4b-post-plan.txt 2>&1
```

- Exit code: **0**.
- Text result: **No changes**.
- JSON material actions: **0**; **0 add / 0 change / 0 destroy**.
- All 32 newly created resources refreshed as no-op.
- Installation image still null; all four table protection guards still true.
- Warning count: **0** in pre-plan, apply and post-plan logs.

## MX integrity and security review

This change performed infrastructure metadata/IAM provisioning only. It did not
create an installation plan, initialize a publication HEAD/receipt, write
Registry/source-connection rows, change checkpoints or mutate RAW/CORE. Existing
resources were no-op in the audited apply; the subsequent plan is clean.
No business data was inspected to claim stronger data-content verification.

Private diagnostic logs, state inventories, saved plans and JSON metadata were
kept outside Git under `/tmp` with restrictive umask. No raw state, credential,
token, API key, secret value, `.env`, plan, cache or real customer data is included
in either runbook. The secret version `1` input is a metadata reference, not a
secret value. No service-account key was generated.

Passed: Cloud Shell and local `terraform fmt -check`, Terraform validate before
provisioning, exact plan allowlist/guards, metadata/state/post-plan checks and
`git diff --check`. No application code changed, so Python/frontend suites were
not rerun for these two documentation-only Git changes.

## Explicitly not executed

```text
Cloud Build: NO
Artifact Registry push: NO
Installation image: NONE
Installation Cloud Run jobs created: NO
Cloud Run execution: NO
Scheduler execution: NO
UP Zero API: NO
Meta API: NO
Source probes: NO
MX plan-only: NO
Installation create-plan: NO
Installation dispatch: NO
Installation worker: NO
BigQuery business-data SELECT: NO
BigQuery business-data DML: NO
Secret value read: NO
Checkpoint mutation: NO
RAW mutation: NO
CORE mutation: NO
Registry row mutation: NO
Source connection row mutation: NO
Terraform import/state rm/state mv/state push/destroy: NO
PR/merge: NO
```

The authorized Terraform apply did change the DEV remote state and the listed
infrastructure resources. GCP metadata/provider APIs were called for verification;
“API: NO” above refers specifically to UP Zero and Meta business integrations.

## Recommended next step — not executed

Review this provisioning evidence and qualify a separate Installation image in a
subsequent authorized change. Keep `installation_image=null` until qualification
and a fresh runtime plan receive approval. No build, image publication, runtime
provisioning, dispatch or MX onboarding is initiated by this report.
