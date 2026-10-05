# CHANGE #19.3 — Dashboard restoration

## Authority and deployment boundary

Visual and interaction authority: `797dbbff09df0d8a5d93f3c24332c508b25d6012`.
Starting implementation: `9cc7a726500d9460a09af309ae7cedb8605a4b08` on
`change-19-3-dashboard-restoration`. Production remains the accepted #19.2 deployment.
This change delivers a real-data preview for visual approval; promotion requires explicit approval.
No connector expansion, navigation redesign, second store or installation replan is included.

## Inventory before implementation

The following inventory was made from the canonical Git tree and current feature/component
sources before runtime edits. A = certified backend contract exists; B = persisted evidence
exists but a read projection/presenter is missing; C = source evidence requires promotion;
D = not presently certified. A missing field stays null, including unknown booleans.

All routes retain the shared Application/Shell, fonts, sidebar, workspace picker, top period
picker, PageHead, responsive panel/card grids and portrait PDF export. All original DataTables
retain sorting, pagination and current-page/all-rows spreadsheet export. Exports must use the
same authorized real collection, never a demo collection or silently truncated cursor page.

| Route(s) / original feature | Cards, tables and charts | Filters/search | Original interaction / navigation | Current regression and cause | Support / intended correction | Acceptance |
|---|---|---|---|---|---|---|
| `/b2b` / OverviewPage | Revenue, order, customer and relationship metrics; lead cards; revenue and customer series; efficiency | Period and FiltersBar | Shared workspace and period controls; panel exports | Preview branches replace lead/customer chart sections; original hooks disabled live | A commercial/daily data; B observed relationships; D lead approval and lifetime claims retain widgets with null | Displayed aggregates and metadata equal canonical reads; missing proof remains null |
| `/b2b/commercial` / CommercialPage | Original order metrics and order table | Period, original FiltersBar and order status | Every order link opens OrderDialog; customer link from dialog | RealOrders replaces layout/table and loses dialog; useOrder disabled | A list/metrics/status; B scoped order/items detail; D unapproved contacts unavailable | Open populated detail, reconcile line/order semantics, navigate customer, close |
| `/b2b/acquisition` / AcquisitionPage | Eight acquisition cards, four lead cards, conversion distribution, first observed customer/order tables | Period / FiltersBar | Customer detail and OrderDialog | Separate real summary drops original lists/velocity/lead components | A observed first purchase aggregates; B first-purchase lists; D confirmed new, approval conversion and approval-to-order velocity | Original panels remain; lists clickable; history-sensitive claims null |
| `/b2b/retention` / RetentionDashboard | Four retention cards, daily retention line, five purchase stages, cohort matrix | Period / FiltersBar | Original progress and cohort hover/explanation | Separate real summary changes stages/layout and omits original trend | A retention/cohort/gaps; B stage revenues and daily series; D immature cohort/lifetime unavailable | Counts, transitions, maturity and daily aggregates match materializations |
| `/b2b/customers`, `/customers` / CustomersPage | Four portfolio cards and original customer table | Name/city search, state, segment, media + shared FiltersBar | Customer links; sorting, pagination and exports | RealCustomers substitutes generic table and removes controls; hooks disabled | A safe profile/observed metrics; B full authorized pagination and supported local filters; D definitive new/reactivated/influence without evidence disabled | Search/filter changes real results; customer link works; full export collection |
| `/customers/{id}` / CustomerDetailPage | Original identity header/profile strip, five commercial cards | Customer scope; shared period | Back; Journey/Orders/Products/Marketing tabs; order dialog; product drawer; campaign links; exports | RealCustomer summary replaces template and original customer/order hooks disabled | A summary, customerOrders, customer360, timeline, customerProducts, influence participation; B safe presenters/enrichment; D sensitive contacts and lifetime metrics null | All tabs load certified data or explicit unavailable state; no dead links |
| `/b2b/products`, `/products` / ProductsLegacy | Original four cards, ranking/table, ProductDrawer commercial/stock/grade/color-size panels | Period / FiltersBar; original table sorting | Product opens Sheet; drawer sections; exports | RealProducts generic table has no drawer; hook composition is demo-only | A commercial product aggregates; B exact product_key detail and CORE identifiers/SKU/images; C names if source evidence missing from CORE; D stock/grade/ABC retained unavailable | Real list, stable detail, requested/fulfilled preserved, no synthetic stock |
| `/b2b/geography` / GeographyPage | SVG state map, state ranking, seven state cards, top cities | Metric selector, points toggle, period / FiltersBar | State click/keyboard selects detail; city/state exports; customer navigation | RealGeography returns 424 and replaces map | B order/shipping geographic projection if canonical address evidence proves UF/city; D new/approval/influence counts null | Populated authorized map; shipping semantics documented; aggregate parity |
| `/b2b/performance`, `/media` / InfluencePage | Eight performance cards (four on media), original spend/revenue chart, influenced customer/order/campaign tables | Period / FiltersBar | Customer, order dialog and campaign links; exports | Separate Intelligence summary/table presentation; original resources disabled | A certified Intelligence influence and Meta spend; B original DTO/daily presenters; D attribution/ROI without proof unavailable | Layout retained, explicit influence semantics, actual spend and drill-downs |
| `/performance` / PerformancePage | Original campaign table and notice | Period / FiltersBar | Campaign detail and `/media` navigation | Alternate simplified real page replaces original | A campaign Intelligence; B safe original presenter | Original table, campaign link, correct nullable ratios |
| `/campaigns`, `/campaigns/meta` / CampaignsPage | Eight KPI cards, three creative ranking panels, daily charts, platform/region panels, campaign table | Campaign name, campaign status, shared period/FiltersBar | Campaign detail; creative Sheet when metadata certified; geography link; exports | RealCampaigns replaces MarketingContent; original marketing query calls demo; empty creatives hide entire component | A campaigns/influence; B Meta daily/catalog spend, impressions, clicks, CTR/CPC/CPM and series; D attribution/creative metadata where uncertified | Actual campaign list/search/status, original sections remain, no demo images |
| `/campaigns/{id}` / CampaignDetailPage | Original spend/influence metric cards and participation tables | Authorized campaign/period scope | Customer/Orders tabs, customer links, order detail and exports | Simplified real detail; original campaign hook disabled | A campaign/customer/order participation; B presenters and original dialog | Real scoped detail and participants; no cross-store entity access |

