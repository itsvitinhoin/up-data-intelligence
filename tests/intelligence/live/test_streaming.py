"""Synthetic chunk/identity/model parity and disk-backed large publication, no cloud IO."""

import hashlib
import json
import os
import re
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import Mock, patch

import pytest
from google.cloud import bigquery

from src.analytics.cloud.transport import CloudConfig
from src.bigquery.writer import REQUEST_BYTES, request_bytes
from src.domain.models import SafeError
from src.influence.engine import InfluenceScope
from src.influence.identity import IdentityContext, resolve
from src.influence.materialization import materialize as reference_influence
from src.intelligence.live.events import FIELDS, EventReader
from src.intelligence.live.influence import InfluenceStream
from src.intelligence.live.materialize import build, build_stream
from src.intelligence.live.publication import Writer, commit_sql
from src.intelligence.live.schema import PUBLICATION
from src.intelligence.live.spool import DiskAnchors, Rows, Spool, clock
from src.performance.engine import build as reference_performance
from src.performance.engine import build_from_influence
from src.utils.data import canonical, digest
from tests.change16.test_stack import fixture16


class EventTransport:
    """Partition-aware SQLite BigQuery fake; responses honor real unit/cost bounds."""

    def __init__(
        self,
        spool,
        policy,
        events,
        *,
        rows=100000,
        payload=32 * 1024 * 1024,
        envelope=128 * 1024**3,
    ):
        self.config = CloudConfig(
            "synthetic-dev", "southamerica-east1", 1024**3, 30, False, rows, payload, envelope
        )
        self.db = spool.db
        self.db.execute(
            "CREATE TABLE source_events(fid TEXT,hash TEXT,day TEXT,at TEXT,store TEXT,source TEXT,anchor BOOL,data TEXT)"
        )
        self.db.execute("CREATE INDEX source_hash ON source_events(day,hash)")
        self.calls = []
        self.bytes_processed = 0
        self.reserved_query_bytes = self.query_count = self.rows_read = self.duration_ms = 0
        self.client = Mock()
        self.delivered = []
        self.total_source_bytes = 0
        for fact in events:
            fid = fact.get("fact_id")
            data = canonical(fact)
            self.total_source_bytes += len(data.encode())
            self.db.execute(
                "INSERT INTO source_events VALUES(?,?,?,?,?,?,?,?)",
                (
                    fid,
                    hashlib.sha256(fid.encode()).hexdigest() if fid is not None else None,
                    policy.reference().local_date(fact["occurred_at"]),
                    clock(fact["occurred_at"]),
                    fact.get("store_id"),
                    fact.get("source_system"),
                    fact.get("order_id") is not None
                    or fact.get("event_name") == "register_approved",
                    data,
                ),
            )
        self.db.commit()

    def query(self, sql, params, **kwargs):
        ceiling = self.config.maximum_bytes_billed
        if self.reserved_query_bytes + ceiling > self.config.maximum_total_bytes_billed:
            raise ValueError("analytics_execution_query_budget_exhausted")
        self.reserved_query_bytes += ceiling
        self.query_count += 1
        self.calls.append((sql, {p.name: p.value for p in params}, kwargs))
        p = self.calls[-1][1]
        where = "store=? AND source=? AND at>=? AND at<?"
        values = [p["store"], "upzero", clock(p["history_from"]), clock(p["as_of"])]
        if "order_id IS NOT NULL OR event_name='register_approved'" in sql:
            where += " AND anchor=1"
        if "day" in p:
            where += " AND day=?"
            values.append(p["day"])
        if "prefix" in p:
            where += " AND substr(hash,1,?)=?"
            values.extend([len(p["prefix"]), p["prefix"]])
        if "intelligence_event_inventory_total" in sql:
            n, d, i = self.db.execute(
                'SELECT COUNT(*),COUNT(DISTINCT fid),COALESCE(SUM(fid IS NULL OR trim(fid)=""),0) FROM source_events WHERE '
                + where,
                values,
            ).fetchone()
            return [{"n": n, "distinct_n": d, "invalid_n": i}], None
        if "intelligence_event_inventory */" in sql:
            return [
                dict(zip(("day", "n", "distinct_n", "invalid_n"), r, strict=True))
                for r in self.db.execute(
                    'SELECT day,COUNT(*),COUNT(DISTINCT fid),COALESCE(SUM(fid IS NULL OR trim(fid)=""),0) FROM source_events WHERE '
                    + where
                    + " GROUP BY day ORDER BY day",
                    values,
                )
            ], None
        if "intelligence_event_split" in sql:
            result = self.db.execute(
                "SELECT substr(hash,1,?),COUNT(*) FROM source_events WHERE "
                + where
                + " GROUP BY substr(hash,1,?)",
                [p["depth"], *values, p["depth"]],
            )
            return [{"prefix": prefix, "n": n} for prefix, n in result], None
        assert "intelligence_event_leaf" in sql
        result = []
        size = 0
        for (data,) in self.db.execute(
            "SELECT data FROM source_events WHERE " + where + " ORDER BY hash,fid", values
        ):
            if len(result) >= self.config.maximum_rows:
                raise ValueError("analytics_unit_too_large_partition_required")
            size += len(data.encode())
            if size > self.config.maximum_payload_bytes:
                raise ValueError("analytics_unit_payload_too_large_partition_required")
            result.append(json.loads(data))
        self.delivered.append((len(result), size))
        return result, None


