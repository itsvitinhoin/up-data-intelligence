from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace

import httpx
import pytest

from src.domain.models import SafeError
from src.installation.gateway import InstallationGateway
from src.installation.model import Limits
from src.installation.orchestrator import Orchestrator
from src.installation.worker import Worker
from tests.installation.fakes import MemoryLedger
from tests.installation.test_planner import NOW, graph


class Gateway:
    def __init__(self, error=None):
        self.posts = []
        self.error = error
        self.op = {"done": False}
        self.exec = {}

    def submit(self, row):
        self.posts.append(row["work_unit_id"])
        if self.error:
            raise SafeError(self.error)
        return "projects/synthetic/locations/test/operations/synthetic"

    def operation(self, name):
        return self.op

    def validate(self, *args):
        pass

    def execution(self, *args):
        return self.exec


def setup(error=None):
    c, p, rows = graph(1)
    ledger = MemoryLedger(c, p, rows)
    gateway = Gateway(error)
    leases = []

    def lease(key):
        leases.append(key)
        return nullcontext()

    return (
        ledger,
        gateway,
        Orchestrator(ledger, gateway, lease, lambda p, r: (False, False), clock=lambda: NOW),
        leases,
    )


def test_reservation_before_post_one_store_and_no_duplicate_claim():
    ledger, gateway, orchestrator, leases = setup()
    assert orchestrator.dispatch() == 1 and leases == [
        "installation-orchestrator-global",
        ledger.c.store_id,
    ]
    row = next(r for r in ledger.units() if r["status"] == "DISPATCHING")
    assert row["attempt_count"] == 1 and row["dispatch_operation_name"]
    worker = Worker(
        ledger, lambda c, r, limits: {"complete": True}, lambda k: nullcontext(), clock=lambda: NOW
    )
    # Operation metadata CAS advanced revision, but reservation identity stays pinned.
    assert row["revision"] > row["reservation_revision"]
    worker.execute(
        row["store_id"],
        row["work_unit_id"],
        row["reservation_revision"],
        row["dispatch_token"],
        row["pipeline"],
    )
    with pytest.raises(SafeError, match="work_conflict"):
        worker.execute(
            row["store_id"],
            row["work_unit_id"],
            row["reservation_revision"],
            row["dispatch_token"],
            row["pipeline"],
        )
    assert ledger.units()[0]["status"] == "COMPLETE"


@pytest.mark.parametrize(
    "code,state",
    [("work_dispatch_unknown", "DISPATCH_UNKNOWN"), ("installation_launch_rejected", "BLOCKED")],
)
def test_post_unknown_no_second_post(code, state):
    ledger, gateway, orchestrator, _ = setup(code)
    orchestrator.dispatch()
    assert next(r for r in ledger.units() if r["resource"] == "verification")["status"] == state
    for _ in range(3):
        orchestrator.dispatch()
    assert len(gateway.posts) == 1
    assert ledger.plans()[0]["status"] == (
        "OUTCOME_UNKNOWN" if state == "DISPATCH_UNKNOWN" else "BLOCKED"
    )


def test_crash_after_reservation_without_known_operation_is_ambiguous():
    ledger, gateway, orchestrator, _ = setup()
    ledger.reserve(ledger.units()[0], "synthetic", NOW, Limits())
    orchestrator.dispatch()
    assert not gateway.posts
    assert ledger.units()[0]["status"] == "DISPATCH_UNKNOWN"


