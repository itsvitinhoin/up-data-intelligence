"""Synthetic only. No GCP clients, source APIs, credentials discovery or live jobs."""

import copy
import io
import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from google.api_core.exceptions import BadRequest, NotFound

from src.admin.contracts import AdminError, Principal, decode_body, parse_request
from src.admin.http import create_wsgi_app
from src.admin.repository import BigQueryOnboarding, final_rows
from src.admin.secrets import SecretManagerStore
from src.admin.service import OnboardingService
from src.analytics.cloud.transport import CloudConfig
from src.control_plane.model import StoreConfig
from src.control_plane.preflight import Prerequisites
from src.intelligence.live.runtime import binding

SYNTHETIC = "SYNTHETIC-ONLY-NOT-A-REAL-API-KEY"
AT = "2026-10-02T03:00:00+00:00"
ADMIN = Principal("synthetic-admin", "ADMIN_UP", frozenset({"synthetic-tenant"}))
KEY = "11111111-1111-4111-8111-111111111111"


def body(slug="synthetic-brand", up=True, meta=False):
    return {
        "tenant_id": "synthetic-tenant",
        "store": {
            "name": "Synthetic Brand",
            "slug": slug,
            "operation_b2b": True,
            "operation_b2c": True,
            "timezone": "America/Sao_Paulo",
            "currency": "BRL",
            "history_from": "2026-01-01",
            "qualifying_order_statuses": [
                "RESERVED",
                "CONFIRMED",
                "PROCESSING",
                "INVOICED",
                "SHIPPED",
            ],
        },
        "sources": {
            "upzero": {
                "enabled": up,
                "credential": SYNTHETIC if up else None,
                "store_identifier": None,
            },
            "meta": {
                "enabled": meta,
                "account_id": "123456789" if meta else None,
                "api_version": "v26.0" if meta else None,
            },
        },
    }


class Memory:
    def __init__(self):
        self.ops = {}
        self.configs = {}
        self.workspace = {}
        self.sources = []
        self.meta = []
        self.calls = []
        self.fail = None

    def lookup(self, subject, key):
        self.calls.append("lookup")
        return next(
            (
                copy.deepcopy(o)
                for o in self.ops.values()
                if o["admin_subject_hash"] == subject and o["idempotency_key"] == key
            ),
            None,
        )

    def get(self, operation_id):
        self.calls.append("get")
        return copy.deepcopy(self.ops.get(operation_id))

    def config(self, store):
        self.calls.append("config")
        return self.configs.get(store)

    def bindings(self, store):
        self.calls.append("bindings")
        return copy.deepcopy(self.workspace.get(store, []))

    def reserve(self, request, operation):
        self.calls.append("reserve")
        store = request.config.store_id
        if store in self.configs:
            raise AdminError("store_already_registered")
        new = request.bindings(AT)
        if any(
            a["workspace_operation_id"] == b["workspace_operation_id"]
            for rows in self.workspace.values()
            for a in rows
            for b in new
        ):
            raise AdminError("workspace_binding_conflict")
        self.ops[operation["operation_id"]] = copy.deepcopy(operation)
        self.configs[store] = replace(request.config, created_at=AT, updated_at=AT)
        self.workspace[store] = new
        return copy.deepcopy(operation)

    def transition(self, operation, **changes):
        self.calls.append("transition")
        assert self.ops[operation["operation_id"]]["revision"] == operation["revision"]
        updated = {**operation, **changes, "revision": operation["revision"] + 1}
        self.ops[operation["operation_id"]] = copy.deepcopy(updated)
        return updated

    def finalize(self, request, operation):
        self.calls.append("finalize")
        if self.fail == "definite":
            raise AdminError("registry_write_failed", 503)
        if self.fail == "unknown":
            raise AdminError("onboarding_write_outcome_unknown", 503)
        config, sources, meta = final_rows(request, operation)
        if any(
            a["connection_id"] == b["connection_id"] or a["store_id"] == config.store_id
            for a in self.sources
            for b in sources
        ):
            raise AdminError("connection_collision")
        if any(
            a["account_id"] == config.meta_account_id or a["store_id"] == config.store_id
            for a in self.meta
        ):
            raise AdminError("meta_account_collision")
        assert self.configs[config.store_id].revision == 1
        self.sources.extend(sources)
        self.meta.extend(meta)
        self.configs[config.store_id] = config
        result = {
            **operation,
            "revision": operation["revision"] + 1,
            "status": "INSTALLING",
            "current_step": "CONFIGURED",
            "error_code": None,
            "completed_at": AT,
        }
        self.ops[operation["operation_id"]] = copy.deepcopy(result)
        return result

    def exact_final(self, request, expected):
        return self.ops[expected["operation_id"]] == expected


