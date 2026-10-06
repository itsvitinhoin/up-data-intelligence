# CHANGE #19.3C — Manager Dashboard V2 and private preview preparation

## Boundary

Branch `change-19-3c-manager-dashboard-v2`, from
`317f0f6865602e5415a8f774bb1e61ceee3d9b2f`. The accepted Stage 1 foundation
is preserved: 18 tables, 52 table grants, four additive Meta fields, ten Job
updates, no post-plan changes. This change stops before Stage 2 apply and any
credentialed source probe, enrichment, extension execution or historical extraction.
Production and scheduler configuration are preserved.

## Templates and visual system

`frontend/src/dashboard/registry.ts` owns controlled template, metric, widget,
filter and availability registries. Templates are `current-standard.v1`,
`b2b-standard.v2` and `b2c-standard.v2`. Definitions contain labels, metric IDs,
position, visibility and approved sizes. They contain no SQL or executable business
formulas. Presenters project certified HTTP contracts; backend semantics remain authoritative.

The existing Shell, MetricCard, PageHead, Panel, Choice, DataTable, Sheet,
OrderDialog, ProductDrawer, charts and exports are reused. V1 remains the default
when the server-only `UP_DASHBOARD_TEMPLATE` flag is absent. `manager-v2` selects
V2 in an isolated preview. Admins can switch back to V1 in Personalizar Dashboard.
Old routes remain, with explicit V2 aliases rather than deletion.

B2B V2 groups: Visão Geral; ERP (seven pages); Performance (overview, funnel,
new customers, repurchase, registrations, ads, journey); Ecommerce (nine pages);
WhatsApp (three pages). ERP and WhatsApp remain visible with unavailable states.
B2C: Visão Geral, Pedidos, Clientes (overview/list), Produtos (analysis/stock),
Performance (platforms/funnel/campaigns/monthly history). All 28 JINI concepts
have separate registry IDs. A Forecast widget identity is reserved only; no forecast
calculation or forecast page is implemented.

V2 executive, Performance, acquisition and repurchase layouts expose the requested
14/17/13/14 slots. Unsupported paid amounts, ERP/Google/TikTok inputs, registration
cohorts, reactivation, lifetime LTV and definitive CAC remain NULL/—. Fulfilled is
never mapped to paid; first observed is never mapped to confirmed acquisition.
Certified Meta spend maps only to Meta spend, never total multi-platform spend.
Observed recurring buyers are labelled with their observed-history basis.

Funnel stages/transitions are displayed with explicit unavailable values where
source/period semantics do not match. Certified cart/checkout rates come from the
backend, without frontend business formulas. Purchase progression supports six
separate slots; the existing 5+ aggregate is not mislabelled as fifth/sixth purchase.
Existing observed cohort/retention visuals remain below, with their original labels.
Monthly B2C history uses the existing DataTable/export components with NULL cells
until monthly publication evidence exists. Unsupported platforms can be selected
but never present another platform's numbers. V2 cards omit decorative sparklines.

Personalization supports visibility, order, full/half size, landing page and page/
template reset. Preferences are **session-memory only**, keyed by authenticated
user, tenant, workspace and template. Invalid widget IDs/sizes are rejected.
No new preferences table/IAM is added to the exact five-resource Stage 2 plan.
Durable cross-session preferences require separate reviewed infrastructure and
server-side authorization; they are not claimed as delivered here.

## Data contracts and detail security

Existing #19.3B adapters/readers are retained: exact catalog identity, product
family/variants, color/size/hex, certified stock, exact parent order/version items,
requested versus fulfilled, current catalog provenance, creative/ad daily evidence,
Meta previews/rankings and grouped journey events. Their new protected tables are
not populated by this change. No fuzzy product/SKU identity or demo images in live mode.

New contact projection: `GET /v1/customers/{id}/contact`, exposed only through the
live authenticated same-origin BFF. Private Python API resolves the canonical
workspace, then DashboardService authorizes the grant before constructing its reader.
The query is parameterized and bounded, selects only cpf/cnpj/email/phone plus
identity and observation timestamp from the exact store/customer CORE row. Missing
identity returns 404; duplicate/mismatched identity fails closed. Metadata labels
`current_core_profile`; this is not historical order-contact evidence.