def test_known_operation_reconciles_execution_no_post_retry():
    ledger, gateway, orchestrator, _ = setup()
    orchestrator.dispatch()
    gateway.op = {"done": True, "response": {"name": "synthetic-execution"}}
    gateway.exec = {"completionTime": NOW, "failedCount": 1}
    orchestrator.dispatch()
    assert len(gateway.posts) == 1
    assert ledger.units()[0]["execution_name"] == "synthetic-execution"
    assert ledger.units()[0]["status"] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize(
    "code,state",
    [
        ("retry_after_deferred", "DEFERRED"),
        ("unclassified", "BLOCKED"),
        ("source_verification_outcome_unknown", "OUTCOME_UNKNOWN"),
        ("registry_write_outcome_unknown", "OUTCOME_UNKNOWN"),
        ("bigquery_write_outcome_unknown", "RUNNING"),
    ],
)
def test_worker_allowlist_retry_and_unknown(code, state):
    ledger, _, _, _ = setup()
    row = ledger.reserve(ledger.units()[0], "synthetic", NOW, Limits())

    def fail(*args):
        raise SafeError(code)

    with pytest.raises(SafeError):
        Worker(ledger, fail, lambda k: nullcontext(), clock=lambda: NOW).execute(
            row["store_id"],
            row["work_unit_id"],
            row["revision"],
            row["dispatch_token"],
            row["pipeline"],
        )
    saved = ledger.u[row["work_unit_id"]]
    assert saved["status"] == state
    assert bool(saved["next_eligible_at"]) == (state == "DEFERRED")


def test_configuration_change_blocks_before_source_call():
    ledger, gateway, orchestrator, _ = setup()
    ledger.c = replace(ledger.c, revision=ledger.c.revision + 1)
    assert orchestrator.dispatch() == 0 and not gateway.posts
    assert ledger.plans()[0]["status"] == "BLOCKED"
    ledger, _, _, _ = setup()
    row = ledger.reserve(ledger.units()[0], "synthetic", NOW, Limits())
    ledger.c = replace(ledger.c, revision=ledger.c.revision + 1)

    def fail(*args):
        raise AssertionError("source must not be called")

    with pytest.raises(SafeError, match="configuration_changed"):
        Worker(ledger, fail, lambda k: nullcontext(), clock=lambda: NOW).execute(
            row["store_id"],
            row["work_unit_id"],
            row["revision"],
            row["dispatch_token"],
            row["pipeline"],
        )


def test_partial_then_ready_without_lifetime_or_activation():
    c, p, rows = graph(2)
    ledger = MemoryLedger(c, p, rows)
    publications = {"partial": False, "final": False}
    orch = Orchestrator(
        ledger,
        Gateway(),
        lambda k: nullcontext(),
        lambda p, r: (publications["partial"], publications["final"]),
        clock=lambda: NOW,
    )
    facts = sorted(
        (r for r in ledger.u.values() if r["resource"] == "analytics_facts"),
        key=lambda r: r["sequence"],
    )
    facts[0]["status"] = "COMPLETE"
    publications["partial"] = True
    plan = orch.refresh(ledger.plans()[0])
    assert (
        plan["status"] == "PARTIAL"
        and not ledger.c.facts_complete
        and not ledger.c.history_complete
    )
    assert ledger.c.facts_coverage_to == facts[0]["filters"]["to"]
    for r in ledger.u.values():
        r["status"] = "COMPLETE"
    publications["final"] = True
    plan = orch.refresh(plan)
    assert plan["status"] == "COMPLETE" and ledger.c.status == "READY" and not ledger.c.sync_enabled
    assert (
        ledger.c.facts_complete
        and not ledger.c.history_complete
        and ledger.c.history_coverage is None
    )
    for pipeline in ["upzero", "meta", "analytics", "intelligence"]:
        assert not ledger.c.eligible(pipeline)


def test_global_capacity_and_max_dispatch_caps():
    c, p, rows = graph(1)
    ledger = MemoryLedger(c, p, rows)
    original = deepcopy(rows[0])
    for i in range(4):
        plan = {**p, "plan_id": f"synthetic-plan-{i}", "store_id": f"synthetic-store-{i}"}
        row = {
            **original,
            "plan_id": plan["plan_id"],
            "work_unit_id": f"synthetic-unit-{i}",
            "store_id": plan["store_id"],
        }
        ledger.p[plan["plan_id"]] = plan
        ledger.u[row["work_unit_id"]] = row
    # isolate admission from unrelated registry config projection in this selector test
    orch = Orchestrator(
        ledger,
        Gateway(),
        lambda k: nullcontext(),
        lambda p, r: (False, False),
        limits=Limits(global_parallel_store_limit=2, max_dispatches=1),
        clock=lambda: NOW,
    )
    orch.refresh = lambda p: p
    assert orch.dispatch() == 1
    assert orch.dispatch() == 1
    assert orch.dispatch() == 0


