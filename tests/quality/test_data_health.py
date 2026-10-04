from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.control_plane.model import Window
from src.domain.models import SafeError
from src.quality.data_health import (
    RULES,
    DataHealth,
    Finding,
    intelligence_current,
    publication_history,
)
from src.utils.data import digest
from tests.control_plane.test_control_plane import config
from tests.control_plane.test_recurring import head

AT = "2026-10-04T07:30:00Z"


def store():
    return config(
        status="ACTIVE",
        sync_enabled=True,
        analytics_enabled=True,
        upzero_enabled=True,
        upzero_connection_id="synthetic-up",
        facts_complete=True,
        facts_coverage_from="2026-09-01T00:00:00Z",
        facts_coverage_to="2026-10-04T03:00:00Z",
    )


def receipt(c, generation=4, end="2026-10-04", start="2026-09-01"):
    return {
        "store_id": c.store_id,
        "policy_hash": head(c)["policy_hash"],
        "generation": generation,
        "record_kind": "RECEIPT",
        "status": "completed",
        "report_from": start,
        "report_to": end,
        "as_of": end + "T03:00:00Z",
    }


def test_health_receipts_same_day_and_growth_never_shrink():
    c = store()
    publication_history(c, [receipt(c, 3, "2026-10-03"), receipt(c)], AT)
    publication_history(c, [receipt(c), receipt(c, 5)], AT)
    with pytest.raises(SafeError, match="regression"):
        publication_history(c, [receipt(c), receipt(c, 5, start="2026-10-03")], AT)
    with pytest.raises(SafeError, match="regression"):
        publication_history(c, [receipt(c), receipt(c, 5, "2026-10-03")], AT)


def test_health_result_keys_are_idempotent_and_aggregate_only():
    finding = Finding("no_pending_raw", 0)
    first = finding.row("synthetic", "2026-10-04T03:00:00Z", "audit-one", AT)
    second = finding.row("synthetic", "2026-10-04T03:00:00+00:00", "audit-two", AT)
    assert first["row_key"] == second["row_key"]
    assert first["record_id"] is None
    assert (
        first["row_key"] != finding.row("other", "2026-10-04T03:00:00Z", "audit-one", AT)["row_key"]
    )


def test_health_intelligence_requires_exact_base_receipt_and_window():
    c = store()
    base = head(replace(c, facts_complete=False), end="2026-10-04", as_of="2026-10-04T03:00:00Z")
    window = Window.previous_closed_day(c.timezone, AT)
    window = replace(window, report_from="2026-09-01")
    r = {
        **receipt(c),
        "publication_id": "b" * 64,
        "base_generation": base["generation"],
        "base_publication_id": base["publication_id"],
        "history_complete": False,
        "facts_complete": True,
        "meta_complete": True,
    }
    rows = [r, {**r, "record_kind": "HEAD"}]
    intelligence_current(rows, base, window, c)
    for field, value in (
        ("base_generation", 1),
        ("history_complete", True),
        ("meta_complete", False),
    ):
        bad = deepcopy(rows)
        for row in bad:
            row[field] = value
        with pytest.raises(SafeError):
            intelligence_current(bad, base, window, c)
    with pytest.raises(SafeError):
        intelligence_current(rows + [rows[0]], base, window, c)


def healthy_checker(c):
    transport = Mock(config=SimpleNamespace(project="synthetic-project"))
    transport.query.return_value = ([{"failed": 0, "checked": 33}], None)
    checker = DataHealth(transport)
    checker.pre = Mock()
    checker.pre.publication.return_value = [
        head(replace(c, facts_complete=False), end="2026-10-04", as_of="2026-10-04T03:00:00Z")
    ]
    checkpoints, runs = [], []
    for resource, filters in (
        ("customers", {"limit": 200}),
        ("orders", {"start_date": "2026-08-31", "end_date": "2026-10-03"}),
        ("analytics_facts", {"from": c.history_from, "to": "2026-10-04T03:00:00Z"}),
    ):
        key = digest([c.store_id, c.upzero_connection_id, resource, filters, "backfill"])
        cp = {
            "store_id": c.store_id,
            "connection_id": c.upzero_connection_id,
            "resource": resource,
            "filters": filters,
            "mode": "backfill",
            "plan_key": key,
            "run_id": resource,
            "status": "complete",
            "pending_raw_id": None,
        }
        checkpoints.append(cp)
        runs.append(
            {
                "store_id": c.store_id,
                "source": "upzero",
                "resource": resource,
                "plan_key": key,
                "run_id": resource,
                "status": "completed",
                "core_records_failed": 0,
                "finished_at": AT,
            }
        )
    checker.pre.rows.side_effect = lambda store_id, table, *args: {
        "up_ops.sync_checkpoints": checkpoints,
        "up_ops.sync_runs": runs,
        "up_core.source_connections": [
            {"source_system": "upzero", "connection_id": c.upzero_connection_id, "status": "active"}
        ],
        "up_analytics.analytics_publications": [receipt(c)],
    }.get(table, [])
    return checker, transport


