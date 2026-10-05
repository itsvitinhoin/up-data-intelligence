# CHANGE #19.3B — Dashboard data completion

## State and approved reference

Implementation is local and under acceptance. It is **not a completed live preview**.
No #19.3B infrastructure has been applied, no source connection has been changed,
and no historical extraction has been requested for MX.

The user-confirmed visual reference is the deployment
`up-data-intelligence-p484pm1uv-victorcheunin-6445s-projects.vercel.app`.
Its archived frontend matches the approved baseline commit
`cc9fa59488e7c24b2baaa634ea09bd7d7d19be6d`. The separately named #19.3A branch and
`b2b-standard.v2` template engine were not present in that source; this change
preserves the actual reviewed components rather than claiming those missing assets.
The field-level audit is in [the coverage audit](CHANGE_19_3B_DATA_COVERAGE_AUDIT.md).

## Data contracts

Catalog adds exact product/variant/attribute/inventory identities, current snapshots,
version membership and explicit completed observations. Current names/colors are
labeled as current catalog evidence, not historical order snapshots. Missing exact
identity, price, stock or color remains null. Inventory counts never come from sales.
Catalog extraction shares the canonical 20-page / 600-second slice ceilings.

Ad/day creative reads use separate Meta creative tables and exact account/configuration
coverage. Current creative metadata may supply sanitized thumbnail/video references.
Reach/frequency across days remain unavailable without a compatible period observation.
Purchases, value and CPA require an explicit purchase action definition; overlapping
Meta action types are never summed. Campaign attribution is not paid influence.

Products and order details resolve only exact canonical variant identifiers. Sales
by color/size use version-scoped order items with requested and fulfilled values
separate. Customer campaign drilldown is scoped by store and customer, avoiding
per-order request fan-out. Journey rows preserve timestamps and deterministic ties,
including unknown/unresolved evidence, without asserting causal attribution.
Geography uses canonical shipping snapshot state/city for orders in the selected period.

All reads retain publication HEAD/RECEIPT consistency, query budgets, authorization
before business IO and transport money as decimal strings. No demo fallback is added.

### Deliberately unresolved metrics

Lead source events exist, but counts of events are not counts of people. Lead cohort
and denominator semantics require the manager's explicit decision and identity proof.
The corresponding metrics remain unavailable (`METRIC SEMANTICS DECISION REQUIRED`).
Lifetime-sensitive metrics remain null with `history_complete=false`.

The current Customer Intelligence policy prohibits full personal/company identifiers,
email and phone in product responses. Those fields remain null pending an explicit
policy exception; source availability alone does not authorize disclosure.

## Admin Brand Control Plane

The initial authenticated brand list is a lightweight summary, with creation date
unknown for legacy MX. Configuration, operational health and extraction detail load
only when their respective dialogs open. Source health and initial Installation
completion are separate concepts. Next sync is not fabricated.

Existing UP Zero credentials are write-only, never prefilled, stored in browser state,
returned, hashed into operation metadata or automatically resent. Rotation persists
intent before one Secret Manager version write, verifies the pinned candidate and
atomically updates the reference. Old versions are preserved. Unknown writes/probes
retain leases and require reconciliation. Meta always uses the server-owned global
pinned token; no per-brand token is collected.

Explicit disablement preserves historical data and disables dependent pipelines.
Reactivation does not automatically claim fresh Analytics/Intelligence evidence.

### Adding Meta to an installed B2B brand

The dedicated connection-management `add` operation accepts an account ID and API
version, not a token, store ID or tenant ownership change. ADMIN_UP authorization
and canonical workspace binding precede IO. Under normal-dispatch, Installation-global
and store leases, it requires a complete initial installation, no pending checkpoint/
RAW/extension, absent Meta connection and absent/conflict-free Meta account binding.

A one-page server-only account probe verifies account/timezone/currency. Atomic CAS
persists the source, account binding, Registry revision and one purpose-specific
`META_SOURCE_ADDITION` extension plan: four ordered catalog units and campaign/ad
Insights units for each closed day in the currently certified window. Only Meta work
is created. No second initial plan, unrelated source reinstall, onboarding operation,
new secret or publication is created. Intelligence is not enabled by intention alone.
An ambiguous probe is never repeated automatically.

An absent UP Zero source on a brand without an existing certified commercial contract
still needs a dedicated commercial adoption contract. The UI does not collect a key
or claim successful configuration for that unsupported transition. Existing UP Zero
connections can be rotated, disabled and reactivated. Other commerce/media/ERP providers
are visible as unavailable and cannot collect credentials or pretend to ingest data.

### Historical extraction

