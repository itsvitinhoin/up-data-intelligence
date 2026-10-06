"""Synthetic operational evidence; no source/API calls."""

import pytest

from src.dashboard.contracts import ReadError
from src.dashboard.leads import operational_counts
from src.dashboard.queries import build


def row(generated=2, approved=3, invalid_identity=0, conflicts=0):
    return dict(
        generated=generated,
        approved=approved,
        invalid_identity=invalid_identity,
        conflicts=conflicts,
    )


def test_approval_backlog_is_operational_not_cohort():
    result = operational_counts(row(), facts_complete=True)
    assert result["leads_generated"] == 2
    assert result["leads_approved"] == 3
    assert result["lead_qualification_rate"] == "150"
    assert result["approved_conversion_rate"] is None
    assert result["lead_coverage"]["operational_counts"] is True
    assert result["lead_coverage"]["conversion"] is False


def test_real_zero_is_distinct_from_uncovered_and_zero_denominator():
    assert operational_counts(row(0, 0), facts_complete=True)["leads_generated"] == 0
    assert operational_counts(row(0, 0), facts_complete=True)["lead_qualification_rate"] is None
    for r, covered in [(row(), False), (row(invalid_identity=1), True)]:
        assert operational_counts(r, facts_complete=covered)["leads_generated"] is None


@pytest.mark.parametrize(
    "bad", [row(conflicts=1), row(generated=-1), row(approved=None), row(generated=1.5)]
)
def test_invalid_or_conflicting_identity_fails_closed(bad):
    with pytest.raises(ReadError):
        operational_counts(bad, facts_complete=True)


def test_query_pins_period_snapshot_store_and_event_identity():
    q = build(
        "up-data-intelligence-dev",
        "operational_leads",
        store="injection",
        from_day="2026-09-01",
        to_day="2026-09-02",
        timezone="America/Sao_Paulo",
        as_of="2026-09-02T03:00Z",
    )
    assert "injection" not in q.sql
    assert "GROUP BY fact_id" in q.sql
    assert "store_id=@store" in q.sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at" in q.sql
    assert "DATE(occurred_at,@timezone)>=@from" in q.sql
    assert "DATE(occurred_at,@timezone)<@to" in q.sql
    assert "user_id" not in q.sql
    assert "order_matches!=1 OR customer_id IS NULL" in q.sql
    assert "p.order_at>=i.approved_at" in q.sql
    assert "p.order_at<TIMESTAMP(@to,@timezone)" in q.sql
    assert "p.policy_hash=@policy" in q.sql


def test_operational_leads_reach_overview_acquisition_with_generation_pinning():
    from src.dashboard.service import DashboardService
    from tests.dashboard.test_read_api import GRANT, KEY, PRINCIPAL, PROJECT, FakeReader, policy

    p = policy.__wrapped__()
    reader = FakeReader(p)
    reader.override["operational_leads"] = [row()]
    reader.override["acquisition_first"] = [
        dict(invalid_first_orders=0, customers=1, orders=1, requested="100", fulfilled="80")
    ]
    service = DashboardService(PROJECT, {p.store_id: p}, lambda: reader, KEY, catalog_enabled=True)
    for name in ("overview", "acquisition"):
        result = getattr(service, name)(
            PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02"
        )
        assert result["data"]["lead_qualification_rate"] == "150"
        assert result["data"]["leads_generated"] == 2
        assert result["data"]["approved_converted"] is None
        q = next(
            c
            for c in reversed(reader.calls)
            if c.name == ("overview_details" if name == "overview" else "operational_leads")
        )
        assert q.parameters["snapshot_at"][1] == service.publication.snapshot_at
        assert q.parameters["as_of"][1] == service.publication.as_of
        assert q.parameters["store"][1] == GRANT.store_id


def test_conversion_requires_complete_deterministic_registration_identity():
    evidence = {**row(), "unresolved_approved": 0, "converted": 1}
    result = operational_counts(evidence, facts_complete=True)
    assert result["approved_converted"] == 1
    assert result["approved_conversion_rate"].startswith("33.333")
    assert result["lead_coverage"]["conversion"] is True
    assert (
        operational_counts({**evidence, "unresolved_approved": 1}, facts_complete=True)[
            "approved_converted"
        ]
        is None
    )
    assert operational_counts(evidence, facts_complete=False)["approved_conversion_rate"] is None
