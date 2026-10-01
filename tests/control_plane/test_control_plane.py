"""Synthetic multi-store isolation, lifecycle and bounded remote fan-out."""

import hashlib
import json
import threading
import time
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest

from src.analytics.cloud.transport import CloudConfig
from src.control_plane.budget import BoundedClient, ExecutionBudgetExceeded
from src.control_plane.dispatcher import Dispatcher
from src.control_plane.gateway import RunGateway
from src.control_plane.model import JOBS, PIPELINES, REGISTRY, StoreConfig, Window
from src.control_plane.preflight import Prerequisites
from src.control_plane.registry import Admin, StoreAdmin
from src.control_plane.repository import BigQueryRegistry
from src.control_plane.worker import Actions, StoreWorker
from src.domain.models import SafeError
from src.security.lease import local_lease

ADMIN = Admin("synthetic-admin", "ADMIN_UP")
WINDOW = Window(
    "2026-09-01",
    "2026-09-02",
    "2026-09-02T03:00:00Z",
    "2026-09-03T00:00:00Z",
    "2026-09-03T00:00:00Z",
)


def config(store="brand-one", **kwargs):
    return StoreConfig(
        store,
        operation_b2b=True,
        timezone="America/Sao_Paulo",
        currency="BRL",
        history_from="2026-09-01T00:00:00Z",
        policy_version="1.0.0",
        qualifying_order_statuses=("CONFIRMED", "SHIPPED"),
        **kwargs,
    )


class MemoryRegistry:
    def __init__(self, stores=()):
        self.stores = {s.store_id: s for s in stores}

    def get(self, store):
        return self.stores.get(store)

    def save(self, config, expected_revision):
        existing = self.get(config.store_id)
        assert (existing.revision if existing else None) == expected_revision
        self.stores[config.store_id] = config

    def eligible(self, pipeline, limit):
        return [
            c
            for c in sorted(self.stores.values(), key=lambda s: s.store_id)
            if c.eligible(pipeline)
        ][:limit]


def service(tmp_path):
    registry = MemoryRegistry()
    return StoreAdmin(registry, lambda store: local_lease(str(tmp_path / store)), lambda c: None)


def test_admin_registration_lifecycle_and_uniqueness(tmp_path):
    admin = service(tmp_path)
    payload = config().row()
    for k in ("row_key", "status", "revision", "sync_enabled", "created_at", "updated_at"):
        del payload[k]
    c = admin.register(ADMIN, payload)
    assert c.status == "DRAFT" and not c.sync_enabled and c.created_at
    with pytest.raises(SafeError, match="store_already_registered"):
        admin.register(ADMIN, payload)
    with pytest.raises(SafeError, match="ready_store_required"):
        admin.change(ADMIN, c.store_id, "activate-store")
    assert admin.change(ADMIN, c.store_id, "validate-store").status == "READY"
    assert admin.change(ADMIN, c.store_id, "activate-store").sync_enabled
    assert admin.change(ADMIN, c.store_id, "pause-store").status == "PAUSED"
    c = admin.change(ADMIN, c.store_id, "update-store", {"store_name": "Synthetic brand"})
    assert c.status == "DRAFT" and not c.sync_enabled and c.revision == 5
    assert admin.read(ADMIN, c.store_id) == c
    with pytest.raises(SafeError, match="store_id_is_immutable"):
        admin.change(ADMIN, c.store_id, "update-store", {"store_id": "other"})


def test_registration_can_generate_id_and_requires_operation(tmp_path):
    admin = service(tmp_path)
    assert admin.register(ADMIN, {"operation_b2b": True}).store_id.startswith("store-")
    with pytest.raises(SafeError, match="store_operation_required"):
        admin.register(ADMIN, {})


@pytest.mark.parametrize("role", ["CLIENT_USER", "ADMIN", ""])
def test_registry_admin_only_before_any_read(tmp_path, role):
    admin = service(tmp_path)
    admin.registry = Mock()
    for call in (
        lambda: admin.read(Admin("subject", role), "brand-one"),
        lambda: admin.register(Admin("subject", role), {}),
        lambda: admin.change(Admin("subject", role), "brand-one", "pause-store"),
    ):
        with pytest.raises(SafeError, match="admin_up_required"):
            call()
    admin.registry.get.assert_not_called()
    admin.registry.save.assert_not_called()


@pytest.mark.parametrize(
    "key,value",
    [
        ("timezone", "Invalid/Nowhere"),
        ("currency", "ZZZ"),
        ("currency", "brl"),
        ("operation_b2b", 1),
        ("status", "active"),
        ("qualifying_order_statuses", ("CANCELED",)),
    ],
)
def test_invalid_config(key, value):
    with pytest.raises((SafeError, ValueError)):
        replace(config(), **{key: value})


@pytest.mark.parametrize(
    "field", ["token", "api_key", "secret_data", "credentials", "status", "sync_enabled"]
)
def test_registry_rejects_sensitive_and_lifecycle_fields(tmp_path, field):
    with pytest.raises(SafeError, match="unsupported_registry_fields"):
        service(tmp_path).register(ADMIN, {field: "synthetic"})


