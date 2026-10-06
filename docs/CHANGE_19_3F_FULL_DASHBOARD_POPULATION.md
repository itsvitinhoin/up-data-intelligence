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
