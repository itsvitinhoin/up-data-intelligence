"""Synthetic multi-chunk reads; every BigQuery client is fake."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from test_cloud_adapter import FakeClient

from src.analytics.cloud.facts import FactSpool
from src.analytics.cloud.reader import BigQueryAnalyticsReader, SourceGeneration
from src.analytics.cloud.runner import materialize
from src.analytics.cloud.transport import CloudConfig, Transport
from src.analytics.cloud.writer import BigQueryAnalyticsWriter, Publication
from src.analytics.engine import funnel_rows
from src.analytics.materialization import plan_changes
from src.analytics.parity import load_fixture
from src.analytics.serialization import encode_tables
from src.utils.data import timestamp


def setup(count, days=1, **limits):
    p, s = load_fixture(Path("tests/fixtures/analytics_readiness/synthetic.json"))
    start = datetime.fromisoformat("2026-03-01T04:00:00+00:00")
    names = ["product_view", "add_to_cart", "checkout_started", "purchase"]
    s.events[:] = [
        {
            "store_id": p.store_id,
            "source_system": "upzero",
            "fact_id": f"synthetic-{i:08}",
            "session_id": "one-session",
            "event_name": names[i % 4],
            "occurred_at": (start + timedelta(days=i % days, seconds=i % 3600)).isoformat(),
        }
        for i in range(count)
    ]
    f = FakeClient()
    f.source = dict(
        zip(
            ("orders", "customers", "order_items", "analytics_events"),
            (s.orders, s.customers, s.items, s.events),
            strict=True,
        )
    )
    t = Transport(
        f, CloudConfig("synthetic-project", "southamerica-east1", 1000000, 30, False, **limits)
    )
    pub = Publication(
        p, SourceGeneration(p.as_of, "a" * 64, True), plan_changes(p, s, None, None), 0, True
    )
    return p, s, f, t, pub


@pytest.mark.parametrize("days", [1, 2])
def test_over_100k_complete_sessions_one_atomic_publication(days):
    p, s, f, t, pub = setup(100003, days)
    reader = BigQueryAnalyticsReader(t, p)
    receipt = materialize(reader, BigQueryAnalyticsWriter(t), pub)
    expected = encode_tables({"analytics_funnel_daily": funnel_rows(p.reference(), s.events)})[
        "analytics_funnel_daily"
    ]
    assert f.rows["analytics_funnel_daily"] == expected
    assert (
        sum(
            r[k]
            for r in expected
            for k in ("product_views", "add_to_cart", "checkout_started", "purchase")
        )
        == 100003
    )
    assert reader.source_rows_read == 100003 and reader.largest_chunk_rows <= 100000
    assert reader.source_chunks > 1
    queries = [(sql, kw) for sql, kw in f.calls if "/* analytics_facts_" in sql]
    snapshots = {
        timestamp(str(p.value))
        for _, kw in queries
        for p in kw["job_config"].query_parameters
        if p.name == "snapshot_at"
    }
    assert snapshots == {timestamp(pub.source.snapshot_at)}
    assert all(
        "FOR SYSTEM_TIME AS OF @snapshot_at" in sql
        and "store_id=@store" in sql
        and "source_system='upzero'" in sql
        for sql, _ in queries
    )
    assert all("OFFSET" not in sql and "LIMIT" not in sql for sql, _ in queries)
    assert sum(sql.startswith("BEGIN TRANSACTION") for sql, _ in f.calls) == 1
    assert f.generation == 1 and len(f.receipts) == 1
    reads = reader.source_rows_read
    assert materialize(reader, BigQueryAnalyticsWriter(t), pub) == receipt
    assert reader.source_rows_read == reads and f.generation == 1 and len(f.receipts) == 1


def test_intermediate_failure_never_stages_or_publishes_and_retry():
    p, _, f, t, pub = setup(300, maximum_rows=128)
    f.failure = "fact_leaf_2"
    with pytest.raises(RuntimeError, match="intermediate"):
        materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    assert not any(f.rows.values()) and not f.receipts and f.generation == 0
    assert not any(sql.startswith("CREATE TEMP TABLE stage_") for sql, _ in f.calls)
    f.failure = None
    materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    assert f.generation == 1 and len(f.receipts) == 1


def test_small_snapshot_equivalence_orphans_ties_and_incomplete_flags():
    p, s, f, t, pub = setup(80, maximum_rows=32)
    # All events share timestamps; fact_id tiebreak and whitespace behavior matter.
    for i, row in enumerate(s.events):
        row["occurred_at"] = "2026-03-01T04:00:00Z"
        row["session_id"] = [None, "  ", " session ", "other"][i % 4]
    p = replace(p, facts_complete=False)
    pub = replace(pub, policy=p)
    materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    expected = encode_tables({"analytics_funnel_daily": funnel_rows(p.reference(), s.events)})[
        "analytics_funnel_daily"
    ]
    assert f.rows["analytics_funnel_daily"] == expected
    assert all(r["session_conversion_rate"] is None for r in expected)


def test_byte_limit_subdivision_and_store_policy_isolation():
    p, s, f, t, pub = setup(100, maximum_payload_bytes=4096)
    s.events.append({**s.events[0], "store_id": "foreign-store", "fact_id": "foreign-fact"})
    reader = BigQueryAnalyticsReader(t, p)
    materialize(reader, BigQueryAnalyticsWriter(t), pub)
    assert reader.source_rows_read == 100 and reader.source_chunks > 1
    assert all(
        r["store_id"] == p.store_id and r["policy_hash"] == p.policy_hash
        for r in f.rows["analytics_funnel_daily"]
    )


def test_execution_reservation_budget_blocks_before_next_submission():
    p, _, f, t, pub = setup(100, maximum_total_bytes_billed=1000000)
    with pytest.raises(ValueError, match="execution_query_budget_exhausted"):
        materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    assert len(f.calls) == 1 and not f.receipts and f.generation == 0
    assert t.reserved_query_bytes == 1000000


def test_spool_duplicate_across_days_incomplete_and_wrong_store(tmp_path):
    p, s, *_ = setup(5)
    spool = FactSpool(tmp_path / "facts.sqlite", p.reference())
    try:
        spool.add("2026-03-01", s.events)
        with pytest.raises(ValueError, match="incomplete"):
            spool.finish_day("2026-03-01", 6)
        next_day = {**s.events[0], "occurred_at": "2026-03-02T04:00:00Z"}
        with pytest.raises(ValueError, match="duplicate_fact"):
            spool.add("2026-03-02", [next_day])
        with pytest.raises(ValueError, match="source_store"):
            spool.add("2026-03-02", [{**next_day, "store_id": "other"}])
        with pytest.raises(ValueError, match="day_mismatch"):
            spool.add("2026-03-02", [s.events[1]])
        assert spool.rows == 5
    finally:
        spool.close()


def test_duplicate_fact_inventory_stops_before_publication():
    p, s, f, t, pub = setup(5)
    s.events.append(deepcopy(s.events[0]))
    with pytest.raises(ValueError, match="duplicate_or_invalid"):
        materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    assert not f.receipts and f.generation == 0


def test_spool_capacity_is_fail_closed(tmp_path):
    p, s, *_ = setup(2)
    spool = FactSpool(tmp_path / "facts.sqlite", p.reference(), maximum_bytes=1)
    try:
        with pytest.raises(ValueError, match="spool_budget"):
            spool.add("2026-03-01", s.events)
        assert spool.rows == 0
    finally:
        spool.close()


@pytest.mark.parametrize("table", ["customers", "orders", "order_items"])
def test_commerce_inputs_keep_technical_cap(table):
    p, s, f, t, pub = setup(0, maximum_rows=1)
    # Distinct fake source rows ensure this is a capacity failure, not deduplication.
    rows = f.source[table]
    f.source[table] = rows + deepcopy(rows)
    with pytest.raises(ValueError, match="unit_too_large"):
        BigQueryAnalyticsReader(t, p).read(table, pub.source, full_refresh=True)


def test_failure_after_closed_day_still_publishes_nothing():
    p, _, f, t, pub = setup(20, days=2)
    f.failure = "fact_leaf_2"
    with pytest.raises(RuntimeError, match="intermediate"):
        materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    assert not f.receipts and f.generation == 0 and not any(f.rows.values())
    assert t.bytes_processed is None  # failed query is not claimed as zero cost


def test_missing_leaf_row_aborts_before_any_publication(monkeypatch):
    p, _, f, t, pub = setup(20)
    query = t.query

    def incomplete(sql, parameters, **kwargs):
        rows, session = query(sql, parameters, **kwargs)
        if "/* analytics_facts_leaf */" in sql:
            rows.pop()
        return rows, session

    monkeypatch.setattr(t, "query", incomplete)
    with pytest.raises(ValueError, match="chunk_incomplete"):
        materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    assert not f.receipts and f.generation == 0 and not any(f.rows.values())
