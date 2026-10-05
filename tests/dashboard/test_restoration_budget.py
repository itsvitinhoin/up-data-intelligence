"""Exercise the real per-request reservation guard with synthetic V2 evidence."""

from unittest.mock import Mock

import pytest

from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.dashboard.service import DashboardService
from tests.dashboard.test_installation import GRANT, PRINCIPAL
from tests.dashboard.test_read_api import FakeReader
from tests.installation.test_read_model import PlannedReader


@pytest.mark.parametrize("resource,queries", [("retention", 7), ("customer", 6)])
def test_original_drills_fit_unchanged_v2_request_budget(resource, queries):
    planned = PlannedReader(complete=True)
    facts = FakeReader(planned.policy)
    budget = ReadBudget("up-data-intelligence-dev", "southamerica-east1")
    client = Mock()
    transport = BigQueryReadSession(client, budget)
    calls = []

    class Reader:
        def query(self, query, **kwargs):
            calls.append(query)
            rows = (
                planned.query(query, **kwargs)
                if query.name.startswith("installation_") or query.name == "head"
                else facts.query(query, **kwargs)
            )
            job = Mock(total_bytes_processed=1)
            job.result.return_value = rows
            client.query.return_value = job
            return transport.query(query, **kwargs)

    service = DashboardService(
        budget.project,
        {},
        lambda: Reader(),
        b"synthetic-cursor-signing-key-32-bytes",
        installation_v2=True,
    )
    result = (
        service.retention(PRINCIPAL, GRANT)
        if resource == "retention"
        else service.customer(PRINCIPAL, GRANT, "c1")
    )
    assert result["metadata"]["history_complete"] is False
    assert len(calls) == queries
    assert transport.reserved_bytes == queries * budget.maximum_bytes_billed
    assert transport.reserved_bytes <= budget.maximum_total_bytes_billed
    for call in client.query.call_args_list:
        config = call.kwargs["job_config"]
        assert config.maximum_bytes_billed == 1073741824
        assert config.use_query_cache is False
    assert all(q.parameters["store"][1] == GRANT.store_id for q in calls)


@pytest.mark.parametrize("problem", ["negative", "duplicate_day", "too_many_days", "bad_array"])
def test_retention_bundle_rejects_invalid_or_unbounded_projection(problem):
    from src.dashboard.contracts import ReadError
    from src.dashboard.queries import build
    from tests.dashboard.test_read_api import GRANT, KEY, PRINCIPAL, PROJECT

    policy = PlannedReader(complete=True).policy
    reader = FakeReader(policy)
    bundle = reader.query(
        build(PROJECT, "retention_details"),
        request_id="synthetic",
        store_id=GRANT.store_id,
        generation=4,
    )
    if problem == "negative":
        bundle[0]["distribution"][0]["customers"] = -1
    elif problem == "duplicate_day":
        bundle[0]["series"] *= 2
    elif problem == "too_many_days":
        bundle[0]["series"] *= 367
    else:
        bundle[0]["cohorts"] = None
    reader.override["retention_details"] = bundle
    service = DashboardService(PROJECT, {policy.store_id: policy}, lambda: reader, KEY)
    with pytest.raises(ReadError):
        service.retention(PRINCIPAL, GRANT)
