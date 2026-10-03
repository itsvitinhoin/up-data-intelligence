# CHANGE #18.4C — Installation Image Qualification

## Current decision

**IMAGE QUALIFIED — READY FOR INSTALLATION RUNTIME DEPLOYMENT**

The authorized continuation completed: six build-infrastructure resources created,
Installation image published and verified, offline container smoke checks passed,
and the single post-apply plan reported no changes. `installation_image` remains
`null`; no Installation Job or runtime deployment was created.

The initial blocked attempt and read-only identity audit below are retained as
historical evidence. Their statements describe those earlier attempts, not the
final state. See **Authorized continuation — completed** for the final results.

## Initial decision — historical

**IMAGE QUALIFICATION BLOCKED — REVIEW REQUIRED**

Stopped at phase 3, before base selection, tag creation or build submission.
The available build history does not establish the approved custom/restricted
build identity required by the request. No image was built or published.

## Baseline

- Approved source commit: `4523aff6ae9d52398be4d00157ffcf50b50c8221`.
- Source tree: `87d9876deeeac2d20e59a9d537e06610173983a2`.
- Branch: `change-18-4c-installation-image-qualification`.
- Local and Cloud Shell checkouts were clean at the approved source commit before
  qualification. No additional commit preceded any build.
- Cloud Shell initially retained the previous #18.4B pre-documentation checkout;
  the approved remote commit was fetched and explicitly checked out before the
  new branch was created. No merge, rebase or source modification was performed.
- DEV project: `up-data-intelligence-dev`; region: `southamerica-east1`.

Only this blocked-qualification report is added locally. No runtime or
infrastructure file was changed.

## Upload audit

`gcloud meta list-files-for-upload` passed the existing `.gcloudignore` allowlist:

- **237 files**, comprising **150 Python runtime files**, **81 SQL files** and
  the six required files below.
- Required files: `Dockerfile`, `.dockerignore`, `requirements.lock`,
  `cloudbuild.yaml`, `docs/upzero-openapi.json` and
  `config/analytics/mx-fashion.dev.json`.
- Every listed file was tracked in Git and matched the exact runtime path rules.
- No `.git`, `.env`, tfvars, tfstate, tfplan, credential file, test fixture,
  frontend, venv or cache was included.
- Runtime upload files were scanned for common private-key/token/API-key
  patterns; none was found. The Analytics policy is non-secret.
- `.gcloudignore`, `.dockerignore`, Dockerfile and repository Cloud Build config
  were preserved.

The upload list was written privately to `/tmp/change18-4c-upload-files.txt`.
No source upload or Cloud Build submission occurred.

## Registry metadata

Read-only repository metadata confirmed:

- Repository: `projects/up-data-intelligence-dev/locations/southamerica-east1/repositories/up-data-intelligence`.
- Format: `DOCKER`.
- `dockerConfig.immutableTags=true`.

No repository, tag or IAM configuration was changed.

## Build identity — blocker

The regional query requested the latest 10 builds and returned two. Both were
successful and used the following technical service-account identity:

```text
projects/up-data-intelligence-dev/serviceAccounts/876521886531-compute@developer.gserviceaccount.com
```

| Historical Build ID | Status | Identity |
| --- | --- | --- |
| `1b9a0657-c425-43ee-89d8-756f308e1c68` | SUCCESS | Default Compute Engine service account |
| `65381517-177c-449d-b4ad-338e82abe6f6` | SUCCESS | Default Compute Engine service account |

This is a default Compute Engine identity, not evidence of the custom build
identity required by the request. Successful builds alone do not establish
restricted IAM or approval to reuse that account. Its effective permissions
were not audited, and this report does not claim it has broad or restricted
access. The finite regional history also does not prove that no suitable custom
account exists elsewhere; none was established by the inspected evidence.

The request explicitly says to stop if an approved restricted build identity
cannot be established and not to automatically use a broad default identity.
Therefore no account was selected for #18.4C, and no service-account key was
created or read. No IAM change or new staging bucket was attempted.

## Base image

