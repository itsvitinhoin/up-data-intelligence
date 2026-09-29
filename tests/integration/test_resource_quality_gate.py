import json
import logging
import sys
from dataclasses import asdict

import httpx
import pytest

from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.domain.models import SafeError
from src.ingestion.engine import Engine
from src.jobs import cli
from src.quality.gate import blocking, evaluate
from src.quality.rules import result


def configure(tmp_path, monkeypatch, resource, end="2026-09-02"):
    path = str(tmp_path / "state.sqlite")
    cfg = Settings("A", "Synthetic", "a", "UTC", "conn-A", "2026-09-01T00:00:00Z", state_path=path)
    monkeypatch.setenv("UP_CONFIG_JSON", json.dumps(asdict(cfg)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["job", "--mode", "backfill", "--resource", resource, "--from", "2026-09-01", "--to", end],
    )
    return path


def events(caplog, name):
    return [
        e
        for r in caplog.records
        if r.name == "upzero" and (e := json.loads(r.message))["event"] == name
    ]


@pytest.mark.parametrize(
    "resource,other",
    [("customers", "orders"), ("orders", "customers"), ("analytics_facts", "orders")],
)
def test_independent_bootstrap_persists_global_alert_and_exits_zero(
    tmp_path, monkeypatch, caplog, resource, other
):
    caplog.set_level(logging.INFO, logger="upzero")
    path = configure(tmp_path, monkeypatch, resource)
    assert cli.main() == 0
    repo = SQLiteRepository(path)
    checks = repo.read("quality_results", "A")
    assert any(
        c["rule_id"] == "sync_delayed"
        and c["resource"] == other
        and c["severity"] == "alert"
        and c["failed_count"]
        for c in checks
    )
    assert all(s["status"] == "completed" for s in repo.read("sync_runs", "A"))
    decision = events(caplog, "execution_finished")[-1]
    assert decision["ingestion_status"] == "completed"
    assert (
        decision["resource_quality_status"] == "pass"
        and decision["global_quality_status"] == "alert"
    )
    assert decision["exit_code"] == 0
    assert any(
        e["severity"] == "alert" and e["resource"] == other for e in events(caplog, "data_quality")
    )
    ids = {
        e["parent_execution_id"]
        for name in ("sync_started", "sync_finished", "data_quality", "execution_finished")
        for e in events(caplog, name)
    }
    assert len(ids) == 1


def test_customers_ignore_analytics_warning_but_keep_records(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    path = configure(tmp_path, monkeypatch, "analytics_facts")
    assert cli.main() == 0
    configure(tmp_path, monkeypatch, "customers")
    assert cli.main() == 0
    checks = SQLiteRepository(path).read("quality_results", "A")
    warnings = [
        c
        for c in checks
        if c["rule_id"] == "purchase_without_order_id_before_effective" and c["failed_count"]
    ]
    assert warnings and all(c["severity"] == "warning" for c in warnings)
    assert events(caplog, "execution_finished")[-1]["blocking_for_requested_resource"] is False


@pytest.mark.parametrize("requested", ["customers", "all"])
def test_customer_duplicates_block_relevant_resource(tmp_path, monkeypatch, requested, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    path = configure(tmp_path, monkeypatch, requested)
    assert cli.main() == 0
    repo = SQLiteRepository(path)
    customer = repo.read("customers", "A")[0]
    repo.write({"customers": [customer | {"row_key": "synthetic-second-key"}]})
    assert cli.main() == 1
    decision = events(caplog, "execution_finished")[-1]
    assert (
        decision["ingestion_status"] == "completed"
        and decision["resource_quality_status"] == "fail"
    )
    assert any(
        c["rule_id"] == "duplicate_customers" and c["failed_count"] == 1
        for c in repo.read("quality_results", "A")
    )


def test_quality_infrastructure_error_never_claims_process_success(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    path = configure(tmp_path, monkeypatch, "customers")

    def fail(*args):
        raise SafeError("quality_query_failed")

    monkeypatch.setattr(cli, "reconcile", fail)
    assert cli.main() == 1
    assert SQLiteRepository(path).read("sync_runs", "A")[0]["status"] == "completed"
    decision = events(caplog, "execution_finished")[-1]
    assert (
        decision["ingestion_status"] == "completed"
        and decision["global_quality_status"] == "unknown"
    )


def test_earlier_child_with_errors_still_fails_if_latest_completed(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    configure(tmp_path, monkeypatch, "customers", "2026-09-03")
    original = Engine.run

    def run(self, resource, filters, **kwargs):
        summary = original(self, resource, filters, **kwargs)
        return (
            summary | {"status": "completed_with_errors"}
            if filters["start_date"] == "2026-09-01"
            else summary
        )

    monkeypatch.setattr(Engine, "run", run)
    assert cli.main() == 1
    assert [e["status"] for e in events(caplog, "sync_finished")] == [
        "completed_with_errors",
        "completed",
    ]
    assert events(caplog, "execution_finished")[-1]["ingestion_status"] == "failed"


def test_daily_windows_failure_resume_counters_and_idempotence(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    path = configure(tmp_path, monkeypatch, "customers", "2026-09-04")
    requests = []

    def handler(req):
        day = req.url.params["start_date"]
        requests.append(day)
        rows = (
            []
            if "after_id" in req.url.params
            else [{"id": str(int(day[-2:])), "name": "Synthetic"}]
        )
        return httpx.Response(200, json={"data": rows})

    monkeypatch.setattr(cli, "transport", lambda _: httpx.MockTransport(handler))
    transform = Engine.transform
    armed = True

    def fail_once(self, raw):
        nonlocal armed
        if armed and raw["request_filters"]["start_date"] == "2026-09-02":
            armed = False
            raise SafeError("synthetic_write_interrupted")
        return transform(self, raw)

    monkeypatch.setattr(Engine, "transform", fail_once)
    assert cli.main() == 1
    repo = SQLiteRepository(path)
    runs = repo.read("sync_runs", "A")
    assert sorted(r["status"] for r in runs) == ["completed", "failed"]
    failed = next(r for r in runs if r["status"] == "failed")
    assert failed["source_records_read"] == 1 and failed["core_records_inserted"] == 0
    cp = next(c for c in repo.read("sync_checkpoints", "A") if c["run_id"] == failed["run_id"])
    assert cp["status"] != "complete" and cp["pending_raw_id"]
    assert cli.main() == 0
    assert len(repo.read("customers", "A")) == 3
    assert len({c["customer_id"] for c in repo.read("customers", "A")}) == 3
    runs = repo.read("sync_runs", "A")
    assert len(runs) == 3 and all(r["status"] == "completed" for r in runs)
    assert failed["run_id"] in {r["run_id"] for r in runs}
    assert all(
        r["source_records_read"] == r["core_records_processed"] == r["core_records_inserted"] == 1
        for r in runs
    )
    assert all(r["raw_pages_written"] == 2 and r["core_records_failed"] == 0 for r in runs)
    assert all(c["status"] == "complete" for c in repo.read("sync_checkpoints", "A"))
    before = list(requests)
    assert cli.main() == 0
    assert requests == before and repo.read("sync_runs", "A") == runs
    summary = events(caplog, "execution_finished")[-1]
    assert (
        summary["child_runs"] == 3
        and summary["core_records_inserted"] == summary["source_records_read"] == 3
    )
    assert summary["metrics_scope"] == "cumulative_unique_child_runs"
    assert len({e["parent_execution_id"] for e in events(caplog, "execution_finished")}) == 3


@pytest.mark.parametrize(
    "rule,scope,requested,severity,expected",
    [
        ("duplicate_customers", "all", "customers", "alert", True),
        ("duplicate_orders", "all", "customers", "alert", False),
        ("duplicate_facts", "analytics_events", "analytics_facts", "alert", True),
        ("sync_delayed", "orders", "all", "alert", True),
        ("purchase_without_order_id_after_effective", "all", "analytics_facts", "alert", True),
        ("purchase_item_without_order_id_after_effective", "all", "customers", "alert", False),
        ("invalid_meta_parser", "all", "analytics_facts", "warning", False),
        ("unknown_global_integrity", "all", "customers", "alert", True),
    ],
)
def test_explicit_gate_policy(rule, scope, requested, severity, expected):
    assert blocking(result("A", "q", scope, rule, severity), requested) is expected


def test_inline_order_items_block_but_old_infrastructure_failure_does_not():
    summary = [{"status": "completed"}]
    item = result("A", "r", "orders", "duplicate_order_items", "alert")
    historical = result("A", "r", "orders", "internal_failure", "alert")
    assert evaluate("orders", summary, [], [item])["exit_code"] == 1
    assert evaluate("orders", summary, [], [historical])["exit_code"] == 0


def test_bigquery_checks_have_same_scope_and_preserve_severity(monkeypatch):
    from types import SimpleNamespace

    from src.bigquery.repository import BigQueryRepository
    from src.quality.service import reconcile

    repo = object.__new__(BigQueryRepository)
    repo.project = "synthetic-project"
    rows = [
        SimpleNamespace(rule_id="duplicate_customers", failed_count=1, checked_count=2),
        SimpleNamespace(rule_id="invalid_meta_parser", failed_count=6, checked_count=2239),
    ]
    repo.client = SimpleNamespace(
        query=lambda *args, **kwargs: SimpleNamespace(result=lambda: rows)
    )
    monkeypatch.setattr(repo, "read", lambda *args: [])
    writes = []
    monkeypatch.setattr(repo, "write", writes.append)
    cfg = Settings("A", "Synthetic", "a", "UTC", "c", "2026-09-01T00:00:00Z")
    checks = reconcile(repo, cfg, "quality-synthetic")
    assert checks[0]["resource"] == "customers" and checks[0]["severity"] == "alert"
    assert checks[1]["resource"] == "analytics_facts" and checks[1]["severity"] == "warning"
    assert writes == [{"quality_results": checks}]
    assert blocking(checks[0], "customers") and not blocking(checks[1], "customers")


def test_quality_only_uses_requested_scope(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    configure(tmp_path, monkeypatch, "customers")
    assert cli.main() == 0
    monkeypatch.setattr(sys, "argv", ["job", "--mode", "quality", "--resource", "customers"])
    assert cli.main() == 0
    decision = events(caplog, "execution_finished")[-1]
    assert (
        decision["ingestion_status"] == "not_requested"
        and decision["global_quality_status"] == "alert"
    )
    monkeypatch.setattr(sys, "argv", ["job", "--mode", "quality", "--resource", "all"])
    assert cli.main() == 1