Lists, commercial summaries and Intelligence DTOs continue to exclude PII. The
contact is read only after opening its detail dialog, never prefetched or placed in
React Query/localStorage/sessionStorage, discarded on close/unmount/scope switch,
and excluded from print/PDF. Responses are `private, no-store`; no PII in SQL values,
logs, timings, acceptance screenshots or reports. No secret reference/value is added
to any browser response. Contact is not exposed by the loopback preview-token route.

Admin retains compact brand cards and actions Ver Dashboard, Configurar Integrações,
Saúde das Integrações, Extrair Histórico. Existing secret is “Configurada”, never
prefilled; future providers reject credentials. Health reads safe operational metadata
on demand. Historical requests use bounded Installation V2 extension plans; no
actual request or execution is submitted during this change.

## Lead semantic decision

**METRIC SEMANTICS DECISION REQUIRED**

Existing read-only audit observed 873 `register_submitted` and 595
`register_approved` facts. These are event counts, not unique-person lead counts.
Source fields: `event_name`, `occurred_at`, `user_id`, canonical identity resolution;
orders and purchase sequence provide qualifying order timestamps/identity. Customer
current status cannot establish historical approval time. No new source probe is run.

- **Option A — registration cohort:** distinct canonical people whose first valid
  registration submission falls in the selected period. Approved leads are members
  of that same cohort with a proved approval by the report cutoff. Qualification =
  approved cohort / submitted cohort × 100. Conversion = approved cohort members
  with a qualifying order after approval by cutoff / approved cohort × 100.
  Each person counts once. Approval/order may occur after registration month, so
  30/60/90-day cells require maturity and known registration/approval evidence.
- **Option B — operational event-period cohorts:** distinct submitters in the period,
  distinct people approved in the period, conversion of the approval-period cohort
  by cutoff. Submission and approval cohorts are different. Dividing period approvals
  by period submissions is a throughput ratio, potentially above 100%, not a cohort
  qualification rate. Cancellation/current-status changes cannot backdate approval.

Recommendation: Option A for qualification/acquisition cohorts, with separate
explicit approval-period conversion if needed operationally. Confirm the canonical
person key, first/repeated-registration rule and cancelled/reapproved behavior before
materializing lead metrics. Until then all definitive lead cards/cohorts stay NULL.
Neither option proves payment. This decision does not block template/Admin/preview work.
Meta purchase-action inspection is prepared by the existing connector/probe contract,
but remains pending credentialed Stage 2 acceptance; no action type is guessed from
commercial influence and no probe is executed.

## Loader and performance

`public/media/up-loader.mp4` is byte-identical to Downloads/Sample 5.mp4:
SHA256 `bcd1d0c256ea327db2043fd51977f151d4965d8b3aa89226083e18e19151138e`.
Autoplay/muted/inline/loop, playback rate 1.5. Cold publication loads use the video
inside the existing Shell; secondary/refetch widgets use skeletons. Failure and
reduced-motion paths retain accessible fallback.

Server-Timing exposes numeric durations only: auth, WIF, upstream/private API,
BigQuery, serialization, API total, BFF serialization and BFF total. Whitelists
strip descriptions, unknown keys, scope, identifiers, PII and credentials.

Read-only DEV samples, certified Analytics generation 6 and Intelligence generation
4, window 2026-09-01 → 2026-10-05 exclusive, history_complete=false:

| Surface | Queries | Bytes processed | Cache hits | Query duration ms |
| --- | ---: | ---: | ---: | ---: |
| Overview | 7 | 56,559 | 0 | 9,720 |
| Orders | 6 | 48,940 | 0 | 6,575 |
| Customers | 6 | 211,091 | 0 | 6,180 |
| Products | 8 | 295,227 | 0 | 8,257 |
| Performance | 7 | 82,982 | 0 | 7,096 |
| Meta campaigns | 7 | 74,270 | 0 | 6,949 |

Includes canonical Registry/HEAD/RECEIPT authority reads. Each query ceiling is
256MiB, existing total guard 8GiB, timeout 60s; no unlimited reads. These are direct
service cold-read measurements, **not deployed preview latency or production SLO**.
BQ cache is explicitly disabled. No measurement is claimed for uncreated preview APIs.

