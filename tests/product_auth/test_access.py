import io
import json
import time

import pytest

from src.dashboard.contracts import ReadError
from src.product_auth.access import resolve, verified_identity
from src.product_auth.http import create_admin_app, create_read_app
from src.product_auth.session import Sessions
from src.utils.data import digest


class Repository:
    def __init__(self, role="ADMIN_UP", tenant="tenant-a", workspace=None):
        identity = verified_identity(
            {"uid": "synthetic", "email": " TEST@example.invalid ", "email_verified": True}
        )
        self.identity = identity
        self.rows = [
            {
                "row_key": digest([identity.identity_hash, tenant, workspace]),
                "identity_hash": identity.identity_hash,
                "role": role,
                "tenant_id": tenant,
                "workspace_operation_id": workspace,
                "status": "ACTIVE",
            }
        ]
        self.workspaces = [
            {
                "row_key": digest([tenant, "workspace-a"]),
                "tenant_id": tenant,
                "brand_id": "brand-a",
                "workspace_operation_id": "workspace-a",
                "store_id": "technical-a",
                "operation": "B2B",
                "status": "ACTIVE",
            }
        ]

    def access(self, identity_hash):
        assert identity_hash == self.identity.identity_hash
        return self.rows

    def bindings(self, tenants):
        return self.workspaces


class Verifier:
    def __init__(self):
        self.claims = {
            "uid": "synthetic",
            "email": "test@example.invalid",
            "email_verified": True,
            "auth_time": int(time.time()),
        }
        self.created = []
        self.revoked = []

    def session(self, value):
        if value != "verified-cookie":
            raise ReadError(401, "invalid_session")
        return self.claims

    def token(self, value):
        if value != "fresh-id-token":
            raise ReadError(401, "invalid_identity_token")
        return self.claims

    def create(self, value):
        self.created.append(value)
        return "server-only-cookie"

    def revoke(self, uid):
        self.revoked.append(uid)


def call(app, path, query="", method="GET", cookie="verified-cookie", body=None):
    payload = json.dumps(body or {}).encode()
    env = {
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REQUEST_METHOD": method,
        "HTTP_X_UP_SESSION": cookie,
        "CONTENT_LENGTH": str(len(payload)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(payload),
    }
    result = []
    data = b"".join(app(env, lambda status, headers: result.append((status, dict(headers)))))
    return int(result[0][0].split()[0]), json.loads(data), result[0][1]


def test_verified_email_hash_not_claims_authority():
    a = verified_identity(
        {
            "uid": "one",
            "email": " TEST@example.invalid ",
            "email_verified": True,
            "role": "ADMIN_UP",
        }
    )
    b = verified_identity({"uid": "one", "email": "test@example.invalid", "email_verified": True})
    assert a == b
    assert "test@" not in repr(a)
    with pytest.raises(ReadError, match="verified_email_required"):
        verified_identity({"uid": "one", "email": "test@example.invalid", "email_verified": False})


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "conflict",
        "disabled",
        "wrong_hash",
        "wrong_tenant",
        "duplicate_binding",
        "wrong_key",
    ],
)
def test_access_fail_closed(mutation):
    r = Repository()
    if mutation == "duplicate":
        r.rows.append(dict(r.rows[0]))
    elif mutation == "conflict":
        r.rows.append(dict(r.rows[0], role="CLIENT_USER"))
    elif mutation == "disabled":
        r.rows[0]["status"] = "DISABLED"
    elif mutation == "wrong_hash":
        r.rows[0]["identity_hash"] = "wrong"
    elif mutation == "wrong_tenant":
        r.workspaces[0]["tenant_id"] = "other"
    elif mutation == "duplicate_binding":
        r.workspaces.append(dict(r.workspaces[0]))
    elif mutation == "wrong_key":
        r.rows[0]["row_key"] = "wrong"
    with pytest.raises(ReadError):
        resolve(r.identity, r)


