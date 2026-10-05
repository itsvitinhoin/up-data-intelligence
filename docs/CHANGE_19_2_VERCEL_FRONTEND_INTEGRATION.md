# CHANGE #19.2 — Vercel frontend integration

## Baseline and visual audit (before frontend edits)

Canonical main: `797dbbff09df0d8a5d93f3c24332c508b25d6012`.
Authenticated backend: `71cabe793232f15698c77b823c23b1446d722010`.
Working branch: `change-19-2-vercel-frontend-integration`, created from the authenticated backend with a clean worktree. No merge into main.

Existing Vercel project: `prj_97pqMmRY596f2PNg4ipCsA1r8Jbo`, team `team_t671r3SZj4i6JvObobazq9UH` (`victorcheunin-6445s-projects`), Git `itsvitinhoin/up-data-intelligence`, production branch `main`, root `frontend`, framework `nextjs`.
Production reference: `dpl_6QZMoStEdzScJ2XPWBPLZPj7NVaZ`, same SHA as canonical main. Domain: `up-data-intelligence.vercel.app`. This deployment must remain available for rollback.

The MCP connector could not access the project; the existing authenticated Vercel CLI confirmed its identity. Existing environment names only were inspected: `META_ACCESS_TOKEN` (production). Its value was not read; no source credential is required in the integrated frontend.

### Complete frontend diff classification

A = backend/auth integration; B = real-data state; C = visual/product change; D = tests/support. All 62 changed files are included below. Mixed files are classified by purpose/hunk. No C change is accepted automatically.

