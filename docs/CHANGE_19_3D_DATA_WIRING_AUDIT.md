# CHANGE #19.3D — Manager V2 data wiring acceptance

The implementation preserves Manager V2 page/section order and existing bodies. It does not promote production, start historical extraction or add another provider. The initial 21-column matrix was created before changing values; its implementation section is the authoritative local mapping audit.

## Implemented and deployed to private Preview

81 metric IDs map explicitly to read resource, response path, formatter and coverage rule; 21 widgets and 10 reused body contracts are enumerated and tested. Resource incompatibility cannot borrow a page's Overview value. NULL stays unavailable and a covered zero stays zero. Existing decimal monetary text remains exact in transport and monthly aggregation.

Operational registration readers deduplicate canonical fact IDs independently for submitted and approved events inside the selected local period. Approval backlog is retained and qualification may exceed 100%. Conversion requires an unambiguous event→order→customer relation plus qualifying purchase after approval and before both selected exclusive end and certified as_of. Missing identity keeps conversion NULL. MX currently has 588 unresolved approvals, so no conversion value is fabricated.

Overview/acquisition expose operational counts; retention exposes observed recurring orders, revenue/ticket, mean/median days. Monthly history retains six original groups and distinct monthly customers. Funnel uses compatible session rates and exact purchase/product/purchase_item events. Journey, commercial order rows and geography retain their existing authorized read contracts. Seller-period aggregation is explicitly still not certified.

Contacts are authorized on demand only. Order snapshot reads use the official nested wholesale/retail document and geography paths, independently from the current customer profile; no profile fallback is merged. Lists/exports never acquire these fields automatically.

Basic Meta reads remain independent of creative previews. Additional campaign/day link-clicks, landing-page views and reach-sum reads use the Intelligence source snapshot, exact account and configuration. Landing-page-view NUMERIC is transported as decimal text, not rounded to an integer. Reach sum is not unique period reach. Actions/action_values are absent in the currently persisted 35 campaign/day rows; an empty action list is not a claim of source absence.

The new source reads are gated by the existing completion feature flag used by private Preview; production has that feature off. This flag does not assert catalog completeness. Queries remain parameterized, read-only, store-scoped and budgeted by the existing read repository: 256 MiB maximum/query and 8 GiB per-request reservation ceiling in the deployed product API. The two additional table reads are analytics_events and meta_live_insights_daily. The IAM member is shared by existing Read runtimes. The user explicitly approved this security impact before apply; the two new grants are table-scoped READ only. Production images and feature flags remain unchanged.

## B2C review

An authenticated internal administrator can select B2C Demo in personalization and return to B2B Live. Demo uses a separate Providers/QueryClient instance and deterministic local fixtures. It never creates a live B2C grant or sends demo data through BFF/Read APIs. Real B2C failures never fall back to demo. The persistent `B2C · DADOS DEMONSTRATIVOS` indicator survives print/export. Hard reload exits the in-memory review and returns to the authenticated live boundary.

Synthetic sales, approved/cancelled revenue, orders, customers, media spend, ROAS/CAC/LTV and sessions/cart/checkout metrics share one projection. No random values. Existing details, filters, monthly history, campaigns and personalization remain navigable. Offline authenticated acceptance measured zero `/api/` requests after entry into the B2C review, including navigation across all review pages.

## Read-only live evidence

Observed on 2026-10-06, with parameterized 1 GiB/query / 128 GiB/execution guards; reports contain aggregate counts only.