def test_client_explicit_workspace_and_admin_denied():
    r = Repository(role="CLIENT_USER", workspace="workspace-a")
    a = resolve(r.identity, r)
    a.dashboard().authorize("tenant-a", "technical-a", "B2B")
    with pytest.raises(ReadError):
        a.dashboard().authorize("tenant-a", "other", "B2B")
    with pytest.raises(ReadError):
        a.binding("other", "workspace-a", "B2B")
    with pytest.raises(ReadError):
        a.binding("tenant-a", "other", "B2B")
    with pytest.raises(ReadError, match="admin_up_required"):
        a.admin()
    assert "technical-a" not in json.dumps(a.catalog())
    assert "example.invalid" not in json.dumps(a.catalog())
    r.workspaces.clear()
    with pytest.raises(ReadError, match="workspace_binding_required"):
        resolve(r.identity, r)


def test_no_implicit_client_tenant_access():
    r = Repository(role="CLIENT_USER")
    with pytest.raises(ReadError):
        resolve(r.identity, r)


def test_session_exchange_revocation_and_no_access_cache():
    r, v = Repository(), Verifier()
    s = Sessions(v, r)
    assert s.exchange("fresh-id-token") == "server-only-cookie"
    assert s.authenticate("verified-cookie").role == "ADMIN_UP"
    r.rows[0]["status"] = "DISABLED"
    with pytest.raises(ReadError):
        s.authenticate("verified-cookie")
    s.logout("verified-cookie")
    assert v.revoked == ["synthetic"]


@pytest.mark.parametrize("state", ["unverified", "old", "unprovisioned", "invalid"])
def test_exchange_rejected_before_cookie_creation(state):
    r, v = Repository(), Verifier()
    token = "fresh-id-token"
    if state == "unverified":
        v.claims["email_verified"] = False
    elif state == "old":
        v.claims["auth_time"] = int(time.time()) - 301
    elif state == "unprovisioned":
        r.rows = []
    else:
        token = "invalid"
    with pytest.raises(ReadError):
        Sessions(v, r).exchange(token)
    assert v.created == []


def test_private_read_auth_scope_and_no_business_io():
    r, v = Repository(), Verifier()

    def business(_):
        raise AssertionError("Unauthorized requests must never construct business reader")

    app = create_read_app(lambda: Sessions(v, r), business)
    assert call(app, "/v1/session", cookie="")[0] == 401
    assert call(app, "/v1/session", cookie="invalid")[0] == 401
    assert call(app, "/v1/session")[0] == 200
    for query in [
        "tenant_id=other&workspace_operation_id=workspace-a&operation=B2B",
        "tenant_id=tenant-a&workspace_operation_id=other&operation=B2B",
        "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B&store_id=technical-a",
    ]:
        assert call(app, "/v1/dashboard/overview", query)[0] == 403
    r.rows.clear()
    assert call(app, "/v1/session")[0:2] == (403, {"error": {"code": "access_not_provisioned"}})


def test_private_admin_cookie_not_json_and_client_denied():
    r, v = Repository(), Verifier()

    def business():
        raise AssertionError("No onboarding IO for auth routes or client")

    app = create_admin_app(lambda: Sessions(v, r), business)
    status, data, headers = call(
        app, "/v1/auth/session", method="POST", body={"id_token": "fresh-id-token"}
    )
    assert status == 200 and "server-only-cookie" not in json.dumps(data)
    for attribute in [
        "__Host-up_session=",
        "Secure",
        "HttpOnly",
        "SameSite=Lax",
        "Path=/",
        "Max-Age=43200",
    ]:
        assert attribute in headers["Set-Cookie"]
    assert call(app, "/v1/auth/logout", method="POST")[2]["Set-Cookie"].endswith("Max-Age=0")
    client = Repository(role="CLIENT_USER", workspace="workspace-a")
    app = create_admin_app(lambda: Sessions(v, client), business)
    assert call(app, "/v1/admin/onboarding", method="POST")[0] == 403
    assert call(app, "/v1/admin/onboarding", method="POST", cookie="")[0] == 401


