# CHANGE #19.1 — Authenticated DEV product serving

## Status and authority

Implementation and offline acceptance are complete on `change-19-1-auth-http-serving`,
based on `9b6e9c5eddffafcc88c1180023fb8801c75c1cec`.
**AUTHENTICATED DEV PRODUCT READY — REAL MX DASHBOARD LIVE**

Private APIs, canonical MX authorization, permanent verified ADMIN_UP provisioning and the
public HTTPS web are deployed. Negative/positive private acceptance and deployed browser
acceptance passed. The DEV product is available at
https://up-web-oynuekcxwa-rj.a.run.app. This is DEV acceptance, not production promotion.
No PROD resources are authorized.
No ingestion, Analytics, Intelligence, recurring coverage, Installation or Data Health
business semantics are changed.

The DEV precheck found 16 current Data Health checks with zero blocking failures
at `2026-10-04T21:11:30.241700Z`. MX Registry remains ACTIVE, sync enabled,
revision 11, facts complete, history incomplete. All six data schedulers remain ENABLED;
the three Foundation schedulers remain PAUSED.

**Approved canonical ownership:** the user explicitly authorized legacy metadata adoption:
tenant `mx-fashion`, brand `brand-mx-fashion`, workspace `mx-fashion-b2b`, technical store
`mx-fashion`, operation B2B, status ACTIVE. Grupo UP is the platform operator, not the customer
tenant. `demo-up` stays demo-only. No MX B2C binding is created.
The initial approved operator must be a verified Firebase identity before the access CLI
grants ADMIN_UP for tenant mx-fashion. Clear addresses are omitted here.

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

Cloud Run terminates TLS before Next standalone. Next can construct request.url from its
internal 0.0.0.0:$PORT authority. Only when K_SERVICE=up-web, the BFF instead compares Origin
against the actual incoming Host, restricted to the generated up-web-*.run.app HTTPS service
hostname, and requires X-Forwarded-Proto=https. X-Forwarded-Host is never trusted. The CSRF
cookie remains host-only; exact origin, Fetch Metadata and double-submit checks all remain.
An explicit proxy test covers valid TLS termination and rejects changed origin/host/protocol.
Custom production domains require a separately reviewed serving-origin configuration.

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

- Python full suite: 2163 passed (including 23 product-auth cases), 126.33s.
- Ruff check/format and mypy: passed (162 source files at this checkpoint).
- Frontend: 250 tests / 22 files, 2.84s; lint, typecheck, format-check passed.
- Next production build: passed outside the restricted sandbox; the restricted Turbopack
  attempt stalled and was terminated, then the qualified repeat completed.
- Authenticated offline browser: 2 passed, Chrome, 6.5s. It uses synthetic intercepted
  Firebase/BFF responses over local HTTPS, proves first access, verification messaging,
  server catalog, secure HttpOnly cookie, no browser token persistence, unavailable real
  coverage and header search without demo substitution, POST logout and protected-route denial.
  No Firebase Auth IndexedDB database is created. Existing B2B/Installation preview E2E:
  11 passed, 14.2s.
- pip-audit of product-requirements.lock and the installed Python environment: no known vulnerabilities.
- npm production audit: zero vulnerabilities. Full npm audit has five high entries in the
  existing dev-only ESLint -> fast-glob -> micromatch -> braces chain (one advisory surfaced
  across five packages). braces 3.0.3 has no published fix for that stack-exhaustion advisory;
  no unrelated mass upgrade/downgrade is applied. This is a documented tooling limitation,
  not a claim of a clean full npm audit. Production runtime excludes these dev packages.
- Terraform fmt-check and validate: passed in a local backend-free copy. Live Stage 1
  and its reconciliation are recorded below; a fresh final live plan returned No changes.

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

## Staged live acceptance

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

### Stage 1 actual evidence

Immutable images were built from clean pushed commits using the existing approved DEV build
service account and explicit source allowlist. No credentials were build inputs.

