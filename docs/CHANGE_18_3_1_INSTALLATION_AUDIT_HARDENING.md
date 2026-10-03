# CHANGE #18.3.1 — Installation Audit Hardening

Incremental offline audit of #18.3, based exactly on
`772cb8dd707c198ea2edaf589d4cddb42ea25a45`. The original #18.3 runbook remains
unchanged; this document records the subsequent corrections.

## 1. Initial BLOCKED plans are diagnostics, not persisted installations

`Planner.calculate()` legitimately returns `BLOCKED` and no units when a
checkpoint requires review or a pending Meta extraction needs configuration
recovery. Persisting this initial diagnostic would occupy the immutable
one-plan-per-store ledger and prevent a corrected installation from starting.

A shared `require_creatable_plan()` guard now raises
`installation_plan_not_creatable` for an initial BLOCKED plan. Both CLI
`--create-plan` and automatic onboarding `prepare()` call it before
`ledger.create()`. `BigQueryLedger.create()` independently calls it before any
ledger query, transaction, registry update or plan/unit insert.

`--plan-only` still returns the original blocked diagnostic and its cause.
After the operator repairs the source evidence through a separately approved
procedure, planning can run again and the first valid plan can be created.
This change introduces no delete, reopen or supersede operation. Existing plans
that become BLOCKED during execution retain their existing recovery semantics.

## 2. Exhausted transient Meta GETs defer work

Previously, exhausted internal retries returned the last failing HTTP response,
which pagination classified as `meta_request_failed`. The Worker correctly did
not retry that definitive code, so transient failures could prematurely block
installation.

The GET transport now classifies exhausted retries as follows:

| Result | Safe code | Work behavior |
| --- | --- | --- |
| HTTP 429 | `meta_retry_deferred` | DEFERRED; third failed slice BLOCKED |
| HTTP 500–599 | `meta_retry_deferred` | DEFERRED; third failed slice BLOCKED |
| `httpx.TransportError` during GET | `meta_retry_deferred` | Safe to retry a read; same failure limit |
| HTTP 400, 401, 403 and other non-transient unsuccessful responses | `meta_request_failed` | Definitive; no internal retry |
| Invalid configuration / invalid response | Existing definitive codes | Unchanged |

Only GETs are covered. This does not authorize repeating any ambiguous POST.
Sanitized HTTP attempts remain in the audit page envelope; a failed page has no
source entities and retains its pagination error. Token scrubbing remains active.
A subsequent successful internal retry retains its prior success behavior.

The existing Worker allowlist and transitions were not changed:
`failure_count` increments once per failed work execution, independently of
`attempt_count` (including healthy slices). Failures 1–2 are DEFERRED with a
future `next_eligible_at`; failure 3 is BLOCKED with `work_retry_exhausted` and
no automatic next eligibility.

## 3. READY V2 matches the frontend operational contract

The V2 reader now explicitly requires:

- COMPLETE plan and a nonempty set of work units, all COMPLETE;
- logical progress 100%, with a known required-unit denominator;
- no ambiguous, blocked, pending or running work;
- `facts_complete=true`, validated HEAD/RECEIPT and a non-null certified window;
- registry `sync_enabled=false` explicitly;
- at least one source, all configured, active and COMPLETE;
- at least one resource, all COMPLETE and none with `pending_raw=true`.

`history_complete` is deliberately not a READY V2 requirement. A completed
requested interval can be READY while lifetime history remains partial. The
frontend parser already enforced the source/resource conditions; its runtime
code is unchanged and new adversarial tests protect those checks. V1 behavior
and every visual component remain unchanged.

Contradictory COMPLETE plan/work with a PENDING source, a RUNNING resource or a
COMPLETE resource with pending RAW cannot produce READY. A valid publication,
complete source/resource evidence, complete facts and partial lifetime history
can still produce READY. Publication validation has not been replaced by these
operational guards.

## Preserved invariants

CAS, revisions, reservation revisions, dispatch tokens, exactly-once POST
submission, DISPATCH_UNKNOWN / OUTCOME_UNKNOWN, ambiguous BigQuery writes and
non-expiring leases are unchanged. LEGACY_RESUME, checkpoint keys, cursor,
pending RAW, filters, modes, run IDs and contiguous coverage are unchanged.
No registry capability flags are falsified. READY never enables scheduled sync.

The 20-page slice limit, 600-second soft budget, Cloud Run `max_retries=0`,
least-privilege IAM and lack of orchestrator Secret Manager access are unchanged.
No Terraform, schema, policy, dataset, scheduler or frontend component was edited.
No migration is required.

## Tests and offline validation

New Python tests cover both checkpoint-review and pending-Meta planning
blocks, CLI and automatic creation guards, unchanged in-memory registry/ledger,
replanning after corrected evidence and defensive rejection before any SQL.
Meta tests use only `httpx.MockTransport`: repeated 429/500/503 and transport
failures, definitive 400/401/403, retained attempt audits and integrated Meta
work-unit transitions through third-failure exhaustion, with healthy attempts
already counted. Read-model tests inject contradictory source/resource
projections and enforce disabled sync; existing valid HEAD/RECEIPT fixtures
continue to prove READY with `history_complete=false`.

Frontend tests reject READY with incomplete sources/resources, pending RAW,
missing sources/resources or inactive/unconfigured sources. Existing V1/V2
contract tests remain intact. Python sockets are denied by the suite; CLI cloud
factories, ADC discovery and leases are replaced with local fakes. No SDK cloud
client is constructed by these tests.

Final offline results: **2,052 Python tests**, **229 frontend tests** and
**8 Playwright installation/onboarding tests** passed. This adds 25 Python and
10 frontend cases. Ruff lint/format, mypy (150 source files), frontend lint,
typecheck/format, production webpack build, Terraform fmt/validate and
`git diff --check` passed. The local browser had content and expected controls,
with no framework overlay or reported browser errors.

Required verification commands:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
cd frontend
npm test -- --run
npm run lint
npm run typecheck
npm run format:check
NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack
# Start the isolated offline localhost:3117 server as in the #18.3 runbook.
DASHBOARD_E2E_LIVE=0 ./node_modules/.bin/playwright test \
  --config=playwright.installation.config.ts
cd ..
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform validate
git diff --check
```

The local browser and Playwright use synthetic intercepted API responses. Local
provider startup may require relaxing the process sandbox for `validate`; this
is schema validation only, without `init`, credentials, plan or resource access.
Production webpack build here is a local validation artifact, not a Docker build
or deployment.

## Explicitly not executed

```text
GCP live: NO
BigQuery live: NO
Secret Manager live: NO
UP Zero live: NO
Meta live: NO
Cloud Run: NO
Terraform plan: NO
Terraform apply: NO
Schedulers: NO CHANGE
MX live: NO CHANGE
```

No real probes, replay, checkpoint reset, RAW deletion, secret/credential
changes, PR or merge were performed. No real customer data was added.

## Remaining limitations and next step

Offline mocks and structural validation do not certify cloud permissions,
provider drift, source availability or real extraction throughput. Existing
persisted BLOCKED installations have no new automatic recovery flow. Meta
pending-configuration recovery still needs separately authorized operator work;
this change prevents persistence of its planning diagnostic only.

Next: audit the branch/commit and approve integration. Any DEV provisioning,
image build/deploy, source probe or execution must be authorized separately.
Do not execute those steps automatically as part of this change.