class CountingStage:
    """No full staged timeline list: keys/counts on disk; receipts only in RAM."""

    def __init__(self, spool, fail=None, rows=100000):
        self.db = spool.db
        self.db.execute("CREATE TABLE staged(name TEXT,key TEXT,PRIMARY KEY(name,key))")
        self.config = CloudConfig(
            "synthetic-dev",
            "southamerica-east1",
            1024**3,
            30,
            False,
            rows,
            32 * 1024 * 1024,
            128 * 1024**3,
        )
        self.counts = {}
        self.receipts = []
        self.head = 0
        self.fail = fail
        self.calls = []
        self.inserts = []
        self.staged_receipt = None

    def query(self, sql, params, **kwargs):
        self.calls.append((sql, kwargs))
        p = {p.name: p.value for p in params}
        if sql.startswith("SELECT *"):
            return [r for r in self.receipts if r["publication_id"] == p["publication"]], None
        if kwargs.get("create_session"):
            self.db.execute("DELETE FROM staged")
            self.counts = {}
            return [], "synthetic-session"
        if sql.startswith("CALL"):
            return [], None
        if sql.startswith("INSERT INTO _SESSION"):
            name = re.search(r"stage_(\w+)", sql)[1]
            rows = json.loads(p["rows"])
            actual = request_bytes(sql, bigquery.QueryJobConfig(query_parameters=params))
            assert actual <= REQUEST_BYTES
            assert len(rows) <= self.config.maximum_rows
            self.inserts.append((name, len(rows), actual))
            for row in rows:
                self.db.execute("INSERT INTO staged VALUES(?,?)", (name, row["row_key"]))
                self.counts[name] = self.counts.get(name, 0) + 1
            if name == PUBLICATION:
                assert len(rows) == 1
                self.staged_receipt = rows[0]
            if self.fail == name:
                raise ValueError("synthetic_stage_failure")
            return [], None
        assert sql.startswith("BEGIN")
        assert self.head == p["expected"]
        assert all(self.counts.get(name, 0) == n for name, n in json.loads(p["counts"]).items())
        if self.fail == "commit":
            raise TimeoutError("synthetic_commit_unknown")
        self.receipts.append(self.staged_receipt)
        self.head = p["generation"]
        if self.fail == "response":
            raise TimeoutError("synthetic_response_lost")
        return [], None


def materialize_offline(p, s, a, spool, *, chunks=None):
    context = IdentityContext.build(
        s["customers"], s["orders"], s["identity_links"], s["events"], index=DiskAnchors(spool)
    )
    return build_stream(
        p,
        {k: v for k, v in s.items() if k != "events"},
        events=chunks if chunks is not None else [s["events"]],
        context=context,
        spool=spool,
        **a,
    )


def records(artifact):
    return {
        name: sorted(rows, key=lambda r: r["row_key"])
        for name, rows in artifact["tables"].items()
        if name != PUBLICATION
    }