Existing customer summary/product family/campaign reads operate in bounded sets,
not one request per list row. Retention submodels already share one statement;
product variant catalog lookup is batched. Existing publication-tied Analytics and
Intelligence materializations are the read models. No extra materialization/table
or authorization cache is introduced. Hover/focus prefetch allows only certified
aggregate V2 pages, keyed by user/scope/publication/period; excludes PII, lists,
detail, ERP/WhatsApp and B2C. Session/workspace changes clear the query cache.

## Preview release preparation

Required preview-only variables after approved Stage 2 apply:
`UP_DASHBOARD_TEMPLATE=manager-v2`, `UP_READ_SERVICE_URL=<private preview Read URL>`,
`UP_ADMIN_SERVICE_URL=<private preview Admin URL>`, existing authenticated live
Firebase/WIF settings. Never modify Vercel production or expose service credentials.
No functional preview is claimed while private APIs are absent.

Stage 2 must pass `scripts/dashboard_completion_preview_guard.py`: exactly two
private DEV preview services, two service-scoped Vercel invoker grants, one accessor
on the existing global Meta secret. Approved region/accounts, min=0/max=3, immutable
product-api image; never worker image, public invoker, wildcard or extra IAM.
Automatic enrichment and enriched health remain false; no extension/backfill work runs.

## Validation and release evidence

Final test counts, immutable image evidence and saved plan path/SHA are recorded in
the release addendum below. Offline screenshots are synthetic contracts explicitly;
they are not proof of deployed real-data acceptance. V1 restoration/security/loader
E2E and V2 B2B/B2C E2E are required before committing the release source.

## Offline acceptance

- Python full suite: **2,423 passed** in 124.30s. Ruff check/format: PASS
  (339 files); mypy: PASS (183 source files); diff check: PASS.
- Frontend: **328 passed / 30 files**; ESLint, typecheck and Prettier check: PASS.
- Playwright synthetic, no external/source API calls: **11 passed**. Manager B2B
  3 (15.0s), B2C 1 (7.3s), V1 restoration/auth/loader 6 (10.7s), secure onboarding
  1 (2.6s). Personalization hide/reset/reorder/full-half/landing selection, actual
  V1 switch, error termination, contact on-demand/clear, order/product dialogs,
  campaign detail, search, workspace, mobile and loader are exercised.
- Production frontend build: **PASS using `npm run build -- --webpack`**. The
  requested default `npm run build` was attempted: Turbopack failed creating a
  process/port (`Operation not permitted`) in this host. No application workaround
  or dependency change was made; the production Webpack compile/typecheck/routes
  completed. Default Turbopack build is not claimed as validated.
- A regression test now covers error-before-empty-data branching: a failed funnel
  ends in an explicit failure rather than an endless skeleton. The older onboarding
  test's labels were aligned with the approved compact lifecycle card (INSTALLING,
  unknown progress), preserving credential clearing and no-dashboard-query assertions.

Synthetic screenshot set: `b2b-overview`, `b2b-performance`, `b2b-funnel`,
`b2b-new-customers`, `b2b-repurchase`, `b2b-ecommerce`, `b2b-erp`, `b2b-whatsapp`,
`admin`, `b2c-overview`, `b2c-clients-overview`, `b2c-clients`, `b2c-products`,
`b2c-stock`, `b2c-performance`, `b2c-history`. Sidebar is included in each capture.
Private/local evidence directory:
`/Users/victorin/.codex/visualizations/2026/09/28/01a0e92f-dfe4-7e70-92ed-1f2d3eebd906/manager-v2`.
No real contact, source payload or credential is captured.

## Read-only live safety

2026-10-05 audit: Registry ACTIVE/sync=true, revision 12, facts_complete=true,
history_complete=false, Facts coverage through 2026-10-05T03:00Z. Certified
Analytics generation 6 HEAD/RECEIPT identity matches; Sep 1 → Oct 5 exclusive.
Latest Data Health: **16 rules, 0 blocking failures**, checked at
2026-10-05T07:00:10.073507Z. The metadata audit query ceiling was 64MiB,
30s timeout; billed 30MiB. No business mutation or source/secret-value read.