@pytest.mark.parametrize("status", ["DRAFT", "READY", "PAUSED", "ERROR", "DISABLED"])
def test_only_active_sync_pipeline_are_eligible(status):
    active = config(
        status="ACTIVE", sync_enabled=True, upzero_enabled=True, upzero_connection_id="up-one"
    )
    assert active.eligible("upzero")
    assert not replace(active, status=status).eligible("upzero")
    assert not replace(active, sync_enabled=False).eligible("upzero")
    assert not active.eligible("meta")


def test_dynamic_policy_partial_history_and_explicit_facts_coverage():
    c = config(
        analytics_enabled=True,
        upzero_enabled=True,
        upzero_connection_id="up-one",
        facts_complete=True,
        facts_coverage_from="2026-09-01T00:00:00Z",
        facts_coverage_to="2026-09-02T03:00:00Z",
    )
    p = c.policy(WINDOW)
    assert not p.history_complete and p.facts_complete and p.currency == "BRL"
    assert (
        p.store_id == c.store_id
        and p.policy_hash != replace(c, store_id="brand-two").policy(WINDOW).policy_hash
    )
    with pytest.raises(SafeError, match="facts_window_not_certified"):
        c.policy(
            replace(
                WINDOW,
                report_to="2026-09-03",
                as_of="2026-09-03T03:00:00Z",
                source_snapshot_at="2026-09-04T00:00:00Z",
                calculated_at="2026-09-04T00:00:00Z",
            )
        )
    with pytest.raises(SafeError, match="history_coverage_required"):
        replace(c, history_complete=True).ready()


def test_previous_closed_day_has_local_midnight_and_explicit_snapshot():
    w = Window.previous_closed_day("America/Sao_Paulo", "2026-10-01T12:00:00Z")
    assert (w.report_from, w.report_to) == ("2026-09-30", "2026-10-01")
    assert w.as_of == "2026-10-01T03:00:00+00:00"
    assert w.source_snapshot_at == w.calculated_at == "2026-10-01T12:00:00+00:00"


def test_dispatcher_selects_stores_and_bounds_actual_inflight_workers(tmp_path):
    stores = [
        config(
            "brand-" + str(n),
            status="ACTIVE",
            sync_enabled=True,
            upzero_enabled=True,
            upzero_connection_id="up-" + str(n),
        )
        for n in range(8)
    ]
    stores += [
        replace(stores[0], store_id="paused", status="PAUSED"),
        replace(stores[0], store_id="disabled", upzero_enabled=False),
    ]
    lock = threading.Lock()
    active = maximum = 0
    visited = []

    class Gateway:
        def run_and_wait(self, pipeline, c, window):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(active, maximum)
                visited.append(c.store_id)
            time.sleep(0.01)
            with lock:
                active -= 1
            return True

    dispatch = Dispatcher(
        MemoryRegistry(stores),
        Gateway(),
        lambda *a: None,
        lambda key: local_lease(str(tmp_path / key)),
        2,
    )
    result = dispatch.run("upzero", lambda _: WINDOW)
    assert len(result) == 8 and all(r.status == "completed" for r in result)
    assert set(visited) == {c.store_id for c in stores[:8]} and maximum == 2 and active == 0
    with (
        local_lease(str(tmp_path / "store-dispatch-global")),
        pytest.raises(SafeError, match="store_busy"),
    ):
        dispatch.run("upzero", lambda _: WINDOW)


def test_uncertain_launch_stops_queued_launches_and_retains_global_lock_contract():
    stores = [
        config("brand-" + str(n), status="ACTIVE", sync_enabled=True, meta_enabled=True)
        for n in range(4)
    ]
    gateway = Mock()
    gateway.run_and_wait.side_effect = SafeError("worker_execution_outcome_unknown")
    with pytest.raises(SafeError, match="worker_execution_outcome_unknown"):
        Dispatcher(
            MemoryRegistry(stores), gateway, lambda *a: None, lambda _: nullcontext(), 1
        ).run("meta", lambda _: WINDOW)
    assert gateway.run_and_wait.call_count == 1


def test_worker_rechecks_revision_eligibility_and_lease_isolation(tmp_path):
    one = config(
        status="ACTIVE", sync_enabled=True, upzero_enabled=True, upzero_connection_id="up-one"
    )
    two = replace(one, store_id="brand-two")
    registry = MemoryRegistry([one, two])
    action = Mock()
    worker = StoreWorker(
        registry, lambda *a: None, lambda key: local_lease(str(tmp_path / key)), action, lambda: {}
    )
    worker.execute(one.store_id, 1, "upzero", WINDOW)
    assert action.call_args.args == (one, "upzero", WINDOW)
    with local_lease(str(tmp_path / one.store_id)):
        with pytest.raises(SafeError, match="store_busy"):
            worker.execute(one.store_id, 1, "upzero", WINDOW)
        worker.execute(two.store_id, 1, "upzero", WINDOW)
    with pytest.raises(SafeError, match="store_registry_changed"):
        worker.execute(two.store_id, 2, "upzero", WINDOW)
    registry.stores[two.store_id] = replace(two, status="PAUSED")
    with pytest.raises(SafeError, match="store_not_eligible"):
        worker.execute(two.store_id, 1, "upzero", WINDOW)
    assert action.call_count == 2


class FakeTransport:
    def __init__(self, rows=()):
        self.config = SimpleNamespace(project="synthetic-dev", location="southamerica-east1")
        self.records = list(rows)
        self.calls = []

    def query(self, sql, parameters, **kwargs):
        self.calls.append((sql, parameters, kwargs))
        return self.records, None


