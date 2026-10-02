from copy import deepcopy
from dataclasses import replace

import pytest

from src.dashboard.contracts import ReadError
from src.dashboard.service import DashboardService
from src.installation.publication import policy_for
from tests.dashboard.test_installation import GRANT, PRINCIPAL, Reader
from tests.dashboard.test_read_api import head
from tests.installation.test_planner import NOW, graph


class PlannedReader(Reader):
    def __init__(self, complete=False):
        super().__init__()
        c, plan, units = graph(2)
        c = replace(
            c,
            store_id=GRANT.store_id,
            upzero_connection_id="synthetic-connection",
            status="READY" if complete else "DRAFT",
            facts_complete=complete,
            facts_coverage_from=c.history_from if complete else None,
            facts_coverage_to=plan["target_as_of"] if complete else None,
        )
        plan["store_id"] = c.store_id
        plan["status"] = "COMPLETE" if complete else "PARTIAL"
        for unit in units:
            unit["store_id"] = c.store_id
            if complete or unit["sequence"] <= 11:
                unit["status"] = "COMPLETE"
        self.plan = [plan]
        self.units = units
        self.registry = [{**c.row(), "snapshot_at": NOW}]
        pub = sorted(
            (
                r
                for r in units
                if r["unit_kind"] == "PUBLISH_ANALYTICS" and r["status"] == "COMPLETE"
            ),
            key=lambda r: r["sequence"],
        )[-1]
        self.policy = policy_for(c, pub, NOW)
        self.heads = [head(self.policy)]
        for r in self.resources:
            r.update(
                state="COMPLETE",
                pending_raw=False,
                checkpoint_status="complete",
                pending_count=0,
                blocked_count=0,
                pending_raw_count=0,
            )
        if not complete:
            self.resources[-1].update(checkpoint_status="running", pending_count=1)

    def query(self, query, **kwargs):
        if query.name == "installation_publication_flags":
            return [
                {
                    "history_complete": self.policy.history_complete,
                    "facts_complete": self.policy.facts_complete,
                    "currency": self.policy.currency,
                    "reporting_timezone": self.policy.reporting_timezone,
                }
            ]
        if query.name in {"installation_plans", "installation_units"}:
            self.calls.append(query)
            return deepcopy(self.plan if query.name == "installation_plans" else self.units)
        return super().query(query, **kwargs)


@pytest.mark.parametrize("complete,state", [(False, "PARTIAL"), (True, "READY")])
def test_v2_partial_and_ready_without_lifetime_proof(complete, state):
    reader = PlannedReader(complete)
    service = DashboardService(
        "up-data-intelligence-dev",
        {GRANT.store_id: reader.policy},
        lambda: reader,
        b"synthetic-key-not-a-real-secret-32b",
        installation_v2=True,
    )
    result = service.installation(PRINCIPAL, GRANT)
    data = result["data"]
    assert result["metadata"]["contract_version"] == "installation.v2"
    assert data["overall_state"] == state and data["history_complete"] is False
    assert data["available_window"] and data["installation_plan_id"]
    assert data["progress"]["kind"] == "CHUNKS"
    if complete:
        assert data["progress"]["percent"] == 100 and data["work"]["pending"] == 0
    service._scope(PRINCIPAL, GRANT)
    assert service.policy.history_complete is False
    assert service.policy.report_to == data["available_window"]["to"]
    assert service._response({})["metadata"]["history_complete"] is False


def test_complete_units_without_head_never_unlock():
    reader = PlannedReader(True)
    reader.heads = []
    result = DashboardService(
        "up-data-intelligence-dev",
        {GRANT.store_id: reader.policy},
        lambda: reader,
        b"synthetic-key-not-a-real-secret-32b",
    ).installation(PRINCIPAL, GRANT)
    assert (
        result["data"]["overall_state"] == "BLOCKED" and result["data"]["available_window"] is None
    )


def test_v2_ambiguous_work_not_polled_as_running():
    reader = PlannedReader()
    reader.units[-1]["status"] = "OUTCOME_UNKNOWN"
    reader.plan[0]["status"] = "OUTCOME_UNKNOWN"
    result = DashboardService(
        "up-data-intelligence-dev", {}, lambda: reader, b"synthetic-key-not-a-real-secret-32b"
    ).installation(PRINCIPAL, GRANT)
    assert (
        result["data"]["overall_state"] == "OUTCOME_UNKNOWN"
        and result["data"]["work"]["ambiguous"] == 1
    )


def test_v2_unauthorized_before_any_io():
    def fail():
        raise AssertionError("no IO")

    service = DashboardService(
        "up-data-intelligence-dev",
        {},
        fail,
        b"synthetic-key-not-a-real-secret-32b",
        installation_v2=True,
    )
    with pytest.raises(ReadError):
        service._scope(None, GRANT)


def test_existing_certified_head_survives_adoption_before_any_new_publication():
    reader = PlannedReader()
    for row in reader.units:
        if row["unit_kind"] == "PUBLISH_ANALYTICS":
            row["status"] = "PENDING"
    result = DashboardService(
        "up-data-intelligence-dev", {}, lambda: reader, b"synthetic-key-not-a-real-secret-32b"
    ).installation(PRINCIPAL, GRANT)
    assert result["data"]["overall_state"] == "PARTIAL"
    assert result["data"]["available_window"]["to"] == reader.policy.report_to
