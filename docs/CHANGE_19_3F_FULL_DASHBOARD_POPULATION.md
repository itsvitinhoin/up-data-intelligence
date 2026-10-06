# CHANGE #19.3F — full dashboard population

Status: implementation and offline acceptance in progress. This document does not
certify the final Preview, completed historical backfill or green live Health.
Production serving and aliases remain frozen. Scheduler schedules are unchanged.

## Source authority

UP Zero is the commercial authority. Requested and fulfilled revenue remain
separate. Explicit `payment_status=paid` certifies paid order counts and their
percentage only where every order has known payment status. No explicit paid
amount, payment timestamp or documented all-or-nothing amount contract was found.
Paid revenue and paid ROAS remain NULL (`SOURCE_DOES_NOT_PROVIDE`).

Registration metrics count technically deduplicated `register_submitted` and
`register_approved` events in the selected period. Approval backlog is permitted.
The September reconciliation is 864 registrations / 588 approvals / approximately
68.06%. The event exposes `user_id` (including nested `user.id`); orders expose
`customer_id`. No documented deterministic relationship between these identities
was found in the inspected contract/raw projections. Approved conversion remains
NULL (`IDENTITY_RELATIONSHIP_NOT_PROVABLE`), without fuzzy contact joins.

Observed purchase sequences separately expose stages 1 through 6. Lifetime new
customers, CAC and lifetime LTV remain unavailable with `history_complete=false`.
Reactivation requires a proven 90-day history; bounded source history must not be
represented as lifetime proof.

## Dedicated Meta authority

The reviewed MX account reporting definition selects only
`offsite_conversion.fb_pixel_purchase` and its matching action value. Official
Graph and the inspected Ads Manager both reported 2 purchases and BRL 6514.69 for
the inspected September–4 October range. These values belong only to Meta pages.
Global requested ROAS uses UP Zero requested revenue / certified available Meta
spend, explicitly identifying Meta-only media coverage.

Non-additive reach/frequency use official `all_days` Insights at account,
campaign, adset and ad grain. Two new current/version tables keep period snapshots
separate from additive daily and creative metrics. Date range, reporting
configuration and entity grain are part of identity. Every read proves matching
completed checkpoints/runs, zero CORE failures and no pending RAW. Daily series
requires independent contiguous daily evidence; missing evidence returns NULL.
Creative previews are current official catalog metadata, not historical images.

## Product completion

Existing catalog work is resumed, never duplicated. Official product image reads
are bounded and occur in Installation V2, not in product drawers. Image-only work
requires the existing products/variants/attributes/inventory observation complete.
Three additive image tables preserve RAW/current/version evidence. Read projection
requires exact product/variant identity and a certified shared observation cutoff.
Current stock is explicitly a current snapshot. Order snapshot contact remains
protected detail-only; it does not enter aggregate cache, lists or exports.

## Read performance

The initial Overview reader waterfall measured 11583 ms. Consolidated publication
context and commercial aggregates reduced an isolated DEV read to two BigQuery
queries / 3111 ms cold and one / 1306 ms warm. These are isolated reader results,
not final-host acceptance or an application SLO.

A bounded process-local aggregate cache expires after 30 seconds and is keyed by
trusted tenant/workspace, complete publication identity, policy, period and SQL
contract. Authorization and publication are freshly resolved for each request.
Entity/PII projections cannot enter the cache. Replicas may miss independently.

The protected authenticated Preview measured Overview BigQuery work at 1991 ms
and 968 ms on a reused read, with BFF totals 3673 ms and 3052 ms respectively.
These measurements do not meet the complete server response target. Fresh access
and workspace evidence is therefore consolidated into one bounded parameterized
statement, retaining every isolation/revocation guard and no authorization cache.
Only the two pure aggregate Performance projections additionally use the bounded
cache, keyed by both freshly verified Analytics and Intelligence publications.
Detail/timeline/customer queries and both HEAD resolutions remain uncached.

General Performance also exposes existing supported UP Zero requested revenue,
requested/explicitly-paid order counts, requested ROAS and Meta impressions/clicks
using the current card components. No Meta purchase value enters these cards.

## Stage 1 and authenticated Preview evidence

The exact reviewed Stage 1 binary, SHA256
`76b3decf463e7ca08f74dea1af44a5fa4bd1a8dc3ca597987aad075c3033f9ad`,
was applied once successfully: 12 creates and 6 updates. Fresh post-plan showed
No changes. Four Installation Jobs passed their single `--help` smokes. Production
services, other Job templates and all nine Scheduler states matched the pre-apply
snapshot. The reviewed table grants are unchanged from the approval.

Deployment `dpl_AstgzsxTzgpYT2dsLs9e9VM1QyCj`, source commit
`9bb357dd35aa5f5626ef6a558bb484d5ba788709`, passed protected Vercel access and
the user's real application login. Live MX Overview, Performance and Funnel
loaded with certified values. This is intermediate acceptance; no final success
or Production promotion is claimed.

The user additionally authorized the 41 missing daily Meta history work units
between 21 July and 31 August 2026. Read-only canonical preflight proved current
Meta coverage valid and that expanded UP Zero history would otherwise invalidate
cumulative Intelligence. This complementary extension preserves the existing
binding/reporting definition, budgets and bounded V2 processing. It must complete
before the historical UP Zero publication is expanded. Neither historical plan
has been persisted at this documentation point; current catalog work is preserved.

## Live gates still required

Offline release validation: Python 2563 passed; frontend 34 files / 353 tests
passed; Ruff, formatting, mypy (192 source files), frontend lint/typecheck/format,
Terraform format/validate and diff whitespace checks passed. Webpack production
build passed. Offline Chrome acceptance passed four B2B/Admin tests and one
ten-route B2C Demo test. These fixture-backed tests do not certify live data.

Finish current catalog and image observations, execute the authorized missing UP
Zero history only through bounded V2 work, certify selected Meta creative/period
observations, reconcile the six Health failures through canonical pipelines,
publish immutable reviewed Preview runtimes, and audit the protected authenticated
final host. Do not remove Preview protection or use a bypass. Team-wide policy
changes require a separate decision.

The final acceptance requires masked B2B/Admin screenshots, ten B2C Demo routes,
real authenticated E2E, six-page final-host latency measurements, remote
Webpack/Turbopack builds and zero blocking Health failures. No success title is
valid before these gates pass. ERP/Google/TikTok/WhatsApp remain explicit future
connectors. B2B Live never falls back to demo values.