- Requested tag: `python:3.13-slim-bookworm`.
- The historical successful builds contain a digest-pinned `_PYTHON_BASE`
  substitution. This metadata was observed, but phase 4 was not advanced after
  the phase-3 blocker.
- Selected `PYTHON_BASE` / base digest for this release: **NOT SELECTED**.
- No mutable-tag release build was executed.

## Build and smoke tests

- New Build ID / build timestamp: **NOT AVAILABLE — NOT SUBMITTED**.
- New build status: **NOT EXECUTED**.
- Local source qualification: `.venv/bin/pytest -q tests/installation`:
  **88 passed in 16.33 seconds**, using offline tests.
- Foundation container `--help`: **NOT EXECUTED**.
- Installation container CLI `--help`: **NOT EXECUTED**.
- Container imports / ZoneInfo / OpenAPI smoke: **NOT EXECUTED**.
- Temporary Cloud Build config: **NOT CREATED**.
- No build retry occurred.

The local test result does not qualify a container that has not been built.

## Final image

```text
VERSION: NOT CREATED
IMAGE_TAG: NOT CREATED
Final digest: NOT AVAILABLE
IMAGE_REF: NOT AVAILABLE
Digest cross-check: NOT EXECUTED
```

Intended repository image path only:
`southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation`.
No tag was reserved, reused, moved or published.

## Runtime verification

No runtime update, Job creation/execution, Scheduler operation or Terraform
command was performed by #18.4C. The last approved existing Control Plane image,
recorded by the #18.4B verification, is:

```text
southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:47e4ce9ecd849642950fecff6e0a6ab88756e9cba04c9729c20dacbcd9dfcd2e
```

`installation_image` retains its null default and is absent from `dev.tfvars`.
`git diff -- infra/terraform` and the specific tfvars diff are empty.

No Installation Job was created. The preceding #18.4B live verification found
zero Installation Jobs. A fresh phase-12 runtime metadata inventory was **not
executed** because this change stopped before publication; the previous finding
is not presented as a new live measurement.

## Security

Cloud activity was limited to the authorized upload-list audit and read-only
Artifact Registry / Cloud Build metadata. No source APIs, business-data queries,
Secret Manager values or production services were accessed. The uploaded-file
list is a local listing, not an upload.

Only this sanitized report is added to Git's working tree. It contains no
credential key, token, secret value, tfstate, tfplan or real customer data.
Private metadata files remain outside the repository under `/tmp`.

## Explicitly not executed

```text
Cloud Build submit: NO
Artifact Registry publication: NO
Terraform plan: NO
Terraform apply: NO
Terraform destroy/import/state mutation: NO
Installation tfvars update: NO
Installation Cloud Run jobs created: NO
Cloud Run execution: NO
Scheduler execution/mutation: NO
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
Replay: NO
RAW mutation: NO
CORE mutation: NO
Registry row mutation: NO
Source connection mutation: NO
PR/merge: NO
```

## Git publication status

No runbook commit or push has been performed. The request gates publication
on build/verification; this qualification stopped before build. The local branch
still points at the exact approved source commit, with only this new report
untracked. No source commit was rewritten.

## Recommended next step — not executed

Provide the technical email of an existing approved custom build service account
and evidence of its restricted permissions / successful use, together with the
approved source-staging location if required. Alternatively, explicitly approve
a separate read-only identity/IAM audit to establish a suitable existing build
identity. No account provisioning or IAM modification is authorized by #18.4C.

Then resume from the identity guard and qualify a pinned base, unique tag,
network-disabled container smokes, publication and digest verification. Do not
substitute the default Compute account merely because it built previous images.


## Build identity audit

### Scope and context

A separately authorized read-only audit completed after the phase-3 blocker.
This section supplements the earlier inspection; statements above about IAM
not yet being audited describe that earlier stage.

- Project: `up-data-intelligence-dev`.
- Active submitter: `upagency.oficial@gmail.com`.
- Branch: `change-18-4c-installation-image-qualification`.
- Required source HEAD: `4523aff6ae9d52398be4d00157ffcf50b50c8221`, unchanged.
- Local working tree still contains only this untracked report; Cloud Shell
  passed the same baseline guard and had no unexpected working-tree changes.