class SecretClient:
    def __init__(self):
        self.metadata = None
        self.versions = []
        self.calls = []
        self.fail = None

    def get_secret(self, **kw):
        self.calls.append("get")
        if self.metadata is None:
            raise NotFound("synthetic missing")
        return self.metadata

    def create_secret(self, **kw):
        self.calls.append("create")
        self.metadata = NS(
            labels=kw["secret"]["labels"],
            replication=NS(user_managed=NS(replicas=[NS(location="southamerica-east1")])),
        )
        return self.metadata

    def list_secret_versions(self, **kw):
        self.calls.append("list")
        return self.versions

    def add_secret_version(self, **kw):
        self.calls.append("add")
        if self.fail == "definite":
            raise BadRequest(SYNTHETIC)
        if self.fail != "unknown_empty":
            self.versions.append(
                NS(name=kw["parent"] + "/versions/1", state=1, data=kw["payload"]["data"])
            )
        if self.fail in {"unknown_empty", "unknown_committed"}:
            raise TimeoutError(SYNTHETIC)
        return self.versions[-1]

    def access_secret_version(self, **kw):
        self.calls.append("access")
        found = next(v for v in self.versions if v.name == kw["name"])
        return NS(payload=NS(data=found.data))


@pytest.fixture
def setup():
    repo, client = Memory(), SecretClient()
    secrets = SecretManagerStore(
        client,
        project="synthetic-dev",
        project_number="123456",
        region="southamerica-east1",
        environment="dev",
    )
    leases = []

    def lease(key):
        leases.append(key)
        return nullcontext()

    return (
        OnboardingService(
            repo, secrets, lease, b"synthetic-subject-key-minimum-32-bytes", lambda: AT
        ),
        repo,
        client,
        leases,
    )


@pytest.mark.parametrize(
    "principal,code",
    [
        (None, "unauthenticated"),
        (Principal("wrong", "VIEWER", ADMIN.tenants), "admin_up_required"),
        (Principal("", "ADMIN_UP", ADMIN.tenants), "admin_up_required"),
        (Principal("wrong", "ADMIN_UP", frozenset()), "tenant_forbidden"),
    ],
)
def test_auth_before_io(setup, principal, code):
    svc, repo, client, leases = setup
    with pytest.raises(AdminError, match=code):
        svc.create(principal, KEY, body())
    assert not repo.calls and not client.calls and not leases


@pytest.mark.parametrize(
    "path,value",
    [
        (("store", "slug"), "BAD SLUG"),
        (("store", "timezone"), "Not/AZone"),
        (("store", "currency"), "XYZ"),
        (("store", "history_from"), "2026-02-30"),
        (("store", "name"), "a" * 121),
        (("sources", "upzero", "credential"), " "),
        (("sources", "upzero", "credential"), "a" * 8193),
        (("sources", "upzero", "credential"), "abc\nvalue"),
        (("sources", "meta", "account_id"), "not-id"),
    ],
)
def test_validation(setup, path, value):
    data = body(meta=True)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    svc, repo, client, _ = setup
    with pytest.raises(AdminError, match="invalid_onboarding_request"):
        svc.create(ADMIN, KEY, data)
    assert not repo.calls and not client.calls


def test_unknown_fields_no_operation_duplicate_json_and_key(setup):
    svc, repo, client, _ = setup
    for data in [
        dict(body(), secret_resource_name="synthetic"),
        {**body(), "sources": {**body()["sources"], "erp": {}}},
    ]:
        with pytest.raises(AdminError):
            svc.create(ADMIN, KEY, data)
    data = body()
    data["store"].update(operation_b2b=False, operation_b2c=False)
    with pytest.raises(AdminError):
        svc.create(ADMIN, KEY, data)
    with pytest.raises(AdminError, match="idempotency"):
        svc.create(ADMIN, "bad", body())
    with pytest.raises(AdminError):
        decode_body(b'{"a":1,"a":2}')
    with pytest.raises(AdminError):
        decode_body(b" " * 32769)
    assert not repo.calls and not client.calls