def test_registry_sql_parameters_cas_and_duplicate_detection():
    fake = FakeTransport([config().row()])
    repo = BigQueryRegistry(fake)
    with pytest.raises(SafeError, match="registry_store_scope_mismatch"):
        repo.get("untrusted'--")
    assert repo.get("brand-one").store_id == "brand-one"
    sql, parameters, _ = fake.calls[-1]
    assert "brand-one" not in sql and parameters[0].value == "brand-one"
    repo.save(config(), None)
    assert "ASSERT NOT EXISTS" in fake.calls[-1][0] and "@record" in fake.calls[-1][0]
    repo.save(replace(config(), revision=2), 1)
    assert "@revision" in fake.calls[-1][0] and "BEGIN TRANSACTION" in fake.calls[-1][0]
    fake.records.append(config().row())
    with pytest.raises(SafeError, match="duplicate_store_registry"):
        repo.get("brand-one")


def test_registry_rejects_bad_inventory_and_truncation():
    c = config(status="ACTIVE", sync_enabled=True, meta_enabled=True)
    fake = FakeTransport([c.row(), c.row()])
    repo = BigQueryRegistry(fake)
    with pytest.raises(SafeError, match="invalid_dispatch_registry"):
        repo.eligible("meta", 10)
    with pytest.raises(SafeError, match="dispatch_store_limit_exceeded"):
        repo.eligible("meta", 1)


def preflight(records):
    pre = Prerequisites(FakeTransport())
    pre.rows = lambda store, table, columns="*", snapshot=None: records.get(table, [])
    return pre


def test_connection_ownership_and_missing_meta_binding_fail_closed():
    c = config(
        status="ACTIVE", sync_enabled=True, upzero_enabled=True, upzero_connection_id="up-one"
    )
    pre = preflight(
        {
            "up_core.source_connections": [
                {
                    "source_system": "upzero",
                    "status": "active",
                    "connection_id": "foreign",
                    "secret_resource_name": "synthetic",
                }
            ]
        }
    )
    with pytest.raises(SafeError, match="upzero_connection_not_ready"):
        pre.check(c, "upzero", WINDOW)
    source = {
        "source_system": "upzero",
        "status": "active",
        "connection_id": "up-one",
        "secret_resource_name": "projects/synthetic-dev/secrets/up-intelligence-upzero-brand-one/versions/1",
    }
    pre = preflight({"up_core.source_connections": [source]})
    assert pre.source(c) == source
    source["secret_resource_name"] = "projects/foreign-project/secrets/key/versions/1"
    with pytest.raises(SafeError, match="approved_upzero_secret_version_required"):
        pre.source(c)
    meta = replace(
        c,
        upzero_enabled=False,
        meta_enabled=True,
        meta_connection_id="meta-one",
        meta_account_id="100",
        meta_api_version="v24.0",
    )
    pre.transport.records = []
    for pipeline in ("meta", "intelligence"):
        m = replace(
            meta,
            analytics_enabled=pipeline == "intelligence",
            intelligence_enabled=pipeline == "intelligence",
            upzero_enabled=pipeline == "intelligence",
        )
        if pipeline == "intelligence":
            pre.source = lambda _: {}
        with pytest.raises(ValueError, match="META_ACCOUNT_BINDING_REQUIRED"):
            pre.check(m, pipeline, WINDOW)


def source_inventory(c):
    cps = []
    runs = []
    for resource, filters in (
        ("customers", {"limit": 200}),
        ("orders", {"start_date": "2026-08-31", "end_date": "2026-09-01", "limit": 200}),
        ("analytics_facts", {"from": c.history_from, "to": WINDOW.as_of, "limit": 1000}),
    ):
        cps.append(
            {
                "store_id": c.store_id,
                "connection_id": c.upzero_connection_id,
                "resource": resource,
                "status": "complete",
                "pending_raw_id": None,
                "filters": filters,
                "run_id": resource,
            }
        )
        runs.append(
            {
                "run_id": resource,
                "status": "completed",
                "core_records_failed": 0,
                "finished_at": WINDOW.source_snapshot_at,
            }
        )
    return {"up_ops.sync_checkpoints": cps, "up_ops.sync_runs": runs}


def test_upzero_dependency_coverage_pending_and_failure():
    c = config(upzero_connection_id="up-one")
    records = source_inventory(c)
    pre = preflight(records)
    pre.upzero_complete(c, WINDOW)
    records["up_ops.sync_checkpoints"][-1]["filters"]["from"] = "2026-09-01T01:00:00Z"
    with pytest.raises(SafeError, match="upzero_history_window_not_covered"):
        pre.upzero_complete(c, WINDOW)
    records = source_inventory(c)
    pre = preflight(records)
    records["up_ops.sync_checkpoints"][-1]["pending_raw_id"] = "synthetic-raw"
    with pytest.raises(SafeError, match="upzero_source_not_complete"):
        pre.upzero_complete(c, WINDOW)
    records["up_ops.sync_checkpoints"][-1]["pending_raw_id"] = None
    records["up_ops.sync_runs"][-1]["core_records_failed"] = 1
    with pytest.raises(SafeError, match="upzero_complete_checkpoint_required"):
        pre.upzero_complete(c, WINDOW)