- Read commands covered service-account inventory, recent build descriptions,
  repository/project IAM, custom-role metadata, the historical staging bucket's
  metadata/IAM and relevant predefined-role permission metadata.
- No build, upload, IAM write, Terraform, Secret Manager, Cloud Run, Scheduler,
  source API, business-data query, PR or merge was executed.

### Existing accounts and classification

The project service-account list returned **13 enabled accounts**: 12 UP
runtime accounts and the default Compute Engine account. The names and display
names demonstrate runtime roles, not a dedicated build/CI purpose.

All UP account IDs below use `@up-data-intelligence-dev.iam.gserviceaccount.com`:

| Account ID | Apparent purpose |
| --- | --- |
| `up-foundation-dev` | UP Zero ingestion/normalization |
| `up-meta-dev` | Meta runtime |
| `up-analytics-dev` | Analytics materialization |
| `up-intelligence-dev` | Intelligence runtime |
| `up-scheduler-dev` | Foundation scheduling identity |
| `up-cp-dispatch-dev` | Control Plane dispatcher |
| `up-cp-schedule-dev` | Control Plane scheduling identity |
| `up-cp-upzero-dev` | Control Plane UP Zero worker |
| `up-cp-meta-dev` | Control Plane Meta worker |
| `up-cp-analytics-dev` | Control Plane Analytics worker |
| `up-cp-intelligence-dev` | Control Plane Intelligence worker |
| `up-install-orchestrator-dev` | Installation ledger orchestrator |

Default Compute Engine account:
`876521886531-compute@developer.gserviceaccount.com`.

Project IAM also references the legacy default Cloud Build account
`876521886531@cloudbuild.gserviceaccount.com`; it is not a custom build account.
Google-managed service agents referenced in project IAM were classified
separately, rather than treated as build candidates:

- `service-876521886531@gcp-sa-cloudbuild.iam.gserviceaccount.com` — Cloud Build agent.
- `service-876521886531@gcp-sa-artifactregistry.iam.gserviceaccount.com` — Artifact Registry agent.
- `service-876521886531@containerregistry.iam.gserviceaccount.com` — Container Registry agent.
- `service-876521886531@gcp-sa-cloudscheduler.iam.gserviceaccount.com` — Scheduler agent.
- `service-876521886531@gcp-sa-pubsub.iam.gserviceaccount.com` — Pub/Sub agent.
- `service-876521886531@serverless-robot-prod.iam.gserviceaccount.com` — Cloud Run agent.

No build/CI-specific custom account was identified. The project custom-role
inventory contained the existing Control Plane data writer, poll, RunJob,
Foundation writer, lease writer, onboarding reader and administrator roles;
none was identified as a dedicated build/CI role.

### Historical builds and source staging

Both regional historical builds were described individually and confirmed:

| Build ID | Status | Build identity | Logging |
| --- | --- | --- | --- |
| `1b9a0657-c425-43ee-89d8-756f308e1c68` | SUCCESS | Default Compute Engine SA | CLOUD_LOGGING_ONLY |
| `65381517-177c-449d-b4ad-338e82abe6f6` | SUCCESS | Default Compute Engine SA | CLOUD_LOGGING_ONLY |

Both `source.storageSource` records identify
**`gs://up-data-intelligence-dev_cloudbuild`**, with archive objects under the
existing `source/` prefix. Exact bucket/object/generation metadata was retained
privately in the two `/tmp/change18-4c1-build-<BUILD_ID>.json` files. No archive
was opened, downloaded or uploaded; no bucket object inventory was performed.
Neither build has a `logsBucket`; both use `CLOUD_LOGGING_ONLY`.

### Artifact Registry publishers/readers

Direct repository policy on `up-data-intelligence`:

