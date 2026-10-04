# CHANGE #19.1 — Authenticated DEV product serving

## Status and authority

Implementation and offline acceptance are complete on `change-19-1-auth-http-serving`,
based on `9b6e9c5eddffafcc88c1180023fb8801c75c1cec`.
This document is not live product acceptance. No PROD resources are authorized.
No ingestion, Analytics, Intelligence, recurring coverage, Installation or Data Health
business semantics are changed.

The DEV precheck found 16 current Data Health checks with zero blocking failures
at `2026-10-04T21:11:30.241700Z`. MX Registry remains ACTIVE, sync enabled,
revision 11, facts complete, history incomplete. All six data schedulers remain ENABLED;
the three Foundation schedulers remain PAUSED.

**Required ownership input:** both `workspace_store_bindings` and `onboarding_operations`
are empty. MX has no canonical tenant/workspace binding. The owner tenant must be supplied
and its initial canonical administrative binding reviewed before a product grant for MX.
Do not substitute `demo-up`, infer ownership from a login, or grant a synthetic tenant real
MX data. The initial approved operator must also be a verified Firebase identity before
the access CLI grants ADMIN_UP. Clear addresses are omitted here.

## Service boundaries

```
HTTPS browser -> Firebase Auth -> Next same-origin BFF (up-web)
                                  | ADC target-audience Google ID token
                                  | internal X-UP-Session
                                  +-> private up-read-api
                                  +-> private up-admin-api
```

`up-web` has no BigQuery, Storage lease or Secret Manager permissions. Its account can
only invoke the two private application services. Runtime private URLs are server envs.
Google identity credentials are never returned to the browser.

Private APIs retain Cloud Run IAM enforcement; they receive no allUsers/allAuthenticatedUsers
binding. Their ingress allows the authenticated web service to reach their run.app URL.
The Python application independently verifies `X-UP-Session` on every request. IAM service
identity alone cannot authorize a user.

Read composes `DashboardService`/`IntelligenceDashboardService`, `InstallationReader`,
`BigQueryReadSession`, and product authentication. Runtime Registry and the certified
HEAD/RECEIPT resolve policy; the static MX policy is not product authorization/configuration.
Admin composes the existing OnboardingService, BigQueryOnboarding, Secret Manager SAGA
and canonical cloud lease. CLIENT_USER is denied before onboarding/credential IO.
No successful live onboarding creates a second real brand in this acceptance.

## Authentication and session lifecycle

Email/password authentication uses initializeAuth with in-memory persistence only from its
first initialization (no default IndexedDB/local/session persistence). First access
creates an authentication identity and sends verification; it does not create a product grant.
Unverified accounts cannot exchange their token for a session. Password reset uses the SDK
and a generic UI message. The temporary ID token stays in the exchange's local async variable;
SDK signOut runs in finally. It is never put in React state, storage, URLs or logs.

POST `/api/auth/session` sends only the short-lived token after double-submit CSRF. The
private Admin auth handler verifies signature, revocation, verified email, recent auth_time
(<=300 seconds) and server grants before creating a 12h Firebase session. The credential
travels back only as Set-Cookie, never JSON:

`__Host-up_session=...; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200`

POST `/api/auth/logout` requires CSRF and revokes Firebase refresh tokens for the authenticated
UID (Firebase's operation revokes that user's sessions). After confirmed revocation, it clears
the cookie. An already expired/revoked session also clears its stale browser cookie. An unknown
revocation outcome returns a safe operational error, without a mutation retry.

No authorization caching is enabled: principal_access is reread per request, so disabling a
grant takes effect independently of the 12h cookie. Firebase session verification uses
check_revoked=True. Catalog/UI caching does not authorize the backend.

## Principal access and scopes

Canonical identity is SHA256(lowercase(trim(verified session email))). No clear email, UID,
credential or custom claim is stored as the authorization authority. `up_ops.principal_access`
is a separately gated additive product table, outside the business schema generator.
Required fields: row_key, identity_hash, role, tenant_id, status, created_at, updated_at;
workspace_operation_id is nullable only for ADMIN_UP. Roles are ADMIN_UP and CLIENT_USER;
statuses ACTIVE and DISABLED. Duplicate/conflicting/disabled/invalid grants fail closed.

ADMIN_UP is tenant scoped. CLIENT_USER needs an explicit workspace operation grant.
Both resolve technical stores through canonical workspace_store_bindings. No tenant-wide
implicit client grant exists. GET `/v1/session` exposes role, tenants and safe workspace
catalog fields only; no technical store IDs, emails or secret references are in the catalog.

The browser sends tenant_id/workspace_operation_id/operation. Legacy UI `Scope.store_id`
is only a workspace alias in live mode; it is never forwarded as a technical store parameter.
The BFF checks catalog membership, obtains its Google token for the target API audience,
and forwards fresh headers. Browser identity headers are stripped/overwritten. The private
API resolves and checks the scope independently before constructing a business read service.
Customer/order isolation remains in the canonical DashboardService.