@pytest.mark.parametrize("size", [1, 2, 100000])
def test_small_artifact_full_parity_and_hash_independent_of_chunks_and_order(size):
    p, s, a = fixture16("synthetic-brand")
    old = build(p, s, **a)
    events = list(reversed(s["events"]))
    with Spool() as spool:
        new = materialize_offline(
            p, s, a, spool, chunks=[events[i : i + size] for i in range(0, len(events), size)]
        )
        assert records(new) == records(old)
        assert all(isinstance(v, Rows) for k, v in new["tables"].items() if k != PUBLICATION)
        signature = new["publication"]["publication_id"], new["publication"]["source_snapshot_hash"]
    with Spool() as spool:
        repeat = materialize_offline(p, s, a, spool, chunks=[s["events"]])
        assert signature == (
            repeat["publication"]["publication_id"],
            repeat["publication"]["source_snapshot_hash"],
        )


@pytest.mark.parametrize("scope", list(InfluenceScope))
def test_three_scope_influence_parity(scope):
    p, s, a = fixture16("synthetic-brand")
    s["orders"].append({**s["orders"][0], "order_id": "o2", "created_at": "2026-09-08T12:00:00Z"})
    s["events"].append(
        {
            **s["events"][0],
            "fact_id": "repeat-touch",
            "order_id": "o1",
            "occurred_at": "2026-09-06T12:00:00Z",
        }
    )
    source = {k: v for k, v in s.items() if k != "items"}
    expected = reference_influence(
        p.reference(), source, calculated_at=a["calculated_at"], influence_scope=scope
    )
    with Spool() as spool:
        context = IdentityContext.build(
            s["customers"], s["orders"], s["identity_links"], s["events"], index=DiskAnchors(spool)
        )
        stream = InfluenceStream(
            spool, p.reference(), s["customers"], s["orders"], context, a["calculated_at"]
        )
        for event in reversed(s["events"]):
            stream.consume(event)
        actual = stream.finish("a" * 64)[scope.value]
        for name, rows in expected["tables"].items():
            assert sorted(actual["tables"][name], key=lambda r: r["row_key"]) == sorted(
                rows, key=lambda r: r["row_key"]
            )


def test_identity_context_disk_equals_reference_without_invented_identity():
    p, s, a = fixture16("synthetic-brand")
    s["events"].append(
        {
            **s["events"][0],
            "fact_id": "no-evidence",
            "order_id": None,
            "session_id": None,
            "visitor_id": None,
            "user_id": s["customers"][0]["customer_id"],
        }
    )
    expected = resolve(s["events"], s["orders"], s["customers"], s["identity_links"])
    with Spool() as spool:
        ctx = IdentityContext.build(
            s["customers"],
            s["orders"],
            s["identity_links"],
            (
                f
                for f in s["events"]
                if f.get("order_id") is not None or f["event_name"] == "register_approved"
            ),
            index=DiskAnchors(spool),
        )
        assert {f["fact_id"]: ctx.resolve_event(f) for f in s["events"]} == expected
        assert ctx.resolve_event(s["events"][-1]).customer_id is None
        with pytest.raises(ValueError, match="immutable"):
            ctx.index.add({})


def test_performance_precomputed_parity_and_no_resolver_call():
    p, s, a = fixture16("synthetic-brand")
    source = {k: v for k, v in s.items() if k != "items"}
    args = {k: a[k] for k in ("meta_insights", "meta_campaigns", "coverage", "calculated_at")}
    expected = reference_performance(p.reference(), source, accounts=(a["account"],), **args)
    pre = reference_influence(p.reference(), source, calculated_at=a["calculated_at"])
    with patch(
        "src.performance.engine.influence_build",
        side_effect=AssertionError("must not resolve again"),
    ):
        actual = build_from_influence(
            p.reference(),
            {**source, "events": []},
            influence=pre["tables"],
            source_snapshot_hash="b" * 64,
            accounts=(a["account"],),
            **args,
        )

    def semantic(rows):
        return [{k: v for k, v in r.items() if k != "generation"} for r in rows]

    assert {n: semantic(r) for n, r in actual["tables"].items()} == {
        n: semantic(r) for n, r in expected["tables"].items()
    }