## Field and shared-control classification

| Field/control family | Class | Evidence and treatment |
|---|---|---|
| Requested/fulfilled/cancelled orders and revenue, quantities, commercial status | A | Analytics and current CORE, separate semantics. Fulfilled never means paid. Money transports as decimal text. |
| Order item identity, quantities, unit price, present snapshot/version relationship | B | Existing CORE order_items. Detail must validate parent version and exact item identity; gross item sums are distinct from order totals when discounts/shipping differ. |
| Customer display name/company, current city/state, first/last observed purchase, frequency | A | Approved projection only; current profile does not prove historical shipping geography. |
| CPF/CNPJ, email, phone and full address | D | Not part of approved product projection; original fields remain unavailable. |
| Definitive new customer/CAC/lifetime LTV/history-sensitive segments | D | `history_complete=false`; null, never zero or false. |
| Product key, canonical asset/variant/SKU | A/B | Stable Analytics key plus exact CORE projection; no name/SKU fuzzy matching. Canonical product_id can remain null. |
| Product name/image | D for the current MX source contract | Current CORE has 407 item rows and no name/image. Persisted RAW order item observations (2,752 across versions) contain only id, original_qty, qty, sku, status, unit_price and variant_id. Name/image are not supplied; no approximate name or synthetic image is used. |
| Inventory, grade, colors/sizes, ABC, risk, sell-through | D pending evidence | No inventory certification from commercial order aggregates. Original stock/grade panels retained, unavailable. |
| Geography | B, source evidence confirmed | 24/24 persisted orders have valid canonical UF and nonempty shipping city. The period projection uses shipping geography, not current customer addresses; 1,210/1,219 profiles have state/city. No fuzzy matching or geocoding. |
| Observed influence vs attributed revenue | A / D | Intelligence influence is not Meta attribution. Preserve incomplete definitive influence nullability. |
| Meta campaign ID/name/status, spend, impressions/clicks | A/B | Existing catalog and daily insights; ratios derived only from compatible numerators/denominators. |
| Meta creatives, reach/frequency, platform-attributed revenue/purchases | B/D pending audit | Expose only certified source fields; empty creative evidence does not remove page sections or imply zero. |
| Period | A | Initial login/workspace period comes from current certified window; backend validates requested range. |
| Collection/category/channel shared filters | D unless explicit read support | Preserve controls disabled with explanation. Never silently ignore selected filters. |
| Name/state/status local filters, sort and pagination | A/B | Operate on the complete scoped authorized collection, or explicit backend filters. No partial-page pseudo-search. |
| Search overlay | B | Use live DataApi collection/search with scoped identity, clickable real results. |
| Drawer/dialog lazy reads | B | Correct adapter in live mode; entity ownership validated server-side before business reads. |
| Responsive behavior | A | Preserve original CSS/component breakpoints, horizontal table/stock matrix scrolling and Sheets/Dialogs. Verify desktop/mobile with canonical captures. |