| Image | Source commit | Build ID | Build and Artifact Registry digest |
| --- | --- | --- | --- |
| Product API | 51453f4d42563f1c7ba7c6d9b891883eecad20e0 | 79983fbc-dee4-4388-b250-c4a545ad9298 | sha256:309308234f0d8b5d3c746251fc0a4898805cf08cc25b08b49c7579912b5bc848 |
| Web, not deployed | 5a21bd69187ff6283a69edb1f5130040764313f8 | d14a9d73-0556-443e-bb00-73c7e2a6d1b0 | sha256:f3cc6cb27d947e0f9d86b2159b68849a337785a0aca151ea64e3ad42f9dc931f |

Both builds succeeded and each digest was independently matched against Artifact Registry.
The earlier web build bf4a5ff4-d3c9-4577-998a-0da8dd76c372
(sha256:a756f42fdcaf5cdd1117ee2a66812b0044b2b9ef815fc6125e69eab7de968192)
is superseded by the HTTPS proxy CSRF fix; it was never deployed or accepted. API code did
not change after its source commit; subsequent Terraform/docs/web changes do not require an
API rebuild. Python and Node bases were digest-pinned, not moving build tags.

The first composition plan failed before a saved plan/apply because the optional legacy
admin's custom roles were absent. The product-owned equivalents described above fixed the
composition without enabling that legacy admin or widening permissions.

Saved plan R2 contained exactly 60 additive product resources, zero updates/deletes/replacements,
no public web, and no changes to existing data/Job/Scheduler resources. Its binary SHA256 was
`bffd71063af86e8a6466e8de1031526aa5c68217358699c94024c771265fc4b1`.
It was applied once: 59 resources completed; Identity Platform configuration failed definitively
because Cloud Shell's ADC quota project targeted its own tooling project. No ambiguous mutation
was retried and the original saved plan was not reapplied.

A product-only Google provider alias sets the explicit DEV billing/quota project; it does not
change credentials, IAM grants, the default provider or data infrastructure. R3 reconciled all
59 resources as no-op and contained only Identity Platform configuration creation. Saved binary
SHA256: `19e30ea3ae85611d1cdae2543ad752026841d911e3e47fcf56d365dd1345c7c9`.
One apply succeeded (exit 0); the fresh post-plan returned No changes (detailed exit 0).
Private binary/JSON plans and deployment secrets remain outside Git.

Private HTTPS services (Cloud Run IAM required):

- Read: https://up-read-api-oynuekcxwa-rj.a.run.app
- Admin: https://up-admin-api-oynuekcxwa-rj.a.run.app

Neither has allUsers/allAuthenticatedUsers. Both are Ready and run the immutable product API
image. Anonymous direct requests were denied by Cloud Run with 403. IAM-authenticated calls
without a user session returned 401 unauthenticated; invalid sessions returned 401 invalid_session.
The final service inventory independently confirmed the API digest and dedicated account on
each private service, roles/run.invoker granted exclusively to the product Web service account,
and up-web absent. No anonymous application service was introduced by Stage 1.
Live project IAM matched the reviewed allowlist: Read has only jobUser and its get-user role;
Admin has jobUser, its three-permission Firebase role and the two scoped onboarding roles;
Web has no project role. All three service accounts have zero user-managed keys. Firebase
custom roles' exact live permissions match the table above. Table/invoker/conditional bucket
bindings reconciled against the saved plan with no drift.

A disposable synthetic Firebase identity tested actual email/password authentication:
unverified token exchange returned 403 verified_email_required; after test-only verification,
exchange returned 403 access_not_provisioned. No session/grant was issued. The test identity was
deleted successfully, its private password file removed, and no payload/token/password logged.

The final read-only precheck again found 16 Data Health rules, zero blocking failures,
MX ACTIVE/sync=true/revision 11/history=false/facts=true, and zero rows in bindings,
onboarding_operations and principal_access. All six intended data schedulers remain ENABLED;
up-foundation-dev-sync, up-foundation-dev-reconcile and up-foundation-dev-quality remain PAUSED.
No business/source API, secret value read, data mutation or scheduler alteration was needed.