def test_cost_limits_apply_to_legacy_repository_and_same_job_reattach():
    sdk = Mock()
    sdk.query.return_value.job_id = "j1"
    sdk.query.return_value.total_bytes_processed = 5
    sdk.query.return_value.result.return_value = []
    bounded = BoundedClient(
        sdk,
        CloudConfig(
            "synthetic-dev", "southamerica-east1", 10, 30, False, maximum_total_bytes_billed=20
        ),
    )
    job = bounded.query("SELECT 1")
    assert sdk.query.call_args.kwargs["job_config"].maximum_bytes_billed == 10
    assert sdk.query.call_args.kwargs["job_retry"] is None
    assert sdk.query.call_args.kwargs["retry"] is None
    job.result()
    job.result()
    assert bounded.bytes_processed == 5
    bounded.query("SELECT 2", job_id="fixed")
    assert sdk.query.call_args.kwargs["job_retry"] is None
    with pytest.raises(ExecutionBudgetExceeded, match="store_execution_budget_exhausted"):
        bounded.query("SELECT 3")
    assert sdk.query.call_count == 2


def test_run_gateway_uses_same_job_overrides_and_waits_for_terminal():
    calls = []
    execution = (
        "projects/synthetic-dev/locations/southamerica-east1/jobs/up-meta-worker/executions/e1"
    )

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "name": "projects/synthetic-dev/locations/southamerica-east1/operations/o1",
                    "done": True,
                    "response": {"name": execution},
                },
            )
        return httpx.Response(
            200, json={"name": execution, "completionTime": "synthetic", "succeededCount": 1}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gateway = RunGateway(
            client,
            "synthetic-dev",
            "southamerica-east1",
            "leases",
            maximum_bytes_billed=10,
            maximum_total_bytes_billed=20,
        )
        assert gateway.run_and_wait("meta", config(), WINDOW)
        assert calls[0].url.path.endswith("/jobs/up-meta-worker:run")
        override = json.loads(calls[0].content)["overrides"]
        args = override["containerOverrides"][0]["args"]
        assert override["taskCount"] == 1 and args[args.index("--store-id") + 1] == "brand-one"
        assert "--expected-revision" in args and len(calls) == 2
        assert not any(word in calls[0].content.decode() for word in ("token", "secret", "policy"))


def test_unknown_run_outcome_is_not_retried():
    handler = Mock(side_effect=httpx.ReadTimeout("synthetic"))
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(SafeError, match="worker_execution_outcome_unknown"),
    ):
        RunGateway(
            client,
            "synthetic-dev",
            "southamerica-east1",
            "leases",
            maximum_bytes_billed=10,
            maximum_total_bytes_billed=20,
        ).run_and_wait("meta", config(), WINDOW)
    assert handler.call_count == 1


def test_gateway_rejects_foreign_execution_metadata():
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "done": True,
                        "response": {"name": "projects/foreign/locations/x/jobs/bad/executions/e"},
                    },
                )
            )
        ) as client,
        pytest.raises(SafeError, match="worker_execution_outcome_unknown"),
    ):
        RunGateway(
            client,
            "synthetic-dev",
            "southamerica-east1",
            "leases",
            maximum_bytes_billed=10,
            maximum_total_bytes_billed=20,
        ).run_and_wait("meta", config(), WINDOW)


def test_shared_schema_is_only_addition_and_old_terraform_preserved():
    root = Path("infra/terraform")
    old = json.loads(Path("tests/fixtures/change161/base_tables.json").read_text())
    active = json.loads((root / "tables.json").read_text())
    assert set(active) - set(old) == {REGISTRY}
    assert all(active[name] == spec for name, spec in old.items())
    hashes = json.loads(Path("tests/fixtures/change161/base_schema_hashes.json").read_text())
    for name, sha in hashes.items():
        assert hashlib.sha256((root / "schemas" / (name + ".json")).read_bytes()).hexdigest() == sha
    schema = json.loads((root / "schemas" / (REGISTRY + ".json")).read_text())
    assert {f["name"] for f in schema if f["mode"] == "REQUIRED"} == {
        "row_key",
        "store_id",
        "status",
        "revision",
    }
    assert active[REGISTRY]["dataset"] == "up_ops" and active[REGISTRY]["cluster"] == [
        "status",
        "store_id",
    ]
    for name, sha in json.loads(
        Path("tests/fixtures/change161/base_terraform_hashes.json").read_text()
    ).items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha


def test_shared_terraform_constant_pipeline_inventory_and_paused_schedulers():
    source = Path("infra/terraform/control_plane.tf").read_text()
    assert (
        "mx-fashion" not in source
        and "var.pilot" not in source
        and "config/analytics" not in source
    )
    assert "paused    = true" in source and "max_retries     = 0" in source
    assert "control_plane_max_parallel_stores" in source and "default = 2" in source
    assert '"run.jobs.runWithOverrides"' in source
    assert (
        "google_bigquery_dataset" not in source
        and "google_secret_manager_secret_version" not in source
    )
    assert all(
        "store" not in line or "max_parallel_stores" in line
        for line in source.splitlines()
        if "for_each" in line
    )
    assert JOBS == {p: "up-" + p + "-worker" for p in PIPELINES}
    for path in Path("src/control_plane").glob("*.py"):
        text = path.read_text()
        assert "mx-fashion" not in text and "config/analytics/" not in text
        assert "subprocess" not in text and "terraform-bin" not in text