| Role | Principal |
| --- | --- |
| `roles/artifactregistry.writer` | `serviceAccount:876521886531-compute@developer.gserviceaccount.com` |
| `roles/artifactregistry.writer` | `user:upagency.oficial@gmail.com` |
| `roles/artifactregistry.reader` | `user:upagency.oficial@gmail.com` |

No dedicated custom build SA has Writer directly on this repository.

### Candidate IAM and excess privilege

**Candidate custom build SA: NONE.** Runtime identities were not repurposed;
default accounts and Google-managed service agents were not selected.
Accordingly, no candidate-specific SA policy or key inventory was requested.
No key material was created, read or required by this audit.

The historical Compute build SA has **`roles/editor` on the project**. This is
now an observed broad grant, unlike the earlier name-only inspection. It fails
the requirement not to depend on Owner/Editor. Its repository Writer alone does
not make the account qualified.

The active submitter has unconditional project bindings for **`roles/owner`**
and **`roles/cloudbuild.builds.editor`**. The legacy default Cloud Build SA has
`roles/cloudbuild.builds.builder` at project scope. No direct project
`roles/logging.logWriter` binding was found in the inspected policy.
Permission metadata confirms the historical Editor role includes
`logging.logEntries.create`; previous successful logging therefore does not
establish a least-privilege dedicated logger grant.

No IAM binding was added, removed or repaired.

### Submitter permission evidence

The direct project bindings and authoritative predefined-role metadata establish
these allow grants for the current submitter:

- `cloudbuild.builds.create/get`: included in `roles/cloudbuild.builds.editor`
  (also present in the granted Owner role).
- `iam.serviceAccounts.actAs`: included in the granted project Owner role.
  No dedicated candidate exists, so no candidate-specific SA-policy certification
  or impersonation attempt was performed.
- Source upload: the staging bucket grants `roles/storage.legacyBucketOwner` to
  `projectOwner:up-data-intelligence-dev` and
  `projectEditor:up-data-intelligence-dev`. Role metadata confirms
  `storage.objects.create` in that bucket role. The submitter's project Owner
  membership therefore provides an existing allow path for source upload.

These findings describe observed allow policies, not a comprehensive evaluation
of organization/folder inheritance, IAM Deny or principal access boundaries.
No live build, impersonation, object read/write or permission-changing test was
used to prove end-to-end access. Owner/Editor are reported as excess privilege,
not accepted as a substitute for a restricted build identity.

### Staging metadata and IAM

Only the staging bucket identified by the historical builds was inspected:

```text
gs://up-data-intelligence-dev_cloudbuild/source/
```

Bucket metadata:

- Location: **US**, multi-region; this is the existing staging location, not a
  proposed change to the approved runtime region.
- Uniform bucket-level access: **false**.
- Public access prevention: **inherited**.

Bucket IAM:

- `roles/storage.legacyBucketOwner` — project owners and project editors.
- `roles/storage.legacyBucketReader` — project viewers.
- No `allUsers` or `allAuthenticatedUsers` binding appeared in this bucket policy.
- Default object ACL metadata includes project owners/editors as OWNER and
  project viewers as READER.

The existing source-access model is broad and relies on legacy convenience
principals/ACLs. No prefix-scoped Viewer grant for a custom build SA was found.
The inspected IAM policy alone is not proof that all objects/ACLs or the
organization's inherited public-access policy are private. No bucket hardening,
ACL modification, new bucket or staging-object operation was performed.

### Decision and next step

**NO QUALIFIED BUILD IDENTITY — PROVISIONING REQUIRED**

No inspected existing account meets the full custom-build contract, particularly
the dedicated identity, direct repository Writer and least-privilege logging/
staging requirements. There is no qualified path to resume #18.4C without a
separately authorized identity/IAM change.

Recommend a separate minimal IAM change to provision a dedicated build SA,
Writer only on `up-data-intelligence`, project `roles/logging.logWriter`, and
necessary read access to the already-used source staging, preferably restricted
to `source/`. No Secret Manager access, Owner/Editor or JSON key should be needed.
Revalidate submitter create-build/actAs/upload evidence for that account. Current
submitter grants already provide the observed allow path; do not add redundant
broad project roles. Reducing existing Owner/Editor grants or changing bucket
access controls requires a separate scope review, not an automatic fix here.