### Canonical MX adoption and private positive acceptance

One guarded, parameterized metadata transaction inserted exactly the approved B2B binding.
Its canonical row key is digest([tenant_id,workspace_operation_id]):
`75f64f5e5694c6dfeb3793fdb100b381f864024d37d1491e2a85c353deacd3c1`.
created_at and updated_at use the same server timestamp. The post-read proved all logical
fields and timestamp equality, exactly one MX binding and no B2C binding. No Registry,
source connection, Meta binding, onboarding operation, Installation plan or publication
was created/changed by the bootstrap.

The private helper's initial SQL used the reserved variable name AT. BigQuery returned
DONE/invalidQuery before any mutation; a reconciliation read proved zero bindings. A corrected
helper used adopted_at and its separately guarded attempt succeeded. This was a definite
syntax failure, not an ambiguous write retry and not a runtime/business code change.

Two disposable verified synthetic identities were granted scoped ADMIN_UP and CLIENT_USER
through the existing CLI. Cloud Shell user ADC requires
GOOGLE_CLOUD_QUOTA_PROJECT=up-data-intelligence-dev for Firebase Admin calls; this sets the
quota project only. The initial grant attempt failed before writing; a read proved zero
grants before the correctly configured CLI proceeded. No credential file or IAM expansion
was needed. The permanent operator uses the same CLI after human email verification.

Private live acceptance passed:

| Check | Result |
| --- | --- |
| ADMIN_UP / CLIENT_USER catalog | 200; only tenant mx-fashion and workspace mx-fashion-b2b |
| Wrong tenant / wrong workspace | 403 workspace_forbidden |
| Browser technical store parameter | 403 technical_store_scope_forbidden |
| CLIENT_USER attempting onboarding | 403 admin_up_required |
| Invalid ADMIN payload | 400 invalid_onboarding_request before durable mutation |
| Disabled grant | immediate 403 access_disabled_or_invalid |
| Logout / previously issued session | cookie cleared; old session rejected with 401 |
| Overview, Orders, Acquisition, Retention, Customers, Products | 200; exact canonical DashboardService parity |
| Installation | READY; canonical parity |
| Performance / Campaigns | 200; canonical IntelligenceDashboardService parity |
| Period outside certified coverage | 400 |

The audited Analytics snapshot was generation 5, policy hash
`3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c`,
report_from 2026-09-01, report_to 2026-10-04 exclusive, as_of 2026-10-04T03:00:00Z.
Requested revenue was decimal string 99033.96, fulfilled revenue 85384.51; history_complete
remained false and facts_complete true. Intelligence surfaces used generation 3. These are
observed audit values, not hardcoded product generations; final browser regression rechecks
current publication metadata. Customer/order rows and identity values were not printed.

### Stage 2 deployment and authenticated browser acceptance

The reviewed saved plan contains exactly two creates (up-web and its public invoker binding)
and one update (Identity Platform authorized_domains only). No existing data resource,
Scheduler, Job, private-service IAM or secret changes. Saved binary SHA256:
`9a84d710ec6b5423a53599194169f1ce7d08223a3a8be08d61175a1244c69ef8`.
After the permanent operator gate passed, the saved binary hash and exact resource guard
were revalidated. A fresh read-only Data Health check proved 16 rules and zero blocking
failures; the exact six ENABLED data schedulers and three PAUSED Foundation schedulers were
unchanged. The saved plan was applied once (exit 0). A fresh post-plan returned No changes
(detailed exit 0). The public DEV URL is https://up-web-oynuekcxwa-rj.a.run.app.
The private deployed-browser helper has traces/video/screenshots disabled, reads synthetic
passwords from private /tmp files, and does not print credentials.