def test_no_client_discovery_without_dev_gates(monkeypatch):
    from src.control_plane.cli import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "registry",
            "read-store",
            "--project",
            "up-data-intelligence-dev",
            "--confirm-project",
            "up-data-intelligence-dev",
            "--store-id",
            "brand-one",
            "--confirm-store",
            "brand-one",
            "--lease-bucket",
            "synthetic",
        ],
    )
    with patch("src.control_plane.cli.clients") as sdk:
        assert main() == 1
    sdk.assert_not_called()


def test_store_worker_does_not_run_action_on_failed_dependencies():
    c = config(status="ACTIVE", sync_enabled=True, intelligence_enabled=True)
    action = Mock()
    worker = StoreWorker(
        MemoryRegistry([c]),
        Mock(side_effect=SafeError("meta_source_not_complete")),
        lambda _: nullcontext(),
        action,
        lambda: {},
    )
    with pytest.raises(SafeError):
        worker.execute(c.store_id, 1, "intelligence", WINDOW)
    action.assert_not_called()


def test_dynamic_analytics_publication_parameters_are_isolated_and_initialized_once():
    c = config(upzero_enabled=True, analytics_enabled=True, upzero_connection_id="up-one")
    fake = FakeTransport([])
    action = Actions(fake, Mock(), lease_bucket="synthetic")
    with patch("src.control_plane.worker.analytics_materialize") as publish:
        action.analytics(c, WINDOW)
    assert len(fake.calls) == 2
    assert "store_id=@store AND policy_hash=@policy" in fake.calls[0][0]
    pub = publish.call_args.args[2]
    assert (
        pub.policy.store_id == c.store_id
        and pub.expected_generation == 0
        and pub.source.completeness_confirmed
    )
    assert pub.policy.report_from == WINDOW.report_from and pub.policy.as_of == WINDOW.as_of
    fake.records = [
        {
            "record_kind": "HEAD",
            "generation": 3,
            "status": "completed",
            "publication_id": "synthetic",
        },
        {
            "record_kind": "RECEIPT",
            "generation": 3,
            "status": "completed",
            "publication_id": "synthetic",
        },
    ]
    fake.calls = []
    with patch("src.control_plane.worker.analytics_materialize") as publish:
        action.analytics(c, WINDOW)
    assert len(fake.calls) == 1 and publish.call_args.args[2].expected_generation == 3


def test_unavailable_meta_does_not_block_independent_upzero_or_v1_analytics():
    c = config(
        status="ACTIVE",
        sync_enabled=True,
        upzero_enabled=True,
        analytics_enabled=True,
        meta_enabled=True,
        upzero_connection_id="up-one",
        meta_connection_id="meta-one",
        meta_account_id="100",
        meta_api_version="v24.0",
    )
    pre = preflight(source_inventory(c))
    pre.source = Mock(return_value={})
    pre.account = Mock(side_effect=SafeError("meta_binding_required"))
    pre.check(c, "upzero", WINDOW)
    pre.check(c, "analytics", WINDOW)
    pre.account.assert_not_called()
    with pytest.raises(SafeError, match="meta_binding_required"):
        pre.check(c, "meta", WINDOW)


def test_activation_revalidates_binding_and_no_worker_or_terraform_side_effect(tmp_path):
    admin = service(tmp_path)
    c = config(status="READY")
    admin.registry.stores[c.store_id] = c
    admin.validate = Mock(side_effect=SafeError("meta_binding_required"))
    with pytest.raises(SafeError, match="meta_binding_required"):
        admin.change(ADMIN, c.store_id, "activate-store")
    assert admin.registry.get(c.store_id) == c


def test_meta_checkpoint_requires_exact_account_window_completed_run():
    from src.connectors.meta.config import Account
    from src.intelligence.live.runtime import reporting

    c = config(meta_account_id="100", meta_connection_id="meta-one", meta_api_version="v24.0")
    account = Account(c.store_id, "100", "meta-one", "v24.0", c.timezone, c.currency)
    report = reporting(account, c.policy(WINDOW))
    cp = {
        "resource": "meta_live_insights_daily",
        "connection_id": c.meta_connection_id,
        "status": "complete",
        "pending_raw_id": None,
        "filters": {
            "account": account.snapshot(),
            "insights": {**report.snapshot(), "level": "campaign"},
        },
        "run_id": "synthetic-meta",
    }
    run = {
        "run_id": "synthetic-meta",
        "status": "completed",
        "core_records_failed": 0,
        "finished_at": WINDOW.source_snapshot_at,
    }
    catalogs = [
        {
            **cp,
            "resource": "meta_live_" + r,
            "connection_id": c.meta_connection_id,
            "filters": {"account": account.snapshot(), "insights": None},
        }
        for r in ("accounts", "campaigns", "adsets", "ads")
    ]
    pre = preflight({"up_ops.sync_checkpoints": [cp] + catalogs, "up_ops.sync_runs": [run]})
    pre.account = lambda _: account
    pre.meta_complete(c, WINDOW)
    run["status"] = "failed"
    with pytest.raises(SafeError, match="meta_source_not_complete"):
        pre.meta_complete(c, WINDOW)
    run["status"] = "completed"
    cp["filters"]["insights"]["since"] = "2026-08-01"
    with pytest.raises(SafeError, match="meta_complete_checkpoint_required"):
        pre.meta_complete(c, WINDOW)