- Analytics generation 6: 2026-09-01 → 2026-10-05 exclusive; as_of 2026-10-05T03:00Z. Intelligence generation 4, base 6. history_complete=false.
- Selected-period canonical registration events: 864 submitted, 588 approved; identity conflicts and missing event identities zero. Qualification 68.055555…%. All approvals lack an order ID: conversion unavailable.
- 309 purchase_item events, invalid identities zero. 18 observed qualifying buyers/orders; zero observed recurring buyers.
- 24 order snapshots: all 24 contain email, phone and nested wholesale CNPJ. No contact values were printed.
- Current catalog: 336 products, 3120 variants, 2 attributes, 2440 inventory rows at the aggregate sample. Existing catalog extension remains PARTIAL/RUNNING with zero recorded failures. Its inventory counters continued advancing; no second extraction was launched.
- Current Meta: 35 campaign/day rows; landing-page views populated on 35, actions/action_values populated on zero. Source capability/enrichment remains B, never E.
- Persisted Data Health at 07:00Z has six blocking findings: analytics_cutoff_current, no_nonterminal_previous_day_runs, no_pending_raw, upzero_customers_fresh, upzero_orders_covered, upzero_facts_covered. Prior 2026-10-05 Health was green.
- Later operational snapshot has zero pending RAW across all checkpoint groups; only inventory checkpoint/run is running. Customers/orders/facts last completed 2026-10-05. The earlier pending-RAW alert must not be represented as current pending RAW. No checkpoint/run/lease was repaired and no business worker was launched.

## Remaining ingestion and certification

Existing bounded inventory work must finish and certify its catalog observation before current-stock/grade completeness can be asserted. Product names/references, exact variant IDs and official images/attribute terms remain subject to that resource's certification and exact identity coverage. Missing image/color fields are not invented and do not imply the source lacks them.

Official creative preview, ad-level insights, actions and action_values enrichment remains uncompleted in live evidence. No overlapping purchase action definition is selected. Recovered or partial data is not freshness proof. The Admin health section exposes durable coverage/resource status, not secrets or payload.

## History and future connectors

Confirmed first-ever buyers, definitive lifetime CAC/LTV/full retention/reactivation require separately authorized earlier history. Minimum useful analysis window: 2025-01-01 → 2026-09-01, then current coverage; definitive lifetime classification still requires all earlier source history, so the proposed date alone is not proof. No historical backfill was started.

ERP paid/direct sales, ERP stock/sellers, Google, TikTok and WhatsApp require separate certified connectors. Fulfilled revenue is never paid. Meta influence is never provider attribution. A total across all media providers is unavailable until all relevant platforms are certified.

## User decisions

No further lead-definition decision is required. The initial CORE inspection alone was insufficient to ask a Meta purchase question. The later official read-only Graph inspection below now supplies actual sanitized alternatives and an explicit outstanding purchase-selector decision. Reactivation additionally requires a business inactivity threshold alongside history; neither decision authorizes historical extraction now.

## Deployment and performance gate

The exact saved plan was applied once after explicit approval: SHA256 `52c88ff3421da8e56544a9db9314e2b3666560d63f36e26b3f5f09c275a333ff`; two private Preview image updates and two table READ grants, zero deletes/replacements. Apply exit 0; fresh post-plan exit 0 (No changes); Terraform fmt/validate passed. Protected Job templates, production service templates, Preview service invoker IAM and all nine scheduler states matched the before snapshot. Production Read identity gained only the two expressly approved table READ grants; production code and flags were not deployed. No success claim for complete live data wiring or current freshness is made while Health/enrichment acceptance is pending.

Existing Server-Timing instrumentation is retained. Numeric opt-in Preview diagnostics are implemented; final authenticated-host measurements for auth/WIF/API/BQ/serialization remain blocked by the Vercel SSO failure recorded below. No end-to-end dominant latency or per-page request count is invented. Internal audit reads share the existing React Query keys to deduplicate card/widget readers. Contact calls occur only when a detail is opened.

## Validation

Full Python: 2443 passed. Focused dashboard: 222 passed. Ruff and mypy: pass (185 source files). Frontend: 335 tests in 31 files, lint/typecheck/format pass. Next.js webpack production build passes; Turbopack local build encountered environment EPERM while opening its PostCSS process port. Authenticated offline E2E: 4 passed; demo E2E: 1 passed. Final validation is repeated after the last changes.

## Preview deployment provenance