def test_gateway_exact_post_once_and_name_scope():
    seen = []

    def handler(req):
        seen.append(req.method)
        raise httpx.ReadTimeout("synthetic sensitive payload")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gw = InstallationGateway(client, "synthetic-dev", "southamerica-east1", "synthetic-bucket")
    _, _, rows = graph(1)
    row = {**rows[0], "dispatch_token": "synthetic"}
    with pytest.raises(SafeError, match="work_dispatch_unknown"):
        gw.submit(row)
    assert seen == ["POST"]
    for name in [
        "projects/foreign/locations/southamerica-east1/operations/x",
        "projects/synthetic-dev/locations/southamerica-east1/operations/x?token=bad",
    ]:
        with pytest.raises(SafeError):
            gw.operation(name)
    assert seen == ["POST"]
    client.close()


def test_retries_have_separate_failure_limit_from_healthy_slice_attempts():
    ledger, _, _, _ = setup()
    original = ledger.units()[0]

    def fail(*args):
        raise SafeError("retry_after_deferred")

    worker = Worker(ledger, fail, lambda k: nullcontext(), clock=lambda: NOW)
    for attempt in range(3):
        row = ledger.reserve(ledger.u[original["work_unit_id"]], "synthetic", NOW, Limits())
        with pytest.raises(SafeError, match="retry_after_deferred"):
            worker.execute(
                row["store_id"],
                row["work_unit_id"],
                row["reservation_revision"],
                row["dispatch_token"],
                row["pipeline"],
            )
        current = ledger.u[row["work_unit_id"]]
        assert current["failure_count"] == attempt + 1
        assert current["status"] == ("BLOCKED" if attempt == 2 else "DEFERRED")
    assert current["last_error_code"] == "work_retry_exhausted"


def test_operation_metadata_race_after_worker_completion_is_safe():
    ledger, gateway, orch, _ = setup()

    def submit(row):
        gateway.posts.append(row["work_unit_id"])
        Worker(
            ledger, lambda *a: {"complete": True}, lambda k: nullcontext(), clock=lambda: NOW
        ).execute(
            row["store_id"],
            row["work_unit_id"],
            row["reservation_revision"],
            row["dispatch_token"],
            row["pipeline"],
        )
        return "projects/synthetic/locations/test/operations/synthetic"

    gateway.submit = submit
    orch.dispatch()
    row = ledger.units()[0]
    assert row["status"] == "COMPLETE" and row["dispatch_operation_name"]
    gateway.op = {"done": True, "response": {"name": "synthetic-execution"}}
    gateway.exec = {"completionTime": NOW, "failedCount": 1}
    orch.reconcile(row)
    assert ledger.units()[0]["status"] == "COMPLETE"


def test_known_completed_execution_preserves_successful_yield():
    ledger, gateway, orch, _ = setup()
    orch.dispatch()
    row = ledger.units()[0]
    Worker(
        ledger,
        lambda *a: {"yielded": True, "complete": False},
        lambda k: nullcontext(),
        clock=lambda: NOW,
    ).execute(
        row["store_id"],
        row["work_unit_id"],
        row["reservation_revision"],
        row["dispatch_token"],
        row["pipeline"],
    )
    gateway.op = {"done": True, "response": {"name": "synthetic-execution"}}
    gateway.exec = {"completionTime": NOW, "succeededCount": 1}
    orch.reconcile(row)
    assert ledger.units()[0]["status"] == "PENDING" and ledger.units()[0]["failure_count"] == 0
