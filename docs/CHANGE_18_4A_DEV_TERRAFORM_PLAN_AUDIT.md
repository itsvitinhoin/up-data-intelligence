# CHANGE #18.4A — DEV Terraform Plan & Drift Audit

## Baseline

- Approved branch: `change-18-3-1-installation-audit-hardening`.
- Exact initial commit: `c50e79b2908c034dcacda9c7b00eb862bfdd1d9e`.
- Audit branch: `change-18-4a-dev-terraform-plan-audit`, created from that commit.
- Initial working tree: clean.
- Inspection timestamp: `2026-10-03T04:07:20Z` (UTC).
- Authorized project: `up-data-intelligence-dev`.
- Expected project number: `876521886531`; **not verified remotely**.
- Configured region / dataset location / lease bucket location: `southamerica-east1`.
- Configured pilot: `mx-fashion`.
- Configured lease bucket: `up-data-intelligence-dev-876521886531-leases`.

## Decision

**PLAN BLOCKED — REVIEW REQUIRED**

The existing local ADC cannot read the required DEV metadata/backend. No state
inventory, refresh-only plan, full plan or plan JSON could be produced. No
infrastructure or drift approval is possible from this inspection. Unknown
counts are not zero. No apply is authorized by this report.

## DEV identity verification

`gcloud projects describe up-data-intelligence-dev` failed because the local
CLI has no active account. No login, account selection or auth configuration
change was performed.

Read-only Cloud Resource Manager project lookup using the existing ADC then
returned HTTP **403 / PERMISSION_DENIED**. The project number remains an
expected configuration reference, not a verified live identity. One lookup
explicitly supplied the DEV quota project; another used the existing ADC
configuration (no quota project). Both returned 403. No token, credential
contents or response payload was published.

This failure does not establish whether the project exists or which particular
project-level permission/quota condition denied the metadata request. It is a
blocker to identity certification, not evidence that the expected number is
wrong.

## Terraform backend

The declared backend remains unchanged:

```hcl
backend "gcs" {
  bucket = "up-data-intelligence-dev-876521886531-tfstate"
  prefix = "foundation/dev"
}
```

Expected default-workspace state path:
`gs://up-data-intelligence-dev-876521886531-tfstate/foundation/dev/default.tfstate`.
This is the expected path only; the object was not read.

Before init there was no cached `.terraform/terraform.tfstate` backend metadata.
The following authorized init was attempted, with private output under `/tmp`:

```bash
terraform -chdir=infra/terraform init -input=false -no-color
```

Exit code: **1**. Initialization failed while querying existing workspaces:
Cloud Storage HTTP 403, permission **`storage.objects.list` denied** on
`up-data-intelligence-dev-876521886531-tfstate` (the API also allows the
possibility that the bucket is not visible/does not exist).

No `-reconfigure`, `-migrate-state` or `-force-copy` was used. Workspace identity
could not be verified; no workspace was created or selected. State inspection
and plans were not attempted after this failure. No intentional state write,
lock object creation, migration or state recovery command was performed.

## Offline checks

Passed before live metadata access and repeated at the end:

- `terraform fmt -check -recursive infra/terraform`.
- `terraform -chdir=infra/terraform validate`.
- `git diff --check` (including the staged runbook).

The local process sandbox initially prevented provider schema startup.
`validate` passed when the installed provider was allowed to start locally;
this did not require a plan or cloud resource request.

Programmatic configuration checks passed:

- `dev.tfvars` has no `installation_image` assignment.
- `installation.tf` still declares `installation_image` default `null`.
- No `TF_VAR_installation_image`, `TF_VAR_project_id`, `TF_WORKSPACE` or
  `TF_CLI_ARGS{,_init,_plan}` override was present.
- No `*.auto.tfvars` / `*.auto.tfvars.json` file was present.
- DEV project, locations, pilot, lease bucket and `scheduler_paused=true` match
  the approved references.
- Terraform, tfvars, images/digests, Python, frontend and schemas were not edited.

## State inventory