| File | Category | Decision |
| --- | --- | --- |
| `frontend/.dockerignore` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/Dockerfile` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/README.md` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/docs/api-integration.md` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/next.config.ts` | A / D | Pinned auth dependencies, standalone runtime and safe logging. |
| `frontend/package-lock.json` | A / D | Pinned auth dependencies, standalone runtime and safe logging. |
| `frontend/package.json` | A / D | Pinned auth dependencies, standalone runtime and safe logging. |
| `frontend/playwright.b2b-preview.config.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/playwright.installation.config.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/playwright.onboarding.config.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/playwright.product-auth.config.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/src/app/api/admin/onboarding/[operationId]/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/admin/onboarding/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/auth/config/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/auth/csrf/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/auth/logout/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/auth/session/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/dashboard/installation/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/api/session/route.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/app/globals.css` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/app/layout.tsx` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/components/installation-state.tsx` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/components/period-filter.tsx` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/components/shell.tsx` | A / B / C | Keep server catalog, source labels and unavailable boundary; remove LiveBrands bypass. |
| `frontend/src/features/admin.tsx` | A / B | Keep original layout and forms; connect catalog, onboarding and installation; disable unsupported writes. |
| `frontend/src/features/auth.tsx` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/features/brand-integrations.tsx` | A / B | Keep original layout and forms; connect catalog, onboarding and installation; disable unsupported writes. |
| `frontend/src/features/live-brands.tsx` | C | Reject separate admin layout. Restore approved AdminShell and brand cards. |
| `frontend/src/features/live-login.tsx` | A / C | Keep real auth fields; restore canonical brand, intro, typography and proof block. |
| `frontend/src/features/providers.tsx` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/features/secure-onboarding.tsx` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/hooks/use-dashboard-read.tsx` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/hooks/use-installation.ts` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/hooks/use-overview-data.ts` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/hooks/use-resource.ts` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/lib/dashboard-source.ts` | B | Certified coverage, loading, nullability or installation state in existing components. |
| `frontend/src/proxy.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/http.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/installation-bridge.server.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/installation.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/onboarding-bridge.server.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/onboarding.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/read-bridge.server.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/api/server.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/auth/bff.server.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/auth/catalog.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/services/auth/client.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/types/domain.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/types/installation.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/src/types/onboarding.ts` | A | Required authentication, HTTP contracts, verified scope or secure onboarding. |
| `frontend/tests/e2e/b2b-real-preview.spec.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/e2e/installation.spec.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/e2e/onboarding.spec.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/e2e/product-auth.spec.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/fixtures/installation.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/fixtures/onboarding.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/installation-v2.test.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/installation.test.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/onboarding.test.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/overview-source-state.test.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tests/product-auth.test.ts` | D | Tests, documentation or deployment support; no visual authority. |
| `frontend/tsconfig.json` | D | Tests, documentation or deployment support; no visual authority. |

### Visual decisions

The existing `.app`, `.sidebar`, `.main`, `.topbar`, `.brand-search`, `.workspace-grid.brand-integrations`, `.brand-card-heading`, `.brand-card-meta`, `.brand-card-actions`, card/table/filter components and route map remain canonical. The main baseline login brand/intro/proof block is restored in real login. Required email/password/verification controls replace the demo selector in the existing login card.

The #19.1 `LiveBrands` admin replacement is rejected. `/admin` uses the approved `AdminShell` and brand card structure with safe server catalog and installation reads. Unsupported mutations must be unavailable, not routed to demo API. The existing secure onboarding contract supplies the required live fields using the current dialog/form components. Fields not persisted by the contract must not claim a successful save.

Only appended installation styles exist in the baseline CSS diff; no typography, palette or shell redesign is adopted. Dashboard feature pages, base card/table components and navigation config are unchanged between these baselines. ERP/B2C remain visible but real coverage is unavailable.

## Serving architecture (implemented offline)

Vercel same-origin BFF → Vercel OIDC → bounded GCP WIF → dedicated `up-product-vercel-dev` identity → private Read/Admin APIs. No key files, source secrets or data-layer grants on the Vercel service account. User authorization is independently enforced by private APIs through the HttpOnly session and canonical workspace bindings.

Production federation is restricted to the exact team/project/production identity. Preview federation is a separate, default-disabled scope requiring explicit review before enablement. No production alias promotion until the user approves the validated preview.

Cloud Run `up-web` remains a temporary DEV validation surface, not the visual reference; no deletion. Data pipelines, business semantics, publications, Installation, Data Health and scheduler configuration remain unchanged.

## Offline acceptance before live approval

Offline validation: Python 2,163 tests passed; Ruff check and format passed (294 files); mypy passed (162 source files). Frontend 262 tests / 23 files, lint, typecheck and Prettier passed. Playwright: 3 authenticated/admin tests, 11 B2B/Installation tests, 1 synthetic onboarding test passed. Terraform 1.16.4 fmt and validate passed, with backend disabled for initialization. No live infrastructure mutation or product deployment has occurred.

Local default Turbopack build failed with an explicit OS process/port restriction; the supported `npm run build -- --webpack` production build passed. The actual Vercel build must pass before preview acceptance. New dependencies are exact-pinned `@vercel/oidc` 4.0.0 and `server-only` 0.0.1. Runtime dependency audit reports zero vulnerabilities; the existing development-only ESLint glob dependency advisories remain documented in #19.1 and are not mass-upgraded here.

Twelve canonical screenshots were captured before integration: desktop login/admin/Overview/Orders/Acquisition/Retention/Customers/Products/Performance/Campaigns plus mobile Campaigns/admin. They are private local visual references, not customer exports. Final live visual comparison remains pending.

Read-only DEV precheck: latest Data Health `2026-10-04T21:11:30.241700Z`, 16 rules, zero blocking failures. Six data schedulers remain ENABLED; three Foundation schedulers remain PAUSED. No pipeline execution is required by this frontend integration.

Existing Vercel project: `prj_97pqMmRY596f2PNg4ipCsA1r8Jbo`, team `team_t671r3SZj4i6JvObobazq9UH`, root `frontend`, framework Next.js, production branch `main`. Current production `dpl_6QZMoStEdzScJ2XPWBPLZPj7NVaZ` matches main `797dbbff09df0d8a5d93f3c24332c508b25d6012`; retain it for rollback. CLI access is verified; the connector account could not access this project, so no alternative project is created.

Preview trust is not active. Its proposed separate provider trusts the exact same team/project with environment `preview`. Vercel's documented OIDC claims do not include a branch/deployment identity; this IAM scope therefore covers that project's previews, not just this branch. Environment configuration can be restricted to this branch, but is not an IAM branch restriction. Both providers grant only `roles/iam.workloadIdentityUser` on the dedicated account, which has only `roles/run.invoker` on the two private product APIs. No data-layer or secret permissions are proposed.

Live preview, parity, final security isolation and user-approved production promotion remain pending. No success claim yet.


## Preview build and pending federation review

Source commit `09d21f469036c22c51469194c9604696e77e5e1a` is pushed on `change-19-2-vercel-frontend-integration`, without merge/PR. The Git integration created preview `dpl_8pswemnJTGRbb5NFexxBmNamhJy2` at `https://up-data-intelligence-dmbkg8kue-victorcheunin-6445s-projects.vercel.app`. Actual Vercel `npm run build` with Next.js 16.3.7 Turbopack passed (compiled in 29.9s; 48 pages generated; Build Completed in 52s). Thus the local Turbopack restriction is not reproduced on Vercel. The preview remains Vercel-protected and not functionally accepted: runtime environment configuration and WIF are not applied yet.