def test_intelligence_dependency_rejects_missing_duplicate_and_changed_v1_head():
    c = config()
    p = c.policy(WINDOW)
    head = {
        "record_kind": "HEAD",
        "generation": 1,
        "policy_hash": p.policy_hash,
        "publication_id": "synthetic",
        "status": "completed",
    }
    receipt = {
        **head,
        "record_kind": "RECEIPT",
        "report_from": p.report_from,
        "report_to": p.report_to,
        "as_of": p.as_of,
    }
    records = {"up_analytics.analytics_publications": []}
    pre = preflight(records)
    with pytest.raises(SafeError, match="analytics_completed_head_required"):
        pre.analytics_complete(c, WINDOW)
    records["up_analytics.analytics_publications"] = [head, receipt]
    pre.analytics_complete(c, WINDOW)
    records["up_analytics.analytics_publications"].append(head)
    with pytest.raises(SafeError, match="analytics_completed_head_required"):
        pre.analytics_complete(c, WINDOW)
    pre.rows = lambda store, table, columns="*", snapshot=None: (
        [head, receipt] if snapshot else [{**head, "generation": 2}]
    )
    with pytest.raises(SafeError, match="analytics_publication_changed_after_snapshot"):
        pre.analytics_complete(c, WINDOW)


def test_failed_registry_transaction_is_ambiguous_and_retains_lock_contract():
    transport = FakeTransport()
    transport.query = Mock(side_effect=TimeoutError("SYNTHETIC_PRIVATE_DETAIL"))
    with pytest.raises(SafeError, match="registry_write_outcome_unknown") as exc:
        BigQueryRegistry(transport).save(config(), None)
    assert "PRIVATE_DETAIL" not in str(exc.value)


def test_cloud_global_lease_is_retained_for_unknown_worker_and_registry_outcome():
    from src.security.lease import cloud_lease

    for code in ("worker_execution_outcome_unknown", "registry_write_outcome_unknown"):
        blob = Mock()
        with patch("google.cloud.storage.Client") as client:
            client.return_value.bucket.return_value.blob.return_value = blob
            with pytest.raises(SafeError, match=code), cloud_lease("synthetic-bucket", "global"):
                raise SafeError(code)
        blob.upload_from_string.assert_called_once()
        assert blob.upload_from_string.call_args.kwargs["if_generation_match"] == 0
        blob.delete.assert_not_called()


def test_launch_definitely_rejected_does_not_claim_unknown():
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(403, json={}))
        ) as client,
        pytest.raises(SafeError, match="worker_launch_rejected"),
    ):
        RunGateway(
            client,
            "synthetic-dev",
            "southamerica-east1",
            "leases",
            maximum_bytes_billed=10,
            maximum_total_bytes_billed=20,
        ).run_and_wait("meta", config(), WINDOW)


def test_async_run_polling_waits_for_execution_completion():
    execution = (
        "projects/synthetic-dev/locations/southamerica-east1/jobs/up-meta-worker/executions/e1"
    )
    operation = "projects/synthetic-dev/locations/southamerica-east1/operations/o1"
    responses = iter(
        [
            {"name": operation},
            {"name": operation, "done": True, "response": {"name": execution}},
            {"name": execution},
            {"name": execution, "completionTime": "synthetic", "succeededCount": 1},
        ]
    )
    sleep = Mock()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=next(responses)))
    ) as client:
        assert RunGateway(
            client,
            "synthetic-dev",
            "southamerica-east1",
            "leases",
            maximum_bytes_billed=10,
            maximum_total_bytes_billed=20,
            sleep=sleep,
        ).run_and_wait("meta", config(), WINDOW)
    assert sleep.call_count == 2


def test_budget_marks_unknown_mutation_but_not_read_failure():
    sdk = Mock()
    sdk.query.side_effect = TimeoutError("synthetic")
    bounded = BoundedClient(
        sdk,
        CloudConfig(
            "synthetic-dev", "southamerica-east1", 10, 30, False, maximum_total_bytes_billed=20
        ),
    )
    with pytest.raises(TimeoutError):
        bounded.query("SELECT 1")
    assert not bounded.mutation_outcome_unknown and bounded.bytes_processed is None
    with pytest.raises(TimeoutError):
        bounded.query("INSERT INTO synthetic VALUES (1)")
    assert bounded.mutation_outcome_unknown


