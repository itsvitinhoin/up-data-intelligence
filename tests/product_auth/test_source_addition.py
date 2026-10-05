from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from src.admin.connection_repository import BigQueryConnections
from src.admin.contracts import AdminError, Principal
from src.admin.source_addition import SourceAddition
from src.domain.models import SafeError
from tests.installation.test_extensions import installed
from tests.installation.test_planner import NOW
from tests.product_auth.test_connection_management import ADMIN, BINDING, KEY

PAYLOAD = dict(provider="meta", action="add", account_id="1234567", api_version="v23.0")


class Repo:
    def __init__(self):
        c, self.original_source, self.pub, *_ = installed()
        self.c = replace(
            c,
            meta_enabled=False,
            intelligence_enabled=False,
            meta_connection_id=None,
            meta_account_id=None,
            meta_api_version=None,
        )
        self.ops, self.plans, self.units = {}, [], []
        self.busy = False
        self.mutations = []

    def config(self, store):
        assert store == self.c.store_id
        return self.c

    def operation(self, key):
        return deepcopy(self.ops.get(key))

    def ensure_addition(self, binding, config, account):
        if self.busy:
            raise AdminError("integration_addition_prerequisites_failed")
        assert binding["store_id"] == config.store_id == account.store_id

    def reserve_operation(self, op):
        self.ops[op["operation_id"]] = deepcopy(op)
        self.mutations.append("reserve")
        return op

    def transition(self, op, **changes):
        new = dict(op, **changes, revision=op["revision"] + 1)
        self.ops[op["operation_id"]] = deepcopy(new)
        return new

    def finalize_addition(self, op, binding, old, updated, source, account, plan, units):
        assert old == self.c and op["current_step"] == "VERIFIED"
        self.c, self.added_source, self.account = updated, source, account
        self.plans.append(deepcopy(plan))
        self.units.extend(deepcopy(units))
        result = dict(op, status="COMPLETE", current_step="COMMITTED", revision=op["revision"] + 1)
        self.ops[op["operation_id"]] = deepcopy(result)
        self.mutations.append("commit")
        return result


def service():
    repo, probe, retained = Repo(), Mock(), []

    @contextmanager
    def lease(key):
        try:
            yield
        except SafeError as exc:
            retained.append((key, exc.code))
            raise

    return (
        SourceAddition(
            repo, lambda _: repo.pub, probe, lease, b"synthetic-subject" * 3, lambda: NOW
        ),
        repo,
        probe,
        retained,
    )


def test_new_meta_source_has_only_meta_work_and_preserves_installed_store():
    s, r, probe, _ = service()
    before = r.c
    original = deepcopy(r.original_source)
    result = s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert result["data"]["status"] == "COMPLETE" and result["data"]["action"] == "add"
    assert r.c.revision == before.revision + 1 and r.c.meta_enabled
    for name in (
        "status",
        "sync_enabled",
        "history_complete",
        "history_from",
        "analytics_enabled",
        "intelligence_enabled",
        "facts_coverage_from",
        "facts_coverage_to",
        "upzero_connection_id",
    ):
        assert getattr(r.c, name) == getattr(before, name)
    assert r.original_source == original and r.added_source["secret_resource_name"] is None
    assert len(r.plans) == 1 and len(r.units) == 64  # 4 catalog + 30 campaign + 30 ad/day
    assert all(u["source"] == "meta" and u["status"] == "PENDING" for u in r.units)
    assert {u["resource"] for u in r.units} == {
        "accounts",
        "campaigns",
        "adsets",
        "ads",
        "insights",
        "creative_insights",
    }
    assert not any(u["unit_kind"] in {"PUBLISH_ANALYTICS", "LEGACY_RESUME"} for u in r.units)
    probe.assert_called_once_with(r.c, "meta-add", None)
    assert not any(k in str(result) for k in ("secret", "account_id", "credential"))
    s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert len(r.plans) == 1 and probe.call_count == 1