Anonymous requests to both private Read/Admin `/v1/session` returned HTTP 403. Static browser bundle scan found no STS/IAM Credentials endpoints, WIF configuration, dedicated service account, private-key marker or OIDC exchange function. Actual deployed browser-token/session acceptance remains pending.

Read-only Terraform saved plan: `/tmp/change19-2/vercel-federation.plan` on Cloud Shell, SHA256 `e207bdbcd70f3e036be2ac70f4e707c4b10669dc8d3e4cda45a0f495942b485d`. Proposed changes: ten creates (dedicated SA/pool, production and separately reviewed preview providers, STS/IAM Credentials service resources, two scoped federation members and two private-service invoker members); one update adding only `up-data-intelligence.vercel.app` to Firebase authorized domains. No destroys/replacements/data Jobs/schedulers. All prior authorized domains remain. No apply.

The automatic approval review rejected the attempt to configure branch-scoped preview application variables before the required preview-scope review. That command did not execute; no environment values were changed. The explicit user question now covers the saved plan and this branch's application configuration. Preview provider stays default-disabled in code and must not be applied before that response. No production promotion is authorized by preview-trust approval.

Production promotion must follow the actual Vercel platform behavior. Official documentation states preview promotion rebuilds with production variables: https://vercel.com/docs/deployments/promote-preview-to-production . Revalidate production runtime identity, build, auth, metadata and parity after promotion; do not describe a rebuilt deployment as byte-identical to the preview. Preserve the previous production deployment for rollback.


## Approved preview federation — applied and reconciled

The user explicitly approved the exact saved plan and temporary preview trust in #19.2. Cloud Shell saved plan `/tmp/change19-2/vercel-federation.plan` was rehashed before apply: `e207bdbcd70f3e036be2ac70f4e707c4b10669dc8d3e4cda45a0f495942b485d`. Its audited scope remained 10 creates, one update, no deletes/replacements. Applied exactly once, exit 0. Fresh Terraform post-plan returned exit 0 / **No changes**. No data Job, scheduler, table, business policy or source credential changed.

The update added only the canonical Vercel domain to Firebase authorized domains. No preview hostname or wildcard was added: actual email/password login on the configured preview succeeded without an additional authorized-domain mutation.

The dedicated Vercel account invokes only the private Read and Admin services. Neither private service has anonymous invoker access. Final anonymous HTTPS probes returned Cloud Run IAM HTTP 403 for both. The Vercel provider is `up-product-vercel-preview` in pool `up-product-vercel-dev`, project number `876521886531`; team/project/environment restrictions match the reviewed plan. Vercel runtime has no ADC fallback. An invalid user session traversed the deployed Vercel Function → OIDC → STS → service account → private Read API chain and returned the expected application 401; subsequent positive session and data responses prove the authenticated chain.