def test_success_draft_pending_numeric_version_and_idempotency(setup):
    svc, repo, client, leases = setup
    first = svc.create(ADMIN, KEY, body())
    second = svc.create(ADMIN, KEY, body())
    assert first == second and first["status"] == "INSTALLING"
    config = repo.configs[first["store_id"]]
    assert config.status == "DRAFT" and config.revision == 2
    assert not any(
        (
            config.sync_enabled,
            config.history_complete,
            config.facts_complete,
            config.analytics_enabled,
            config.intelligence_enabled,
        )
    )
    assert config.upzero_enabled and not config.eligible("upzero")
    assert config.history_from == "2026-01-01T03:00:00+00:00"
    assert first["workspace_operations"][0]["id"] != first["store_id"]
    assert client.calls.count("add") == 1 and client.calls.count("create") == 1
    assert len(repo.sources) == 1 and repo.sources[0]["status"] == "pending"
    assert (
        repo.sources[0]["secret_resource_name"]
        == "projects/synthetic-dev/secrets/up-intelligence-upzero-synthetic-brand/versions/1"
    )
    assert SYNTHETIC not in json.dumps([first, second, repo.ops, repo.sources, config.row()])
    assert "secret_resource_name" not in json.dumps(first)
    assert SYNTHETIC not in repr(parse_request(body()))
    assert leases[:2] == ["store-registry-registration-global", "synthetic-brand"]
    assert len(repo.ops) == 1 and len(repo.workspace) == 1


def test_idempotency_conflict_and_changed_credential(setup):
    svc, repo, client, _ = setup
    first = svc.create(ADMIN, KEY, body())
    changed = body()
    changed["store"]["name"] = "Different"
    with pytest.raises(AdminError, match="idempotency_conflict"):
        svc.create(ADMIN, KEY, changed)
    changed = body()
    changed["sources"]["upzero"]["credential"] = "SYNTHETIC-DIFFERENT-ONLY"
    assert parse_request(changed).request_hash == parse_request(body()).request_hash
    with pytest.raises(AdminError, match="credential_retry_mismatch"):
        svc.create(ADMIN, KEY, changed)
    assert (
        repo.ops[first["operation_id"]]["status"] == "INSTALLING" and client.calls.count("add") == 1
    )


@pytest.mark.parametrize("failure,success", [("unknown_committed", True), ("unknown_empty", False)])
def test_secret_outcome_unknown_never_blind_add(setup, failure, success):
    svc, repo, client, _ = setup
    client.fail = failure
    if success:
        assert svc.create(ADMIN, KEY, body())["status"] == "INSTALLING"
    else:
        for _ in range(2):
            with pytest.raises(AdminError, match="secret_write_outcome_unknown"):
                svc.create(ADMIN, KEY, body())
        assert not repo.sources and next(iter(repo.configs.values())).revision == 1
    assert client.calls.count("add") == 1


def test_crash_after_secret_before_reference_reconciles(setup):
    svc, repo, client, _ = setup
    original = repo.transition

    def interrupt(operation, **changes):
        if changes.get("current_step") == "SECRET_READY":
            raise RuntimeError("synthetic process interrupted")
        return original(operation, **changes)

    repo.transition = interrupt
    with pytest.raises(AdminError, match="onboarding_failed"):
        svc.create(ADMIN, KEY, body())
    assert next(iter(repo.ops.values()))["current_step"] == "VERSION_INTENT"
    repo.transition = original
    assert svc.create(ADMIN, KEY, body())["status"] == "INSTALLING"
    assert client.calls.count("add") == 1


def test_secret_collision_and_sanitized_definite_failure(setup):
    svc, repo, client, _ = setup
    client.fail = "definite"
    with pytest.raises(AdminError) as caught:
        svc.create(ADMIN, KEY, body())
    assert SYNTHETIC not in str(caught.value)
    assert next(iter(repo.ops.values()))["current_step"] == "VERSION_RETRY_ALLOWED"
    client.fail = None
    assert svc.create(ADMIN, KEY, body())["status"] == "INSTALLING"
    assert len(client.versions) == 1


def test_existing_mx_and_cross_tenant_workspace_fail_without_secret(setup):
    svc, repo, client, _ = setup
    mx = StoreConfig("mx-fashion", status="ACTIVE", revision=9, sync_enabled=True)
    repo.configs[mx.store_id] = mx
    with pytest.raises(AdminError, match="store_already_registered"):
        svc.create(ADMIN, KEY, body("mx-fashion"))
    assert repo.configs[mx.store_id] == mx and not client.calls
    repo.workspace["another"] = [
        {"workspace_operation_id": "synthetic-brand-b2b", "tenant_id": "other"}
    ]
    with pytest.raises(AdminError, match="workspace_binding_conflict"):
        svc.create(ADMIN, KEY, body())
    assert not client.calls


