# CHANGE #19.0 — MX DEV data acceptance

## Outcome and snapshot

DATA ACCEPTED — READY FOR PRODUCT GO-LIVE.

This accepts the available, explicitly covered data. It does not certify lifetime
history, payment amounts or definitive paid influence. Product HTTP serving,
production authentication and frontend production binding remain outside this Change.

- Audit ID: `8b214cbc-a3a8-40b0-ad02-14bef801e7e7`.
- Project/location: `up-data-intelligence-dev` / `southamerica-east1`.
- Store: `mx-fashion`; timezone `America/Sao_Paulo`; currency `BRL`.
- One logical cutoff: `2026-10-04T03:00:00Z`.
- Local certified window: `[2026-09-01,2026-10-04)`; 33 closed days, Sep 1–Oct 3.
- Registry remained revision 11, ACTIVE, sync=true, facts_complete=true,
  history_complete=false throughout the acceptance cycle.
- Policy hash: `3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c`.

Source comparisons concern this same logical cutoff. CORE oracles use time travel
at each publication's actual input snapshot, avoiding comparison against later writes:
Analytics `2026-10-04T20:33:48.809256Z`; Intelligence
`2026-10-04T20:39:20.655167Z`. Customers is a current snapshot rather than a lifetime
claim. Private helpers and evidence were kept under `/tmp/mx-data-acceptance-19` in
Cloud Shell; no customer rows, source payloads, IDs, secrets or cursors enter Git.

## Method and zero-tolerance gates

`src/quality/data_accuracy.py` compares identities before values. Duplicates, absent
identities, missing identities and unexpected identities fail independently of totals.
Every required field is then compared at its semantic grain. Money uses Decimal;
floats are rejected, scale-only differences such as 71852 and 71852.00 are equal,
and NULL/unknown retain their meanings. There is no generic float money tolerance.

The seven SQL reference models recalculate from CORE with all inputs pinned using
parameterized `FOR SYSTEM_TIME AS OF @source_snapshot_at`. Normal compilation is
unchanged. Every active Analytics row/field is compared, including money, flags,
nullability, key/grain and dates. No approximate name/SKU/geography resolution is used.

| Layer / check | Expected | Actual | Delta | Status |
|---|---:|---:|---:|---|
| Source → CORE: Customers unique current identities | 1211 | 1211 | 0 | PASS |
| Source → CORE: Orders in certified local window | 22 | 22 | 0 | PASS |
| Source → CORE: latest-parent Order items | 366 | 366 | 0 | PASS |
| Source → CORE: Facts in certified local window | 457398 | 457398 | 0 | PASS |
| Source → CORE: Meta catalogs accounts/campaigns/adsets/ads | 1 / 5 / 15 / 36 | 1 / 5 / 15 / 36 | 0 | PASS |
| Source → CORE: latest-day campaign Insights grain | 1 | 1 | 0 | PASS |
| RAW → CORE: per-run page/count ledger mismatches | 0 | 0 | 0 | PASS |
| CORE → Analytics: exact model parity | 7 | 7 | 0 | PASS |
| CORE → Intelligence: campaign/day spend/impressions/clicks grains | 33 | 33 | 0 | PASS |
| CORE → Intelligence: source snapshot hash mismatch | 0 | 0 | 0 | PASS |
| Intelligence: publication/model invariants failed | 0 | 0 of 19 | 0 | PASS |
| Analytics → Dashboard: surfaces passed | 6 | 6 | 0 | PASS |
| Duplicate/invalid/missing/unexpected required identities | 0 | 0 | 0 | PASS |
| Contiguous coverage gaps / pending RAW | 0 / 0 | 0 / 0 | 0 | PASS |
| Current certifying CORE failures | 0 | 0 | 0 | PASS |
| Active publication / Dashboard identity mismatch | 0 | 0 | 0 | PASS |
| Current blocking Analytics / health findings | 0 / 0 | 0 / 0 | 0 | PASS |

Historical error ledger is preserved and scoped separately below; this table does not
pretend that every past execution succeeded.