**Temporary trust boundary:** preview federation covers the approved project's previews, not an IAM-enforceable branch. Application variables are branch-scoped, which does not narrow provider trust. Disable/remove the preview provider and its federation binding before/during an explicitly approved production cutover. Do not retain this temporary trust indefinitely. Production federation remains separately restricted to production; no production application configuration or promotion is authorized by this acceptance.

## Configured immutable preview

Ten encrypted application variables were created only for preview branch `change-19-2-vercel-frontend-integration`: `DASHBOARD_DATA_MODE`, the two private service URLs, Firebase public configuration, and the five GCP federation identifiers. `VERCEL_ENV` is supplied by Vercel. No service-account key, GCP token or source secret was configured.

Environment changes require a new immutable deployment. The existing reviewed preview was redeployed with target preview, producing:

- deployment: `dpl_Gxex3P9DvNKk5vkus2Lw4SiLcDpo`;
- URL: `https://up-data-intelligence-ommuitezi-victorcheunin-6445s-projects.vercel.app`;
- source runtime commit: `09d21f469036c22c51469194c9604696e77e5e1a` (the subsequent `30503d8` commit only documented review);
- status: Ready, actual Vercel production build successful;
- same existing project/team, target preview, no production promotion.

The branch alias is `up-data-intelligence-git-ch-f89a6d-victorcheunin-6445s-projects.vercel.app`. Acceptance evidence refers to the immutable URL above, since future documentation pushes may move the branch alias.

## Actual HTTPS authentication and authorization acceptance

Four disposable synthetic Firebase identities were used; passwords existed only in private `/tmp` files. Two temporary grants were created/revoked through the canonical principal-access CLI. No new real brand, store, binding, onboarding operation or installation plan was created. No clear identity, password, ID token, session cookie, customer row or source payload is included in this report.

| Gate | Result |
| --- | --- |
| Real Firebase email/password login, ADMIN_UP | PASS; canonical MX B2B catalog and existing admin shell |
| Verified CLIENT_USER with explicit MX workspace | PASS; real B2B dashboard |
| Unverified identity | HTTP 403; no product session |
| Verified, unprovisioned identity | HTTP 403; no product session |
| Wrong tenant / workspace | HTTP 403 before business route invocation |
| Browser technical store injection | HTTP 400 `invalid_read_scope`, rejected by BFF allowlist |
| CLIENT_USER administrative POST | HTTP 403 with valid CSRF |
| ADMIN_UP malformed payload within authorized tenant | HTTP 400; no durable mutation |
| Missing CSRF on session / admin / logout | HTTP 403 |
| Disabled principal access | HTTP 403 immediately with existing session |
| Logout | Session cookie cleared; replay of the previous session returned HTTP 401 |
| Session cookie | Secure, HttpOnly, SameSite=Lax, Path=/, 12-hour maximum |
| Browser storage | No auth token / Firebase auth persistence in localStorage, sessionStorage or IndexedDB; session not JS-readable |
| Security headers | Constrained CSP, nosniff and private/no-store responses present |
| Private service anonymous access | Read 403 / Admin 403 from Cloud Run IAM |

Vercel deployment protection remained enabled. The official CLI generated one automation bypass for acceptance, which supplied a temporary HttpOnly protection cookie to the isolated test browser. This is distinct from the Firebase user session. The generated bypass is revoked after acceptance; no bypass credential is committed or configured in the app.

## Real data and canonical service parity