def test_meta_global_semantics_and_compatibility(setup):
    svc, repo, client, _ = setup
    result = svc.create(ADMIN, KEY, body(up=False, meta=True))
    assert result["sources"] == [{"source": "meta", "state": "PENDING"}]
    assert repo.sources[0]["secret_resource_name"] is None and not client.calls
    transport = NS(query=lambda *a: (repo.meta, None), config=NS(project="synthetic-dev"))
    account = binding(transport, "synthetic-brand", "123456789")
    assert account == Prerequisites(transport).account(repo.configs["synthetic-brand"])
    repo.meta[0]["currency"] = "USD"
    with pytest.raises(Exception, match="registry_meta_binding_mismatch"):
        Prerequisites(transport).account(repo.configs["synthetic-brand"])


def test_connection_and_meta_collisions_fail_closed(setup):
    svc, repo, client, _ = setup
    repo.meta = [{"store_id": "other", "account_id": "123456789"}]
    with pytest.raises(AdminError, match="meta_account_collision"):
        svc.create(ADMIN, KEY, body(up=False, meta=True))
    assert not repo.sources
    repo.meta = []
    repo.sources = [{"connection_id": "synthetic-second-upzero", "store_id": "other"}]
    with pytest.raises(AdminError, match="connection_collision"):
        svc.create(ADMIN, str(uuid4()), body("synthetic-second"))
    assert len(repo.sources) == 1


def test_bq_unknown_keeps_intent_no_second_mutation(setup):
    svc, repo, client, _ = setup
    repo.fail = "unknown"
    for _ in range(2):
        with pytest.raises(AdminError, match="onboarding_write_outcome_unknown"):
            svc.create(ADMIN, KEY, body())
    assert repo.calls.count("finalize") == 1 and client.calls.count("add") == 1
    assert next(iter(repo.ops.values()))["current_step"] == "FINALIZING"


def test_readback_auth_and_secret_free(setup):
    svc, repo, client, _ = setup
    result = svc.create(ADMIN, KEY, body())
    assert svc.read(ADMIN, result["operation_id"]) == result
    with pytest.raises(AdminError, match="not_found"):
        svc.read(Principal("other-admin", "ADMIN_UP", ADMIN.tenants), result["operation_id"])
    assert SYNTHETIC not in json.dumps(result)


def test_http_auth_limits_https_and_duplicate_json(setup):
    svc, repo, client, _ = setup
    responses = []
    env = {
        "PATH_INFO": "/v1/admin/onboarding",
        "REQUEST_METHOD": "POST",
        "wsgi.url_scheme": "https",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": "2",
        "wsgi.input": io.BytesIO(b"{}"),
        "HTTP_IDEMPOTENCY_KEY": KEY,
    }

    def start(status, headers):
        responses.append((status, headers))

    app = create_wsgi_app(lambda: svc, lambda _: None)
    assert b"unauthenticated" in b"".join(app(env, start)) and env["wsgi.input"].tell() == 0
    app = create_wsgi_app(lambda: svc, lambda _: ADMIN)
    env["CONTENT_LENGTH"] = "999999"
    assert b"request_body_too_large" in b"".join(app(env, start))
    env["CONTENT_LENGTH"] = "2"
    env["wsgi.url_scheme"] = "http"
    assert b"https_required" in b"".join(app(env, start))
    assert not repo.calls and not client.calls


class SQLTransport:
    config = CloudConfig("synthetic-dev", "southamerica-east1", 1000000, 10, False)

    def __init__(self):
        self.calls = []
        self.data = {}
        self.fault = None

    def query(self, sql, parameters, **kwargs):
        self.calls.append((sql, parameters, kwargs))
        if sql.startswith("BEGIN"):
            if self.fault:
                raise self.fault
            return [], None
        table = next((name for name in self.data if f".{name}`" in sql), None)
        return self.data.get(table, []), None