## UP Zero source parity

Canonical connectors and normalization were used; pinned secret values remained
server-side. Returned payloads were consumed privately and never logged/exported.

Customers: eight source pages, 1211 unique customers; duplicate, missing and unexpected
current IDs all zero. Matching identity digest:
`f4db97d1b4621f3b7ca46a31e8dab5e9892664e7ae9c41055375b4a0a65ebf15`.

Orders: 22 identities, four CANCELED, with exact per-order status, timestamp, requested
and fulfilled money, quantities and item counts. No aggregate compensation between
wrong identities is accepted. Items: 366 identities, all latest-parent version
relationships valid, exact quantities/original quantities/unit prices/status.
Duplicate or invalid source identities and parent mismatches = zero.

| Financial / quantity check | Source | CORE | Delta |
|---|---:|---:|---:|
| Orders | 22 | 22 | 0 |
| Canceled orders | 4 | 4 | 0 |
| Requested revenue (BRL) | 99033.96 | 99033.96 | 0 |
| Fulfilled revenue (BRL) | 85384.51 | 85384.51 | 0 |
| Requested item quantity | 404 | 404 | 0 |
| Fulfilled item quantity | 349 | 349 | 0 |

Every day within the certified range was checked, including days without orders.
Canceled requested revenue is 16552.40 at both Analytics and Dashboard. CANCELED
participates in the defined financial/cancellation KPIs and is excluded from the
qualifying purchase sequence. Requested and fulfilled remain distinct; neither proves paid.

Order identity digest:
`3bb8372f9d253b58e0227ca5387ede57625fe4035ddfb9129c99b743babb6af5`.
Item identity digest:
`a3fdd0472868fc208ea19d4aafcf5e16c2587594421ad67ad0341475addd4b64`.

Facts: 458 source pages; 457398 events in `[Sep 1 local midnight,Oct 4 local midnight)`.
All event identities, event names, timestamps, quantities and values match. All 617
local-day/event buckets match row count, quantity/value sums, NULL counts and stable
non-PII digest. Duplicate/missing/unexpected identities and field mismatches = zero.

Facts identity digest:
`2c101b401d43e230fb619536e09bb860b92914a68d12c71916fc3b73dc5f0214`.
Facts record digest:
`b3eb0bde41297efa01c51ac5f805b36b9f99b76f0c5c06aefe0bc16ca66ac2eb`.

| Fact event name | Source count | CORE count | Delta |
|---|---:|---:|---:|
| add_to_cart | 1282 | 1282 | 0 |
| cart_abandoned | 278 | 278 | 0 |
| cart_created | 671 | 671 | 0 |
| cart_view | 164 | 164 | 0 |
| category_view | 6980 | 6980 | 0 |
| checkout_delivery | 33 | 33 | 0 |
| checkout_payment | 26 | 26 | 0 |
| checkout_review | 24 | 24 | 0 |
| checkout_started | 76 | 76 | 0 |
| form_start | 4877 | 4877 | 0 |
| login | 269 | 269 | 0 |
| page_view | 61105 | 61105 | 0 |
| product_item_click | 15607 | 15607 | 0 |
| product_item_impression | 344741 | 344741 | 0 |
| product_view | 17778 | 17778 | 0 |
| purchase | 23 | 23 | 0 |
| purchase_item | 309 | 309 | 0 |
| register_approved | 576 | 576 | 0 |
| register_submitted | 839 | 839 | 0 |
| remove_from_cart | 351 | 351 | 0 |
| search | 1087 | 1087 | 0 |
| whatsapp_button_click | 302 | 302 | 0 |

Purchase event count is not order count or qualifying purchase count; these have
different canonical grains. No event is interpreted as confirmed payment.

## RAW and ingestion ledger

All eight persisted RAW resources were audited by run using aggregate page count,
distinct RAW identity count and payload.data array length. No payload was exported.
The 171 sync runs were reconciled with the page and record ledgers: mismatches = zero;
duplicate RAW page identities = zero. Current certifying runs are completed with
core_records_failed=0; all 139 checkpoints have pending_raw=NULL.