The DEV CLI uses `python -m src.product_auth.cli grant|revoke|list`, explicit --live,
--project/--confirm-project and --tenant. CLIENT_USER grant also requires
--workspace-operation-id/--confirm-workspace-operation. It privately prompts for email,
verifies the Firebase user, stores only its hash and uses parameterized bounded SQL.
There is no arbitrary SQL interface or automatic write retry after an unknown outcome.

## Proposed IAM (review before any apply)

Firebase server privileges are custom roles, not roles/firebaseauth.admin:

| Service | Custom role | Exact permissions |
| --- | --- | --- |
| Read | upProductFirebaseRead_dev | firebaseauth.users.get |
| Admin | upProductFirebaseAdmin_dev | firebaseauth.users.get, firebaseauth.users.createSession, firebaseauth.users.update |

These support independent revocation/disabled-user checks, session creation and logout.
They do not allow user creation/deletion, provider/configuration administration or key creation.

Read: BigQuery jobUser plus table-scoped dataViewer on the explicit Dashboard/Installation/
Intelligence read table allowlist and principal_access/workspace_store_bindings. No updateData,
Secret Manager or Storage permission.

Admin: BigQuery jobUser; principal_access read; canonical table writer (get/getData/updateData)
only on store_runtime_config, workspace_store_bindings, onboarding_operations,
source_connections and meta_account_bindings. Existing #18.2 secret create permission
is container-create only; version reconciliation privileges are conditioned to the
`up-intelligence-upzero-` namespace. No global Meta token access. Lease privileges
(create/get/delete) are restricted to the existing lease bucket's leases/ objects.
No owner/editor/bigquery.admin/secretmanager.admin role is introduced.

The first Stage 1 plan could not be saved because the optional legacy admin is unset and
its #18.2 custom roles do not exist. No apply occurred. Product serving now creates identical
product-owned roles only when those legacy roles are absent; no legacy admin is enabled:
`upProductOnboardingCreate_dev`: secretmanager.secrets.create;
`upProductOnboardingReconcile_dev`: secretmanager.secrets.get, secretmanager.versions.add,
secretmanager.versions.list, secretmanager.versions.access. The latter binding retains the
same UP Zero namespace condition. This changes infrastructure composition only; no API
image or business runtime changed.

Web: roles/run.invoker only on Read/Admin. Public invocation is applied to up-web only in
Stage 2, after private acceptance. No service-account key is created/downloaded.

The stable private onboarding HMAC key is supplied through private deployment input and
Admin runtime env only. Sensitive plans/state must remain private; never check them in or
print full env/config JSON. Firebase browser API key/project config is public by design;
its API key is restricted to identitytoolkit and securetoken APIs.

## BFF and browser defenses

State-changing auth/admin routes require HTTPS, exact Origin, Sec-Fetch-Site same-origin
where supplied, and a 64-hex double-submit token. `__Host-up_csrf` is Secure/Strict/Path=/;
only the CSRF token is readable by JS. Inputs are streamed with a 16KiB auth / 32KiB admin
limit. Malformed JSON is 400. No GET logout exists.

Per-response CSP uses a nonce for Next scripts, self-only script origins, no wildcard
scripts/connections, frame-ancestors none, object-src none, base-uri/form-action self.
Firebase email/password needs only `https://identitytoolkit.googleapis.com` for account/
verification/reset and `https://securetoken.googleapis.com` for token refresh. No external
Firebase iframe/script origins are allowed. Styles allow inline values because the approved
component/chart library uses them; this does not permit inline scripts. DEV local eval is
restricted to NODE_ENV=development and absent in the production image.

Authenticated HTML/JSON sets private/no-store, nosniff and strict-origin-when-cross-origin
Referrer-Policy. No request payload/cookie/token is logged; Gunicorn access logging is disabled.
SDK errors are replaced by safe error codes. Product read query budgets are explicit: 256MiB/query, 8GiB per business reader,
60s/query. The lower per-query ceiling allows bounded Registry/publication plus Intelligence
reads without increasing the canonical total guard. Authorization is separately capped at
64MiB/query, 128MiB per request (at most two metadata queries), 30s/query. Admin SAGA retains
1GiB/query and an 8GiB execution ceiling. No ingestion/business cost guard is removed.

## Frontend modes and availability

Demo and read-api-preview retain their explicit existing behavior. Live is server selected;
it boots Providers from /api/session, offers only catalog workspaces, and cannot select
roles or technical stores. A single CLIENT_USER workspace is auto-selected. ADMIN_UP gets
catalog-based brands and protected canonical onboarding; no demo admin catalog is used.

Live failures stay 401/403/424/503 or an unavailable page. Unsupported B2C/ERP and uncertified
resources show unavailable coverage. There is no live -> demo fallback. Source labels come
from real publication metadata; history-sensitive metrics preserve null. The layout/components
and business metrics remain the approved frontend base.

