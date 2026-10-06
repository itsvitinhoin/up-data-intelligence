"""Publication coverage must survive the admission DTO boundary."""

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.admin.history import HistoryService
from src.dashboard.contracts import Publication
from src.installation.extensions import ExtensionPlanner
from tests.installation.test_extensions import installed
from tests.installation.test_planner import NOW


@pytest.mark.parametrize("history_complete", [False, True])
def test_certified_flags_are_preserved_for_extension_admission(monkeypatch, history_complete):
    config, source, row, checkpoints, runs = installed()
    config = replace(config, history_complete=history_complete)
    published = Publication(
        store_id=config.store_id,
        policy_hash=row["policy_hash"],
        generation=row["generation"],
        publication_id=row["publication_id"],
        snapshot_at=NOW,
        as_of=row["as_of"],
        report_from=row["report_from"],
        report_to=row["report_to"],
    )
    primary = Mock()
    primary.plans.return_value = [{"plan_id": "primary", "status": "COMPLETE"}]
    primary.units.return_value = [{"status": "COMPLETE"}]
    monkeypatch.setattr("src.admin.history.BigQueryLedger", lambda _: primary)
    monkeypatch.setattr(
        "src.admin.history.available",
        lambda *args: (
            SimpleNamespace(history_complete=history_complete, facts_complete=True),
            published,
        ),
    )
    ledger = SimpleNamespace(transport=SimpleNamespace(config=SimpleNamespace(project="dev")))
    service = HistoryService(ledger, lambda _: nullcontext(), b"synthetic", lambda: NOW)
    evidence = service.publication(config)
    assert evidence["history_complete"] is history_complete
    assert evidence["facts_complete"] is True
    if history_complete:
        return  # Admission below exercises the installed partial-history fixture.
    plan, units = ExtensionPlanner().calculate(
        config,
        source,
        "CATALOG_SNAPSHOT",
        "2026-09-30",
        "2026-10-01",
        NOW,
        requested_by_hash="c" * 64,
        checkpoints=checkpoints,
        runs=runs,
        publication=evidence,
    )
    assert plan["status"] == "RUNNING"
    assert len(units) == 1
    assert units[0]["resource"] == "catalog"