Authenticated requests specify provider and inclusive local start/end dates. The server
uses exclusive ends and rejects future periods, invalid ownership and oversized ranges.
The purpose-specific V2 ledger keeps the initial installation graph immutable.
Deterministic identities include source/configuration/policy/window evidence. Certified
intervals are subtracted without crossing gaps; pending/ambiguous evidence blocks admission.
No manual RAW/CORE/checkpoint edits, resets or giant synchronous source fetch exist.

The current certified dashboard remains readable while extension work is pending.
Normal recurring workers are held back for that store when the extensions opt-in is
active, preventing those workers from claiming a backfill-owned checkpoint. This can
increase recurring lag until the bounded extension completes; it is not a data cache.
Historical publication runs only after contiguous source coverage is proven, retains
current certified end/as-of and may move the start backward. Subsequent full refreshes
read the earlier certified source bound too, without editing original `history_from`
or manufacturing lifetime proof. There is no fake cancellation button.

No real MX historical extraction is authorized merely by acceptance. The user must
choose and approve its provider, date range and intended scope.

## Loader and timing

The original user asset `Sample 5.mp4` is copied intact to `/media/up-loader.mp4`.
It runs muted/inline/looped at playback rate 1.5 on cold critical content loads,
without locking sidebar/navigation or flashing on background refresh. Reduced motion
and media failure use the existing accessible fallback; loading errors expose retry.

Safe numeric Server-Timing separates BFF identity/upstream and private API auth/query
cost. Request authorization is not cached. Independent product/customer/marketing calls
are parallel; customer campaign detail avoids N+1 reads. **No live before/after latency
improvement is claimed yet.** The required six-page measured comparison is pending.

## Live evidence gathered so far (read-only / bounded probes)

The latest metadata-only audit on 2026-10-05 used a 64-MiB query ceiling and billed
31,457,280 bytes. MX remained ACTIVE/sync enabled, Registry revision 12,
`history_complete=false`, `facts_complete=true`, coverage through 2026-10-05T03:00Z.
Analytics generation 6 has matching completed HEAD/RECEIPT identity, report
2026-09-01 → 2026-10-05 exclusive and as-of 2026-10-05T03:00Z.
The latest Data Health run at 2026-10-05T07:00:10.073507Z contains 16 rules and zero
blocking findings. This is evidence at that read, not a promise about future runs.

Bounded UP Zero/Meta source shape probes are documented in the coverage audit.
They did not persist business payloads and do not constitute full catalog/ad coverage.

## Deployment stages and review boundaries

All new behavior is fail-closed by default. Stage 1 adds 18 tables, additive nullable
Meta fields, scoped table grants and reviewed runtime image/feature updates. Its offline
guard is `scripts/dashboard_completion_plan_guard.py`. It rejects scheduler changes,
project IAM, destruction, source/secret identity changes and capacity changes.

Admin access to the existing global Meta secret is a separate false-by-default switch
`dashboard_completion_admin_meta_probe`. Stage 2 creates exactly two private DEV preview
APIs, their scoped Vercel invokers and that single scoped secret-access grant.
`scripts/dashboard_completion_preview_guard.py` checks the five-resource stage, immutable
image, server identity, pinned configuration, private invocation and min=0/max=3 capacity.
Passing a guard is not user IAM approval. Saved-plan JSON, binary SHA and exact grant
inventory must be reviewed before apply. Preview federation is separately scoped and
cannot be admitted implicitly by either guard.

The existing production private API services and Vercel production deployment remain
pinned. A future #19.3B Vercel Preview uses only the new private DEV API URLs. No `--prod`
deploy, production promotion, scheduler change or automatic historical extraction is
part of preview acceptance. No min-instance increase or shared PII cache is proposed.

## Outstanding acceptance

- Complete source-addition coverage for absent commerce sources requires its explicit
  commercial adoption contract; it must not be disguised as brand creation.
- Approved lead semantics/identity, personal-data policy decision and Meta purchase
  action definition where not certified.
- Clean commit review and immutable runtime build.
- Exact saved live plans, IAM review, scoped apply and post-plan checks.
- Bounded current catalog/ad enrichment and certified read coverage.
- Authenticated real Preview browser checks (six B2B pages, Admin, drilldowns, loader,
  isolation), screenshots without personal data and measured before/after costs.
- Fresh Data Health acceptance after materialization and unchanged production proof.

Do not declare `MX DATA COMPLETION PREVIEW READY` until these gates are satisfied.

## Offline validation checkpoint