All nine preview resources returned HTTP 200: Overview, Orders, Acquisition, Retention, Customers, Products, Performance, Campaigns and Installation. The six Analytics surfaces resolved the actual active generation **5**, policy hash `3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c`, window `[2026-09-01, 2026-10-04)`, as-of `2026-10-04T03:00:00Z`, `history_complete=false`, `facts_complete=true`. Performance/Campaigns resolved Intelligence generation **3**, Analytics base **5**, matching window/policy/as-of. These generations were observed, not hardcoded application bindings.

Comparison used current canonical `DashboardService` / `IntelligenceDashboardService` with the same publication and dates, read-only and under existing query budgets. Full normalized response digests matched for all eight Analytics/Intelligence resources, including rows, nullability, metadata and pagination counts; session-bound opaque cursors were excluded from the comparison. Money remained exact transport strings. Overview requested `99033.96`, fulfilled `85384.51`, cancelled requested `16552.40`, orders requested 22. Requested/fulfilled remain distinct. Confirmed new customers, full LTV, CAC and paid revenue remain NULL where proof is absent. An out-of-coverage request returned HTTP 400, not invented zeros.

Installation comparison matched all stable fields after excluding request snapshot time and normalizing integral non-monetary JSON numbers (`100.0` in Python equals `100` after browser JSON serialization). Initial byte-oriented hashing flagged only this progress representation, not a product/data difference; no runtime change was made. Installation remains READY, plan COMPLETE, work COMPLETE 45, required progress 43/43, history incomplete, same certified window.

## Approved UI acceptance

Real login retained the approved introduction, typography and layout. `/admin` retained the existing sidebar, brand cards, search, dialogs and Dashboard action, using only the safe live catalog. Brand/source fields absent from the backend remain unavailable rather than being enriched from demo fixtures. Existing navigation loaded Overview, Orders, Acquisition, Retention, Customers, Products, Performance and Meta Campaigns with their final **Dados reais** source badge. Desktop screenshots were compared with the previously captured canonical Vercel references: existing shell, palette, typography, cards, charts and navigation are preserved; only approved authentication/data/coverage content differs.

Tests navigate through the real menu, preserving the selected workspace state. A full browser reload as ADMIN_UP requires selecting the authorized workspace again; this is not a data/auth failure. Assertions require the final workspace source badge rather than accepting a loading label or the sidebar's generic real-mode label. Two initial helper mistakes (inclusive frontend dates and extra period parameters on Installation) correctly triggered contract rejection and were corrected only in private test scripts. An ambiguous text selector for two coverage notices was likewise corrected in the test helper. No product workaround or code patch was needed.

ERP remains visible and renders **Indisponível / Cobertura ainda não certificada**, with no demo fallback. No MX B2C workspace exists; unauthorized B2C scope returns 403 and cannot resolve demo data.

## Data Health, scheduler freeze and cleanup

Final certified Data Health observed `2026-10-04T21:11:30.241700Z`: 16 rules, zero blocking failures. Scheduler inventory unchanged:

| Scheduler | State |
| --- | --- |
| up-upzero-dispatch | ENABLED |
| up-meta-dispatch | ENABLED |
| up-analytics-dispatch | ENABLED |
| up-intelligence-dispatch | ENABLED |
| up-installation-dispatch | ENABLED |
| up-data-health-dispatch | ENABLED |
| up-foundation-dev-sync | PAUSED |
| up-foundation-dev-reconcile | PAUSED |
| up-foundation-dev-quality | PAUSED |

No source API, secret value, ingestion, worker, replay, business DML, publication write or scheduler operation was required by #19.2 preview acceptance. Only authorized federation infrastructure, preview application configuration and disposable auth metadata changed. Temporary grants were revoked through the canonical CLI; disposable Firebase users are removed and absence verified. Private credential/cookie artifacts are cleaned after acceptance.

## Stop boundary and production review

**VERCEL PREVIEW READY — EXISTING UI + REAL AUTH + REAL DATA**

The validated runtime code has not changed since its complete offline suites: Python 2,163 tests, Ruff check/format (294 files), mypy (162 sources); frontend 262 tests/23 files, lint/typecheck/format/build; 15 relevant offline Playwright tests; Terraform fmt/validate. Actual configured Vercel build and the live acceptance gates above passed. Only this runbook is updated after acceptance; `git diff --check` is repeated before commit.