Qualification remains blocked. This report is kept local and uncommitted as
instructed. The source HEAD and all Terraform/runtime files remain unchanged.


## Authorized continuation — completed

### Scope and code

The subsequent request explicitly authorized provisioning a dedicated DEV build
identity, staging bucket and four IAM bindings, then one Installation image
build/publication. It did not authorize deploying the Installation runtime.

Committed changes are limited to:

- `infra/terraform/build_identity.tf`: the required non-secret submitter variable
  and exactly the six approved build resources. Defining the variable in this
  file avoids modifying the existing `variables.tf`.
- `infra/terraform/environments/dev.tfvars`: append only
  `build_submitter_member = "user:upagency.oficial@gmail.com"`.
- `tests/control_plane/test_control_plane.py`: the existing preservation test
  accepts only that exact additive DEV input, while still hashing all original
  content and other existing Terraform files unchanged.
- This existing #18.4C runbook: preserve the earlier evidence and record the
  completed continuation in the same narrative.

Runtime Python, Dockerfile, ignore files, repository `cloudbuild.yaml`, policy,
existing schemas, Terraform runtime resources and `installation_image` were not
changed. No credentials, secret values, real customer data, local state, saved
plans or temporary build artifacts are included in the Git changes.

### Terraform build infrastructure

| Address | Approved scope |
| --- | --- |
| `google_service_account.build` | Dedicated `up-build-dev`, DEV project only; no key |
| `google_service_account_iam_member.build_submitter` | Approved submitter, `roles/iam.serviceAccountUser` on new SA only |
| `google_project_iam_member.build_logging` | New SA, `roles/logging.logWriter` on DEV project |
| `google_artifact_registry_repository_iam_member.build_writer` | New SA, `roles/artifactregistry.writer` on existing `up-data-intelligence` repository only |
| `google_storage_bucket.build_source` | New dedicated DEV source bucket |
| `google_storage_bucket_iam_member.build_source_viewer` | New SA, `roles/storage.objectViewer` on new bucket only |

One pre-apply gate used the existing remote backend, `environments/dev.tfvars`,
the approved current Control Plane digest and Meta secret version reference `1`.
The saved plan `/tmp/change18-4c-fast.plan` contained exactly six CREATE actions:
**6 to add, 0 to change, 0 to destroy**, without replacements. All existing Jobs,
Schedulers and BigQuery resources were no-op. The user then explicitly confirmed
applying only this audited plan. Its recorded checksum was rechecked before apply.

The saved plan was applied once, without an automatic retry:
**6 added, 0 changed, 0 destroyed; exit code 0**.

One post-apply plan used the same inputs and reported **No changes**:
**0 add, 0 change, 0 destroy; exit code 0**. Pre-plan, apply and post-plan logs
contained zero warnings. No additional plan or apply was needed.

### Identity and source staging

Build service account:

```text
up-build-dev@up-data-intelligence-dev.iam.gserviceaccount.com
```

It has only the new scoped Writer/Logger/Viewer grants above. No Owner, Editor,
Secret Manager, BigQuery, Cloud Run Admin or service-account key was granted.
The submitter's previously observed Owner binding was preserved as requested;
this step does not claim to remove that pre-existing broad privilege.

Dedicated staging path:

```text
gs://up-data-intelligence-dev-876521886531-build-source/source
```

Bucket location is `southamerica-east1`; uniform bucket-level access is enabled,
public access prevention is enforced, `force_destroy=false`,
`prevent_destroy=true`, versioning is disabled, and objects have a Delete lifecycle
rule at age 7 days. No public binding was added. The legacy bucket was not used
for this build. Build logging uses `CLOUD_LOGGING_ONLY`.

### Source and build provenance

The build source remained exactly the approved runtime source:

```text
source commit: 4523aff6ae9d52398be4d00157ffcf50b50c8221
source tree:   87d9876deeeac2d20e59a9d537e06610173983a2
```

