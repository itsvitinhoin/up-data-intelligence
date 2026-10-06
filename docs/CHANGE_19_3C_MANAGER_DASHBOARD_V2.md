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