def test_meta_worker_resumes_prior_pending_window_before_refresh():
    from src.connectors.meta.config import Account, Insights
    from src.utils.data import digest

    c = config(meta_account_id="100", meta_connection_id="meta-one", meta_api_version="v24.0")
    account = Account(c.store_id, "100", "meta-one", "v24.0", c.timezone, c.currency)
    old = Insights("2026-08-30", "2026-08-30", "impression", ("7d_click",), None)
    filters = {"account": account.snapshot(), "insights": {**old.snapshot(), "level": "campaign"}}
    cp = {
        "resource": "meta_live_insights_daily",
        "connection_id": c.meta_connection_id,
        "status": "extracted",
        "pending_raw_id": "synthetic-raw",
        "filters": filters,
        "plan_key": digest(["meta", "insights", filters, 100]),
    }
    repo = Mock()
    repo.read.return_value = [cp]
    pre = Mock()
    pre.account.return_value = account
    action = Actions(
        FakeTransport(),
        pre,
        lease_bucket="synthetic",
        meta_secret_reference="projects/up-data-intelligence-dev/secrets/up-intelligence-meta-global-token/versions/1",
    )
    action.repository = lambda: repo
    with (
        patch("src.control_plane.worker.MetaFoundationLiveConnector") as connector,
        patch("src.control_plane.worker.MetaLiveEngine") as engine,
        patch("src.control_plane.worker.resolve_secret", return_value="SYNTHETIC"),
    ):
        connector.return_value.page_limit = 100
        engine.return_value.core_names = {
            r: "meta_live_" + ("insights_daily" if r == "insights" else r)
            for r in ("accounts", "campaigns", "adsets", "ads", "insights")
        }
        engine.return_value.run.return_value = {"status": "completed", "core_records_failed": 0}
        action.meta(c, WINDOW)
        calls = engine.return_value.run.call_args_list
        assert len(calls) == 6
        assert calls[-2].args == ("insights", old) and not calls[-2].kwargs
        assert calls[-1].kwargs == {"refresh": True}
        assert engine.call_args.kwargs["lease"]().__enter__() is None
        connector.return_value.close.assert_called_once()


@pytest.mark.parametrize(
    "actions", [["update"], ["delete"], ["delete", "create"], ["create", "delete"]]
)
def test_saved_plan_guard_rejects_any_existing_change(actions):
    from scripts.control_plane_plan_guard import check

    with pytest.raises(ValueError, match="NON_ADDITIVE_TERRAFORM_PLAN"):
        check(
            {
                "resource_changes": [
                    {
                        "address": 'google_bigquery_table.tables["orders"]',
                        "change": {"actions": actions},
                    }
                ]
            }
        )


def test_saved_plan_guard_only_registry_and_paused_central_schedulers():
    from scripts.control_plane_plan_guard import check

    registry = {
        "address": 'google_bigquery_table.tables["store_runtime_config"]',
        "index": REGISTRY,
        "type": "google_bigquery_table",
        "change": {
            "actions": ["create"],
            "after": {"table_id": REGISTRY, "dataset_id": "up_ops", "deletion_protection": True},
        },
    }
    scheduler = {
        "address": 'google_cloud_scheduler_job.control_plane["upzero"]',
        "type": "google_cloud_scheduler_job",
        "change": {"actions": ["create"], "after": {"paused": True}},
    }
    assert check({"resource_changes": [registry, scheduler]}) == {
        "add": 2,
        "change": 0,
        "destroy": 0,
    }
    scheduler["change"]["after"]["paused"] = False
    with pytest.raises(ValueError, match="SCHEDULER_MUST_REMAIN_PAUSED"):
        check({"resource_changes": [scheduler]})
    registry["index"] = "unapproved"
    with pytest.raises(ValueError, match="UNAPPROVED_TABLE"):
        check({"resource_changes": [registry]})
    with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
        check({"resource_drift": [{"change": {"actions": ["update"]}}]})


def test_shared_registration_and_schema_generation_deterministic():
    from src.bigquery.schema import generate

    paths = [
        Path("infra/terraform/tables.json"),
        Path("infra/terraform/schemas/store_runtime_config.json"),
        Path("sql/ops/store_runtime_config.sql"),
    ]
    before = {p: p.read_bytes() for p in paths}
    generate()
    assert all(p.read_bytes() == value for p, value in before.items())