Before immutable build: full Python suite **2,405 passed** (122.20 seconds); Ruff
check/format passed (336 files); mypy passed (183 sources); frontend **319 tests / 29
files** passed; lint, typecheck and format check passed. Next.js 16.3.7 production
build with `--webpack` passed, including 50 static pages and all new BFF routes.
Local Turbopack has an OS process/socket restriction; remote Vercel build remains an
independent acceptance gate. Offline HTTPS Playwright: **6 passed** (16.1 seconds),
using isolated installed Chrome because the packaged headless executable was absent.
No real credentials were rotated or historical work admitted by these tests.

Terraform fmt check and validate passed with Terraform 1.16.0 and locked Google
provider 8.4.0, backend disabled for local validation. No local state was read.
Worktree path/credential-signature scan found no .env, credentials, private keys,
Terraform state/plans, caches or test artifacts among the intended source files.
This scan is an additional check, not a claim of a comprehensive security audit.

### Release composition correction

Release review caught that the worker `foundation` image does not install Gunicorn
or Firebase Admin. Stage 2 now requires a separate immutable `product-api` image
from the same runtime source, using the existing hash-locked product dependencies.
The preview guard explicitly rejects a worker image for HTTP serving. Stage 1 Jobs
retain their worker entrypoints; existing production services remain pinned.

## Stage 1 saved-plan review — not applied

Cloud Shell file: `/tmp/dashboard19b-live/stage1.plan`.
SHA256: `8d10d1db404cac27c950e646a5497fff40ebbd9a9c5f5b6190a5840b2d2671d3`.
The existing saved binary was not regenerated during guard corrections.
Guard result: **70 creates, 14 updates, zero deletes/replacements, zero material drift**.
Nine benign drift records are operational table/job metadata and one unchanged
production federation binding's opaque etag, never a new federation permission.

Scope: 18 new tables, 52 table-scoped IAM grants, four additive nullable Meta schema
updates and ten runtime image/feature updates. No scheduler, production API,
Foundation resource, source identity, credential, Secret Manager or capacity change.
Automatic enrichment and enriched Health enforcement remain disabled at this stage.

| Existing service identity | Read additions | Write additions | Grants |
| --- | --- | --- | --- |
| up-cp-analytics-dev | extension plans | extension units; Registry coverage CAS | 3 |
| up-cp-dispatcher-dev | extension plans and units | none | 2 |
| up-cp-intelligence-dev | extension plans and units | none | 2 |
| up-cp-meta-dev | extension plans | extension units; creative daily/current versions | 4 |
| up-cp-upzero-dev | extension plans | extension units; 13 catalog RAW/CORE/version/observation tables | 15 |
| up-data-health-dev | catalog observations and four version tables | none | 5 |
| up-install-orchestrator-dev | included in existing scoped writer contract | extension plans and units | 2 |
| up-product-admin-dev | initial plans/units, checkpoints/runs and three Analytics evidence tables | extension plans/units; integration operations | 10 |
| up-product-read-dev | five catalog evidence tables; Meta binding/ads/creative daily; quality results | none | 9 |

Read grants use `roles/bigquery.dataViewer`; write grants use the existing custom
`upControlPlaneDataWriter_dev` role at table scope. No project/dataset-wide write
permission is added. Exact per-table inventory is in the private Cloud Shell file
`/tmp/dashboard19b-live/stage1-review.json`.

The live plan exposed BigQuery's `INTEGER` spelling for existing `INT64` fields.
The guard compares only that equivalent spelling; required modes, removal, type
changes and extra grants remain rejected. It also resolves the distinct Analytics
schema catalog and publication metadata. **44 focused release-guard tests passed**;
ruff, format, mypy and diff checks passed after these changes.

### Immutable builds

Worker source commit: `d455758628f59b0318301cffac62097677e2c677`.
Cloud Build: `f7c2dad7-951e-4432-8aa8-acf964c7aab2`, SUCCESS.
Worker digest: `sha256:1f99d1e0aa6b994c7e7b7ed4528f235dee0b0549a86ef78417ca05b890e050b0`.

Product API source commit: `df1b7d997d707c36ff8e9f8e13cd0ad0e0cef767`.
Cloud Build: `68476218-629b-472b-8e82-d3c51451472b`, SUCCESS.
Product digest: `sha256:ac0acc7e620cec6f17b171a4ddcd470c33f32d7a67735dbb04da941238c6c365`.
Runtime source is identical between these two commits; the second commit corrects
only preview deployment composition/guard/docs/tests. Both Artifact Registry
digests equal the corresponding build digest. Upload allowlist: 291 files,
zero forbidden paths. No credentials, customer data or Terraform state uploaded.

Stage 1 awaits action-time confirmation because applying the saved plan creates
52 security-sensitive data access grants. Stage 2 private preview APIs and the
Admin global Meta probe grant are separately reviewed and **not** authorized by
this Stage 1 plan. No live preview acceptance or latency improvement is claimed.
