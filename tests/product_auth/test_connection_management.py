from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.admin.connections import ConnectionService
from src.admin.contracts import AdminError, Principal
from src.admin.rotation import RotationStore
from src.domain.models import SafeError
from tests.installation.test_extensions import installed

KEY = "00000000-0000-4000-8000-000000000001"
BINDING = dict(
    tenant_id="tenant-a",
    workspace_operation_id="workspace-a",
    store_id=installed()[0].store_id,
    operation="B2B",
)
ADMIN = Principal("synthetic-admin", "ADMIN_UP", frozenset({"tenant-a"}))
CREDENTIAL = "synthetic-not-a-real-credential"


class Repository:
    def __init__(self):
        self.config, self.source, *_ = installed()
        self.source["secret_resource_name"] = (
            "projects/synthetic-dev/secrets/up-intelligence-upzero-store/versions/1"
        )
        self.ops = {}
        self.writes = []
        self.busy = False

    def snapshot(self, binding, provider):
        if provider == "meta":
            source = dict(
                self.source,
                connection_id=self.config.meta_connection_id,
                source_system="meta",
                secret_resource_name=None,
            )
        else:
            source = self.source
        return self.config, deepcopy(source)

    def ensure_idle(self, *args):
        if self.busy:
            raise AdminError("integration_work_requires_reconciliation")

    def operation(self, key):
        return deepcopy(self.ops.get(key))

    def reserve_operation(self, op):
        self.ops[op["operation_id"]] = deepcopy(op)
        self.writes.append("reserve")
        return op

    def transition(self, op, **changes):
        assert self.ops[op["operation_id"]]["revision"] == op["revision"]
        result = dict(op, **changes, revision=op["revision"] + 1)
        self.ops[op["operation_id"]] = deepcopy(result)
        self.writes.append("transition")
        return result

    def finalize_connection(self, op, binding, c, source, new_config, new_source):
        assert c == self.config
        self.config, self.source = new_config, new_source
        result = dict(op, status="COMPLETE", revision=op["revision"] + 1)
        self.ops[op["operation_id"]] = deepcopy(result)
        self.writes.append("final")
        return result


def service():
    repo = Repository()
    secrets = Mock()
    secrets.versions.return_value = [repo.source["secret_resource_name"]]
    secrets.rotate.return_value = repo.source["secret_resource_name"].rsplit("/", 1)[0] + "/2"
    probe = Mock()
    locks = []

    @contextmanager
    def lease(key):
        try:
            yield
        except SafeError as exc:
            locks.append(exc.code)
            raise

    return (
        ConnectionService(repo, secrets, probe, lease, b"synthetic-subject-key" * 3),
        repo,
        secrets,
        probe,
        locks,
    )


def test_rotation_verifies_before_pin_and_preserves_registry_and_prior_version():
    s, r, secrets, probe, _ = service()
    before = r.config
    result = s.mutate(
        ADMIN, BINDING, KEY, dict(provider="upzero", action="rotate", credential=CREDENTIAL)
    )
    assert result["data"]["status"] == "COMPLETE"
    assert r.config == before and r.source["secret_resource_name"].endswith("/2")
    probe.assert_called_once_with(before, "upzero", r.source["secret_resource_name"])
    assert "credential" not in str(r.ops) and CREDENTIAL not in str(r.ops)
    assert "/versions/" not in str(result)
    s.mutate(ADMIN, BINDING, KEY, dict(provider="upzero", action="rotate", credential=CREDENTIAL))
    assert secrets.rotate.call_count == probe.call_count == 1
    secrets.compare.assert_called_once()


@pytest.mark.parametrize(
    "principal",
    [
        None,
        Principal("client", "CLIENT_USER", frozenset({"tenant-a"})),
        Principal("admin", "ADMIN_UP", frozenset({"other"})),
    ],
)
def test_unauthorized_cannot_read_metadata_or_secret(principal):
    s, r, secrets, probe, _ = service()
    r.snapshot = Mock(side_effect=AssertionError("forbidden IO"))
    with pytest.raises(AdminError):
        s.mutate(
            principal, BINDING, KEY, dict(provider="upzero", action="rotate", credential=CREDENTIAL)
        )
    secrets.rotate.assert_not_called()
    probe.assert_not_called()
    r.snapshot.assert_not_called()


