"""Synthetic new-brand automation and final transactional activation guards."""

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.control_plane.cli import gated
from src.domain.models import SafeError
from src.installation.automation import AutoPrepare
from src.installation.cli import main
from src.installation.model import Limits
from src.installation.orchestrator import Orchestrator
from src.installation.repository import BigQueryLedger
from tests.installation.fakes import MemoryLedger
from tests.installation.test_persistence import Transport
from tests.installation.test_planner import NOW, config, graph
from tests.installation.test_runtime import Gateway


def test_global_auto_prepare_bounds_isolates_blocks_and_does_not_duplicate():
    ledger = Mock()
    good = replace(config(), store_id="good-brand")
    bad = replace(good, store_id="bad-brand")
    ops = [
        {"operation_id": "bad-op", "store_id": bad.store_id, "status": "INSTALLING"},
        {"operation_id": "good-op", "store_id": good.store_id, "status": "INSTALLING"},
    ]
    ledger.onboardings.return_value = ops
    saved = {}
    ledger.config.side_effect = lambda s: {good.store_id: good, bad.store_id: bad}[s]
    ledger.plans.side_effect = lambda s: saved.get(s, [])
    ledger.evidence.return_value = ([], [])

    def create(c, p, u):
        saved[c.store_id] = [p]

    ledger.create.side_effect = create

    def source(c, s):
        if c.store_id == bad.store_id:
            raise SafeError("source_verification_required")
        return {"status": "pending"}

    prepare = AutoPrepare(
        ledger, source, lambda k: nullcontext(), Limits(max_stores=2), clock=lambda: NOW
    )
    prepare(None)
    ledger.onboardings.assert_called_once_with(2, None)
    ledger.block_onboarding.assert_called_once_with(ops[0], "source_verification_required", NOW)
    assert (
        ledger.create.call_count == 1 and ledger.create.call_args.args[0].store_id == good.store_id
    )
    # BLOCKED operation is omitted by the real bounded selector on later ticks.
    ledger.onboardings.return_value = [ops[1]]
    prepare(None)
    assert ledger.create.call_count == 1


def test_auto_prepare_unknown_stops_without_failure_receipt_or_next_store():
    ledger = Mock()
    c = config()
    op = {"store_id": c.store_id, "status": "INSTALLING"}
    ledger.onboardings.return_value = [op]
    ledger.plans.return_value = []
    ledger.config.return_value = c
    source = Mock(side_effect=SafeError("bigquery_write_outcome_unknown"))
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        AutoPrepare(ledger, source, lambda k: nullcontext(), Limits())(None)
    ledger.block_onboarding.assert_not_called()
    ledger.create.assert_not_called()


def complete():
    c, p, units = graph(1)
    for r in units:
        r["status"] = "COMPLETE"
    p["onboarding_operation_id"] = "synthetic-op"
    ledger = MemoryLedger(c, p, units)

    def activate(plan, current, at):
        assert current.status == "READY" and not current.sync_enabled
        updated = replace(
            current,
            status="ACTIVE",
            sync_enabled=True,
            revision=current.revision + 1,
            updated_at=at,
        )
        return ledger.update_plan(plan, updated, status="COMPLETE")

    ledger.activate = Mock(side_effect=activate)
    return ledger


def test_final_refresh_auto_activates_only_after_all_gates_and_never_dispatches():
    ledger = complete()
    gateway = Gateway()
    guard = Mock()
    orch = Orchestrator(
        ledger,
        gateway,
        lambda k: nullcontext(),
        lambda p, u: (True, True),
        clock=lambda: NOW,
        auto_activate=True,
        activation=guard,
    )
    assert orch.dispatch() == 0
    guard.assert_called_once()
    ledger.activate.assert_called_once()
    assert ledger.c.status == "ACTIVE" and ledger.c.sync_enabled and not ledger.c.history_complete
    assert not gateway.posts and ledger.plans()[0]["status"] == "COMPLETE"


