"""Synthetic planning lifecycle. All SDK factories, ADC and leases are replaced."""

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace

import pytest

from src.domain.models import SafeError
from src.installation.cli import inspection, main
from src.installation.planner import Planner
from src.installation.repository import BigQueryLedger
from tests.installation.fakes import MemoryLedger
from tests.installation.test_persistence import Transport
from tests.installation.test_planner import END, NOW, config, cp


class PlanningLedger(MemoryLedger):
    def __init__(self, meta_pending=False):
        self.c = config()
        if meta_pending:
            self.c = replace(
                self.c,
                meta_enabled=True,
                meta_connection_id="synthetic-meta",
                meta_account_id="123",
                meta_api_version="v25.0",
            )
        self.p, self.u, self.sources = {}, {}, {}
        self.create_calls = 0
        checkpoint, run = cp(self.c, "customers", {"limit": 200}, "needs_review")
        self.checkpoints, self.runs = [checkpoint], [run]
        if meta_pending:
            self.checkpoints = [
                {
                    "store_id": self.c.store_id,
                    "connection_id": self.c.meta_connection_id,
                    "resource": "ads",
                    "status": "running",
                }
            ]
            self.runs = []

    def rows(self, name, *args, **kwargs):
        return deepcopy(
            {
                "source_connections": [{"status": "pending"}],
                "onboarding_operations": [
                    {
                        "operation_id": "synthetic-install",
                        "store_id": self.c.store_id,
                        "status": "INSTALLING",
                    }
                ],
                "sync_checkpoints": self.checkpoints,
                "sync_runs": self.runs,
            }[name]
        )

    def create(self, config, plan, units):
        self.create_calls += 1
        super().create(config, plan, units)
        self.c = config


def wire_cli(monkeypatch, ledger):
    transport = Transport()
    monkeypatch.setattr("src.control_plane.cli.gated", lambda args: None)
    monkeypatch.setattr("src.control_plane.cli.clients", lambda args: (transport, None))
    monkeypatch.setattr("src.installation.repository.BigQueryLedger", lambda transport: ledger)
    monkeypatch.setattr("src.security.lease.cloud_lease", lambda *args: nullcontext())
    monkeypatch.setattr("src.installation.cli.now", lambda: NOW)
    return transport


@pytest.mark.parametrize("meta_pending", [False, True])
def test_blocked_create_cli_preserves_registry_and_can_replan(monkeypatch, capsys, meta_pending):
    ledger = PlanningLedger(meta_pending)
    original = ledger.c.row()
    transport = wire_cli(monkeypatch, ledger)
    args = ["--store-id", ledger.c.store_id, "--target-as-of", END]
    assert main(["--plan-only", *args]) == 0
    assert '"status": "BLOCKED"' in capsys.readouterr().out
    assert main(["--create-plan", *args]) == 1
    assert ledger.create_calls == 0 and not ledger.p and not ledger.u
    assert ledger.c.row() == original and transport.calls == []
    # Operator repairs evidence outside this change; no deletion/reopening of a plan.
    ledger.checkpoints, ledger.runs = [], []
    assert main(["--create-plan", *args]) == 0
    assert ledger.create_calls == 1 and len(ledger.p) == 1 and ledger.u
    assert next(iter(ledger.p.values()))["status"] == "RUNNING"
    assert not ledger.c.sync_enabled


@pytest.mark.parametrize("meta_pending", [False, True])
def test_automatic_prepare_rejects_blocked_before_create(monkeypatch, meta_pending):
    ledger = PlanningLedger(meta_pending)
    original = ledger.c.row()
    transport = wire_cli(monkeypatch, ledger)
    # No ADC discovery: this stub replaces the factory entirely; no credentials exist.
    monkeypatch.setattr("google.auth.default", lambda **kwargs: (None, None))

    class PrepareOnly:
        def __init__(self, *args, prepare, **kwargs):
            self.prepare = prepare

        def dispatch(self, store):
            self.prepare(store)
            raise AssertionError("blocked planning must stop before dispatch")

    monkeypatch.setattr("src.installation.orchestrator.Orchestrator", PrepareOnly)
    assert main(["--dispatch", "--store-id", ledger.c.store_id]) == 1
    assert ledger.create_calls == 0 and not ledger.p and not ledger.u
    assert ledger.c.row() == original and transport.calls == []


@pytest.mark.parametrize("meta_pending", [False, True])
def test_direct_ledger_blocked_guard_before_any_query_or_transaction(meta_pending):
    fixture = PlanningLedger(meta_pending)
    c = fixture.c
    checkpoints, runs = fixture.checkpoints, fixture.runs
    configured, plan, units = Planner().calculate(
        c, END, NOW, adopt=True, checkpoints=checkpoints, runs=runs
    )
    assert plan["status"] == "BLOCKED" and units == []
    original = deepcopy((configured.row(), plan, units))
    transport = Transport()
    with pytest.raises(SafeError, match="^installation_plan_not_creatable$"):
        BigQueryLedger(transport).create(configured, plan, units)
    assert transport.calls == [] and (configured.row(), plan, units) == original
    diagnostic = inspection(
        {"registry": c.row(), "checkpoints": checkpoints, "runs": runs, "now": NOW},
        END,
        adopt=True,
    )
    assert diagnostic["plan"]["status"] == "BLOCKED"
    assert diagnostic["plan"]["error_code"] == (
        "meta_pending_configuration_requires_recovery"
        if meta_pending
        else "installation_checkpoint_needs_review"
    )