- API source: `151670a650b6bfb10e12b9dce534870067e4429b`.
- Cloud Build: `6f3395a6-2514-4849-9a4d-82cde27508c9`, SUCCESS.
- Build/Artifact Registry digest: `sha256:db89ea80acbccb1bcaf10542d52d01b24dd81b30e7d513b24f7fcbd7aab2b11f`, equal.
- Frontend source: `7a50e341dcded6ebed161d538b1bf41f1f4d7306`; follow-up fixes only the synthetic paid-gauge percentage contract and adds a coherence assertion. No Python/infra change after the API image source.
- Vercel Preview: https://up-data-intelligence-fyjm8gjj0-victorcheunin-6445s-projects.vercel.app/b2b . Deployment exit 0; Vercel production Next/Turbopack build passed. Production alias was not promoted.
- Post-gauge regression: frontend 335/335 tests; lint/typecheck/format and local webpack production build pass; demo E2E 1/1 in 12.2s.
- The approved operator signed in successfully in the new Preview. Real B2B overview, registrations, funnel, retention, order/product/customer tables have been observed. Complete navigation/B2C review and timing acceptance are ongoing; no client/contact values are included in this report.

## Real reader measurements (not authenticated browser timing)

One read-only pass of the deployed API source against canonical live metadata returned Analytics generation 6 and Intelligence generation 4/base 6. It is a domain-reader check, not evidence of an authenticated HTTP or browser session.

| Resource | Query count | BigQuery duration ms | Bytes processed | Result |
| --- | ---: | ---: | ---: | --- |
| Overview | 8 | 9699 | 28480526 | 200 |
| Orders | 6 | 6196 | 48940 | 22 rows |
| Customers | 6 | 6044 | 211235 | 18 rows |
| Products | 8 | 8403 | 1920326 | First 100 rows |
| Retention | 7 | 7055 | 52908 | 200 |
| Geography | 6 | 5918 | 49731 | 9 states; 22/22 orders mapped; monetary delta 0 |
| Acquisition | 8 | 8028 | 28475206 | 200 |
| Performance | 8 | 8108 | 90409 | 200 |
| Funnel | 7 | 6979 | 28473144 | 200 |
| Order contact | 6 | 5964 | 46891 | Snapshot document/email/phone present; no values reported |

Overview aggregate: requested `99033.96`, fulfilled `85384.51`, 22 orders. Operational leads: 864 submitted / 588 approved; qualification `68.05555555555555555555555556`; conversion NULL. Customer360, timeline, customer product profile and campaign detail readers also returned valid envelopes. Covered empty campaign-customer/order lists are distinct from unavailable data.

The first helper used generic ReadBudget defaults (1 GiB/query, 8 GiB total), which reserved only eight calls and rejected order/product detail before catalog proof with query_budget_exceeded. This is a harness configuration mismatch, not proof of deployed failure: product runtime uses 256 MiB/query and 8 GiB total. A second pass uses exactly those existing runtime limits; no application budget was raised.

The deployed invalid-token session exchange returned 401. This confirms that invalid authentication was rejected; it does not establish valid-user acceptance. auth/WIF/API/serialization and browser page-request measurements remain pending valid login, so no end-to-end dominant component or SLO is claimed.

## Authenticated browser follow-up

Live navigation exposed inherited Overview body slots still hardcoded NULL. The follow-up maps observed retention ticket/repeat mean directly from the existing customer period query and adds one bounded, parameterized CORE order quantity aggregate at the same read snapshot/certified cutoff. Its order count must reconcile exactly with Analytics; duplicate/invalid IDs fail closed. Requested and fulfilled pieces remain separate, NULL stays unknown, and a fully covered empty period returns zero pieces. No ingestion/commercial/publication semantics changed. No count of “fulfilled orders” is inferred from quantities, approved status or paid status.

The funnel's rates remain the certified session-chain ratios. Labels now state those denominators and display percent units, avoiding comparison against raw event counts. Purchase progression share uses the same exact ratio-to-percent conversion.