@pytest.mark.parametrize(
    "code",
    [
        "activation_source_not_complete",
        "source_verification_required",
        "recurring_publication_required",
        "upzero_history_window_not_covered",
        "work_checkpoint_mismatch",
    ],
)
def test_invalid_final_evidence_does_not_activate(code):
    ledger = complete()
    guard = Mock(side_effect=SafeError(code))
    gateway = Gateway()
    orch = Orchestrator(
        ledger,
        gateway,
        lambda k: nullcontext(),
        lambda p, u: (True, True),
        clock=lambda: NOW,
        auto_activate=True,
        activation=guard,
    )
    assert orch.dispatch() == 0
    ledger.activate.assert_not_called()
    assert not ledger.c.sync_enabled and not gateway.posts


def test_noncomplete_or_blocked_work_cannot_activate():
    for status in ("PENDING", "RUNNING", "BLOCKED"):
        ledger = complete()
        next(iter(ledger.u.values()))["status"] = status
        guard = Mock()
        orch = Orchestrator(
            ledger,
            Gateway(),
            lambda k: nullcontext(),
            lambda p, u: (True, True),
            clock=lambda: NOW,
            auto_activate=True,
            activation=guard,
        )
        if status == "RUNNING":
            with pytest.raises(SafeError, match="work_execution_outcome_unknown"):
                orch.dispatch()
        else:
            orch.dispatch()
        ledger.activate.assert_not_called()
        guard.assert_not_called()
        assert not ledger.c.sync_enabled


def test_activation_transaction_is_atomic_registry_plan_operation_and_cas():
    t = Transport()
    ledger = BigQueryLedger(t)
    c, p, u = graph(1)
    c = replace(c, status="READY")
    p["status"] = "COMPLETE"
    p["onboarding_operation_id"] = "synthetic-op"
    op = {
        "operation_id": "synthetic-op",
        "store_id": c.store_id,
        "revision": 7,
        "status": "INSTALLING",
    }
    ledger.sql.get = lambda _: op
    ledger.activate(p, c, NOW)
    sql, params, _ = t.calls[-1]
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    assert (
        "onboarding_revision" in sql
        and "status='READY'" in sql
        and "pending_raw_id IS NOT NULL" in sql
    )
    assert (
        "onboarding_operations" in sql
        and "store_runtime_config" in sql
        and "installation_plans" in sql
    )
    assert "status!='COMPLETE'" in sql
    assert c.store_id not in sql


def test_complete_waiting_activation_is_selected_after_crash_between_refresh_and_activation():
    t = Transport()
    ledger = BigQueryLedger(t)
    ledger.plans()
    ledger.units()
    assert all("status='COMPLETE' AND onboarding_operation_id IN" in call[0] for call in t.calls)
    assert all(
        "onboarding_operations" in call[0] and "status='INSTALLING'" in call[0] for call in t.calls
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--plan-only", "--all-stores"],
        ["--create-plan", "--all-stores"],
        ["--worker", "--all-stores"],
        ["--dispatch", "--all-stores", "--store-id", "synthetic"],
        ["--dispatch", "--auto-activate", "--store-id", "synthetic"],
        ["--dispatch"],
    ],
)
def test_invalid_global_cli_gate_before_any_sdk(args):
    with patch("src.control_plane.cli.clients") as sdk:
        assert main(args) == 1
    sdk.assert_not_called()


def test_global_dev_confirmation_is_explicit():
    args = SimpleNamespace(
        live=True,
        project="up-data-intelligence-dev",
        confirm_project="up-data-intelligence-dev",
        location="southamerica-east1",
        lease_bucket="synthetic",
        all_stores=True,
        dispatch=True,
        store_id=None,
        confirm_store=None,
    )
    gated(args)
    args.dispatch = False
    with pytest.raises(SafeError, match="invalid_global_installation_scope"):
        gated(args)