| Resource | RAW pages / records read | CORE processed records | Explicit reused-RAW replay records |
|---|---:|---:|---:|
| Customers | 77 / 3720 | 3809 | 89 |
| Orders | 48 / 145 | 145 | 0 |
| Facts | 974 / 957351 | 959351 | 2000 |
| Meta accounts | 3 / 3 | 3 | 0 |
| Meta campaigns | 3 / 15 | 15 | 0 |
| Meta adsets | 3 / 45 | 45 | 0 |
| Meta ads | 3 / 108 | 108 | 0 |
| Meta Insights | 36 / 62 | 62 | 0 |

These are cumulative processing counters, not unique entity counts. Historical replay
runs reuse RAW and read zero new source records, so their processing is shown separately;
adding it to source reads would create a false discrepancy. Per-run inserted/updated/
failed counters were audited without assuming inserted+updated equals processed when
records are unchanged. Current source/CORE identity parity proves the final state.

Four original Customers backfills retain completed_with_errors with one failure each;
their four checkpoints are recovered and all 1211 current source customers match CORE.
No historical run, checkpoint or quality finding was rewritten to make totals green.

## Meta source and Intelligence parity

The canonical account/configuration/global-secret binding was preserved. Catalog
identities match at counts 1/5/15/36; catalog evidence is independently fresh.
Latest closed day is Oct 3. Exact source/CORE metrics at campaign/day grain:

| Metric | Source | CORE | Delta |
|---|---:|---:|---:|
| Spend | 79 | 79 | 0 |
| Impressions | 3145 | 3145 | 0 |
| Reach | 2437 | 2437 | 0 |
| Clicks | 196 | 196 | 0 |
| Inline link clicks | 93 | 93 | 0 |
| Landing-page views | 124 | 124 | 0 |
| CPC | 0.403061224 | 0.403061224 | 0 |
| CPM | 25.119236884 | 25.119236884 | 0 |
| CTR | 6.232114467 | 6.232114467 | 0 |

Active Meta foundation does not materialize reported purchase/value fields; these are
UNAVAILABLE BY DESIGN rather than inferred from fulfilled revenue or influence.

Canonical Meta coverage accepts the contiguous union of 34 compatible completed
checkpoints covering the 33 required local days, with completed linked runs, no failures
or pending RAW, and fresh catalogs. Extra/overlapping complete intervals do not replace
missing-day evidence. Meta evidence digest:
`8b501efb450142f13515d30c60869dabffd252250b21eedb2a514a9e80729d19`.

Intelligence generation 3 is based on Analytics generation 5 and publication
`07a4c0e48ff4ead6030aa0c74889bc752e715abaeae1c0517d7f767ddcc3bc2e`.
Intelligence publication:
`ffa65556157c14890ea05d715dd1057397cbaee0e5dd3a9c1e09a6efeb1ec92b`.
Window/as_of/policy/base/publication evidence agree. All 19 canonical SQL invariants
passed, including duplicate grains, foreign customers, deduplicated order revenue,
Meta spend and guarded NULL ROAS/CAC/new-customer fields. Dynamic current-period
oracles were used rather than the old initial-window MX validation constants.

| Cumulative paid-media metric | CORE | Intelligence | Delta |
|---|---:|---:|---:|
| Spend | 3191.07 | 3191.07 | 0 |
| Impressions | 125416 | 125416 | 0 |
| Clicks | 9394 | 9394 | 0 |

All 33 campaign/day identities and each metric match exactly. Influence is not
attribution. influence_complete=false remains explicit; definitive ROAS/influence
fields stay NULL under the current contract.

The source snapshot digest was recomputed with canonical bounded EventReader,
EvidenceReader, DiskEvidenceIndex and Spool, without calling the materializer/writer:
`46dbcbe47bc36ff0c4d795224d15be80c56a6d6e2f06b7f788f4d7c9d35eaab7`.
It covers 1211 customers, 22 orders, 366 items, 461109 events in 34 chunks and 146531
resolver-consumed identity links. Query billed bytes: 3581935616, below the 128 GiB
execution ceiling; every query retained its 1 GiB ceiling.

