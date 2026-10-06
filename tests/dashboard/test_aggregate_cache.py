"""Aggregate reuse never substitutes fresh authorization/publication evidence."""

from dataclasses import replace
from decimal import Decimal

import pytest

from src.dashboard.aggregate_cache import AggregateCache, cache_key
from src.dashboard.contracts import Grant, Principal, Publication, ReadError
from src.dashboard.queries import Query
from src.dashboard.service import DashboardService
from tests.dashboard.test_read_api import GRANT, KEY, PRINCIPAL, PROJECT, FakeReader, policy


def test_cache_copies_preserves_null_decimal_and_expires():
    clock = [0.0]
    cache = AggregateCache(clock=lambda: clock[0])
    rows = [{"revenue": Decimal("123.45"), "paid": None}]
    cache.put("key", rows)
    rows[0]["revenue"] = Decimal("0")
    result = cache.get("key")
    assert result == [{"revenue": Decimal("123.45"), "paid": None}]
    assert result is not None
    result[0]["paid"] = 0
    assert cache.get("key")[0]["paid"] is None
    clock[0] = 30
    assert cache.get("key") is None


@pytest.mark.parametrize(
    "field", ["customer_id", "order_id", "email", "phone", "payload", "identity_path"]
)
def test_entity_or_pii_rows_are_never_cached(field):
    cache = AggregateCache()
    cache.put("key", [{"nested": [{field: "private"}]}])
    assert cache.get("key") is None
    assert cache.bytes == 0


def test_cache_is_bounded_by_entries_and_bytes():
    cache = AggregateCache(max_entries=1, max_bytes=100)
    cache.put("one", [{"count": 1}])
    cache.put("two", [{"count": 2}])
    assert cache.get("one") is None
    cache.put("large", [{"aggregate": "x" * 101}])
    assert cache.get("large") is None
    assert cache.get("two") == [{"count": 2}]


def test_key_is_publication_workspace_period_and_contract_specific():
    publication = Publication("s", "p", 1, "a" * 64, "snapshot", "cutoff", "start", "end")
    workspace = ("tenant", "workspace", "s", "B2B")
    query = Query(
        "overview_details",
        "sql",
        {"from": ("DATE", "start"), "snapshot_at": ("TIMESTAMP", "snapshot")},
    )
    original = cache_key(PROJECT, workspace, publication, query, (False, True))
    assert original
    assert original == cache_key(
        PROJECT, workspace, replace(publication, snapshot_at="later"), query, (False, True)
    )
    for changed in (
        replace(publication, generation=2),
        replace(publication, publication_id="b" * 64),
        replace(publication, policy_hash="other"),
    ):
        assert original != cache_key(PROJECT, workspace, changed, query, (False, True))
    for changed in (("other", "workspace", "s", "B2B"), ("tenant", "other", "s", "B2B")):
        assert original != cache_key(PROJECT, changed, publication, query, (False, True))
    assert original != cache_key(
        PROJECT, workspace, publication, replace(query, sql="new SQL"), (False, True)
    )
    assert original != cache_key(
        PROJECT,
        workspace,
        publication,
        replace(query, parameters={"from": ("DATE", "other")}),
        (False, True),
    )
    assert original != cache_key(PROJECT, workspace, publication, query, (True, True))
    assert (
        cache_key(
            PROJECT, ("tenant", "workspace", "other", "B2B"), publication, query, (False, True)
        )
        is None
    )
    assert (
        cache_key(PROJECT, workspace, publication, replace(query, name="customers"), (False, True))
        is None
    )


def test_overview_warm_reuse_still_reads_head_and_rejects_unauthorized_scope():
    p = policy.__wrapped__()
    reader = FakeReader(p)
    cache = AggregateCache()
    service = DashboardService(
        PROJECT, {p.store_id: p}, lambda: reader, KEY, catalog_enabled=True, aggregate_cache=cache
    )
    service.aggregate_workspace = (GRANT.tenant_id, "synthetic-workspace", GRANT.store_id, "B2B")
    period = dict(from_day="2026-09-01", to_day="2026-09-02")
    first = service.overview(PRINCIPAL, GRANT, **period)
    second = service.overview(PRINCIPAL, GRANT, **period)
    assert first == second
    assert sum(q.name == "head" for q in reader.calls) == 2
    assert sum(q.name == "overview_details" for q in reader.calls) == 1
    calls = len(reader.calls)
    denied = Grant("other-tenant", GRANT.store_id, "B2B")
    with pytest.raises(ReadError, match="store_forbidden"):
        service.overview(PRINCIPAL, denied, **period)
    assert len(reader.calls) == calls
    reader.override["head"] = []
    with pytest.raises(ReadError, match="publication_head_missing"):
        service.overview(PRINCIPAL, GRANT, **period)


def test_cache_does_not_cross_trusted_workspaces_or_detail_reads():
    p = policy.__wrapped__()
    reader = FakeReader(p)
    service = DashboardService(
        PROJECT,
        {p.store_id: p},
        lambda: reader,
        KEY,
        catalog_enabled=True,
        aggregate_cache=AggregateCache(),
    )
    for workspace in ("one", "two"):
        service.aggregate_workspace = (GRANT.tenant_id, workspace, GRANT.store_id, "B2B")
        service.overview(PRINCIPAL, GRANT, from_day="2026-09-01", to_day="2026-09-02")
    assert sum(q.name == "overview_details" for q in reader.calls) == 2
    principal = Principal("other-user", "CLIENT_USER", frozenset({GRANT}))
    service.customer(principal, GRANT, "c1")
    service.customer(principal, GRANT, "c1")
    assert sum(q.name == "customer" for q in reader.calls) == 2