Preview-only opt-in numeric Server-Timing diagnostics (`UP_READ_TIMING_LOGS`) collect auth/WIF/BQ/API/serialization durations by resource. The allowlist strips descriptions and all scope/entity/payload values; the flag is off by default.

Follow-up offline verification: 2448 Python tests passed in 131.73s; 227 focused dashboard tests; Ruff/format/mypy passed (185 source files). Frontend full validation and immutable Preview release are repeated for this patch. Authenticated offline E2E: 4/4 passed in 20.1s, including isolated B2C review/return.

Frontend patch regression: 337 tests in 32 files; lint/typecheck/format and webpack production build passed. No new auth/source dependency was added.


## Final immutable Preview releases and precise acceptance boundary

The inherited Overview/funnel/progression follow-up was committed as `35b184abc974d8a54cd93325f239310fc51db27f`. Cloud Build `7bdcd0eb-8c63-4416-bc98-0501cfdcc3ef` succeeded. Build and Artifact Registry agree on `sha256:17237f16ea0b02fbe61d1a4b99e95851f7de96802888562fc89be0fe739a344f`.

Saved `wiring19d2.plan`, SHA256 `74f148283f957e6653349e58cc5835508a31bb9f8ccb61960e7f6a8a141068f5`, was audited and applied exactly once. It contained precisely two private Preview API image updates, zero creates/deletes/replacements/IAM changes. Apply exit 0; post-plan exit 0 / No changes; Terraform fmt/validate passed. Protected normal Job templates, production services, Preview invoker IAM and all nine scheduler states matched the prior inventory. No production image was updated.

A final direct read with the product's existing 256 MiB/query, 8 GiB/request and 60s transport limits verified generation 6, September 1 to October 5 exclusive:

| Check | Result |
| --- | --- |
| Overview | HTTP-domain envelope 200; 9 queries; 11,583 ms BigQuery duration; 28,481,626 bytes processed |
| Orders | 200; 22 rows; 6 queries; 6,540 ms BigQuery duration; 48,940 bytes processed |
| Requested / fulfilled revenue | `99033.96` / `85384.51` |
| Requested / fulfilled pieces | 404 / 349; exact parity with all 22 order rows |
| Requested pieces/order | `18.36363636363636363636363636` |
| Observed retention ticket / repeat days | NULL / NULL; zero recurring qualifying orders, not missing-to-zero substitution |

The second full read pass using those runtime limits returned valid envelopes for all 22 resources, including order/product detail, customer summary/360/timeline/products, campaign detail/customers/orders, selected-period performance and restricted order contact. The original generic-budget harness rejection was not reproduced with the actual runtime budget. These are domain-reader checks, not authentication or browser timing.

Actual authenticated navigation on the `fyjm8gjj0` Preview covered B2B Overview; Performance overview/funnel/new customers/repurchase/registrations/ads/journey; Ecommerce overview/orders/products/stock/sellers/geography/customer intelligence/monthly history. Journey returned its authorized customer table independently of catalog certification. Seller-period projection remained explicitly unavailable. B2C was entered through Admin personalization, navigated across all ten demo routes, displayed its persistent demonstration banner and returned to the real MX B2B context. No customer/contact values or screenshots containing them are included.

That browser pass also exposed a second strict-envelope bug: backend contact responses contain the canonical `pagination: null`, while the frontend contact decoder had allowed only data/metadata. The UI correctly failed closed instead of exposing an unvalidated payload, but the authorized detail was unusable. Commit `5f8e8e4d03b296156d8ed36d664cc708992e8ea9` accepts absent/null pagination for this unpaged projection and continues rejecting non-null pagination, extra envelope fields and credential/payload extras. No backend change or additional Terraform deployment was needed.