The Intelligence policy starts at legacy history_from=Sep 1 UTC midnight, three hours
before report_from local midnight. Its 461109 events therefore include 3711 extra
pre-report events; this is a deliberate window distinction, not a cross-layer mismatch.
The local-window Facts comparison uses 457398 events in both Source and CORE.

## CORE → Analytics

Analytics generation 5 active publication:
`07a4c0e48ff4ead6030aa0c74889bc752e715abaeae1c0517d7f767ddcc3bc2e`.
Exactly one HEAD resolves to exactly one active completed RECEIPT with matching
store/policy/generation/publication/watermark/as_of. The RECEIPT is authoritative for
report_from/report_to; nullable legacy HEAD window fields are not used as authority.

| Model | Reference CORE recalculation | Active Analytics rows | Mismatched fields / identities |
|---|---:|---:|---:|
| analytics_store_daily | 33 | 33 | 0 |
| analytics_customer_metrics | 18 | 18 | 0 |
| analytics_customer_purchase_sequence | 18 | 18 | 0 |
| analytics_cohorts | 3 | 3 | 0 |
| analytics_purchase_distribution | 10 | 10 | 0 |
| analytics_products_daily | 363 | 363 | 0 |
| analytics_funnel_daily | 33 | 33 | 0 |

Daily orders/cancellations/approvals, generated/fulfilled/canceled/unfulfilled revenue,
items per order, qualifying buyers/sequence/distribution/first observed purchase and
frequency, product/day orders/units/revenue, and observed-complete funnel events agree.
The different product item/model counts reflect their documented grains, not lost items.
Sequence duplicate orders/gaps/invalid first purchase all zero. Immature cohort rates
remain NULL. All executable analytics.quality guards ran; blocking findings = zero.
Policy/hash/currency/staleness/input identity/explicit history requirements were also
checked by canonical preflight and exact input/output parity. No unsupported history
or payment proof was silently treated as complete.

## Analytics → Dashboard

The actual DashboardService was called with an internal authorized B2B principal,
query budgets, cursor pagination and Installation V2 integration. Every response used
generation 5, Sep 1–Oct 4 and as_of Oct 4 03:00Z; history_complete=false.

| Surface | Acceptance |
|---|---|
| Overview | 22 orders, four cancellations, requested 99033.96, fulfilled 85384.51, canceled requested 16552.40; all 33 daily series rows match |
| Orders | 22 rows across five pages of five; exact identities/status/money/quantities and stable ordering |
| Acquisition | 18 observed first buyers/orders; requested first-purchase 82481.56, fulfilled 71852.00; confirmed_new_customers=NULL |
| Retention | 18 observed buyers, zero observed recurring buyers, frequency=1; progression/cohorts match; no transition means/medians or retention ticket invented |
| Customers | 18 observed period buyers across four pages; exact observed metrics and stable cursor ordering; total current CORE Customers=1211 is a different population |
| Products | 305 product-key aggregates across 61 pages; exact money/units/order counts/nullability and stable hashed-key order; all 305 unresolved canonical product_id stay NULL |

Overview requested average order value is derived from the matched decimal numerator
99033.96 and denominator 22 (4501.543636... before presentation rounding); the current
Overview DTO does not falsely claim a separate certified AOV field. Money transport
remains decimal strings. Requested≠fulfilled, paid=NULL, definitive new customers,
lifetime LTV and CAC remain NULL. A request for Oct 4–5 is rejected with HTTP 400
interval_outside_publication. No uncaptured day becomes a fabricated zero.

Installation State remains READY, plan COMPLETE, 45/45 total and 43/43 required,
CHUNKS progress 100%, ETA 0 under the real completed-plan contract. No new plan or
work unit was created and no Installation business worker was dispatched.

## Freshness and real Scheduler path