def test_all_rules_checked_no_optional_pipeline_masquerades_as_fresh():
    c = store()
    checker, transport = healthy_checker(c)
    cutoff, findings = checker.check(c, AT)
    assert cutoff.as_of.endswith("03:00:00+00:00")
    assert {f.rule_id for f in findings} == set(RULES)
    assert all(f.failed_count == 0 for f in findings)
    assert next(f for f in findings if f.rule_id == "meta_daily_covered").checked_count == 0
    assert not transport.query.call_args[0][0].startswith(("UPDATE", "INSERT", "DELETE", "MERGE"))


@pytest.mark.parametrize(
    "change,rule",
    [
        ({"sync_enabled": False}, "sync_enabled"),
        ({"status": "READY"}, "registry_active"),
        ({"facts_coverage_to": "2026-10-03T03:00:00Z"}, "analytics_cutoff_current"),
    ],
)
def test_blocking_registry_and_freshness_findings(change, rule):
    c = replace(store(), **change)
    checker, _ = healthy_checker(c)
    _, findings = checker.check(c, AT)
    assert next(f for f in findings if f.rule_id == rule).failed_count == 1


def test_missing_publication_blocks_instead_of_using_empty_success():
    c = store()
    checker, _ = healthy_checker(c)
    checker.pre.publication.return_value = []
    _, findings = checker.check(c, AT)
    assert next(f for f in findings if f.rule_id == "analytics_head_valid").failed_count == 1
    assert (
        next(f for f in findings if f.rule_id == "dashboard_publication_resolves").failed_count == 1
    )


def test_pending_raw_and_old_running_ledger_fail_and_are_not_mutated():
    c = store()
    checker, _ = healthy_checker(c)
    original = checker.pre.rows.side_effect
    checker.pre.rows.side_effect = lambda store_id, table, *args: (
        [{"pending_raw_id": "synthetic-raw"}]
        if table.endswith("sync_checkpoints")
        else [{"status": "running", "started_at": datetime(2026, 10, 3, tzinfo=UTC)}]
        if table.endswith("sync_runs")
        else original(store_id, table, *args)
    )
    _, findings = checker.check(c, AT)
    assert next(f for f in findings if f.rule_id == "no_pending_raw").failed_count == 1
    assert (
        next(f for f in findings if f.rule_id == "no_nonterminal_previous_day_runs").failed_count
        == 1
    )


def test_read_failure_is_not_fabricated_as_zero():
    checker, _ = healthy_checker(store())
    checker.pre.rows.side_effect = RuntimeError("synthetic sanitized failure")
    with pytest.raises(RuntimeError):
        checker.check(store(), AT)


def test_writer_only_quality_results_and_rejects_record_payload():
    checker, transport = healthy_checker(store())
    row = Finding("no_pending_raw", 0).row("synthetic", "2026-10-04T03:00:00Z", "audit", AT)
    checker.persist([row])
    sql, params = transport.query.call_args[0]
    assert "up_ops.quality_results" in sql
    assert "@rows" in sql and "'synthetic'" not in sql
    assert "up_core" not in sql and "store_runtime_config" not in sql
    with pytest.raises(ValueError):
        checker.persist([{**row, "record_id": "not-aggregate"}])
    transport.query.side_effect = TimeoutError()
    with pytest.raises(SafeError, match="health_write_outcome_unknown"):
        checker.persist([row])
    assert transport.query.call_count == 2  # No retry of unknown mutation.
