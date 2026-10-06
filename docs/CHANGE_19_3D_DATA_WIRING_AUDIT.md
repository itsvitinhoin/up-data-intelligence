# CHANGE #19.3D — Manager V2 data wiring acceptance

The implementation preserves Manager V2 page/section order and existing bodies. It does not promote production, start historical extraction or add another provider. The initial 21-column matrix was created before changing values; its implementation section is the authoritative local mapping audit.

## Implemented, not yet deployed

81 metric IDs map explicitly to read resource, response path, formatter and coverage rule; 21 widgets and 10 reused body contracts are enumerated and tested. Resource incompatibility cannot borrow a page's Overview value. NULL stays unavailable and a covered zero stays zero. Existing decimal monetary text remains exact in transport and monthly aggregation.

Operational registration readers deduplicate canonical fact IDs independently for submitted and approved events inside the selected local period. Approval backlog is retained and qualification may exceed 100%. Conversion requires an unambiguous event→order→customer relation plus qualifying purchase after approval and before both selected exclusive end and certified as_of. Missing identity keeps conversion NULL. MX currently has 588 unresolved approvals, so no conversion value is fabricated.

Overview/acquisition expose operational counts; retention exposes observed recurring orders, revenue/ticket, mean/median days. Monthly history retains six original groups and distinct monthly customers. Funnel uses compatible session rates and exact purchase/product/purchase_item events. Journey, commercial order rows and geography retain their existing authorized read contracts. Seller-period aggregation is explicitly still not certified.

Contacts are authorized on demand only. Order snapshot reads use the official nested wholesale/retail document and geography paths, independently from the current customer profile; no profile fallback is merged. Lists/exports never acquire these fields automatically.

Basic Meta reads remain independent of creative previews. Additional campaign/day link-clicks, landing-page views and reach-sum reads use the Intelligence source snapshot, exact account and configuration. Landing-page-view NUMERIC is transported as decimal text, not rounded to an integer. Reach sum is not unique period reach. Actions/action_values are absent in the currently persisted 35 campaign/day rows; an empty action list is not a claim of source absence.

The new source reads are gated by the existing completion feature flag used by private Preview; production has that feature off. This flag does not assert catalog completeness. Queries remain parameterized, read-only, store-scoped and budgeted by the existing read repository: 1 GiB maximum/query and the unchanged per-request reservation ceiling. The two additional proposed table reads are analytics_events and meta_live_insights_daily. Their proposed IAM member is shared by existing Read runtimes; this security impact must be explicitly reviewed before apply, even though only Preview images would change.

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

No further lead-definition decision is required. No Meta purchase question is asked without actual sanitized action names: current CORE lacks those action arrays. After official enrichment, overlapping purchase alternatives must be reported exactly before selecting a purchase definition. Reactivation additionally requires a business inactivity threshold alongside history; that does not authorize historical extraction now.

## Deployment and performance gate

New private Preview API deployment has not occurred in this Change. Proposed table-read IAM is not applied. Existing production APIs, production Vercel deployment, data Jobs and scheduler configuration remain unchanged. No success claim for complete live data wiring or current freshness is made while Health/enrichment acceptance is pending.

Existing Server-Timing instrumentation is retained. Deployment measurements for auth/WIF/API/BQ/serialization have not yet been taken for this code; no dominant latency or page request count is invented. Internal audit reads share the existing React Query keys to deduplicate card/widget readers. Contact calls occur only when a detail is opened.

## Validation

Full Python: 2443 passed. Focused dashboard: 222 passed. Ruff and mypy: pass (185 source files). Frontend: 335 tests in 31 files, lint/typecheck/format pass. Next.js webpack production build passes; Turbopack local build encountered environment EPERM while opening its PostCSS process port. Authenticated offline E2E: 4 passed; demo E2E: 1 passed. Final validation is repeated after the last changes.