def test_binding_conflict_and_missing_binding_fail_closed():
    repo = Repository("CLIENT_USER", workspace="workspace-a")
    repo.workspaces.append(dict(repo.workspaces[0]))
    with pytest.raises(ReadError, match="workspace_binding_invalid"):
        resolve(repo.identity, repo)
    repo.workspaces = []
    with pytest.raises(ReadError, match="workspace_binding_required"):
        resolve(repo.identity, repo)


def test_admin_claim_is_not_an_access_grant():
    repo = Repository("CLIENT_USER", workspace="workspace-a")
    verifier = Verifier()
    verifier.claims.update(role="ADMIN_UP", tenant_id="other", store_id="other")
    access = Sessions(verifier, repo).authenticate("verified-cookie")
    assert access.role == "CLIENT_USER"
    assert access.tenants == frozenset({"tenant-a"})
    with pytest.raises(ReadError, match="admin_up_required"):
        access.admin()


def test_private_read_valid_catalog_and_scope_use_canonical_store(monkeypatch):
    repo = Repository("CLIENT_USER", workspace="workspace-a")
    invoked = []

    def dispatch(service, method, path, query, principal):
        invoked.append((path, query, principal))
        assert service == "business-service"
        assert method == "GET"
        assert path == "/v1/stores/technical-a/overview"
        assert "workspace_operation_id" not in query
        principal.authorize("tenant-a", "technical-a", "B2B")
        with pytest.raises(ReadError):
            principal.authorize("tenant-a", "other", "B2B")
        return 200, {"data": {"requested_revenue": "21.99", "fulfilled_revenue": "18.21"}}

    monkeypatch.setattr("src.product_auth.http.dispatch", dispatch)
    app = create_read_app(lambda: Sessions(Verifier(), repo), lambda _: "business-service")
    status, catalog, _ = call(app, "/v1/session")
    assert status == 200
    assert "technical-a" not in json.dumps(catalog)
    assert not invoked
    status, body, headers = call(
        app,
        "/v1/dashboard/overview",
        "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B",
    )
    assert status == 200
    assert body["data"] == {"requested_revenue": "21.99", "fulfilled_revenue": "18.21"}
    assert headers["Cache-Control"] == "private, no-store"
    assert len(invoked) == 1


def test_firebase_verifier_revocation_expiration_and_safe_errors(monkeypatch):
    from firebase_admin import auth

    from src.product_auth.session import SESSION_SECONDS, FirebaseVerifier

    calls = []

    def verified(value, **kwargs):
        calls.append(kwargs)
        assert kwargs["check_revoked"] is True
        if value == "expired-or-revoked":
            raise ValueError("private token/email details must never leave verifier")
        return Verifier().claims

    monkeypatch.setattr(auth, "verify_session_cookie", verified)
    monkeypatch.setattr(auth, "verify_id_token", verified)
    verifier = FirebaseVerifier("sdk-app")
    assert verifier.session("valid")["email_verified"] is True
    assert verifier.token("valid")["email_verified"] is True
    with pytest.raises(ReadError, match="invalid_session") as error:
        verifier.session("expired-or-revoked")
    assert "private token" not in str(error.value)
    with pytest.raises(ReadError, match="invalid_identity_token"):
        verifier.token("expired-or-revoked")
    created = []
    monkeypatch.setattr(
        auth, "create_session_cookie", lambda token, **kw: created.append(kw) or "cookie"
    )
    assert verifier.create("temporary") == "cookie"
    assert created[0]["expires_in"].total_seconds() == SESSION_SECONDS == 43200
    revoked = []
    monkeypatch.setattr(auth, "revoke_refresh_tokens", lambda uid, **kw: revoked.append(uid))
    verifier.revoke("synthetic")
    assert revoked == ["synthetic"]