@pytest.mark.parametrize(
    "principal",
    [
        None,
        Principal("client", "CLIENT_USER", frozenset({"tenant-a"})),
        Principal("admin", "ADMIN_UP", frozenset({"foreign"})),
    ],
)
def test_source_addition_auth_before_io(principal):
    s, r, probe, _ = service()
    r.config = Mock(side_effect=AssertionError("forbidden IO"))
    with pytest.raises(AdminError):
        s.create(principal, BINDING, KEY, PAYLOAD)
    r.config.assert_not_called()
    probe.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "google"),
        ("api_version", "latest"),
        ("account_id", "act_123"),
        ("credential", "not-collected"),
        ("store_id", "foreign"),
    ],
)
def test_addition_invalid_or_unsupported_config_before_io(field, value):
    s, r, probe, _ = service()
    r.config = Mock(side_effect=AssertionError("forbidden IO"))
    with pytest.raises((AdminError, SafeError)):
        s.create(ADMIN, BINDING, KEY, dict(PAYLOAD, **{field: value}))
    r.config.assert_not_called()
    probe.assert_not_called()


def test_addition_unknown_probe_preserves_lease_and_never_reprobes():
    s, r, probe, retained = service()
    before = r.c
    probe.side_effect = SafeError("source_verification_outcome_unknown")
    with pytest.raises(AdminError, match="source_verification_outcome_unknown"):
        s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert r.c == before and r.plans == []
    assert all(code == "registry_write_outcome_unknown" for _, code in retained)
    assert len(retained) == 3
    probe.side_effect = None
    with pytest.raises(AdminError, match="outcome_unknown"):
        s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert probe.call_count == 1


def test_addition_definite_probe_failure_blocks_without_mutating_source():
    s, r, probe, _ = service()
    probe.side_effect = SafeError("source_verification_failed")
    with pytest.raises(AdminError, match="source_verification_failed"):
        s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert r.plans == [] and next(iter(r.ops.values()))["status"] == "BLOCKED"
    with pytest.raises(AdminError):
        s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert probe.call_count == 1


def test_addition_conflicting_idempotency_and_busy_before_probe():
    s, r, probe, _ = service()
    r.busy = True
    with pytest.raises(AdminError):
        s.create(ADMIN, BINDING, KEY, PAYLOAD)
    assert r.mutations == [] and probe.call_count == 0
    r.busy = False
    s.create(ADMIN, BINDING, KEY, PAYLOAD)
    with pytest.raises(AdminError, match="idempotency_conflict"):
        s.create(ADMIN, BINDING, KEY, dict(PAYLOAD, account_id="1234568"))
    assert probe.call_count == 1


def test_addition_sql_has_atomic_ownership_graph_and_checkpoint_guards():
    repo = BigQueryConnections(Mock())
    sql = repo.addition_guards()
    for term in (
        "@tenant",
        "@workspace",
        "@store",
        "@registry_revision",
        "@account",
        "@connection",
        "pending_raw_id IS NOT NULL",
        "installation_extension_plans",
        "meta_account_collision",
        "status!='COMPLETE'",
    ):
        assert term in sql
    assert BINDING["store_id"] not in sql
    assert "DELETE " not in sql and "UPDATE " not in sql


@pytest.mark.parametrize(
    "change", [{}, {"account_id": "other-account"}, {"currency": "USD"}, {"timezone_name": "UTC"}]
)
def test_candidate_account_probe_requires_exact_config_and_exposes_no_payload(change):
    from src.admin.source_addition import verify_meta_account
    from src.connectors.meta.config import Account
    from src.domain.models import Page

    a = Account("synthetic-store", "1234567", "synthetic-meta", "v23.0", "America/Sao_Paulo", "BRL")
    page = Page(
        {
            "data": [
                dict(
                    account_id=a.account_id,
                    currency=a.currency,
                    timezone_name=a.timezone,
                    name="never-in-error",
                )
                | change
            ]
        },
        {},
        None,
        0,
        "synthetic",
    )
    if change:
        with pytest.raises(SafeError) as error:
            verify_meta_account(page, a)
        assert str(error.value) == "meta_account_configuration_mismatch"
    else:
        assert verify_meta_account(page, a) is None