| Category | Live state count |
| --- | --- |
| BigQuery datasets | NOT DETERMINED |
| BigQuery tables | NOT DETERMINED |
| Service accounts | NOT DETERMINED |
| IAM | NOT DETERMINED |
| Cloud Run Jobs | NOT DETERMINED |
| Cloud Schedulers | NOT DETERMINED |
| Secret containers | NOT DETERMINED |
| Storage buckets | NOT DETERMINED |

`state list`, detailed state inspection and `state pull` were not executed.
No raw state was obtained or included in Git.

## Refresh-only result

- Executed: **NO**, backend initialization/identity prerequisites blocked.
- Exit code: **NOT AVAILABLE**; not 0, 1 or 2 from a plan invocation.
- Drift: **UNKNOWN — REVIEW REQUIRED**.
- Expected / potentially dangerous drift: cannot be classified without evidence.

No `terraform refresh` or refresh-only apply was performed.

## Normal plan result

```text
Add: NOT DETERMINED
Change: NOT DETERMINED
Replace: NOT DETERMINED
Destroy: NOT DETERMINED
No-op/read: NOT DETERMINED
```

No full plan was executed. No binary plan, text plan or plan JSON exists from
this inspection. Consequently, no programmatic plan-action analysis is claimed.

## Installation expected resources — configuration only

These are reviewed definitions in the approved source, **not observed plan
changes**. Their presence/absence in live state is unknown.

| Resource | Action | Expected? | Notes |
| --- | --- | --- | --- |
| `up_ops.installation_plans` | NOT PLANNED | Yes, definition | No partition; clustering `store_id,status` |
| `up_ops.installation_work_units` | NOT PLANNED | Yes, definition | No partition; clustering `store_id,status,plan_id,resource` |
| `google_service_account.installation_orchestrator` | NOT PLANNED | Yes, definition | Account ID `up-install-orchestrator-dev` |
| `google_project_iam_member.installation_query` | NOT PLANNED | Yes, definition | Orchestrator BigQuery jobUser |
| `google_bigquery_table_iam_member.installation` | NOT PLANNED | Yes, definition | 24 table-scoped grants defined: 16 reads, 8 writes |
| `google_storage_bucket_iam_member.installation_lease` | NOT PLANNED | Yes, definition | Lease role bound on the lease bucket |
| `google_project_iam_member.installation_poll` | NOT PLANNED | Yes, definition | Existing custom role with `run.operations.get` |
| `google_bigquery_table_iam_member.installation_admin_read` | NOT PLANNED | Conditional | Two metadata table viewers only if admin member configured; default null |
| `google_cloud_run_v2_job.installation_worker` | NOT PLANNED | Expected 0 instances | Null image disables all three workers |
| `google_cloud_run_v2_job.installation_orchestrator` | NOT PLANNED | Expected 0 instances | Null image sets count to zero |
| `google_cloud_run_v2_job_iam_member.installation_run` | NOT PLANNED | Expected 0 instances | Iterates only the disabled workers |

The only Installation table definitions are the two listed above. No schemas
were changed by this audit; future plan compatibility with existing live
schemas remains unverified.

## Installation jobs

```text
Installation Cloud Run jobs planned: NOT DETERMINED (plan not executed)
Installation Cloud Run instances expected from configuration: 0
installation_image: null
```

The four names `up-installation-orchestrator`, `up-installation-upzero-worker`,
`up-installation-meta-worker` and `up-installation-analytics-worker` are disabled
by the null-image gates. This is not a claim that a full remote-state plan would
create zero jobs or that no such job already exists. Plan certification is
blocked until the authorized state can be read.

## Existing resource changes

| Existing resource category | Observed plan changes | Review status |
| --- | --- | --- |
| MX Foundation jobs | NOT DETERMINED | Blocked |
| BigQuery tables / datasets / schemas | NOT DETERMINED | Blocked |
| IAM / secrets | NOT DETERMINED | Blocked |
| Lease bucket | NOT DETERMINED | Blocked |
| Analytics | NOT DETERMINED | Blocked |
| Control plane / onboarding | NOT DETERMINED | Blocked |

None was modified. No existing resource can be certified as no-op from this
report.

## Destructive changes

**UNKNOWN — BLOCKER**: no plan was generated, so absence of delete/replacement
cannot be certified. No destructive operation was executed. No Terraform code
or state was adjusted to hide differences.