@pytest.mark.parametrize("rows,payload", [(1, 32000000), (100, 2000)])
def test_reader_partitions_and_replays_independent_of_payload_and_rows(rows, payload):
    p, s, a = fixture16("synthetic-brand")
    source = [
        {**s["events"][0], "fact_id": f"synthetic-{i}", "utm_campaign": "x" * 300}
        for i in range(50)
    ]
    with Spool() as data:
        t = EventTransport(data, p, source, rows=rows, payload=payload, envelope=512 * 1024**3)
        reader = EventReader(t, p, a["source_snapshot_at"])
        output = [r for chunk in reader.chunks() for r in chunk]
        assert {r["fact_id"] for r in output} == {r["fact_id"] for r in source}
        assert len(output) == len(source)
        assert all(n <= rows and b <= payload for n, b in t.delivered)
        assert all(
            "FOR SYSTEM_TIME AS OF @snapshot_at" in sql
            and params["snapshot_at"] == a["source_snapshot_at"]
            for sql, params, _ in t.calls
        )
        assert all(
            params["store"] == p.store_id
            and params["history_from"] == p.history_from
            and params["as_of"] == p.as_of
            for _, params, _ in t.calls
        )
        assert all(field in t.calls[-1][0] for field in FIELDS)
        assert not any("OFFSET" in sql for sql, _, _ in t.calls)


@pytest.mark.parametrize("key", [None, "", "   "])
def test_reader_blocks_missing_or_blank_fact_id(key):
    p, s, a = fixture16("synthetic-brand")
    with Spool() as data:
        t = EventTransport(data, p, [{**s["events"][0], "fact_id": key}])
        with pytest.raises(ValueError, match="duplicate_or_invalid_fact_key"):
            list(EventReader(t, p, a["source_snapshot_at"]).chunks())
        assert not t.delivered


@pytest.mark.parametrize("different_day", [False, True])
def test_duplicate_fact_is_blocked_globally_before_yield(different_day):
    p, s, a = fixture16("synthetic-brand")
    second = deepcopy(s["events"][0])
    if different_day:
        second["occurred_at"] = "2026-09-06T12:00:00Z"
    with Spool() as data:
        t = EventTransport(data, p, [s["events"][0], second])
        with pytest.raises(ValueError, match="duplicate_or_invalid_fact_key"):
            list(EventReader(t, p, a["source_snapshot_at"]).chunks())
        assert not t.delivered


def test_reader_anchor_filter_and_store_isolation():
    p, s, a = fixture16("synthetic-brand")
    source = s["events"] + [
        {**s["events"][0], "store_id": "other-store", "fact_id": "foreign"},
        {**s["events"][0], "fact_id": "not-anchor", "order_id": None, "event_name": "page_view"},
    ]
    with Spool() as data:
        t = EventTransport(data, p, source)
        actual = [
            f
            for chunk in EventReader(t, p, a["source_snapshot_at"]).chunks(anchors=True)
            for f in chunk
        ]
        assert {r["fact_id"] for r in actual} == {
            f["fact_id"]
            for f in s["events"]
            if f.get("order_id") is not None or f["event_name"] == "register_approved"
        }


def test_reader_propagates_execution_budget_failure_without_split_workaround():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as data:
        t = EventTransport(data, p, s["events"], envelope=2 * 1024**3)
        with pytest.raises(ValueError, match="analytics_execution_query_budget_exhausted"):
            list(EventReader(t, p, a["source_snapshot_at"]).chunks())
        assert t.query_count == 2 and not t.delivered


@pytest.mark.parametrize("fail", ["analytics_customer_timeline", "commit", "response", None])
def test_streamed_writer_failure_retry_receipt_reconciliation(fail):
    p, s, a = fixture16("synthetic-brand")
    with Spool() as spool:
        artifact = materialize_offline(p, s, a, spool)
        stage = CountingStage(spool, fail)
        if fail in ("analytics_customer_timeline", "commit"):
            with pytest.raises((ValueError, SafeError)):
                Writer(stage).publish(artifact, 0, initialize_head=True)
            assert stage.head == 0 and stage.receipts == []
            stage.fail = None
        receipt = Writer(stage).publish(artifact, 0, initialize_head=True)
        assert stage.head == 1 and len(stage.receipts) == 1
        assert Writer(stage).publish(artifact, 1) == receipt and len(stage.receipts) == 1
        commit = commit_sql("synthetic-dev")
        assert "@counts" in commit and "intelligence_stage_count_mismatch" in commit
        assert (
            commit.index("BEGIN TRANSACTION")
            < commit.index("IF @initialize_head")
            < commit.index("COMMIT TRANSACTION")
        )