def test_run_gateway_accepts_only_explicit_same_project_numeric_canonical_names():
    execution = "projects/123456/locations/southamerica-east1/jobs/up-meta-worker/executions/e1"

    def handler(request):
        return httpx.Response(
            200,
            json={"done": True, "response": {"name": execution}}
            if request.method == "POST"
            else {"completionTime": "synthetic", "succeededCount": 1},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gateway = RunGateway(
            client,
            "synthetic-dev",
            "southamerica-east1",
            "leases",
            project_number="123456",
            maximum_bytes_billed=10,
            maximum_total_bytes_billed=20,
        )
        assert gateway.run_and_wait("meta", config(), WINDOW)
        with pytest.raises(SafeError, match="worker_execution_outcome_unknown"):
            gateway.get(execution.replace("123456", "999999"), "executions", "up-meta-worker")


@pytest.mark.parametrize("b2b", [True, False])
def test_no_implicit_b2b_materialization_for_b2c_or_mixed_store(b2b):
    c = replace(
        config(upzero_enabled=True, upzero_connection_id="up-one", analytics_enabled=True),
        operation_b2b=b2b,
        operation_b2c=True,
    )
    with pytest.raises(SafeError, match="b2c_or_mixed_analytics_contract_not_available"):
        c.ready()
    replace(c, analytics_enabled=False).ready()


def test_pilot_policy_parity_is_fixture_only_not_runtime_dependency():
    from src.analytics.config import AnalyticsPolicy

    p = AnalyticsPolicy.from_dict(
        json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    )
    c = StoreConfig(
        p.store_id,
        operation_b2b=True,
        timezone=p.reporting_timezone,
        currency=p.currency,
        history_from=p.history_from,
        policy_version=p.policy_version,
        qualifying_order_statuses=p.qualifying_order_statuses,
        history_complete=p.history_complete,
        facts_complete=p.facts_complete,
        facts_coverage_from=p.history_from,
        facts_coverage_to=p.as_of,
    )
    w = Window(p.report_from, p.report_to, p.as_of, "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z")
    assert c.policy(w).to_dict() == p.to_dict() and c.policy(w).policy_hash == p.policy_hash


def test_budget_rejection_before_submission_does_not_retain_writer_lease_as_unknown():
    from src.bigquery.writer import AtomicWriter, config_for

    sdk = Mock()
    bounded = BoundedClient(
        sdk,
        CloudConfig(
            "synthetic-dev", "southamerica-east1", 10, 30, False, maximum_total_bytes_billed=10
        ),
    )
    bounded.reserved_bytes = 10
    with pytest.raises(SafeError, match="bigquery_write_failed"):
        AtomicWriter(bounded, "southamerica-east1").execute(
            "INSERT INTO synthetic VALUES(1)", config_for(), "test"
        )
    sdk.query.assert_not_called()
    assert bounded.budget_exhausted and not bounded.mutation_outcome_unknown


def test_worker_sanitizes_budget_vs_ambiguous_mutation_as_distinct_outcomes():
    fake = FakeTransport()
    fake.client = SimpleNamespace(budget_exhausted=True, mutation_outcome_unknown=False)
    action = Actions(fake, Mock(), lease_bucket="synthetic")
    action.analytics = Mock(side_effect=SafeError("bigquery_write_failed"))
    with pytest.raises(SafeError, match="store_execution_budget_exhausted"):
        action(config(), "analytics", WINDOW)
    fake.client.mutation_outcome_unknown = True
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        action(config(), "analytics", WINDOW)


def test_upzero_resume_uses_persisted_page_limit_and_does_not_discard_pending_raw():
    from src.utils.data import digest

    c = config(upzero_enabled=True, upzero_connection_id="up-one")
    filters = {"from": c.history_from, "to": WINDOW.as_of, "limit": 500}
    cp = {
        "store_id": c.store_id,
        "connection_id": c.upzero_connection_id,
        "resource": "analytics_facts",
        "mode": "backfill",
        "filters": filters,
        "pending_raw_id": "synthetic-raw",
        "status": "extracted",
        "updated_at": WINDOW.as_of,
        "plan_key": digest(
            [c.store_id, c.upzero_connection_id, "analytics_facts", filters, "backfill"]
        ),
    }
    repo = Mock()
    repo.read.side_effect = lambda table, *a: [cp] if table == "sync_checkpoints" else []
    pre = Mock()
    pre.source.return_value = {"secret_resource_name": "synthetic-reference"}
    action = Actions(FakeTransport(), pre, lease_bucket="synthetic", page_limit=1000)
    action.repository = lambda: repo
    with (
        patch("src.control_plane.worker.Engine") as engine,
        patch("src.control_plane.worker.UpZeroConnector"),
        patch("src.control_plane.worker.resolve_secret", return_value="SYNTHETIC"),
        patch("src.control_plane.worker.incremental", return_value=({"limit": 1000}, None)),
        patch("src.control_plane.worker.open_order_windows", return_value=[]),
    ):
        engine.return_value.run.return_value = {"status": "completed", "core_records_failed": 0}
        action.upzero(c, WINDOW)
        assert engine.call_count == 2
        assert engine.call_args_list[0].args[0].page_limit == 1000
        assert engine.call_args_list[1].args[0].page_limit is None
        assert any(
            call.args == ("analytics_facts", filters) and call.kwargs == {"mode": "backfill"}
            for call in engine.return_value.run.call_args_list
        )


def test_definitive_sdk_rejection_is_not_unknown_mutation_or_registration():
    from google.api_core.exceptions import Forbidden

    sdk = Mock()
    sdk.query.side_effect = Forbidden("synthetic-rejection")
    bounded = BoundedClient(
        sdk,
        CloudConfig(
            "synthetic-dev", "southamerica-east1", 10, 30, False, maximum_total_bytes_billed=20
        ),
    )
    with pytest.raises(Forbidden):
        bounded.query("INSERT INTO synthetic VALUES (1)")
    assert not bounded.mutation_outcome_unknown
    transport = FakeTransport()
    transport.query = Mock(side_effect=Forbidden("synthetic-rejection"))
    with pytest.raises(SafeError, match="registry_write_failed"):
        BigQueryRegistry(transport).save(config(), None)


def test_terminal_failed_mutation_job_does_not_invent_running_commit():
    from google.api_core.exceptions import BadRequest

    sdk = Mock()
    sdk.query.return_value.state = "DONE"
    sdk.query.return_value.error_result = {"reason": "invalidQuery"}
    sdk.query.return_value.result.side_effect = BadRequest("synthetic-invalid-query")
    bounded = BoundedClient(
        sdk,
        CloudConfig(
            "synthetic-dev", "southamerica-east1", 10, 30, False, maximum_total_bytes_billed=20
        ),
    )
    with pytest.raises(BadRequest):
        bounded.query("INSERT INTO synthetic VALUES(1)").result()
    assert not bounded.mutation_outcome_unknown and bounded.bytes_processed is None