The permanent approved operator initially did not exist in Firebase at the read-only precheck.
A private interactive helper was prepared locally and in Cloud Shell: it validates the
approved identity hash, accepts hidden password input, sends verification through Firebase,
and stores/prints no password or ID token. Human first access created the identity and Firebase
accepted the verification email request.
The initial delivery delay was diagnosed read-only: one enabled, unverified identity and default
Firebase email delivery, with no custom SMTP. A hidden-input resend helper was prepared, without
credential storage. The human subsequently verified the email; an independent lookup confirmed
emailVerified=true and disabled=false. The existing principal-access CLI then granted ADMIN_UP
only for tenant mx-fashion. Post-read proved exactly one ACTIVE tenant-scoped operator grant
with workspace_operation_id=NULL. Only the identity hash is persisted. No verification flag
was forged and no password/token was logged. No PROD exists.

The initial HTTPS acceptance reached all eight data surfaces and passed isolation/CSRF checks,
then stopped on an overly broad private helper assertion rejecting any Firebase IndexedDB.
A separate storage inspection proved only firebase-heartbeat-database/firebase-heartbeat-store
with zero token-bearing records, no auth token in local/session storage and no JS-readable
session cookie. The Firebase SDK maintains this non-authentication heartbeat store
([SDK source](https://github.com/firebase/firebase-js-sdk/blob/main/packages/app/src/indexeddb.ts)).
The helper was refined to reject Firebase Auth/local-storage databases and tokens; deployed
product code, cookie protections and inMemoryPersistence were unchanged. Repository offline
E2E already distinguishes authentication databases. Full HTTPS acceptance was repeated after
that evidence and passed (exit 0); no browser-token safety condition was bypassed.

| Deployed HTTPS check | Result |
| --- | --- |
| Real ADMIN_UP and CLIENT_USER login | Server-owned catalog; verified email required |
| Browser session | Secure, HttpOnly, SameSite=Lax, Path=/, 12 hours |
| Overview / Orders / Acquisition / Retention / Customers / Products | Real generation 5; Overview data/metadata exactly match canonical service |
| Performance / Campaigns | Real Intelligence generation 3 |
| Installation | READY / COMPLETE / 43 of 43 required units |
| Wrong tenant / workspace | 403 |
| Browser technical store parameter | 400 |
| CLIENT_USER admin write | 403 |
| Missing CSRF / changed origin | 403 |
| Invalid ADMIN payload | 400 before durable mutation |
| Outside certified window | 400; no invented zeros |
| Browser auth storage | No tokens in localStorage/sessionStorage/IndexedDB; HttpOnly cookie unreadable |
| Logout | Session endpoint and protected reads return 401 |

The browser used actual Firebase email/password authentication, public Cloud Run HTTPS,
same-origin BFF, service identity and the private APIs. No intercepted live response, demo
fallback, ignored TLS error, trace, video, screenshot credential or customer payload was
needed. Assertions use the current publication observed at acceptance, not a fixed generation
in application code. The available certified window remained 2026-09-01 through
2026-10-04 exclusive; requested/fulfilled monetary strings stayed distinct and history_complete
stayed false. Lifetime-sensitive unavailable metrics remain protected by canonical nullability.

Both disposable test identities were revoked through the principal-access CLI, then deleted
from Firebase with read-only reconciliation proving absence. Their private credential files
were removed. Their hashed grants remain DISABLED for audit; only the permanent approved
operator has ACTIVE ADMIN_UP access. No second live store or onboarding operation was created.
A final read-only audit reconfirmed private API IAM/anonymous 403, immutable image digests,
canonical binding, unchanged MX Registry and zero blocking Data Health failures.

Final scheduler inventory:

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

No source API, source secret value, business DML, Registry/source/Meta mutation, Installation
replan, publication modification or data scheduler change was performed in #19.1. Product
authentication and the explicitly approved legacy ownership metadata are the only added
application state. Product IAM remains within the reviewed least-privilege Stage 1 grants.
The final Stage 2 post-plan was clean; no infrastructure outcome remains ambiguous.

## Remaining production promotion

Separate PROD project/environment, production users/domain, final production E2E and DNS/cutover
are outside #19.1. Data schedulers, Foundation resources and business data are frozen here.