def test_spool_private_and_removed_after_exception():
    with pytest.raises(ValueError):
        with Spool() as spool:
            path = spool.path
            assert os.stat(path).st_mode & 0o777 == 0o600
            assert os.stat(path.parent).st_mode & 0o777 == 0o700
            raise ValueError("synthetic-failure")
    assert not path.exists() and not path.parent.exists()


def large_events(template, n=150000):
    for i in range(n):
        yield {
            **template,
            "fact_id": f"synthetic-large-{i:06d}",
            "event_name": "product_view",
            "order_id": "o1",
            "session_id": f"session-{i % 500:04d}",
            "product_id": f"product-{i % 100:03d}",
            "utm_campaign": "synthetic-" + ("x" * 300),
            "meta_campaign_id": None,
            "meta_adset_id": None,
            "meta_ad_id": None,
            "fbclid": None,
            "fbc": None,
            "gclid": None,
        }


def test_150000_events_over_32mib_and_timeline_staged_without_global_list():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as data, Spool() as spool:
        t = EventTransport(data, p, large_events(s["events"][0]))
        assert t.total_source_bytes > 32 * 1024 * 1024
        reader = EventReader(t, p, a["source_snapshot_at"])
        context = IdentityContext.build(
            s["customers"],
            s["orders"],
            s["identity_links"],
            (f for chunk in reader.chunks(anchors=True) for f in chunk),
            index=DiskAnchors(spool),
        )
        new = build_stream(
            p,
            {k: v for k, v in s.items() if k != "events"},
            events=reader.chunks(),
            context=context,
            spool=spool,
            **a,
        )
        assert len(spool.rows("source:events")) == 150000
        assert reader.rows_processed == 150000  # Main-pass counters; anchors also bounded.
        assert all(
            n <= t.config.maximum_rows and b <= t.config.maximum_payload_bytes
            for n, b in t.delivered
        )
        timeline = new["tables"]["analytics_customer_timeline"]
        assert isinstance(timeline, Rows) and len(timeline) > 100000
        journeys = list(new["tables"]["analytics_customer_journey_summary"])
        assert sum(r["total_events"] for r in journeys) == 150000
        assert journeys[0]["total_sessions"] == 500 and journeys[0]["total_products_viewed"] == 100
        stage = CountingStage(spool)
        Writer(stage).publish(new, 0)
        assert stage.counts["analytics_customer_timeline"] == len(timeline)
        assert stage.head == 1 and len(stage.receipts) == 1
        assert len([c for c in stage.inserts if c[0] == "analytics_customer_timeline"]) > 1


def historical_identity_fixture(case):
    _, s, _ = fixture16("synthetic-brand")
    if case == "registration":
        f = s["events"][1]
        f.update(event_name="register_approved", order_id=None)
        s["identity_links"] = [
            {
                "link_id": "synthetic-registration",
                "source_fact_id": f["fact_id"],
                "source_version_id": f["version_id"],
                "confidence_type": "DETERMINISTIC",
                "evidence_type": "observed_registration_customer",
                "left_namespace": "fact_id",
                "left_id": f["fact_id"],
                "right_namespace": "customer_id",
                "right_id": "c1",
                "occurred_at": f["occurred_at"],
            }
        ]
    elif case == "supported":
        for f in s["events"]:
            f.update(session_id="synthetic-session-" + f["fact_id"], visitor_id=None)
            s["identity_links"].append(
                {
                    "link_id": "link-" + f["fact_id"],
                    "source_fact_id": f["fact_id"],
                    "source_version_id": f["version_id"],
                    "confidence_type": "DETERMINISTIC",
                    "evidence_type": "observed_cooccurrence",
                    "left_namespace": "session_id",
                    "left_id": f["session_id"],
                    "right_namespace": "user_id",
                    "right_id": f["user_id"],
                    "occurred_at": f["occurred_at"],
                }
            )
    elif case == "visitor":
        s["events"][0]["session_id"] = None
    elif case == "ambiguous":
        s["customers"].append({**s["customers"][0], "customer_id": "c2"})
        s["orders"].append({**s["orders"][0], "customer_id": "c2", "order_id": "o2"})
        s["events"].append({**s["events"][1], "fact_id": "f3", "order_id": "o2"})
    elif case == "unknown_order":
        s["events"][0]["order_id"] = "missing"
    elif case == "no_evidence":
        s["events"][0].update(session_id=None, visitor_id=None, user_id="c1")
    return s