def test_unknown_secret_or_probe_never_pins_and_retains_locks():
    for outcome in ("secret", "probe"):
        s, r, secrets, probe, locks = service()
        old = deepcopy(r.source)
        (secrets.rotate if outcome == "secret" else probe).side_effect = SafeError(
            "secret_write_outcome_unknown"
            if outcome == "secret"
            else "source_verification_outcome_unknown"
        )
        with pytest.raises(AdminError, match="outcome_unknown"):
            s.mutate(
                ADMIN, BINDING, KEY, dict(provider="upzero", action="rotate", credential=CREDENTIAL)
            )
        assert r.source == old and "registry_write_outcome_unknown" in locks
        if outcome == "probe":
            probe.side_effect = None
            with pytest.raises(AdminError, match="source_verification_outcome_unknown"):
                s.mutate(
                    ADMIN,
                    BINDING,
                    KEY,
                    dict(provider="upzero", action="rotate", credential=CREDENTIAL),
                )
            assert probe.call_count == 1


def test_busy_work_blocks_before_version_write_or_probe():
    s, r, secrets, probe, _ = service()
    r.busy = True
    with pytest.raises(AdminError, match="requires_reconciliation"):
        s.mutate(
            ADMIN, BINDING, KEY, dict(provider="upzero", action="rotate", credential=CREDENTIAL)
        )
    assert r.writes == []
    secrets.rotate.assert_not_called()
    probe.assert_not_called()


def test_disable_keeps_history_and_other_source_but_disables_dependents():
    s, r, secrets, probe, _ = service()
    before = r.config
    s.mutate(ADMIN, BINDING, KEY, dict(provider="upzero", action="disable", credential=None))
    assert r.source["status"] == "disabled"
    assert (
        not r.config.upzero_enabled
        and not r.config.analytics_enabled
        and not r.config.intelligence_enabled
    )
    assert r.config.meta_enabled == before.meta_enabled and r.config.history_complete is False
    assert r.config.status == before.status and r.config.sync_enabled == before.sync_enabled
    assert (
        r.config.facts_coverage_from == before.facts_coverage_from
        and r.config.history_from == before.history_from
    )
    secrets.rotate.assert_not_called()
    probe.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        dict(provider="google", action="enable", credential=CREDENTIAL),
        dict(provider="meta", action="rotate", credential=None),
        dict(provider="meta", action="enable", credential=CREDENTIAL),
        dict(provider="upzero", action="rotate", credential=""),
        dict(provider="upzero", action="rotate", credential=CREDENTIAL, store_id="foreign"),
    ],
)
def test_provider_contract_rejects_invented_fields_before_io(payload):
    s, r, secrets, probe, _ = service()
    with pytest.raises(AdminError):
        s.mutate(ADMIN, BINDING, KEY, payload)
    assert r.writes == []
    secrets.rotate.assert_not_called()
    probe.assert_not_called()


def test_unknown_version_add_reconciles_one_new_version_without_second_add():
    parent = "projects/synthetic-dev/secrets/up-intelligence-upzero-store"
    client = Mock()
    client.list_secret_versions.side_effect = [
        [SimpleNamespace(name=parent + "/versions/1")],
        [
            SimpleNamespace(name=parent + "/versions/1"),
            SimpleNamespace(name=parent + "/versions/2"),
        ],
    ]
    client.add_secret_version.side_effect = TimeoutError()
    client.access_secret_version.return_value.payload.data = CREDENTIAL.encode()
    secrets = RotationStore(client, "synthetic-dev", "123")
    assert secrets.rotate(
        parent + "/versions/1", [parent + "/versions/1"], CREDENTIAL, reconcile_only=False
    ).endswith("/2")
    assert client.add_secret_version.call_count == 1
    assert client.add_secret_version.call_args.kwargs["retry"] is None