def ledger(request):
    return {
        "row_key": "synthetic-row",
        "operation_id": KEY,
        "idempotency_key": KEY,
        "admin_subject_hash": "synthetic-subject",
        "request_hash": request.request_hash,
        "tenant_id": request.tenant_id,
        "store_id": request.config.store_id,
        "status": "RESERVED",
        "current_step": "RESERVED",
        "error_code": None,
        "secret_version_name": None,
        "revision": 1,
        "created_at": AT,
        "updated_at": AT,
        "completed_at": None,
    }


def test_sql_reservation_finalization_cas_scope_no_plaintext():
    t = SQLTransport()
    repo = BigQueryOnboarding(t)
    req = parse_request(body(meta=True))
    op = ledger(req)
    repo.reserve(req, op)
    op = repo.transition(
        op,
        status="FINALIZING",
        current_step="FINALIZING",
        secret_version_name="projects/synthetic-dev/secrets/up-intelligence-upzero-synthetic-brand/versions/1",
    )
    repo.finalize(req, op)
    assert len(t.calls) == 3
    for sql, params, kw in t.calls:
        assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
        assert req.config.store_id not in sql and SYNTHETIC not in str(params)
        assert kw["job_id"].startswith("onboarding_")
    sql = t.calls[-1][0]
    for text in (
        "registry_revision_conflict",
        "workspace_binding_conflict",
        "connection_collision",
        "meta_account_collision",
        "onboarding_revision_conflict",
        "source_connections",
        "meta_account_bindings",
        "workspace_store_bindings",
        "onboarding_operations",
    ):
        assert text in sql
    assert "secret_data" not in sql and "sync_runs" not in sql


@pytest.mark.parametrize("committed", [True, False])
def test_sql_unknown_reservation_recovers_only_exact_rows(committed):
    t = SQLTransport()
    repo = BigQueryOnboarding(t)
    req = parse_request(body())
    op = ledger(req)
    t.fault = TimeoutError("synthetic unknown")
    if committed:
        t.data = {
            "onboarding_operations": [op],
            "store_runtime_config": [replace(req.config, created_at=AT, updated_at=AT).row()],
            "workspace_store_bindings": req.bindings(AT),
        }
        assert repo.reserve(req, op) == op
    else:
        with pytest.raises(AdminError, match="onboarding_write_outcome_unknown"):
            repo.reserve(req, op)
    assert sum(sql.startswith("BEGIN") for sql, _, _ in t.calls) == 1


def test_sql_finalization_unknown_exact_receipt_and_definite_failure():
    t = SQLTransport()
    repo = BigQueryOnboarding(t)
    req = parse_request(body(meta=True))
    op = ledger(req)
    op.update(
        current_step="FINALIZING",
        status="FINALIZING",
        secret_version_name="projects/synthetic-dev/secrets/up-intelligence-upzero-synthetic-brand/versions/1",
    )
    expected = {
        **op,
        "revision": 2,
        "status": "INSTALLING",
        "current_step": "CONFIGURED",
        "error_code": None,
        "completed_at": AT,
    }
    c, sources, meta = final_rows(req, expected)
    t.data = {
        "onboarding_operations": [expected],
        "store_runtime_config": [c.row()],
        "workspace_store_bindings": req.bindings(AT),
        "source_connections": sources,
        "meta_account_bindings": meta,
    }
    t.fault = TimeoutError("synthetic unknown")
    assert repo.finalize(req, op) == expected
    t.fault = BadRequest("synthetic connection_collision")
    with pytest.raises(AdminError, match="connection_collision"):
        repo.finalize(req, op)


def test_bq_sdk_timestamps_normalized_before_retry():
    t = SQLTransport()
    req = parse_request(body(up=False))
    op = ledger(req)
    sdk_op = {
        **op,
        "created_at": datetime.fromisoformat(AT),
        "updated_at": datetime.fromisoformat(AT),
    }
    t.data = {"onboarding_operations": [sdk_op]}
    repo = BigQueryOnboarding(t)
    assert repo.get(KEY) == op
    assert final_rows(req, repo.get(KEY))[0].created_at == AT