Next uses standalone output, request rendering for CSP nonces/runtime mode and binds
0.0.0.0:$PORT. Python uses separately hash-locked firebase-admin 7.7.0 / gunicorn 26.2.0
in product.Dockerfile; existing Job entrypoints and ingestion lockfiles are untouched.
Web pins Firebase 12.19.0 and google-auth-library 11.1.0. The new grpc transitive dependency
is pinned to 1.14.5 to address its published advisory.

## Offline acceptance

- Python full suite: 2163 passed (including 23 product-auth cases), 121.65s.
- Ruff check/format and mypy: passed (162 source files at this checkpoint).
- Frontend: 249 tests / 22 files, 2.70s; lint, typecheck, format-check passed.
- Next production build: passed outside the restricted sandbox; the restricted Turbopack
  attempt stalled and was terminated, then the qualified repeat completed.
- Authenticated offline browser: 2 passed, Chrome, 5.8s. It uses synthetic intercepted
  Firebase/BFF responses over local HTTPS, proves first access, verification messaging,
  server catalog, secure HttpOnly cookie, no browser token persistence, unavailable real
  coverage and header search without demo substitution, POST logout and protected-route denial.
  No Firebase Auth IndexedDB database is created. Existing B2B/Installation preview E2E:
  11 passed, 14.7s.
- pip-audit of product-requirements.lock and the installed Python environment: no known vulnerabilities.
- npm production audit: zero vulnerabilities. Full npm audit has five high entries in the
  existing dev-only ESLint -> fast-glob -> micromatch -> braces chain (one advisory surfaced
  across five packages). braces 3.0.3 has no published fix for that stack-exhaustion advisory;
  no unrelated mass upgrade/downgrade is applied. This is a documented tooling limitation,
  not a claim of a clean full npm audit. Production runtime excludes these dev packages.
- Terraform fmt-check and validate: passed in a local backend-free copy. No live plan/apply
  has occurred at this checkpoint.

For reproducible offline auth E2E:

```bash
(umask 077; openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -keyout /tmp/product19-offline.key -out /tmp/product19-offline.crt \
  -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1')
cd frontend
./node_modules/.bin/playwright test --config=playwright.product-auth.config.ts
```

The private key stays in /tmp, mode 0600; it is not a deployment credential. Test-only
ignoreHTTPSErrors applies to this disposable local certificate. Live acceptance must use the
valid generated Cloud Run HTTPS URL and cannot ignore certificate failures.

## Staged live acceptance (pending)

Build from clean pushed source: separate immutable Python product API and Next web images,
record source SHA/build IDs/build+Artifact Registry digests. Exclude .env, credentials,
plans/state, local certificates, caches, reports with PII, and temporary auth files.
`cloudbuild.product-api.yaml` and `cloudbuild.product-web.yaml` only build/push; callers must
supply an approved build service account, unique source-commit release tag and digest-pinned
PYTHON_BASE/NODE_BASE. They never deploy or change data Job images. `product.gcloudignore` is
an explicit source allowlist. Firebase runtime config and private API URLs are not build inputs.

Stage 1: deploy Identity Platform config (email/password only), principal table, the private
Read/Admin services, dedicated service accounts and the exact scoped IAM above. up-web stays
absent. Audit saved plan JSON with secrets redacted, no destroys/replacements or existing
resource changes outside approved product serving. Hash exact binary, apply once, fresh plan
No changes. Reconcile unknown outcomes rather than retrying.

Use a disposable synthetic Firebase identity and private random password/token files only;
no Playwright trace/screenshots/video containing credentials. Check anonymous Cloud Run denied,
missing/invalid session 401, unverified/unprovisioned 403, wrong tenant/workspace/store denied
before business query, CLIENT_USER admin denied and valid authorized catalog/real MX Overview.
Disabled/revoked grant must immediately deny. Delete disposable identity after acceptance;
no extra real store is created.

Stage 2 only after private gates: deploy public up-web, add its actual HTTPS hostname to the
Identity Platform authorized domains, audit/hash/apply exact saved plan once and No changes.
Run real browser authentication/navigation over HTTPS for Overview, Orders, Acquisition,
Retention, Customers, Products, Installation and supported Intelligence; logout and recheck
protected route. Prove cookie flags/expiry/CSRF and no auth/service credentials in browser storage
or bundle. Compare HTTP metadata and money with canonical current DashboardService at one
publication snapshot, not a hardcoded generation. Outside-coverage rejection and null lifetime
metrics must remain. Recheck current certified Data Health zero blocking and all nine scheduler
states unchanged. Invalid ADMIN payload/missing CSRF/CLIENT_USER POST are non-mutating live cases;
successful onboarding writes use existing synthetic tests only.

Cloud Run URLs, builds, saved-plan hashes, live tests and final Git evidence remain **pending**.
This change must not be titled authenticated product ready until all gates pass.

## Remaining production promotion

Separate PROD project/environment, production users/domain, final production E2E and DNS/cutover
are outside #19.1. Data schedulers, Foundation resources and business data are frozen here.