HISTORICAL_IDENTITY_HASHES = {
    "direct": "498a48753db558c7036eee65dd0140463a6516458211ade8f8a9aac88b2bbd66",
    "visitor": "5943a325324f8b9a8ea3be23072ca5164c0a2f999757a368859c6ca338cdeb9d",
    "registration": "a29674c3b9297c37ede2e171ba1443855f1f0236c74f8dfea2b3573f6ae1880a",
    "supported": "c00a2254d6ae3ce5a832c68a1a48f456f0b86419776ccb7f6b660400de309de0",
    "ambiguous": "ab7705aa71f88397f42e823d30e58f545078575a661a2bca73307c36119642c8",
    "unknown_order": "4c62e97b71be82f66e99b200ccf30d7fecf7e74f316453f993f7f237b1aa35be",
    "no_evidence": "3ae481d647723c44ea1c2a5b288cbe77dd6f4b6233587aa9d5949167ebfee803",
}


@pytest.mark.parametrize("case,expected", HISTORICAL_IDENTITY_HASHES.items())
def test_identity_matches_frozen_base_resolver(case, expected):
    # Golden digests produced by the independent resolver at ef5459b, synthetic inputs only.
    s = historical_identity_fixture(case)
    with Spool() as spool:
        ctx = IdentityContext.build(
            s["customers"], s["orders"], s["identity_links"], s["events"], index=DiskAnchors(spool)
        )
        actual = {f["fact_id"]: asdict(ctx.resolve_event(f)) for f in s["events"]}
        assert digest(actual) == expected


def test_unresolved_paid_is_preserved_and_coverage_stays_partial():
    p, s, a = fixture16("synthetic-brand")
    s["events"].pop()
    with Spool() as spool:
        new = materialize_offline(p, s, a, spool)
        assert records(new) == records(build(p, s, **a))
        paid = list(new["tables"]["analytics_paid_touchpoints"])
        assert (
            len(paid) == 1 and paid[0]["identity_path"] == [] and paid[0]["evidence_type"] is None
        )
        assert new["publication"]["history_complete"] is False


@pytest.mark.parametrize("bad", ["customers", "events", "store", "duplicate", "cutoff"])
def test_stream_blocks_invalid_sources_before_publication(bad):
    p, s, a = fixture16("synthetic-brand")
    if bad in {"customers", "events"}:
        s[bad][0]["observed_at"] = "2027-01-01T00:00:00Z"
    elif bad == "store":
        s["events"][0]["store_id"] = "other-store"
    elif bad == "duplicate":
        s["events"].append(deepcopy(s["events"][0]))
    elif bad == "cutoff":
        s["events"][0]["occurred_at"] = "2025-01-01T00:00:00Z"
    with Spool() as spool, pytest.raises(ValueError):
        materialize_offline(p, s, a, spool)


def test_writer_accepts_one_shot_receipt_and_rejects_count_mismatch():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as spool:
        artifact = materialize_offline(p, s, a, spool)
        artifact["tables"][PUBLICATION] = iter(artifact["tables"][PUBLICATION])
        stage = CountingStage(spool)
        assert (
            Writer(stage).publish(artifact, 0)["publication_id"]
            == artifact["publication"]["publication_id"]
        )
    with Spool() as spool:
        artifact = materialize_offline(p, s, a, spool)
        name = "analytics_customer_timeline"
        artifact["tables"][name] = iter([])  # one-shot iterator must also validate actual count
        stage = CountingStage(spool)
        with pytest.raises(ValueError, match="row_counts_mismatch"):
            Writer(stage).publish(artifact, 0, initialize_head=True)
        assert stage.head == 0 and stage.receipts == []