@pytest.mark.parametrize(
    "reference",
    [
        None,
        "projects/synthetic-dev/secrets/up-intelligence-upzero-synthetic-brand/versions/latest",
        "projects/synthetic-dev/secrets/up-intelligence-upzero-other/versions/1",
        "projects/foreign-dev/secrets/up-intelligence-upzero-synthetic-brand/versions/1",
    ],
)
def test_invalid_reference_never_finalized(reference):
    t = SQLTransport()
    repo = BigQueryOnboarding(t)
    req = parse_request(body())
    op = {**ledger(req), "secret_version_name": reference}
    with pytest.raises(AdminError, match="onboarding_metadata_invalid"):
        repo.finalize(req, op)
    assert not t.calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "foreign-tenant"),
        ("store_id", "foreign-store"),
        ("brand_id", "brand-foreign"),
        ("workspace_operation_id", "foreign-b2b"),
    ],
)
def test_readback_binding_corruption_fails_closed(setup, field, value):
    svc, repo, _, _ = setup
    result = svc.create(ADMIN, KEY, body(up=False))
    repo.workspace["synthetic-brand"][0][field] = value
    with pytest.raises(AdminError, match="onboarding_metadata_invalid"):
        svc.read(ADMIN, result["operation_id"])


def test_unknown_reservation_rejects_unexpected_connections():
    t = SQLTransport()
    repo = BigQueryOnboarding(t)
    req = parse_request(body(up=False))
    op = ledger(req)
    t.data = {
        "onboarding_operations": [op],
        "store_runtime_config": [replace(req.config, created_at=AT, updated_at=AT).row()],
        "workspace_store_bindings": req.bindings(AT),
        "source_connections": [{"store_id": req.config.store_id, "connection_id": "unexpected"}],
    }
    t.fault = TimeoutError("synthetic uncertain")
    with pytest.raises(AdminError, match="onboarding_write_outcome_unknown"):
        repo.reserve(req, op)
    assert sum(sql.startswith("BEGIN") for sql, _, _ in t.calls) == 1


@pytest.mark.parametrize("candidate", ["disabled", "multiple", "foreign"])
def test_ambiguous_secret_candidates_never_add(setup, candidate):
    svc, repo, client, _ = setup
    request = parse_request(body())
    secret = svc.secrets
    secret.container(request.config.store_id, KEY, reconcile_only=False)
    name = secret.name(request.config.store_id) + "/versions/1"
    client.versions = [NS(name=name, state=1, data=SYNTHETIC.encode())]
    if candidate == "disabled":
        client.versions[0].state = 2
    elif candidate == "multiple":
        client.versions.append(NS(name=name[:-1] + "2", state=1, data=SYNTHETIC.encode()))
    else:
        client.versions[0].name = name.replace("synthetic-brand", "other-brand")
    with pytest.raises(AdminError, match="secret_write_outcome_unknown"):
        secret.initial(request.config.store_id, KEY, SYNTHETIC, reconcile_only=True)
    assert "add" not in client.calls


def test_unknown_bq_transition_read_error_never_second_mutation():
    t = SQLTransport()
    repo = BigQueryOnboarding(t)
    op = ledger(parse_request(body(up=False)))
    t.fault = TimeoutError("synthetic uncertain")
    with pytest.raises(AdminError, match="onboarding_write_outcome_unknown"):
        repo.transition(op, status="FINALIZING", current_step="FINALIZING")
    assert sum(sql.startswith("BEGIN") for sql, _, _ in t.calls) == 1


def test_cloud_lease_uncertain_code_preserved(setup):
    from contextlib import contextmanager

    svc, repo, _, _ = setup
    outcomes = []

    @contextmanager
    def lease(store):
        try:
            yield
        except Exception as exc:
            outcomes.append((store, getattr(exc, "code", None)))
            raise

    svc.lease = lease
    repo.fail = "unknown"
    with pytest.raises(AdminError, match="onboarding_write_outcome_unknown"):
        svc.create(ADMIN, KEY, body(up=False))
    assert outcomes == [
        ("synthetic-brand", "registry_write_outcome_unknown"),
        ("store-registry-registration-global", "registry_write_outcome_unknown"),
    ]


def test_foreign_owned_secret_collision_never_added(setup):
    svc, repo, client, _ = setup
    svc.secrets.container("synthetic-brand", "different-operation", reconcile_only=False)
    with pytest.raises(AdminError, match="secret_name_collision"):
        svc.create(ADMIN, KEY, body())
    assert "add" not in client.calls and not repo.sources
    assert next(iter(repo.ops.values()))["status"] == "BLOCKED"


def test_container_create_unknown_recovers_without_second_create(setup):
    svc, repo, client, _ = setup
    create = client.create_secret

    def unknown(**kwargs):
        create(**kwargs)
        raise TimeoutError(SYNTHETIC)

    client.create_secret = unknown
    assert svc.create(ADMIN, KEY, body())["status"] == "INSTALLING"
    assert client.calls.count("create") == 1 and client.calls.count("add") == 1


