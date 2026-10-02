"""Injected verifiers, real bounded engines and synthetic source responses only."""

from contextlib import closing, nullcontext
from types import SimpleNamespace

import httpx
import pytest

from src.bigquery.repository import SQLiteRepository
from src.connectors.meta.client import MetaConnector
from src.domain.models import SafeError
from src.ingestion.meta import MetaEngine
from src.installation.adapters import InstallationActions, ProbeVerifier
from src.installation.model import Limits
from tests.installation.test_planner import config, graph
from tests.unit.test_meta_foundation import ACCOUNT, TOKEN, source


@pytest.mark.parametrize("system,capability", [("upzero", "customers"), ("meta", "accounts")])
def test_verification_discards_source_payload_and_keeps_safe_capability(system, capability):
    calls = []
    verifier = ProbeVerifier({system: lambda c, row: calls.append(system)})
    result = verifier.verify(config(), {"source": system, "connection_id": "synthetic-connection"})
    assert calls == [system]
    assert set(result) == {
        "verified",
        "source",
        "connection_id",
        "capabilities",
        "verified_at",
        "safe_error",
    }
    assert result["verified"] and result["capabilities"] == [capability]
    assert result["safe_error"] is None
    with pytest.raises(SafeError, match="verification_unavailable"):
        verifier.verify(config(), {"source": "unknown"})


@pytest.mark.parametrize(
    "ambiguous,budget,expected",
    [
        (True, True, "bigquery_write_outcome_unknown"),
        (False, True, "store_execution_budget_exhausted"),
        (False, False, "synthetic_definite"),
    ],
)
def test_cost_wrapper_preserves_uncertain_write_before_budget(ambiguous, budget, expected):
    client = SimpleNamespace(mutation_outcome_unknown=ambiguous, budget_exhausted=budget)
    actions = SimpleNamespace(transport=SimpleNamespace(client=client))
    adapter = InstallationActions(actions, lambda *a: None, lambda *a: None)

    def fail(*args):
        raise SafeError("synthetic_definite")

    adapter.execute = fail
    with pytest.raises(SafeError, match=expected):
        adapter(config(), graph(1)[2][0], Limits())


def test_meta_cursor_yield_reuses_raw_run_checkpoint(tmp_path):
    calls = []

    def response(request):
        cursor = request.url.params.get("after")
        calls.append(cursor)
        row = {**source("campaigns"), "id": "000201" if cursor is None else "000202"}
        paging = (
            {
                "next": "https://graph.facebook.com/v23.0/act_000101/campaigns?after=synthetic",
                "cursors": {"after": "synthetic"},
            }
            if cursor is None
            else {}
        )
        return httpx.Response(200, json={"data": [row], "paging": paging})

    repo = SQLiteRepository(str(tmp_path / "synthetic.sqlite"))
    with closing(
        MetaConnector(ACCOUNT, token=TOKEN, transport=httpx.MockTransport(response), max_pages=1)
    ) as client:
        engine = MetaEngine(repo, client, accounts=(ACCOUNT,), lease=lambda: nullcontext())
        first = engine.advance("campaigns", page_budget=1)
        assert first["yielded"] and not first["complete"] and first["finished_at"] is None
        checkpoint = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
        assert checkpoint["status"] == "running" and checkpoint["pending_raw_id"] is None
        final = engine.advance("campaigns", page_budget=1)
        assert final["complete"] and final["run_id"] == first["run_id"]
        assert calls == [None, "synthetic"]
        assert len(repo.read("meta_campaigns", ACCOUNT.store_id)) == 2
        assert len(repo.read("meta_raw_campaigns", ACCOUNT.store_id)) == 2


def test_active_legacy_secret_keeps_existing_namespace_guard(monkeypatch):
    from src.control_plane.preflight import Prerequisites

    c = config()
    reference = (
        "projects/synthetic-dev/secrets/up-intelligence-upzero-pilot-store-api-key/versions/1"
    )
    metadata = {
        "connection_id": c.upzero_connection_id,
        "source_system": "upzero",
        "status": "active",
        "secret_resource_name": reference,
    }

    class Transport:
        config = SimpleNamespace(project="synthetic-dev")

        def query(self, *args):
            return [metadata], None

    transport = Transport()
    actions = SimpleNamespace(transport=transport, prerequisites=Prerequisites(transport))
    seen = []
    monkeypatch.setattr(
        "src.installation.adapters.resolve_secret", lambda ref: seen.append(ref) or TOKEN
    )
    adapter = InstallationActions(actions, lambda *a: metadata, lambda *a: None)
    _, connector = adapter.upzero(c, active=True)
    connector.close()
    assert seen == [reference]
    metadata["secret_resource_name"] = reference.replace("synthetic-dev", "foreign-dev")
    with pytest.raises(SafeError, match="approved_upzero_secret_version_required"):
        adapter.upzero(c, active=True)
    assert seen == [reference]


def test_pending_onboarding_secret_must_match_project_and_store(monkeypatch):
    actions = SimpleNamespace(
        transport=SimpleNamespace(config=SimpleNamespace(project="synthetic-dev"))
    )
    c = config()
    metadata = {
        "connection_id": c.upzero_connection_id,
        "status": "pending",
        "secret_resource_name": "projects/foreign-dev/secrets/up-intelligence-upzero-synthetic-mx/versions/1",
    }

    def deny(*a):
        raise AssertionError("Secret value must not be read")

    monkeypatch.setattr("src.installation.adapters.resolve_secret", deny)
    with pytest.raises(SafeError):
        InstallationActions(actions, lambda *a: metadata, lambda *a: None).upzero(c, active=False)


def test_verification_metadata_change_never_activates_new_reference():
    _, _, rows = graph(1)
    metadata = iter(
        [{"status": "pending", "updated_at": "old"}, {"status": "pending", "updated_at": "new"}]
    )
    adapter = InstallationActions(SimpleNamespace(), lambda *a: next(metadata), lambda *a: None)
    adapter.verifier = ProbeVerifier({"upzero": lambda *a: None})
    with pytest.raises(SafeError, match="source_verification_outcome_unknown"):
        adapter.execute(config(), rows[0], Limits())