Production remains `dpl_6QZMoStEdzScJ2XPWBPLZPj7NVaZ` at canonical main `797dbbff09df0d8a5d93f3c24332c508b25d6012`; previous production remains available. Production env inventory is unchanged, including its unused legacy `META_ACCESS_TOKEN` name, whose value was never read or copied. No production variable change, promotion, merge, PR or deletion of Cloud Run up-web occurred.

Next action requires explicit user approval: configure production application variables with the production provider, remove the unused frontend source-token variable, disable/remove temporary preview trust through a separately audited saved plan, promote/rebuild the reviewed runtime, and repeat production auth/isolation/parity acceptance. Keep the current production rollback deployment and up-web. The preview approval alone does not authorize these actions.

## Explicitly authorized production promotion — accepted

The user subsequently approved production configuration, removal of the legacy frontend Meta variable and temporary preview federation, promotion, and repeated production acceptance. The preview stop boundary above records the earlier state; this section supersedes its pending production action. Backend serving/data still uses the existing **DEV** project. This is internal DEV product acceptance on the Vercel production target, not creation or promotion of a GCP PROD data environment.

### Preview trust removal and production configuration

Saved removal plan: `/tmp/change19-2/remove-preview.plan`, SHA256 `ef784cb17ec5e6894693ddda01d9098e09e04e3b2fd4164073aecaa601e053b8`. Strict audit proved exactly two deletes: `google_iam_workload_identity_pool_provider.product_vercel["preview"]` and `google_service_account_iam_member.product_vercel_federation["preview"]`; no creates, updates, replacements, Jobs, data resources or schedulers. Applied exactly once after revalidating the hash, exit 0. Fresh post-plan returned exit 0 / **No changes**. The production provider remains ACTIVE; the service account has exactly the canonical production subject federation member. Provider conditions additionally enforce the reviewed team/project IDs. A private inspection initially compared subject names against IDs; the assertion was corrected to the existing canonical subject contract, with no IAM or runtime change.

Ten encrypted variables were configured for the production target, with `DASHBOARD_DATA_MODE=live` and `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID=up-product-vercel-production`. Remaining values are the same approved private API URLs, public Firebase configuration and federation identifiers used by the accepted runtime. `META_ACCESS_TOKEN` was removed from the Vercel production environment. Its value was never read; no source token, Secret Manager version, credential or binding was changed. Vercel runtime continues using short-lived OIDC federation; no service-account key or browser service credential exists.

### Promotion and rollback

Promoted exactly accepted preview `dpl_Gxex3P9DvNKk5vkus2Lw4SiLcDpo` once using the existing project. Vercel created a new production build with production variables, rather than reusing preview build bytes:

- production deployment: `dpl_EA5gpJfDQuyLS7LqfpuWUw8Km9e5`;
- immutable URL: `https://up-data-intelligence-1q5gd7e5n-victorcheunin-6445s-projects.vercel.app`;
- canonical URL: `https://up-data-intelligence.vercel.app`;
- source runtime commit: `09d21f469036c22c51469194c9604696e77e5e1a`, unchanged from the accepted preview;
- API-confirmed target production, action promote, status READY; actual production build passed;
- old production `dpl_6QZMoStEdzScJ2XPWBPLZPj7NVaZ` remains READY and available for rollback;
- `up-web` remains available at its existing Cloud Run URL, with its serving condition True.

Rollback may restore the preserved deployment using the project's deployment rollback action after a deliberate operational decision; do not delete the prior deployment. Reassess authentication/federation configuration if intentionally reverting to the previous demo runtime. No PR, merge or main-branch change is part of this cutover.

### Repeated production HTTPS acceptance