Final frontend source is `5f8e8e4d03b296156d8ed36d664cc708992e8ea9`, Vercel deployment `dpl_62ioNbKKSnYzhE7GHx1pacDa2xwS`, status Ready. Its Next/Turbopack production build passed. Original deployment URL: https://up-data-intelligence-i61omxzms-victorcheunin-6445s-projects.vercel.app/b2b . Stable **Preview-only** alias: https://up-data-intelligence-19-3d.vercel.app/b2b . Production alias was not changed.

**Remaining browser acceptance blocker:** Vercel's own protected-preview `sso-api` returns `FUNCTION_INVOCATION_FAILED` before the dashboard on both the final deployment URL and stable alias. One normal reload did not resolve it. Deployment protection was not disabled or bypassed. The final host's authenticated contact display, updated Overview/progression display and numeric auth/WIF/API timing measurements are therefore pending, rather than claimed as passed. The prior authenticated Preview remains available. Its genuine B2B/B2C results do not stand in for unexecuted final-host acceptance.

Final frontend verification after the contact fix: 337 tests / 32 files, lint/typecheck/format pass; local webpack production build pass; four authenticated offline E2E passed in 20.1s, including isolated demo entry/all-route navigation/return with zero API calls during demo. Python remains 2448 passed in 131.73s; dashboard 227 passed; Ruff/format/mypy pass (185 source files). Diff whitespace validation passes.

## Final current enrichment / Health snapshot

Catalog products 336, variants 3120, attributes 2, inventory 2667. The already-existing catalog extension remains PARTIAL / RUNNING, 2680 pages and 6119 records, zero failures/error code. No duplicate extraction or manual worker was launched. Current catalog completeness and exact labels cannot be certified until the existing snapshot bundle passes its resource proofs. Inventory is current evidence only.

Latest persisted Health remains six blocking findings at 2026-10-06T07:00:12Z; the previous day's result was green. Severity is normalized case-insensitively: the lower-case `alert` rows must not be treated as zero merely because a diagnostic SQL uses upper-case literals. Registry remains revision 12 / ACTIVE / sync=true / facts=true / history=false. Analytics HEAD generation 6 resolves through its receipt (HEAD's own report_from/to are NULL by design); Intelligence generation 4 references base generation 6. No current-day freshness acceptance is asserted.

## Actual Meta action inspection and outstanding semantic decision

A bounded canonical `MetaFoundationLiveConnector` read inspected the pinned account/API/7d_click/impression reporting definition: first the last certified day, then the already-certified September 1–October 4 inclusive period. Both completed in one page (1 and 34 campaign/day rows respectively). The global pinned Meta token was accessed only server-side/in memory; no token, response payload, entity identity or action value was logged or persisted. No RAW/CORE write occurred.

The source returned the following exact action names in the certified period:

```text
add_to_cart, comment, complete_registration, initiate_checkout, landing_page_view,
like, link_click, offsite_add_to_cart_add_20_s_calls,
offsite_complete_registration_add_20_s_calls,
offsite_complete_registration_add_meta_leads,
offsite_content_view_add_20_s_calls, offsite_content_view_add_meta_leads,
offsite_conversion.fb_pixel_add_to_cart,
offsite_conversion.fb_pixel_complete_registration,
offsite_conversion.fb_pixel_initiate_checkout,
offsite_conversion.fb_pixel_purchase, offsite_conversion.fb_pixel_view_content,
offsite_initiate_checkout_add_20_s_calls, offsite_purchase_add_20_s_calls,
omni_add_to_cart, omni_complete_registration, omni_initiated_checkout,
omni_landing_page_view, omni_purchase, omni_view_content,
onsite_conversion.messaging_conversation_replied_7d,
onsite_conversion.messaging_conversation_started_7d,
onsite_conversion.messaging_first_reply,
onsite_conversion.messaging_user_depth_2_message_send,
onsite_conversion.messaging_user_depth_3_message_send,
onsite_conversion.messaging_user_depth_5_message_send,
onsite_conversion.post_net_comment, onsite_conversion.post_net_like,
onsite_conversion.post_net_save, onsite_conversion.post_save,
onsite_conversion.post_unlike, onsite_conversion.post_unsave,
onsite_conversion.total_messaging_connection,
onsite_web_add_to_cart, onsite_web_app_add_to_cart, onsite_web_app_purchase,
onsite_web_app_view_content, onsite_web_initiate_checkout, onsite_web_purchase,
onsite_web_view_content, page_engagement, post, post_engagement,
post_interaction_gross, post_interaction_net, post_reaction, purchase,
video_view, view_content, web_app_in_store_purchase, web_in_store_purchase
```