## Audit status

Inventory complete; production reproduction, source evidence audit and acceptance are in progress.
No success or production promotion is claimed by this inventory.


## Production audit before runtime changes

Six affected pages were reproduced in the approved production deployment using the already
authenticated administrator. Counts below are UI observations at the selected certified period,
not claims that a cursor page is the full collection. Production was not redeployed.

| Surface | Observed regression |
|---|---|
| Orders | 22 rendered rows; row actions link customers but no original order dialog; original list filters absent |
| Customers | 18 rendered rows; original name/state/segment/media controls absent |
| Products | 25 rows on the initial cursor page; no product drawer action |
| Geography | Original state-map evidence not populated; Read API returns 424 geography_coverage_not_certified |
| Performance | Alternate presentation; original filters/trend composition absent |
| Meta | One rendered campaign; original search/status/creative/chart panels absent |

Safe read-only canonical composition audit on 2026-10-05 resolved Analytics generation 6,
Intelligence generation 4 and window [2026-09-01, 2026-10-05). Overview returned 200:
requested revenue 99033.96, fulfilled revenue 85384.51, orders requested 22. Orders,
Customers, Products, Performance and Campaigns returned 200; Geography returned the explicit
424 above. Collections used default page size 20; these reads do not establish full export
parity. The latest 16 Data Health rules had zero blocking failures. Generations may advance
through the existing schedulers; final acceptance resolves the then-current publication again.

Canonical Meta ads currently supplies creative_id only, without certified preview/image
metadata. Original creative panels will remain with explicit unavailable coverage, independently
of the actual campaign list and metrics. No additional Meta endpoint or image fixture is used.

A scoped aggregate audit of all 24 current CORE orders found zero item-count mismatches,
zero requested-quantity mismatches, zero fulfilled-quantity mismatches, zero invalid item
statuses and zero orders without current parent-version lines. Item values use original_qty
and current unit_price for requested gross; removed lines fulfill zero. Order totals are net
commercial amounts. The detail contract exposes explicit gross-to-order adjustments instead
of claiming that discounts/shipping are line revenue or payment. No customer IDs, item IDs,
address values or source payloads were emitted in the audit report.

## Implemented read projection and offline validation

The original component tree now uses a nullable LiveDataApi with explicit envelope validation,
publication consistency, complete bounded cursor collection, safe presenters and scoped lazy
order/product reads. The alternate Real* components have been retired. Explicit demo and
unbound loopback preview remain separate; live errors never select the demo adapter.

Order detail preserves current parent-version item identity, quantities and decimal gross/net
adjustments. Products resolve exact Analytics keys against current CORE and count distinct
buyers, without summing daily buyer counts. Shipping geography uses a preaggregated city JOIN;
the initial correlated ARRAY form failed BigQuery validation and was corrected without changing
its grain. Missing customer identity preserves NULL for customer counts. No table/model was
created and no business data was changed.

Read-only candidate-code validation on DEV resolved Analytics 6 / Intelligence 4. Overview,
orders, customers, products, retention, acquisition, customer detail/360/timeline/products,
performance, campaigns and campaign participation returned 200. Order detail had 11 current
items with quantities reconciled. Geography returned nine states, 22 mapped orders, zero
unmapped orders, and exact zero requested/fulfilled monetary delta against the period order
list. Requests retained 1 GiB/query and 8 GiB/request ceilings; no increase was needed.
Latest health evidence: 16 rules, zero findings, checked 2026-10-05T07:00:10.073507Z.