def test_cli_confirmation_precedes_any_io():
    from types import SimpleNamespace

    from src.product_auth.cli import validate

    args = SimpleNamespace(
        live=True,
        project="up-data-intelligence-dev",
        confirm_project="up-data-intelligence-dev",
        tenant="tenant-a",
        command="grant",
        role="CLIENT_USER",
        workspace_operation_id="workspace-a",
        confirm_workspace_operation="workspace-a",
    )
    validate(args)
    for key, value in [
        ("live", False),
        ("confirm_project", "prod"),
        ("tenant", "bad;sql"),
        ("confirm_workspace_operation", "other"),
    ]:
        current = SimpleNamespace(**{**vars(args), key: value})
        with pytest.raises(ReadError):
            validate(current)


def test_authorization_queries_are_bounded_and_parameterized():
    from src.product_auth.repository import BigQueryAccess

    class Reader:
        queries = []

        def query(self, query, **metadata):
            self.queries.append(query)
            return []

    reader = Reader()
    repo = BigQueryAccess(reader, "up-data-intelligence-dev")
    repo.access("untrusted'input")
    repo.bindings(frozenset({"tenant'input"}))
    assert "untrusted'input" not in reader.queries[0].sql
    assert "tenant'input" not in reader.queries[1].sql
    assert "LIMIT 101" in reader.queries[0].sql
    assert "LIMIT 1001" in reader.queries[1].sql
    with pytest.raises(ValueError):
        BigQueryAccess(reader, "unsafe`project")


def test_one_statement_access_snapshot_is_fresh_and_keeps_all_isolation_guards():
    from copy import deepcopy

    from src.product_auth.repository import BigQueryAccess

    fixture = Repository()

    class Reader:
        def __init__(self):
            self.queries = []

        def query(self, query, **metadata):
            self.queries.append(query)
            return [{"grants": deepcopy(fixture.rows), "bindings": deepcopy(fixture.workspaces)}]

    reader = Reader()
    repo = BigQueryAccess(reader, "up-data-intelligence-dev")
    access = resolve(fixture.identity, repo)
    assert len(reader.queries) == 1
    query = reader.queries[0]
    assert query.name == "access_snapshot"
    assert query.parameters == {"identity": ("STRING", fixture.identity.identity_hash)}
    assert fixture.identity.identity_hash not in query.sql
    assert "LIMIT 101" in query.sql and "LIMIT 1001" in query.sql
    assert "tenant_id IN (SELECT tenant_id FROM grants)" in query.sql
    with pytest.raises(ReadError, match="workspace_forbidden"):
        access.binding("other-tenant", "workspace-a", "B2B")
    with pytest.raises(ReadError, match="workspace_forbidden"):
        access.binding("tenant-a", "other-workspace", "B2B")
    fixture.rows[0]["status"] = "DISABLED"
    with pytest.raises(ReadError, match="access_disabled_or_invalid"):
        resolve(fixture.identity, repo)
    assert len(reader.queries) == 2  # No authorization cache, even on the same object.
    fixture.rows[0]["status"] = "ACTIVE"
    fixture.workspaces[0]["tenant_id"] = "other-tenant"
    with pytest.raises(ReadError, match="workspace_binding_invalid"):
        resolve(fixture.identity, repo)
    assert len(reader.queries) == 3


@pytest.mark.parametrize(
    "rows", [[], [{"grants": None, "bindings": []}], [{"grants": [], "bindings": ["bad"]}]]
)
def test_invalid_access_snapshot_is_rejected(rows):
    from src.product_auth.repository import BigQueryAccess

    class Reader:
        def query(self, query, **metadata):
            return rows

    with pytest.raises(ReadError, match="access_snapshot_invalid"):
        BigQueryAccess(Reader(), "up-data-intelligence-dev").snapshot("synthetic-identity")