No commit preceded the build. The upload audit again returned **237 files**:
150 runtime Python files, 81 SQL files and the six required build/contract/policy
files recorded above. Runtime/upload paths had no diff against the approved
commit. The new Terraform, test and documentation changes were excluded from the
upload allowlist. No credentials, `.env`, tfstate, tfplan, customer data, test data,
frontend, virtual environment or cache entered the build context.

The Python base was resolved from the official image manifest and pinned:

```text
PYTHON_BASE=python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed
VERSION=install-v2-4523aff6ae9d-20261003T053218Z
BUILD_ID=0415a0b4-a3d7-4753-af27-6d7d73795bfd
BUILD_STATUS=SUCCESS
```

The tag was confirmed absent before submission; no existing tag was reused.
A temporary Cloud Build configuration in `/tmp` submitted one regional build
with the explicit new service account and dedicated source staging path.
Repository `cloudbuild.yaml` was preserved. Image labels record the source
commit/tree; these are build-time labels, not source changes.

Build started on **03 October 2026, 02:34:26 BRT** and finished at **02:35:12 BRT**
(`America/Sao_Paulo`). The version timestamp suffix is UTC.

### Offline container smoke checks

All four Cloud Build steps succeeded before image publication:

1. Build image for `linux/amd64` using the pinned base.
2. Run the default Foundation CLI `--help` with `--network=none`.
3. Run `python -m src.installation.cli --help` with `--network=none`.
4. Run the Installation import/assets smoke with `--network=none`.

The last smoke confirmed Python 3.13, x86_64, non-root UID 10001, imports of the
nine existing Installation modules (`cli`, `orchestrator`, `worker`, `planner`,
`model`, `repository`, `gateway`, `publication`, `adapters`),
`ZoneInfo("America/Sao_Paulo")`, JSON parsing of `docs/upzero-openapi.json`, and
reading the non-secret Analytics policy. It did not call any API or Job.

An exact-build log read found one success marker:

```text
INSTALLATION_RUNTIME_SMOKE_OK linux/amd64 non-root ZoneInfo OpenAPI policy imports=9
```

### Verified immutable image

```text
IMAGE_TAG=southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation:install-v2-4523aff6ae9d-20261003T053218Z
DIGEST=sha256:5e9b3d0752cd78abfabf580b39c69eedf487dd72b086c3e62f6f593ccc2288f0
IMAGE_REF=southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:5e9b3d0752cd78abfabf580b39c69eedf487dd72b086c3e62f6f593ccc2288f0
```

Artifact Registry tag metadata, Cloud Build `results.images` and immutable-reference
metadata agreed on the exact digest. Image publication is complete.

### Runtime safety and validation

- **Installation Jobs: 0**.
- The images of all **nine existing Jobs** matched their pre-apply values.
- All **five Control Plane Jobs** retained
  `foundation@sha256:47e4ce9ecd849642950fecff6e0a6ab88756e9cba04c9729c20dacbcd9dfcd2e`.
- `installation_image` remained `null` in the final plan.
- Schedulers and runtime resources were not changed or executed.
- No MX plan-only/create-plan/dispatch, UP Zero/Meta request, source probe,
  checkpoint change, RAW/CORE mutation, business-data SELECT/DML, secret-value
  read, runtime deploy or Installation execution occurred.
- Local and Cloud Shell Terraform formatting/validation passed.
- **750 focused existing Terraform/preservation tests passed**; no full
  Python/frontend suite was rerun because runtime code was unchanged.
- `git diff --check` passed.

The Cloud Shell editor connection was lost after the completed digest/runtime
checks and clean post-plan were visibly returned. No cloud operation was retried
or further remote checkout edit attempted because of that connection loss.
Local code/runbook publication is independent of that editor session.

**IMAGE QUALIFIED — READY FOR INSTALLATION RUNTIME DEPLOYMENT**

Stop here. The image reference is evidence for the next authorized Runtime Plan;
it has not been assigned to `installation_image` or deployed.