| Layer | Expected cutoff | Actual cutoff | Lag | Status |
|---|---|---|---|---|
| UP Zero Orders/Facts + fresh Customers scan | 2026-10-04T03:00Z | 2026-10-04T03:00Z; scan completed 20:20Z | 0 | PASS |
| Meta daily Insights + fresh catalogs | Oct 3 local closed day / Oct 4 03:00Z | Oct 3; catalog cycle completed 20:29Z | 0 | PASS |
| Analytics | Oct 4 03:00Z / report_to Oct 4 | generation 5, same cutoff/window | 0 | PASS |
| Intelligence | Analytics 5 + current Meta union | generation 3, base_generation 5, same cutoff/window | 0 | PASS |
| Dashboard | Analytics 5 / Oct 4 03:00Z | generation 5, Sep 1–Oct 4 | 0 | PASS |

Normal schedulers had no automatic daily attempt since activation; ENABLED alone was
not accepted. Installation already had automatic minute no-op attempts. Exactly one
run-now per normal scheduler exercised Scheduler SA → dispatcher → worker → durable
evidence. Each has one AttemptStarted and one AttemptFinished log with HTTP 200:

| Pipeline | Scheduler attempt UTC | Dispatcher | Worker | Terminal result |
|---|---|---|---|---|
| UP Zero | 20:05:59 | up-store-dispatcher-jrpxh | up-upzero-worker-hj7x6 | SUCCESS / SUCCESS |
| Meta | 20:27:31 | up-store-dispatcher-splx4 | up-meta-worker-lb6vf | SUCCESS / SUCCESS |
| Analytics | 20:33:41 | up-store-dispatcher-q56tv | up-analytics-worker-4m5jh | SUCCESS / SUCCESS |
| Intelligence | 20:39:21 | up-store-dispatcher-mxc67 | up-intelligence-worker-n4bkh | SUCCESS / SUCCESS |

Before every run-now: sole eligible store MX, no related active chain, absent MX/global
normal lease and preceding pipeline reconciled. Each Scheduler was invoked once,
not replaced by a manual dispatcher invocation. UP Zero performed the canonical
incremental scans/reconciliation; current source runs had zero CORE failures. Meta
refreshed four catalogs and collected the closed day. Analytics 4→5 preserved
report_from=Sep 1 and report_to=Oct 4; Intelligence 2→3 accepted the cumulative base.
Same-day rerun did not shrink coverage or create duplicate grains. Final pending RAW=0,
normal/MX/installation-work leases absent. No ambiguous mutation occurred.

## Quality findings and explicit limitations

Current blocking Analytics/health findings: zero. Analytics output validation emitted
12 paid_orders_without_paid_revenue warnings: payment amount is not certified and
revenue_paid remains NULL. These findings are not hidden or converted into payment proof.

Historical quality_results remain intact. Stored aggregate sums include:
invalid_meta_parser Facts=188198 (latest Oct 4), global parser warnings=38; missing
purchase/item order-id warnings in older scopes; old sync_delayed alerts (Customers 11,
Orders 16, Facts 9, latest Sep 29); one old batch-too-large alert; four original Customer
normalization errors. These are cumulative findings across repeated runs/scopes, not
unique current entity counts. Freshness, recovered checkpoints, current zero CORE
failures and current source identity parity provide the superseding operational evidence;
no historical finding was deleted. The parser is unchanged and remains a separate issue.
The six historically investigated placeholder cases are not reclassified as the cause of
Customer failures or as proof that all later parser warnings have the same cause.

| Classification | Data / limitation |
|---|---|
| CORRECT & COMPLETE | Certified local-window commercial counts/money/quantities, Facts, Meta media metrics, active generation/window and durable freshness |
| CORRECT BUT OBSERVED | First observed purchase, buyers, frequency, purchase progression and cohorts; no assertion of lifetime-newness |
| UNAVAILABLE BY DESIGN | Definitive lifetime LTV/CAC/new-customer classification: history_complete=false |
| UNAVAILABLE BY DESIGN | Paid amounts and Meta-reported conversion value absent from the active contracts |
| UNAVAILABLE BY DESIGN | Definitive paid influence/ROAS where influence_complete=false; influence is not attribution |
| UNAVAILABLE BY DESIGN | Canonical product IDs unresolved in 305 product groups; no fuzzy inference |