def test_unknown_version_add_with_multiple_new_candidates_stops():
    parent = "projects/synthetic-dev/secrets/up-intelligence-upzero-store"
    client = Mock()
    client.list_secret_versions.side_effect = [
        [SimpleNamespace(name=parent + "/versions/1")],
        [SimpleNamespace(name=parent + "/versions/" + str(n)) for n in (1, 2, 3)],
    ]
    client.add_secret_version.side_effect = TimeoutError()
    with pytest.raises(SafeError, match="secret_write_outcome_unknown"):
        RotationStore(client, "synthetic-dev", "123").rotate(
            parent + "/versions/1", [parent + "/versions/1"], CREDENTIAL, reconcile_only=False
        )
    assert client.add_secret_version.call_count == 1
    client.access_secret_version.assert_not_called()


@pytest.mark.parametrize(
    "path", ["/v1/admin/integrations/history", "/v1/admin/integrations/configuration"]
)
@pytest.mark.parametrize(
    "role,query,cookie,expected",
    [
        (
            "CLIENT_USER",
            "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B",
            "verified-cookie",
            403,
        ),
        (
            "ADMIN_UP",
            "tenant_id=foreign&workspace_operation_id=workspace-a&operation=B2B",
            "verified-cookie",
            403,
        ),
        (
            "ADMIN_UP",
            "tenant_id=tenant-a&workspace_operation_id=foreign&operation=B2B",
            "verified-cookie",
            403,
        ),
        (
            "ADMIN_UP",
            "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B&store_id=foreign",
            "verified-cookie",
            400,
        ),
        (
            "ADMIN_UP",
            "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B",
            "invalid",
            401,
        ),
    ],
)
def test_private_mutation_authorizes_canonical_scope_before_factory(
    path, role, query, cookie, expected
):
    from src.product_auth.http import create_admin_app
    from src.product_auth.session import Sessions
    from tests.product_auth.test_access import Repository as AccessRepository
    from tests.product_auth.test_access import Verifier, call

    access = AccessRepository(role, workspace="workspace-a" if role == "CLIENT_USER" else None)
    factory = Mock(side_effect=AssertionError("secret/business IO forbidden"))
    app = create_admin_app(lambda: Sessions(Verifier(), access), factory, factory, factory)
    assert (
        call(
            app,
            path,
            query,
            method="POST",
            cookie=cookie,
            body={"provider": "upzero", "action": "rotate", "credential": CREDENTIAL},
        )[0]
        == expected
    )
    factory.assert_not_called()


def test_final_connection_sql_scopes_store_binding_source_revision_and_work_before_write():
    from src.admin.connection_repository import BigQueryConnections
    from tests.installation.test_persistence import Transport

    transport = Transport()
    repository = BigQueryConnections(transport)
    c, source, *_ = installed()
    op = dict(operation_id="c" * 64, provider="upzero", revision=2, status="VERIFIED")
    repository.finalize_connection(
        op,
        BINDING,
        c,
        source,
        c,
        dict(source, secret_resource_name="projects/synthetic-dev/secrets/synthetic/versions/2"),
    )
    sql, params, kwargs = transport.calls[-1]
    assert (
        "@store" in sql and "@tenant" in sql and "@workspace" in sql and "@registry_revision" in sql
    )
    assert (
        "IS NOT DISTINCT FROM" in sql
        and "integration_operations" in sql
        and "BEGIN TRANSACTION" in sql
    )
    assert "installation_extension_plans" in sql and "sync_checkpoints" in sql
    assert source["secret_resource_name"] not in sql and c.store_id not in sql
    assert "MERGE `synthetic-dev.up_ops.store_runtime_config`" not in sql
    assert "up_core.orders" not in sql and "up_raw" not in sql
    assert kwargs["job_id"].startswith("integration_")


def test_definite_secret_write_rejection_is_blocked_and_never_retried():
    s, r, secrets, probe, locks = service()
    old = deepcopy(r.source)
    secrets.rotate.side_effect = AdminError("integration_secret_write_rejected", 503)
    for _ in range(2):
        with pytest.raises(AdminError, match="integration_secret_write_rejected"):
            s.mutate(
                ADMIN, BINDING, KEY, dict(provider="upzero", action="rotate", credential=CREDENTIAL)
            )
    assert secrets.rotate.call_count == 1
    assert next(iter(r.ops.values()))["status"] == "BLOCKED"
    assert old == r.source and "registry_write_outcome_unknown" not in locks
    probe.assert_not_called()