## Scheduler changes

- Source configuration still has `scheduler_paused=true` for Foundation.
- Control plane scheduler definitions still declare `paused=true`.
- Installation defines no scheduler.
- Actual live paused states / proposed scheduler actions: NOT VERIFIED.
- Scheduler modification/execution by this audit: **NONE**.

## IAM audit — source configuration only

Orchestrator reader tables: `onboarding_operations`, `store_runtime_config`,
`source_connections`, `sync_runs`, `sync_checkpoints`, `analytics_publications`,
`analytics_store_daily`, `analytics_funnel_daily`, `installation_plans` and
`installation_work_units`. Writer tables: `installation_plans`,
`installation_work_units` and `store_runtime_config`.

Source-specific workers each read the two Installation tables. UP Zero and
Meta each write `installation_work_units` and `source_connections`; Analytics
writes `installation_work_units` only. The three workers reuse the existing
`control_plane` source-specific service accounts; no universal worker SA is
defined.

The table writer custom role has only `bigquery.tables.get`,
`bigquery.tables.getData` and `bigquery.tables.updateData`; Installation binds it
at table scope. Orchestrator jobUser is project-scoped, as required for query
jobs. The lease custom role (`storage.objects.create/delete/get`) is bound only
on the lease bucket. Operation polling uses `run.operations.get`.

RunJob/overrides grants are scoped to Installation worker jobs and have no
instances while those jobs are disabled. No Installation grant declares
Secret Manager accessor, Owner, Editor, project-wide BigQuery dataEditor or RAW
payload access. Actual live IAM and plan IAM changes remain **unverified**.

## Security

Only this sanitized runbook is committed. The private init diagnostic log is
outside Git in `/tmp/change18-4a-dev-audit/`, under a restrictive umask. Its raw
permission error identifies the credential principal; that identity and raw
error were excluded from this document. No credentials, tokens, `.env`, state,
plan, plan JSON, caches, secret values, customer records or payloads are included.

There is no `google_secret_manager_secret_version` or secret-value data source
in the active root Terraform definitions reviewed. Metadata references to secret
IDs/versions are distinct from secret values. No Secret Manager API was called
by this audit; no secret container/value action is certified without a plan.

## Explicitly not executed

```text
Terraform apply: NO
Terraform destroy: NO
Cloud Build: NO
Artifact Registry push: NO
Cloud Run execution: NO
Installation jobs execution: NO
BigQuery DML: NO
Secret Manager value read: NO
UP Zero API: NO
Meta API: NO
Source probes: NO
Installation create-plan: NO
Installation dispatch: NO
MX plan-only: NO
MX live mutation: NO
Scheduler execution: NO
```

Also not executed: Terraform import, state rm/mv/push, refresh, state migration,
new image/tag/digest, checkpoint reset, RAW cleanup, replay, Registry/source
connection writes, PR or merge. No Secret Manager version/container mutation,
manual schema mutation or infrastructure provisioning was performed.

## Recommended next step — not executed

Have the operator select an already authorized DEV principal in this environment
or perform the audit in its existing authorized Cloud Shell. Confirm access to
DEV project identity metadata (`resourcemanager.projects.get`) and to list/read
the declared state bucket (`storage.objects.list` and `storage.objects.get`).
The actual missing permission observed here is `storage.objects.list`; other
read permissions required by provider refresh have not yet been tested.

A bucket-scoped read-only state grant can satisfy list/get without allowing state
mutation. Do not grant Owner/Editor or broad write privileges just for this audit.
No authentication/IAM changes are performed as part of this change.

Then rerun the authorized #18.4A sequence: verify project number, init without
migration, verify workspace (do not create/switch), read state inventory,
refresh-only plan and full plan with `-lock=false`, followed by sanitized JSON
action/schema/IAM/scheduler review. Exit code 2 means differences, not failure.
Keep installation_image null. Any Installation job creation, existing table
schema change, delete or replacement must stop the audit as specified. Only a
subsequent successful inspection may change the decision to
`PLAN CLEAN — READY FOR REVIEW`; this document does not authorize apply.