## Persistent daily health checker

Job: up-data-health; dedicated SA: up-data-health-dev. Detector only: no source clients,
Secret Manager value reads, ingestion, repair, publication, Registry/checkpoint changes.
It reads fixed-snapshot durable evidence. Rules:

registry_active, sync_enabled, source_connections_active, no_pending_raw,
no_nonterminal_previous_day_runs, upzero_customers_fresh, upzero_orders_covered,
upzero_facts_covered, meta_daily_covered, meta_catalog_fresh, analytics_head_valid,
analytics_cutoff_current, analytics_window_monotonic, intelligence_base_current,
dashboard_publication_resolves, history_semantics_valid.

Disabled pipelines are explicitly not applicable (checked_count=0), never proof of
freshness. Registry inventory is bounded/stable and fail-closed on duplicates/overflow.
Every query has maximum_bytes_billed=1073741824 and execution ceiling=137438953472.

Existing up_ops.quality_results receives aggregate results only: resource=data_health,
record_id=NULL, checked/failed counts and audit ID. Keys are deterministic
`digest([store,canonical-cutoff,rule])`; same-cutoff reruns MERGE the same logical rows.
Blocking alert/error findings persist then exit 1; warnings follow contracted severity.
Unknown read/write outcomes are sanitized failures without automatic mutation retry.
Cloud Run terminal failure and quality_results are the operational failure authority.
No email/Slack recipient or notification channel was invented.

IAM is limited to BQ jobUser; table READ on store_runtime_config, sync_checkpoints,
sync_runs, source_connections, meta_account_bindings, analytics_publications,
analytics_intelligence_publications and analytics_store_daily; table WRITE only on
quality_results via the existing scoped writer role. Existing Scheduler SA can run only
the health Job, not Installation/source workers through this new binding. No dataset/
project data writer or Secret Manager permission was added.

Manual acceptance while Scheduler PAUSED:
execution up-data-health-96rf2, 21:11:24.569149–21:11:53.756225Z, SUCCESS, one task;
audit data-health-ccc82a715f66415196d90ecc2877d3a0, checked_at 21:11:30.241700Z.
Exactly 16 distinct rule keys persisted, record_id=NULL, all checked_count=1,
failed_count=0. Blocking failures=0; health warnings=0. This tests the deployed SA's
real read/write permissions rather than privileged local reads.

Scheduler up-data-health-dispatch is ENABLED, `0 7 * * *` UTC, after the 03/04/05/06
pipeline sequence. Defaults stay PAUSED in Terraform; DEV enabled only after acceptance.
No future scheduled health execution is claimed.

For later authorized manual DEV checks:

```bash
python -m src.quality.data_health_cli --live \
  --project up-data-intelligence-dev --confirm-project up-data-intelligence-dev \
  --location southamerica-east1 --store-id mx-fashion --confirm-store mx-fashion \
  --maximum-bytes-billed 1073741824 --maximum-total-bytes-billed 137438953472
```

If nonzero: inspect safe Cloud Run/quality metadata, reconcile and investigate. Do not
repair business tables or retry an ambiguous write. Alert delivery is later Product Ops.

## Build and Terraform evidence

Source commit: 099a618fae7a2d718af033c2539918aa21f45b8c, clean and pushed before build.
Successful health-only build: ee6bcaf6-2082-4aff-b33f-b737d2d7a6be.
Build and Artifact Registry digest both:
`sha256:9a025ecc0c7940be167f41c5a110fef7bfea5dc26b72ef434d059831d065620f`.

The first build 063462bb-4788-476f-bd01-208916399d4d failed its networkless CLI smoke:
private archive umask produced unreadable source files for UID 10001. Only temporary
archive file/directory permissions were corrected; source content, Dockerfile and
runtime semantics did not change. The second build's health --help smoke passed.
Existing nine Control Plane/Installation images remain digest 0157e83c...95f99a;
Foundation image/config/Jobs/schedulers are unchanged.