The canonical domain directly served the real login and public Firebase configuration. Existing Vercel project protection settings were preserved; **no automation bypass was needed or generated for production acceptance**. Four new disposable synthetic Firebase identities and two temporary grants were used. No permanent administrator credential, customer identity or business data was used in artifacts.

| Production gate | Result |
| --- | --- |
| Real ADMIN_UP browser login and canonical MX catalog | PASS |
| CLIENT_USER login and explicit MX B2B workspace | PASS |
| Unverified / verified-unprovisioned accounts | 403 / 403, no session |
| Wrong tenant / wrong workspace | 403 / 403 |
| Browser technical-store injection | 400, rejected |
| CLIENT_USER admin POST | 403 |
| ADMIN_UP invalid authorized payload | 400 before durable onboarding mutation |
| Missing CSRF on session/admin/logout | 403 |
| Disabled grant with existing session | 403 immediately |
| Session | Secure, HttpOnly, SameSite=Lax, Path=/, maximum 12 hours |
| Browser storage | No auth token in localStorage/sessionStorage/IndexedDB; session not JS-readable |
| Logout / old cookie replay | Cookie cleared / 401 |
| Security headers | CSP, nosniff, private/no-store present |
| Private APIs anonymous access | Read 403 / Admin 403 |
| Outside certified period | 400; no invented zero |
| ERP / unauthorized MX B2C | Unavailable without fixture / 403 |
| Public JavaScript scan | 13 scripts; no private-key, STS/IAM Credentials, federation account or Meta token marker |

Existing menu navigation loaded Overview, Orders, Acquisition, Retention, Customers, Products, Performance and Meta Campaigns with the final **Dados reais** badge. Production screenshots retained the approved shell/components/layout. The installation response remained READY, plan COMPLETE, 45 complete units, required progress 43/43. Unsupported or history-sensitive fields remain unavailable.

All nine production envelopes returned HTTP 200 and matched full normalized current canonical-service response digests, including Installation. Comparison excludes only session-bound cursors, request identity and snapshot time, and normalizes integral non-monetary JSON number representation. Money and NULL values are preserved. Actual Analytics generation **5**, Intelligence generation **3** / Analytics base **5**, window `[2026-09-01, 2026-10-04)`, as-of `2026-10-04T03:00:00Z`, policy hash `3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c`, `history_complete=false`, `facts_complete=true`. Requested `99033.96` and fulfilled `85384.51` remain distinct; complete LTV, CAC, confirmed-new and paid revenue remain NULL.

### Freeze, cleanup, tests and stop

Final Data Health: 16 rules, zero blocking failures, certified check timestamp `2026-10-04T21:11:30.241700Z`. All six data/installation/health schedulers remain ENABLED and the three Foundation schedulers PAUSED, as enumerated above. No scheduler or data-layer semantic change occurred. No source API call, source secret value read, worker execution, ingestion, business DML, checkpoint repair, publication write, replan or new real brand was performed by this promotion.

Both temporary grants were revoked via the canonical CLI; all four synthetic Firebase users were deleted and absence verified. Private password/session/response artifacts are removed after acceptance. The earlier preview bypass was already revoked; production created none.

No runtime file changed after the tested immutable source commit. Its recorded complete suites remain Python 2,163 tests; Ruff check/format 294 files; mypy 162 sources; frontend 262 tests/23 files plus lint/typecheck/format/build; 15 relevant offline Playwright tests; Terraform fmt/validate. This round additionally passed the actual Vercel production build, production browser/auth/isolation/security acceptance, nine-resource canonical parity, coverage/nullability checks, public-bundle scan and Terraform post-plan. Documentation-only diff is checked before commit.

**VERCEL PRODUCT READY — EXISTING UI + REAL AUTH + REAL DATA**

Stop after documenting and pushing this acceptance on `change-19-2-vercel-frontend-integration`. Preserve `up-web` and rollback. GCP PROD promotion, production data environment, production domain/DNS strategy and other Product Production Promotion work remain separate; do not start another Change automatically.