def test_definite_finalization_failure_retry_preserves_secret(setup):
    svc, repo, client, _ = setup
    repo.fail = "definite"
    with pytest.raises(AdminError, match="registry_write_failed"):
        svc.create(ADMIN, KEY, body())
    assert next(iter(repo.ops.values()))["current_step"] == "FINALIZATION_RETRY_ALLOWED"
    assert repo.configs["synthetic-brand"].revision == 1
    repo.fail = None
    assert svc.create(ADMIN, KEY, body())["status"] == "INSTALLING"
    assert client.calls.count("add") == 1 and len(repo.sources) == 1


def test_http_post_get_returns_only_safe_metadata(setup):
    svc, _, _, _ = setup
    app = create_wsgi_app(lambda: svc, lambda _: ADMIN)
    statuses = []

    def start(status, headers):
        statuses.append(status)
        assert ("Cache-Control", "private, no-store") in headers

    payload = json.dumps(body()).encode()
    env = {
        "PATH_INFO": "/v1/admin/onboarding",
        "REQUEST_METHOD": "POST",
        "wsgi.url_scheme": "https",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": io.BytesIO(payload),
        "HTTP_IDEMPOTENCY_KEY": KEY,
    }
    response = b"".join(app(env, start))
    assert statuses[-1] == "201 Created" and SYNTHETIC.encode() not in response
    operation = json.loads(response)["operation_id"]
    env.update(PATH_INFO="/v1/admin/onboarding/" + operation, REQUEST_METHOD="GET")
    assert b"".join(app(env, start)) == response and statuses[-1] == "200 OK"


def test_onboarding_terraform_scope_and_secret_permissions():
    from pathlib import Path

    text = Path("infra/terraform/onboarding.tf").read_text()
    assert (
        '"source_connections", "meta_account_bindings", "workspace_store_bindings", "onboarding_operations"'
        in text
    )
    for permission in [
        "secretmanager.secrets.create",
        "secretmanager.secrets.get",
        "secretmanager.versions.add",
        "secretmanager.versions.list",
        "secretmanager.versions.access",
    ]:
        assert permission in text
    for forbidden in [
        "secretmanager.secrets.delete",
        "secretmanager.admin",
        "roles/editor",
        "roles/owner",
        "google_cloud_run",
        "google_cloud_scheduler",
        "google_secret_manager_secret_version",
    ]:
        assert forbidden not in text
    assert "resource.name.startsWith" in text and "up-intelligence-upzero-" in text
    workers = Path("infra/terraform/control_plane.tf").read_text()
    assert '"source_connections", "workspace_store_bindings", "onboarding_operations"' in workers


def test_unknown_secret_write_read_failure_remains_unknown(setup):
    svc, _, client, _ = setup
    client.fail = "unknown_committed"
    original = client.list_secret_versions

    def list_versions(**kwargs):
        if "add" in client.calls:
            raise TimeoutError(SYNTHETIC)
        return original(**kwargs)

    client.list_secret_versions = list_versions
    for _ in range(2):
        with pytest.raises(AdminError) as caught:
            svc.create(ADMIN, KEY, body())
        assert caught.value.code in {"secret_write_outcome_unknown", "secret_read_failed"}
        assert SYNTHETIC not in str(caught.value)
    assert client.calls.count("add") == 1


def test_installation_readback_only_after_owner_and_tenant_authorization(setup):
    svc, _, _, _ = setup
    result = svc.create(ADMIN, KEY, body())
    calls = []
    svc.installation = lambda tenant, store: (
        calls.append((tenant, store))
        or {
            "data": {"store_id": store},
            "metadata": {"contract_version": "installation.v2"},
            "pagination": None,
        }
    )
    for principal in (
        None,
        Principal("other", "ADMIN_UP", ADMIN.tenants),
        Principal(ADMIN.subject, "ADMIN_UP", frozenset({"foreign-tenant"})),
    ):
        with pytest.raises(AdminError):
            svc.read(principal, result["operation_id"])
    assert not calls
    read = svc.read(ADMIN, result["operation_id"])
    assert calls == [("synthetic-tenant", "synthetic-brand")]
    assert read["installation"]["data"]["store_id"] == "synthetic-brand"
    assert SYNTHETIC not in json.dumps(read) and "secret_version_name" not in read