Health Stage 1: `/tmp/mx-data-acceptance-19/health-stage1-approved.plan`.
SHA256 `b9b05c276ace871b36713cdf77ca2f5d4484f70dace7ea065c0e66d000b1152c`.
Strict guard: 14 CREATE, zero UPDATE/DELETE/replacement: dedicated SA, query binding,
eight table-read bindings, one quality-only writer, Job, scoped invocation and PAUSED
Scheduler. Exact saved plan hash revalidated, applied once, exit 0; post-plan No changes.
No existing infrastructure was changed.

Health Stage 2: `/tmp/mx-data-acceptance-19/health-stage2.plan`.
SHA256 `962b66ee40f326ba87ce163ab6f5a4abf907b3c08b2b5228ef2b70538842ded1`.
Strict guard: exactly one UPDATE, only paused true→false on up-data-health-dispatch;
zero CREATE/DELETE/replacement or other changed fields. Applied exact saved binary
once, exit 0; final post-plan No changes.

| Scheduler | Final state | UTC schedule |
|---|---|---|
| up-upzero-dispatch | ENABLED | 0 3 * * * |
| up-meta-dispatch | ENABLED | 0 4 * * * |
| up-analytics-dispatch | ENABLED | 0 5 * * * |
| up-intelligence-dispatch | ENABLED | 0 6 * * * |
| up-installation-dispatch | ENABLED | * * * * * |
| up-data-health-dispatch | ENABLED | 0 7 * * * |
| up-foundation-dev-reconcile | PAUSED | 0 3 * * * |
| up-foundation-dev-sync | PAUSED | */15 * * * * |
| up-foundation-dev-quality | PAUSED | */30 * * * * |

## Tests, fixes and Git scope

No data transformation/runtime bug or parity mismatch was found; no corrective
business reprocessing was needed. One existing preservation test was updated to allow
only the exact health image/paused-input pair before checking all original Terraform
bytes/hashes. Its first final-suite failure was investigated and reproduced; no
existing baseline assertion was discarded.

- Final Python: 2140 passed in 121.98s; focused accuracy/health/CLI/snapshot tests: 37 passed.
- Ruff check/format: PASS; 284 files formatted. Mypy: PASS, 155 source files.
- Frontend unit tests: 230 passed in 21 files; lint/typecheck/format: PASS.
- Production Next build: PASS, 45 generated pages; build repeated outside the local
  sandbox after an idle restricted process was diagnosed and stopped.
- Relevant offline E2E: eight passed in 6.5s on isolated DEV port 3117, private test flags,
  empty backend URL/tokens and intercepted synthetic APIs. An initial run against the
  production server failed because DEV-only features were intentionally disabled;
  correcting the harness, without changing product guards, resolved all eight.
- Terraform recursive fmt and validate: PASS; final post-plan No changes.
- git diff --check: PASS. Next-generated offline config changes restored after review.

Branch: change-19-0-data-acceptance, from approved c30d4de79707c3a59a8dc78a61639512d28e0779.
Runtime/detector code commit: 099a618fae7a2d718af033c2539918aa21f45b8c.
Final evidence/config/preservation-test commit follows on the same branch, with no PR
or merge. Included scope: new quality detector/comparator/tests, optional reference SQL
snapshot mode, isolated health Terraform/config, strict preservation test and this report.
No .env/credentials/customer data/state/plans/caches/private source snapshots are committed.

## Safety and stop boundary

history_complete forced: NO. Manual RAW/CORE/checkpoint/publication business DML: NO.
MX replan: NO. Source credential/binding change or new secret version: NO.
Unexpected infrastructure/IAM or Foundation scheduler enablement: NO.
Business writes occurred only through the four authorized canonical Scheduler cycles;
new aggregate monitoring writes occurred only through the health detector.
No unknown outcome, unresolved pending RAW or current coverage gap was accepted.

STOP after data acceptance. Do not start public HTTP/API serving, production
authentication or frontend production cutover; those belong to CHANGE #19.1.