Python full suite: 2,192 passed. Original B2B/Installation offline E2E: 11 passed; authenticated
original-component/authentication E2E: 4 passed. Frontend unit suite, lint, typecheck and format
check passed. Production build passed using Next's webpack compiler; Turbopack in this local
sandbox failed binding its internal port (EPERM). The deployed build must be verified separately.

The restricted infrastructure delta prepares a separate immutable Read API image override and
one table-scoped dataViewer grant for up_core.order_items. Admin, Cloud Run web and all data
Jobs/Schedulers remain pinned to their accepted configuration. Preview federation and exact
preview host must be audited separately before applying any access expansion.

Deployed preview/browser parity and private screenshot comparison remain pending. Production
promotion is not authorized by these offline or direct-read results.

## Immutable build and saved preview plan — awaiting access approval

Implementation commit: `8e684c1b329ffc7450636745bb068e8668222759`.
Build allowlist correction: `3a913ff37f04510105c50cbe8b228776c2270e1d`.
Temporary preview provider configuration: `0f7324665a52a21f85f8c5dedbcd1b426f563b8f`.
These commits are pushed only to `change-19-3-dashboard-restoration`, without PR or merge.

The source archive for the Python image contains only the committed product Dockerfile,
hash-pinned product requirements, runtime source and SQL. Two unsuccessful build attempts
failed during source extraction: the archive had been named `.tgz` without gzip encoding.
The corrected archive uses `git archive --format=tar.gz`, passes `gzip -t`, and has a recorded
manifest. The Docker/Cloud Build allowlists also explicitly include the pinned product build
inputs. A prior submission to the default staging bucket was rejected before building;
the accepted build uses the existing dedicated build-source bucket and build service account.
No IAM expansion was used to make the build succeed.

Successful build: `7dfc898c-90cf-4493-813d-932c9f6582d1`, source commit
`3a913ff37f04510105c50cbe8b228776c2270e1d`.
Image: `southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/product-api@sha256:28042ffc9c48824b9684c913302f84e31d91b2ad43472ad26ef54343e39f63ee`.
Cloud Build and Artifact Registry digests match. The image's network-disabled Gunicorn
version smoke passed. No runtime deployment has occurred at this checkpoint.

Final frontend preview: `dpl_GQxdUxgvTPoUH4vhBs1xsGZmhXPn`,
`https://up-data-intelligence-f6dwylmop-victorcheunin-6445s-projects.vercel.app`.
The actual Vercel `npm run build` with Next 16.3.7 Turbopack passed and the deployment is READY.
Only this branch's preview variables were configured. Production remains
`dpl_EA5gpJfDQuyLS7LqfpuWUw8Km9e5`; no promotion or production environment change occurred.
The preview is not yet authenticated/data/functionally accepted.

The former preview provider is in DELETED state. A separately named temporary provider,
`up-product-vercel-preview-19-3`, avoids reusing the deleted identity. Its trust conditions
remain exactly the approved Vercel team, project, preview environment, subject, issuer and
audience. Vercel's claims do not provide a branch restriction: the IAM trust covers this
project's previews. Branch-scoped application variables do not narrow that IAM trust.
The service account still has only private Read/Admin invocation permissions; verified user
session and canonical workspace grants remain mandatory. Remove temporary preview trust
during a separately approved production promotion.

Saved plan: `/tmp/restore19-3/restoration.plan` in Cloud Shell.
SHA256: `abab6dea2350247f4f8ba11f8a5de48ac1cc0d426378e5156088442ab094b470`.
The strict JSON guard proves exactly three creates and two updates:

| Resource | Approved candidate delta |
|---|---|
| Read API service | Image only; all other attributes preserved |
| Read service `up_core.order_items` grant | Table-scoped `roles/bigquery.dataViewer` |
| Preview WIF provider | Exact project/preview identity above |
| Preview federation member | `roles/iam.workloadIdentityUser` on dedicated invoker SA |
| Firebase Identity Platform | Add only the exact final preview hostname |