def test_context_order_link_rows_are_sealed_and_input_mutation_cannot_change_identity():
    s = historical_identity_fixture("registration")
    with Spool() as spool:
        ctx = IdentityContext.build(
            s["customers"], s["orders"], s["identity_links"], s["events"], index=DiskAnchors(spool)
        )
        before = ctx.resolve_event(s["events"][0])
        with pytest.raises(TypeError):
            ctx.orders["o1"]["customer_id"] = "other"
        with pytest.raises(TypeError):
            ctx.links["f2"][0]["right_id"] = "other"
        s["orders"][0]["customer_id"] = "other"
        s["identity_links"][0]["right_id"] = "other"
        assert ctx.resolve_event(s["events"][0]) == before


def test_generation_is_physical_and_does_not_change_logical_stream_publication():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as spool:
        first = materialize_offline(p, s, a, spool)["publication"]["publication_id"]
    with Spool() as spool:
        second = materialize_offline(p, s, {**a, "generation": 2}, spool)
        assert second["publication"]["publication_id"] == first
        assert all(r["generation"] == 2 for rows in second["tables"].values() for r in rows)


@pytest.mark.parametrize("broken", ["inventory", "leaf", "split"])
def test_reader_blocks_missing_inventory_leaf_or_split_rows(broken):
    p, s, a = fixture16("synthetic-brand")
    with Spool() as spool:
        t = EventTransport(
            spool,
            p,
            [s["events"][0], {**s["events"][0], "fact_id": "synthetic-extra"}],
            rows=1 if broken == "split" else 100,
        )
        original = t.query

        def corrupt(sql, params, **kwargs):
            rows, session = original(sql, params, **kwargs)
            marker = {
                "inventory": "intelligence_event_inventory */",
                "leaf": "intelligence_event_leaf",
                "split": "intelligence_event_split",
            }[broken]
            return (rows[1:] if marker in sql else rows), session

        t.query = corrupt
        with pytest.raises(ValueError, match="incomplete"):
            list(EventReader(t, p, a["source_snapshot_at"]).chunks())


def test_runtime_routes_events_through_partitions_and_initializes_head_only_at_commit():
    from dataclasses import make_dataclass

    from src.intelligence.live.runtime import materialize, reporting

    p, s, a = fixture16("synthetic-brand")
    account = a["account"]
    with Spool() as data:
        t = EventTransport(data, p, s["events"])
        stage = CountingStage(data)
        original = t.query
        reads = []

        def route(sql, params, **kwargs):
            reads.append(sql)
            if "/* intelligence_event_" in sql:
                return original(sql, params, **kwargs)
            for table, source in (
                ("customers", "customers"),
                ("orders", "orders"),
                ("order_items", "items"),
                ("identity_links", "identity_links"),
            ):
                if f".up_core.{table}`" in sql:
                    return deepcopy(s[source]), None
            for table, source in (
                ("campaigns", "meta_campaigns"),
                ("insights_daily", "meta_insights"),
            ):
                if f".up_core.meta_live_{table}`" in sql:
                    return deepcopy(a[source]), None
            if ".up_ops.sync_checkpoints`" in sql:
                return [
                    {
                        "filters": {
                            "account": account.snapshot(),
                            "insights": {**reporting(account, p).snapshot(), "level": "campaign"},
                        },
                        "run_id": "synthetic-run",
                    }
                ], None
            if ".up_ops.sync_runs`" in sql:
                return [{"status": "completed", "core_records_failed": 0}], None
            if sql.startswith("SELECT generation"):
                return [], None
            return stage.query(sql, params, **kwargs)

        t.query = route
        base = make_dataclass("SyntheticPublication", list(a["base_publication"]))(
            **a["base_publication"]
        )
        with (
            patch("src.intelligence.live.runtime.BigQueryReadSession") as reader,
            patch("src.intelligence.live.runtime.DashboardService") as service,
        ):
            reader.return_value.reserved_bytes = 0
            service.return_value.publication = base
            service.return_value.reader.calls = []
            receipt = materialize(
                t,
                p,
                account,
                tenant="synthetic-tenant",
                snapshot_at=a["source_snapshot_at"],
                calculated_at=a["calculated_at"],
                initialize_head=True,
            )
        assert receipt["status"] == "completed" and stage.head == 1
        assert all(
            "/* intelligence_event_" in sql for sql in reads if ".up_core.analytics_events`" in sql
        )
        assert not any(sql.startswith("INSERT INTO `") for sql in reads)
        assert any("order_id IS NOT NULL OR event_name='register_approved'" in sql for sql in reads)
