import json
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


@pytest.mark.parametrize(
    "projection,changes",
    [
        ("InstallationSource", {"state": "PENDING"}),
        ("InstallationSource", {"configured": False}),
        ("InstallationSource", {"active": False}),
        ("InstallationResource", {"state": "RUNNING"}),
        ("InstallationResource", {"state": "PENDING"}),
        ("InstallationResource", {"pending_raw": True}),
    ],
)
def test_v2_complete_plan_rejects_incomplete_operational_projection(
    monkeypatch, projection, changes
):
    import src.dashboard.installation as installation

    reader = PlannedReader(True)
    constructor = getattr(installation, projection)
    # Contradictory projection, including COMPLETE+pending RAW; valid publication/work.
    monkeypatch.setattr(
        installation,
        projection,
        lambda *args, **kwargs: replace(constructor(*args, **kwargs), **changes),
    )
    result = DashboardService(
        "up-data-intelligence-dev",
        {},
        lambda: reader,
        b"synthetic-key-not-a-real-secret-32b",
        installation_v2=True,
    ).installation(PRINCIPAL, GRANT)
    data = result["data"]
    assert data["installation_plan_status"] == "COMPLETE"
    assert (
        data["work"]["pending"]
        == data["work"]["running"]
        == data["work"]["blocked"]
        == data["work"]["ambiguous"]
        == 0
    )
    assert data["available_window"] is not None and data["facts_complete"] is True
    assert data["overall_state"] != "READY"
    projected = data["sources"] if projection == "InstallationSource" else data["resources"]
    assert all(all(row[key] == value for key, value in changes.items()) for row in projected)


@pytest.mark.parametrize("sync_enabled", [True, None])
def test_v2_ready_requires_sync_explicitly_disabled(sync_enabled):
    reader = PlannedReader(True)
    reader.registry[0]["sync_enabled"] = sync_enabled
    if sync_enabled is None:
        from src.domain.models import SafeError

        with pytest.raises(SafeError, match="registry_boolean_required"):
            DashboardService(
                "up-data-intelligence-dev",
                {},
                lambda: reader,
                b"synthetic-key-not-a-real-secret-32b",
                installation_v2=True,
            ).installation(PRINCIPAL, GRANT)
        return
    data = DashboardService(
        "up-data-intelligence-dev",
        {},
        lambda: reader,
        b"synthetic-key-not-a-real-secret-32b",
        installation_v2=True,
    ).installation(PRINCIPAL, GRANT)["data"]
    assert data["overall_state"] != "READY"


def test_v2_active_recurring_remains_ready_with_extended_certified_window():
    reader = PlannedReader(True)
    reader.registry[0].update(
        status="ACTIVE", sync_enabled=True, facts_coverage_to="2026-10-04T03:00:00Z"
    )
    reader.registry[0]["snapshot_at"] = "2026-10-04T07:00:00Z"
    reader.policy = replace(reader.policy, report_to="2026-10-04", as_of="2026-10-04T03:00:00Z")
    reader.heads = [head(reader.policy)]
    service = DashboardService(
        "up-data-intelligence-dev",
        {},
        lambda: reader,
        b"synthetic-key-not-a-real-secret-32b",
        installation_v2=True,
    )
    result = service.installation(PRINCIPAL, GRANT)["data"]
    assert result["overall_state"] == "READY"
    assert result["progress"]["percent"] == 100
    assert result["available_window"]["to"] == "2026-10-04"
    assert result["history_complete"] is False
    service._scope(PRINCIPAL, GRANT)
    assert service.policy.report_from == reader.policy.report_from
    assert service.policy.report_to == "2026-10-04"


def consolidated_payload(reader):
    flags = dict(
        history_complete=reader.policy.history_complete,
        currency=reader.policy.currency,
        reporting_timezone=reader.policy.reporting_timezone,
    )
    heads = [
        {
            **h,
            "store_observed_rows": 1,
            "facts_observed_rows": 1,
            "store_flags": [json.dumps(flags)],
            "facts_flags": [json.dumps({"facts_complete": reader.policy.facts_complete})],
        }
        for h in deepcopy(reader.heads)
    ]
    return dict(
        snapshot_at=NOW,
        registry=deepcopy(reader.registry),
        plans=deepcopy(reader.plan),
        units=deepcopy(reader.units),
        heads=heads,
    )


def test_consolidated_context_matches_existing_policy_without_caching_authorization():
    from src.dashboard.installation_queries import build_installation
    from src.installation.publication import resolve_policy

    original = PlannedReader(True)
    expected = resolve_policy(original, "up-data-intelligence-dev", GRANT, "synthetic")

    class ConsolidatedReader(PlannedReader):
        def query(self, query, **kwargs):
            if query.name == "installation_context":
                self.calls.append(query)
                return [consolidated_payload(self)]
            return super().query(query, **kwargs)

    reader = ConsolidatedReader(True)
    actual = resolve_policy(
        reader, "up-data-intelligence-dev", GRANT, "synthetic", consolidated=True
    )
    assert actual == expected
    assert [q.name for q in reader.calls] == ["installation_context"]
    query = build_installation(
        "up-data-intelligence-dev", "installation_context", GRANT.store_id, None
    )
    assert query.sql.count("FOR SYSTEM_TIME AS OF CURRENT_TIMESTAMP()") == 7
    assert "LIMIT 2" in query.sql and "LIMIT 10001" in query.sql
    assert GRANT.store_id not in query.sql
    assert query.parameters == {"store": ("STRING", GRANT.store_id)}


@pytest.mark.parametrize("field,value", [("registry", []), ("plans", []), ("units", "invalid")])
def test_consolidated_context_fail_closed(field, value):
    from src.installation.publication import resolve_policy

    class BrokenReader(PlannedReader):
        def query(self, query, **kwargs):
            assert query.name == "installation_context"
            data = consolidated_payload(self)
            data[field] = value
            return [data]

    if field == "plans":
        assert (
            resolve_policy(
                BrokenReader(True),
                "up-data-intelligence-dev",
                GRANT,
                "synthetic",
                consolidated=True,
            )
            is None
        )
    else:
        with pytest.raises(ReadError):
            resolve_policy(
                BrokenReader(True),
                "up-data-intelligence-dev",
                GRANT,
                "synthetic",
                consolidated=True,
            )


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "foreign", "receipt", "mixed_flags", "no_facts", "unknown_facts"],
)
def test_consolidated_publication_evidence_fail_closed(change):
    from src.installation.publication import resolve_policy

    class BrokenPublication(PlannedReader):
        def query(self, query, **kwargs):
            assert query.name == "installation_context"
            data = consolidated_payload(self)
            h = data["heads"][0]
            if change == "missing":
                data["heads"] = []
            elif change == "duplicate":
                data["heads"].append(deepcopy(h))
            elif change == "foreign":
                h["store_id"] = "other-store"
            elif change == "receipt":
                h["receipt_generation"] += 1
            elif change == "mixed_flags":
                h["store_flags"].append('{"history_complete":true}')
            elif change == "no_facts":
                h["facts_observed_rows"] = 0
            elif change == "unknown_facts":
                h["facts_flags"] = ['{"facts_complete":null}']
            return [data]

    with pytest.raises(ReadError):
        resolve_policy(
            BrokenPublication(True),
            "up-data-intelligence-dev",
            GRANT,
            "synthetic",
            consolidated=True,
        )
