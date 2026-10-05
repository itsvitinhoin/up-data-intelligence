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

## Acceptance status

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