No deletes/replacements, Admin/web changes, business table changes, source credentials,
data Jobs or schedulers are included. The plan has not been applied. Action-time browser
confirmation is pending for this access expansion and temporary synthetic CLIENT_USER
acceptance access limited to MX B2B. Final browser parity, exports, screenshots, privacy,
Health and scheduler inventory remain mandatory after deployment; no success claim is made.

Additional completed checks: frontend 276 unit tests across 25 files, lint, typecheck and
Prettier; Python Ruff and formatting (299 files), mypy (164 source files); Terraform fmt and
validate after the temporary provider configuration; `git diff --check`. No test failure is
hidden by the successful remote frontend or image builds.

## Approved preview deployment and browser review — 2026-10-05

The user explicitly approved the permissions required to finish this preview. The exact
saved plan above was hash-verified and applied once: exit 0, three creates, two updates,
zero destroys. The fresh post-apply plan returned `No changes`. The Read API is READY
with the exact immutable digest recorded above. Admin, Cloud Run web, business tables,
Registry, source configuration and data Jobs were preserved. Scheduler inventory remained
six intended data schedulers ENABLED and three Foundation schedulers PAUSED.

The original `f6dwylmop` preview is superseded. Its build succeeded, but deployment
inspection showed that the ten branch-scoped application variables were absent at runtime;
`/api/auth/config` returned 503 before credential verification. A new preview of the same
frontend source supplies the approved routing/public Firebase/federation configuration
explicitly to build and runtime. No source change, production variable change or production
promotion was needed.

Working preview: `dpl_Aeu6sbx8vvJhby2ebPQtkmEtJzZi`, READY,
`https://up-data-intelligence-p484pm1uv-victorcheunin-6445s-projects.vercel.app`.
The remote Next 16.3.7 Turbopack production build passed. Firebase authorized_domains in
the exact saved plan added the earlier hostname; email/password session exchange was
successfully verified on the new hostname. No additional OAuth/redirect-domain acceptance
is claimed. Production remains `dpl_EA5gpJfDQuyLS7LqfpuWUw8Km9e5`.

Browser acceptance used a disposable verified synthetic CLIENT_USER granted only canonical
MX B2B access. Login, session catalog, workspace selection and real source rendering passed.
The original Overview, Orders, Acquisition, Retention, Customers, Products, Geography,
Performance and Meta Ads surfaces loaded. Order and product drawers, customer profile
tabs and campaign participation tabs were exercised. Products showed the full 305-record
collection, rather than stopping at the first API page. Uncertified stock/variant and
lifetime-dependent fields remained unavailable. Empty campaign participation was displayed
without invented rows. Overview and campaign detail were inspected at 390 × 844; the
temporary viewport override was reset.

Rendered Overview requested `99033.96` and fulfilled `85384.51` matched the canonical
read-only result: Analytics generation 6, 22 orders, report_from `2026-09-01`, report_to
`2026-10-05` exclusive, as_of `2026-10-05T03:00:00Z`, history_complete false and
facts_complete true. Current durable Data Health evidence still contained 16 rules and
zero findings, checked `2026-10-05T07:00:10.073507Z`. The final metadata read exited 0.
No UP Zero/Meta source API, Secret Manager value read or business mutation was performed.

Logout returned the preview to its entry screen. The canonical principal-access CLI revoked
the synthetic grant, and its explicitly disposable Firebase user was deleted; cleanup exited
0. No permanent operator account or production session was changed. The working preview
entry screen was left open for the user's visual review.

Acceptance limits remain explicit: CSV export options for the current six rows and all 305
rows were visible, but the browser download-event tool timed out and no downloaded artifact
was captured. Deployed PDF/export artifact verification is still pending; existing offline
portrait PDF/export checks remain the available evidence. Automated access through a Vercel
protection bypass was rejected by automatic approval review and was not executed; the live
checks used normal authenticated browser access. Cookie/storage security checks were covered
by the existing offline authentication E2E, not independently re-inspected on this deployment.
These results establish a usable real-data preview, not completion of all production-promotion
acceptance gates. No frontend production promotion, PR or merge was performed.