Exact action_values names:

```text
add_to_cart, offsite_conversion.fb_pixel_add_to_cart,
offsite_conversion.fb_pixel_purchase, offsite_conversion.fb_pixel_view_content,
omni_add_to_cart, omni_purchase, omni_view_content, onsite_web_add_to_cart,
onsite_web_app_add_to_cart, onsite_web_app_purchase, onsite_web_app_view_content,
onsite_web_purchase, onsite_web_view_content, purchase, view_content,
web_app_in_store_purchase, web_in_store_purchase
```

**META PURCHASE SEMANTICS DECISION REQUIRED.** Actual overlapping candidates include `offsite_conversion.fb_pixel_purchase`, `purchase`, `omni_purchase`, `onsite_web_purchase`, `onsite_web_app_purchase`, `web_in_store_purchase` and `web_app_in_store_purchase`; the source also returns `offsite_purchase_add_20_s_calls` in actions. None is summed or selected silently. Suggested explicit selector for the site dashboard: `offsite_conversion.fb_pixel_purchase`, subject to business confirmation. This selection would define Meta-reported purchases/value/CPA/ROAS; it would never turn influence into attribution or fulfilled revenue into paid revenue. Source existence is now demonstrated; currently absent persisted arrays are an ingestion/enrichment gap, not source absence.

Reactivation still needs an inactivity threshold, e.g. 90/120/180 days (suggestion: 90 days), as well as earlier history. No historical extraction is authorized by this recommendation. There is no unanswered lead-definition question.

## Observed Preview requests (bounded multi-page sample)

Vercel runtime logs from the authenticated prior-host navigation were read privately and reduced to request counts, with entity IDs removed. The bounded 200-log-row sample represents 50 unique request IDs; log rows repeat, so they are **not** counted as independent requests. The sample covers 2026-10-06T15:40:09Z–15:53:28Z and contains 39 API requests:

| Resource | Requests | Status |
| --- | ---: | --- |
| Installation | 23 | 200 |
| Overview | 4 | 200 |
| Products | 4 | 200 |
| Acquisition | 1 | 200 |
| Campaigns | 1 | 200 |
| Creatives | 1 | 424, enrichment not certified |
| Customers | 1 | 200 |
| Orders | 1 | 200 |
| Order detail | 1 | 200 |
| Performance | 1 | 200 |
| Contact | 1 | 503, canonical nullable-pagination defect described/fixed above |

These counts span navigation and ongoing installation/enrichment polling, **not one isolated page load**. Background polling is already disabled; the active extension remains RUNNING. Admin coverage uses the same React Query keys as the metric/widget readers, but the baseline publication Overview and selected-period Overview remain distinct reads. No universal zero-duplicate request claim is made. Actual isolated-page counts and auth/WIF/BQ/serialization attribution for the final host remain pending protected-preview access. The measured domain Overview's BigQuery work alone was 11.583s; that does not establish a browser SLO or an end-to-end dominant component.

## Stop boundary

Final source/read/presenter contract fixes and the B2C demo are implemented, tested and deployed to Preview. Final-host authenticated acceptance is blocked by Vercel protected-preview SSO, and current enrichment/freshness is explicitly incomplete. No production promotion, historical backfill, new provider integration, manual RAW/CORE/publication/checkpoint DML, credential update or scheduler modification was performed. The only IAM additions remain the two table READ grants explicitly approved by the user in the first saved plan. The follow-up release had no IAM changes.