Schedulers unchanged: UP Zero 03 UTC, Meta 04, Analytics 05, Intelligence 06,
Data Health 07 and Installation every minute remain ENABLED. Foundation sync,
reconcile and quality remain PAUSED. Production serving/images/Vercel are unchanged.

## Immutable release artifacts

Runtime/frontend source: `7af97a10fd6e2427a4c578ea1203ddb070bc34d2`, clean and
pushed before Cloud Build. Product API build `7445b18c-71da-4849-9f78-ff176a06feeb`
completed SUCCESS. Build digest and independently inspected Artifact Registry
digest match:

```text
southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/product-api@sha256:e9150c789b7c2d8ff730021ead7a396c678379bdfe76b8d3044e4ae9e43b6b8a
```

The build uses the existing DEV build identity and allowlisted runtime context,
with an offline Gunicorn version smoke. No serving deployment or source probe ran.
No credential, saved plan/state, customer export, cache or local helper entered Git
or the image context. Static browser output was scanned for private keys/service
credentials. No new dependency was introduced.

Worker runtime is unchanged and reused: source
`d455758628f59b0318301cffac62097677e2c677`, build
`f7c2dad7-951e-4432-8aa8-acf964c7aab2`, digest
`sha256:1f99d1e0aa6b994c7e7b7ed4528f235dee0b0549a86ef78417ca05b890e050b0`.
The new private preview services use product-api, never this worker image.

The strict Stage 2 guard rejected the first plan because provider-computed HTTP
port name was unknown, although the five-resource scope was exact. Infrastructure
commit `207a3cf4997540754b546b835b7e58fda65bcbef` declares `name = http1`
explicitly for the preview ports. It changes no existing service and does not relax
the guard. The guard regression suite passed **20 tests**. Runtime/frontend files
remain byte-identical to the immutable product API source commit.

## Final Stage 2 saved plan — unapplied

Cloud Shell path (not a local Mac file):
`/home/upagency_oficial/dashboard19c-review/stage2.plan`

SHA256:
`bcb1f3968086f728f7f7367946b20a4fbf8abb5c09961932a06422ac6a8ec509`

Terraform fmt/validate PASS. `scripts/dashboard_completion_preview_guard.py`
executed against the actual saved-plan JSON: PASS. Exactly **5 creates, 0 updates,
0 deletes, 0 replacements**. Provider operational drift: 128 allowlisted benign
entries, **0 material drift**; no drift-driven resource mutation is proposed.

| Terraform address | Exact proposed resource / privilege |
| --- | --- |
| `google_cloud_run_v2_service.completion_preview_api["read"]` | Private `up-read-api-data-preview`, existing `up-product-read-dev` identity |
| `google_cloud_run_v2_service.completion_preview_api["admin"]` | Private `up-admin-api-data-preview`, existing `up-product-admin-dev` identity |
| `google_cloud_run_v2_service_iam_member.completion_preview_invoker["read"]` | `roles/run.invoker`, existing `up-product-vercel-dev`, Read preview service only |
| `google_cloud_run_v2_service_iam_member.completion_preview_invoker["admin"]` | Same existing Vercel identity, Admin preview service only |
| `google_secret_manager_secret_iam_member.completion_admin_meta_probe[0]` | `roles/secretmanager.secretAccessor`, `up-product-admin-dev`, existing `up-intelligence-meta-global-token` only |

Both services are DEV southamerica-east1, min=0/max=3, concurrency=8,
120s timeout, 1 CPU/1GiB, deletion protection, IAM invoker enforcement and no public
invoker. Product API digest is the immutable release artifact above. Existing
server subject key/pinned Meta version are reused privately; no value is printed
or copied to frontend. Existing approved preview federation is preserved, not
expanded; production federation and production APIs are unchanged.

Preview variables are documented above for the post-apply phase. This round does
not modify Vercel production, deploy a functional real preview, create either
service or grant the Admin secret accessor. A functional real preview is still
pending exact saved-plan approval/apply and authenticated acceptance.

The binary, JSON and private tfvars remain outside Git/build context with private
permissions. Revalidate SHA and plan/state before an eventual approved apply;
no apply command is executed by this change. Automatic enrichment=false,
enriched health=false, no catalog/creative extension, no Meta credentialed probe,
no historical extraction, no business-data mutation, no scheduler or production
change. Stop boundary reached.
