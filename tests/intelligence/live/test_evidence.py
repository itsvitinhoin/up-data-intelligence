"""Synthetic identity evidence, real partition protocol and SQLite spool; no cloud IO."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from itertools import chain
from unittest.mock import patch

import pytest

from src.analytics.cloud.transport import CloudConfig
from src.influence.identity import IdentityContext, MemoryEvidenceIndex, resolve, resolver_evidence
from src.intelligence.live.evidence import EVIDENCE_PREDICATE, FIELDS, EvidenceReader
from src.intelligence.live.materialize import build, build_stream
from src.intelligence.live.publication import Writer
from src.intelligence.live.spool import DiskAnchors, DiskEvidenceIndex, Spool, clock
from src.utils.data import canonical, digest
from tests.change16.test_stack import fixture16
from tests.intelligence.live.test_streaming import (
    HISTORICAL_IDENTITY_HASHES,
    CountingStage,
    EventReader,
    EventTransport,
    historical_identity_fixture,
    large_events,
    records,
)


def evidence_for(fact, **overrides):
    return {
        "store_id": fact["store_id"],
        "source_system": "upzero",
        "link_id": "link-" + fact["fact_id"],
        "source_fact_id": fact["fact_id"],
        "source_version_id": fact["version_id"],
        "left_namespace": "session_id",
        "left_id": fact.get("session_id"),
        "right_namespace": "user_id",
        "right_id": fact.get("user_id"),
        "confidence_type": "DETERMINISTIC",
        "evidence_type": "observed_cooccurrence",
        "occurred_at": fact["occurred_at"],
        "observed_at": "2026-09-29T00:00:00Z",
        **overrides,
    }


def irrelevant_for(fact):
    for i, fields in enumerate(
        [
            {"left_namespace": "anonymous_id", "right_namespace": "visitor_id"},
            {"left_namespace": "visitor_id", "right_namespace": "session_id"},
            {
                "evidence_type": "observed_order_customer",
                "left_namespace": "order_id",
                "right_namespace": "customer_id",
            },
            {"confidence_type": None},
            {"confidence_type": "PROBABILISTIC"},
            {"evidence_type": "unknown"},
        ]
    ):
        yield evidence_for(fact, link_id=f"noise-{i}", **fields)


class EvidenceTransport:
    """Source table on SQLite; bounded BQ-shaped reads, exactly the SQL predicate."""

    def __init__(
        self, spool, policy, rows, *, limit=100000, payload=32 * 1024**2, envelope=128 * 1024**3
    ):
        self.db = spool.db
        self.config = CloudConfig(
            "synthetic-dev", "southamerica-east1", 1024**3, 30, False, limit, payload, envelope
        )
        self.query_count = self.reserved_query_bytes = self.bytes_processed = 0
        self.calls, self.delivered = [], []
        self.total_relevant_bytes = 0
        self.db.execute("""CREATE TABLE source_evidence(link_id TEXT,hash TEXT,day TEXT,at TEXT,
          store_id TEXT,source_system TEXT,confidence_type TEXT,evidence_type TEXT,
          left_namespace TEXT,right_namespace TEXT,source_fact_id TEXT,source_version_id TEXT,data TEXT)""")
        self.db.execute("CREATE INDEX source_evidence_hash ON source_evidence(day,hash)")
        for row in rows:
            lid, at = row.get("link_id"), row.get("occurred_at")
            data = canonical({f: row.get(f) for f in FIELDS})
            self.total_relevant_bytes += len(data.encode()) if resolver_evidence(row) else 0
            self.db.execute(
                "INSERT INTO source_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    lid,
                    hashlib.sha256(lid.encode()).hexdigest() if lid is not None else None,
                    policy.reference().local_date(at) if at else None,
                    clock(at) if at else None,
                    row.get("store_id"),
                    row.get("source_system"),
                    row.get("confidence_type"),
                    row.get("evidence_type"),
                    row.get("left_namespace"),
                    row.get("right_namespace"),
                    row.get("source_fact_id"),
                    row.get("source_version_id"),
                    data,
                ),
            )
        self.db.commit()

    def query(self, sql, params, **kwargs):
        assert EVIDENCE_PREDICATE in sql
        ceiling = self.config.maximum_bytes_billed
        if self.reserved_query_bytes + ceiling > self.config.maximum_total_bytes_billed:
            raise ValueError("analytics_execution_query_budget_exhausted")
        self.reserved_query_bytes += ceiling
        self.query_count += 1
        p = {p.name: p.value for p in params}
        self.calls.append((sql, p, kwargs))
        where = (
            "store_id=? AND source_system='upzero' AND at IS NOT NULL AND at>=? AND at<? AND source_version_id IS NOT NULL AND "
            + EVIDENCE_PREDICATE
        )
        values = [p["store"], clock(p["history_from"]), clock(p["as_of"])]
        if "AND source_fact_id IS NOT NULL" in sql:
            where += " AND source_fact_id IS NOT NULL"
        if "day" in p:
            where += " AND day=?"
            values.append(p["day"])
        if "prefix" in p:
            where += " AND substr(hash,1,?)=?"
            values += [len(p["prefix"]), p["prefix"]]
        counts = "COUNT(*),COUNT(DISTINCT link_id),COALESCE(SUM(link_id IS NULL OR trim(link_id)=''),0),COALESCE(SUM(source_fact_id IS NULL OR trim(source_fact_id)=''),0)"
        if "intelligence_evidence_inventory_total" in sql:
            row = self.db.execute(
                "SELECT " + counts + " FROM source_evidence WHERE " + where, values
            ).fetchone()
            return [
                dict(zip(("n", "distinct_n", "invalid_n", "invalid_source_n"), row, strict=True))
            ], None
        if "intelligence_evidence_inventory */" in sql:
            result = self.db.execute(
                "SELECT day,"
                + counts
                + " FROM source_evidence WHERE "
                + where
                + " GROUP BY day ORDER BY day",
                values,
            )
            return [
                dict(
                    zip(("day", "n", "distinct_n", "invalid_n", "invalid_source_n"), r, strict=True)
                )
                for r in result
            ], None
        if "intelligence_evidence_split" in sql:
            result = self.db.execute(
                "SELECT substr(hash,1,?),COUNT(*) FROM source_evidence WHERE "
                + where
                + " GROUP BY substr(hash,1,?)",
                [p["depth"], *values, p["depth"]],
            )
            return [{"prefix": key, "n": n} for key, n in result], None
        assert "intelligence_evidence_leaf" in sql
        result, size = [], 0
        for (data,) in self.db.execute(
            "SELECT data FROM source_evidence WHERE " + where + " ORDER BY hash,link_id", values
        ):
            if len(result) >= self.config.maximum_rows:
                raise ValueError("analytics_unit_too_large_partition_required")
            size += len(data.encode())
            if size > self.config.maximum_payload_bytes:
                raise ValueError("analytics_unit_payload_too_large_partition_required")
            result.append(json.loads(data))
        self.delivered.append((len(result), size))
        return result, None


def disk_index(spool, p, a):
    return DiskEvidenceIndex(
        spool,
        store_id=p.store_id,
        history_from=p.history_from,
        as_of=p.as_of,
        calculated_at=a["calculated_at"],
    )


def small_stream(p, s, a, *, chunk_rows=100000, payload=32 * 1024**2, reverse=False):
    links = s["identity_links"][::-1] if reverse else s["identity_links"]
    with Spool() as source, Spool() as spool:
        transport = EvidenceTransport(
            source, p, links, limit=chunk_rows, payload=payload, envelope=512 * 1024**3
        )
        index = disk_index(spool, p, a)
        for chunk in EvidenceReader(transport, p, a["source_snapshot_at"]).chunks():
            for row in chunk:
                index.add(row)
        index.seal()
        context = IdentityContext.build(
            s["customers"], s["orders"], index, iter(s["events"]), index=DiskAnchors(spool)
        )
        result = build_stream(
            p,
            {k: v for k, v in s.items() if k not in {"events", "identity_links"}},
            events=[s["events"][::-1] if reverse else s["events"]],
            context=context,
            spool=spool,
            **a,
        )
        return {
            "tables": {k: list(v) for k, v in result["tables"].items()},
            "publication": result["publication"],
        }


@pytest.mark.parametrize("limit,payload", [(1, 32 * 1024**2), (100, 1300)])
def test_partition_rows_payload_exactly_once_fixed_snapshot_and_filter(limit, payload):
    p, s, a = fixture16("synthetic-brand")
    links = [evidence_for(s["events"][0], link_id=f"synthetic-{i}") for i in range(50)]
    irrelevant = list(irrelevant_for(s["events"][0]))
    foreign = evidence_for(s["events"][0], store_id="other-store", link_id="foreign")
    excluded = [
        evidence_for(s["events"][0], link_id="no-version", source_version_id=None),
        evidence_for(s["events"][0], link_id="no-clock", occurred_at=None),
        evidence_for(s["events"][0], link_id="outside", occurred_at="2027-01-01T00:00:00Z"),
    ]
    with Spool() as data:
        t = EvidenceTransport(
            data,
            p,
            chain(reversed(links), irrelevant, [foreign], excluded),
            limit=limit,
            payload=payload,
            envelope=512 * 1024**3,
        )
        result = [r for c in EvidenceReader(t, p, a["source_snapshot_at"]).chunks() for r in c]
        assert len(result) == 50 and {r["link_id"] for r in result} == {r["link_id"] for r in links}
        assert all(n <= limit and b <= payload for n, b in t.delivered)
        for sql, params, _ in t.calls:
            assert (
                "FOR SYSTEM_TIME AS OF @snapshot_at" in sql
                and params["snapshot_at"] == a["source_snapshot_at"]
            )
            assert (
                params["store"] == p.store_id
                and params["history_from"] == p.history_from
                and params["as_of"] == p.as_of
            )
            assert "OFFSET" not in sql and "SELECT *" not in sql
            assert "left_namespace='session_id' AND right_namespace='user_id'" in sql
            assert "left_namespace='fact_id' AND right_namespace='customer_id'" in sql
            if "_leaf" in sql:
                assert (
                    "source_fact_id IS NOT NULL" in sql and "source_version_id IS NOT NULL" in sql
                )
                assert sql.split("SELECT ", 1)[1].split(" FROM", 1)[0] == ",".join(FIELDS)


@pytest.mark.parametrize(
    "field,invalid",
    [
        ("link_id", None),
        ("link_id", ""),
        ("link_id", "  "),
        ("source_fact_id", None),
        ("source_fact_id", ""),
        ("source_fact_id", "  "),
    ],
)
def test_invalid_relevant_evidence_fails_before_any_leaf(field, invalid):
    p, s, a = fixture16("synthetic-brand")
    with Spool() as data:
        t = EvidenceTransport(data, p, [evidence_for(s["events"][0], **{field: invalid})])
        with pytest.raises(ValueError, match="duplicate_or_invalid_identity_evidence"):
            list(EvidenceReader(t, p, a["source_snapshot_at"]).chunks())
        assert not t.delivered


@pytest.mark.parametrize("across_days", [False, True])
def test_duplicate_link_id_is_rejected_globally(across_days):
    p, s, a = fixture16("synthetic-brand")
    first = evidence_for(s["events"][0])
    second = {**first, "occurred_at": "2026-09-04T00:00:00Z"} if across_days else first
    with Spool() as data:
        t = EvidenceTransport(data, p, [first, second])
        with pytest.raises(ValueError, match="duplicate_or_invalid_identity_evidence"):
            list(EvidenceReader(t, p, a["source_snapshot_at"]).chunks())
        assert not t.delivered


@pytest.mark.parametrize("case,expected", HISTORICAL_IDENTITY_HASHES.items())
def test_memory_and_disk_evidence_equal_frozen_resolver(case, expected):
    p, _, a = fixture16("synthetic-brand")
    s = historical_identity_fixture(case)
    links = [
        {**row, "store_id": p.store_id, "source_system": "upzero"} for row in s["identity_links"]
    ]
    memory = IdentityContext.build(
        s["customers"], s["orders"], MemoryEvidenceIndex(links), s["events"]
    )
    assert digest({f["fact_id"]: asdict(memory.resolve_event(f)) for f in s["events"]}) == expected
    with Spool() as spool:
        index = disk_index(spool, p, a)
        for row in links:
            index.add(row)
        index.seal()
        context = IdentityContext.build(
            s["customers"], s["orders"], index, s["events"], index=DiskAnchors(spool)
        )
        assert (
            digest({f["fact_id"]: asdict(context.resolve_event(f)) for f in s["events"]})
            == expected
        )
        assert {f["fact_id"]: context.resolve_event(f) for f in s["events"]} == resolve(
            s["events"], s["orders"], s["customers"], links
        )


@pytest.mark.parametrize("case", ["supported", "registration", "ambiguous"])
def test_stream_all_models_parity_and_irrelevant_links_cannot_change_results_or_hash(case):
    p, base, a = fixture16("synthetic-brand")
    shape = historical_identity_fixture(case)
    shape["items"] = base["items"]
    shape["identity_links"] = [
        {**row, "store_id": p.store_id, "source_system": "upzero"}
        for row in shape["identity_links"]
    ]
    actual = small_stream(p, shape, a, chunk_rows=1)
    expected = build(p, shape, **a)
    assert records(actual) == records(expected)
    noisy = deepcopy(shape)
    noisy["identity_links"] += list(irrelevant_for(shape["events"][0]))
    # Reversing source order / changing chunks leaves both logical result and v3 ID stable.
    repeated = small_stream(p, noisy, a, reverse=True)
    assert repeated == actual
    assert records(build(p, noisy, **a)) == records(expected)
    assert resolve(
        noisy["events"], noisy["orders"], noisy["customers"], noisy["identity_links"]
    ) == resolve(shape["events"], shape["orders"], shape["customers"], shape["identity_links"])


def test_relevant_evidence_changes_source_hash_v3():
    p, s, a = fixture16("synthetic-brand")
    empty = small_stream(p, s, a)
    s["identity_links"] = [evidence_for(s["events"][0])]
    with_evidence = small_stream(p, s, a)
    assert (
        empty["publication"]["source_snapshot_hash"]
        != with_evidence["publication"]["source_snapshot_hash"]
    )


def test_registration_ambiguity_stays_unresolved_for_disk_index():
    p, base, a = fixture16("synthetic-brand")
    s = historical_identity_fixture("registration")
    s["customers"].append({**s["customers"][0], "customer_id": "c2"})
    links = [{**s["identity_links"][0], "store_id": p.store_id, "source_system": "upzero"}]
    links.append({**links[0], "link_id": "second-registration", "right_id": "c2"})
    expected = resolve(s["events"], s["orders"], s["customers"], links)
    with Spool() as spool:
        index = disk_index(spool, p, a)
        for row in links:
            index.add(row)
        index.seal()
        ctx = IdentityContext.build(
            s["customers"], s["orders"], index, s["events"], index=DiskAnchors(spool)
        )
        assert ctx.resolve_event(s["events"][1]).reason == "ambiguous_registration"
        assert {f["fact_id"]: ctx.resolve_event(f) for f in s["events"]} == expected


def test_evidence_query_budget_is_not_bypassed_by_split():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as data:
        t = EvidenceTransport(data, p, [evidence_for(f) for f in s["events"]], envelope=2 * 1024**3)
        with pytest.raises(ValueError, match="analytics_execution_query_budget_exhausted"):
            list(EvidenceReader(t, p, a["source_snapshot_at"]).chunks())
        assert t.query_count == 2 and t.delivered == []


def test_disk_index_sealed_unique_scoped_and_private():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as spool:
        index = disk_index(spool, p, a)
        row = evidence_for(s["events"][0])
        with pytest.raises(ValueError, match="not_sealed"):
            list(index.links_for(row["source_fact_id"]))
        index.add(row)
        with pytest.raises(ValueError, match="duplicate_or_invalid"):
            index.add(row)
        with pytest.raises(ValueError, match="scope_mismatch"):
            index.add({**row, "link_id": "other", "store_id": "other-store"})
        index.seal()
        with pytest.raises(ValueError, match="immutable"):
            index.add(row)
        result = next(index.links_for(row["source_fact_id"]))
        result["right_id"] = "mutated"
        assert next(index.links_for(row["source_fact_id"]))["right_id"] == row["right_id"]
        assert spool.path.stat().st_mode & 0o777 == 0o600


def test_evidence_failure_cannot_initialize_head_and_disk_retry_is_idempotent():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as data, Spool() as spool:
        stage = CountingStage(spool)
        t = EvidenceTransport(
            data, p, [evidence_for(s["events"][0]), evidence_for(s["events"][1])], limit=1
        )
        index = disk_index(spool, p, a)
        with pytest.raises(RuntimeError):
            for row in (
                r for c in EvidenceReader(t, p, a["source_snapshot_at"]).chunks() for r in c
            ):
                index.add(row)
                raise RuntimeError("synthetic-evidence-failure")
        assert stage.head == 0 and stage.receipts == []
    with Spool() as spool:
        index = disk_index(spool, p, a)
        index.seal()
        ctx = IdentityContext.build(
            s["customers"], s["orders"], index, s["events"], index=DiskAnchors(spool)
        )
        result = build_stream(
            p,
            {k: v for k, v in s.items() if k not in {"events", "identity_links"}},
            events=[s["events"]],
            context=ctx,
            spool=spool,
            **a,
        )
        stage = CountingStage(spool, fail="response")
        receipt = Writer(stage).publish(result, 0, initialize_head=True)
        assert Writer(stage).publish(result, 1) == receipt
        assert len(stage.receipts) == 1


def generated_evidence(template, n=150000):
    for event in large_events(template, n):
        yield evidence_for(event)


def test_150000_relevant_evidence_over_32mib_with_150000_events_and_atomic_publication():
    p, s, a = fixture16("synthetic-brand")
    with Spool() as source, Spool() as spool:
        et = EvidenceTransport(
            source, p, chain(generated_evidence(s["events"][0]), irrelevant_for(s["events"][0]))
        )
        assert et.total_relevant_bytes > 32 * 1024**2
        index = disk_index(spool, p, a)
        reader = EvidenceReader(et, p, a["source_snapshot_at"])
        for chunk in reader.chunks():
            for row in chunk:
                index.add(row)
            spool.db.commit()
        index.seal()
        assert reader.rows_processed == 150000
        assert spool.db.execute(
            "SELECT COUNT(*),COUNT(DISTINCT link_id) FROM evidence_links"
        ).fetchone() == (150000, 150000)
        assert all(
            n <= et.config.maximum_rows and b <= et.config.maximum_payload_bytes
            for n, b in et.delivered
        )
        queries_after_evidence = et.query_count
        t = EventTransport(source, p, large_events(s["events"][0]))
        events = EventReader(t, p, a["source_snapshot_at"])
        ctx = IdentityContext.build(
            s["customers"],
            s["orders"],
            index,
            (f for c in events.chunks(anchors=True) for f in c),
            index=DiskAnchors(spool),
        )
        with patch(
            "src.performance.engine.influence_build",
            side_effect=AssertionError("must not replay facts"),
        ):
            artifact = build_stream(
                p,
                {k: v for k, v in s.items() if k not in {"events", "identity_links"}},
                events=events.chunks(),
                context=ctx,
                spool=spool,
                **a,
            )
        assert len(spool.rows("source:events")) == 150000
        assert events.rows_processed == 150000 and et.query_count == queries_after_evidence
        assert len(artifact["tables"]["analytics_customer_timeline"]) > 100000
        # Reader budgets are fixed, and all actual submitted jobs reserve 1 GiB.
        assert et.reserved_query_bytes == et.query_count * 1024**3 <= 128 * 1024**3
        assert t.reserved_query_bytes == t.query_count * 1024**3 <= 128 * 1024**3
        stage = CountingStage(spool)
        Writer(stage).publish(artifact, 0, initialize_head=True)
        assert stage.head == 1 and len(stage.receipts) == 1
        assert (et.query_count + t.query_count + len(stage.calls)) * 1024**3 <= 128 * 1024**3


@pytest.mark.parametrize("bound", ["rows", "bytes"])
def test_non_event_sources_remain_bounded_and_cannot_hide_identity_list(bound):
    p, s, a = fixture16("synthetic-brand")
    snapshot = {k: v for k, v in s.items() if k not in {"events", "identity_links"}}
    if bound == "rows":
        snapshot["customers"] = [snapshot["customers"][0]] * 100001
    else:
        snapshot["customers"] = [
            {**snapshot["customers"][0], "company_name": "synthetic-" + "x" * (33 * 1024**2)}
        ]
    with Spool() as spool:
        index = disk_index(spool, p, a)
        index.seal()
        ctx = IdentityContext.build(s["customers"], s["orders"], index, [])
        with pytest.raises(ValueError, match="bounded_intelligence_non_event_snapshot_required"):
            build_stream(p, snapshot, events=[], context=ctx, spool=spool, **a)
        with pytest.raises(ValueError, match="source_set_incomplete"):
            build_stream(
                p, {**snapshot, "identity_links": []}, events=[], context=ctx, spool=spool, **a
            )


@pytest.mark.parametrize("corrupt", ["inventory", "leaf", "split"])
def test_evidence_inventory_and_partition_counts_fail_closed(corrupt):
    p, s, a = fixture16("synthetic-brand")
    links = [evidence_for(s["events"][0], link_id=f"link-{i}") for i in range(3)]
    with Spool() as data:
        t = EvidenceTransport(data, p, links, limit=1 if corrupt == "split" else 100)
        original = t.query

        def query(sql, params, **kwargs):
            rows, session = original(sql, params, **kwargs)
            marker = {
                "inventory": "intelligence_evidence_inventory */",
                "leaf": "intelligence_evidence_leaf",
                "split": "intelligence_evidence_split",
            }[corrupt]
            return rows[1:] if marker in sql else rows, session

        t.query = query
        with pytest.raises(ValueError, match="incomplete"):
            list(EvidenceReader(t, p, a["source_snapshot_at"]).chunks())


def test_hash_frames_v3_and_identity_contract_version_explicitly():
    p, s, a = fixture16("synthetic-brand")
    snapshot = {k: v for k, v in s.items() if k not in {"events", "identity_links"}}
    with Spool() as spool:
        original = spool.source_hash(snapshot)
        with patch(
            "src.intelligence.live.spool.IDENTITY_EVIDENCE_CONTRACT_VERSION",
            "identity-evidence:v-next-test",
        ):
            assert spool.source_hash(snapshot) != original
        with patch("src.intelligence.live.spool.hashlib.sha256", wraps=hashlib.sha256) as h:
            spool.source_hash(snapshot)
            h.assert_called_once_with(b"source_snapshot_hash:v3\0")


def test_user_evidence_scans_iterator_without_collecting_per_fact_link_list():
    p, s, a = fixture16("synthetic-brand")
    fact = s["events"][0]
    row = evidence_for(fact)

    class EvidenceIterator:
        def __iter__(self):
            return self

        def __next__(self):
            if self.done:
                raise StopIteration
            self.done = True
            return row

        def __length_hint__(self):
            raise AssertionError("must not collect or sort the evidence stream")

        def __init__(self):
            self.done = False

    class Index:
        def links_for(self, fid):
            assert fid == fact["fact_id"]
            return EvidenceIterator()

    ctx = IdentityContext.build(s["customers"], s["orders"], Index(), [])
    assert ctx.user_evidence(fact) == row["link_id"]


def test_full_runtime_evidence_stream_failure_retry_and_no_query_per_fact():
    from dataclasses import make_dataclass

    from src.intelligence.live.runtime import materialize, reporting

    p, base, a = fixture16("synthetic-brand")
    s = historical_identity_fixture("supported")
    s["items"] = base["items"]
    links = [
        {**row, "store_id": p.store_id, "source_system": "upzero"} for row in s["identity_links"]
    ]
    with Spool() as data:
        et = EvidenceTransport(data, p, links, limit=1)
        t = EventTransport(data, p, s["events"])
        stage = CountingStage(data)
        original = t.query
        queries = []
        fail = True

        def route(sql, params, **kwargs):
            queries.append(sql)
            if "/* intelligence_evidence_" in sql:
                if fail and "_leaf" in sql:
                    raise ValueError("synthetic-evidence-read-failure")
                return et.query(sql, params, **kwargs)
            if "/* intelligence_event_" in sql:
                return original(sql, params, **kwargs)
            for table, key in (
                ("customers", "customers"),
                ("orders", "orders"),
                ("order_items", "items"),
            ):
                if f".up_core.{table}`" in sql:
                    return deepcopy(s[key]), None
            for table, key in (
                ("campaigns", "meta_campaigns"),
                ("insights_daily", "meta_insights"),
            ):
                if f".up_core.meta_live_{table}`" in sql:
                    return deepcopy(a[key]), None
            if ".up_ops.sync_checkpoints`" in sql:
                return [
                    {
                        "run_id": "synthetic-run",
                        "filters": {
                            "account": a["account"].snapshot(),
                            "insights": {
                                **reporting(a["account"], p).snapshot(),
                                "level": "campaign",
                            },
                        },
                    }
                ], None
            if ".up_ops.sync_runs`" in sql:
                return [{"status": "completed", "core_records_failed": 0}], None
            if sql.startswith("SELECT generation"):
                return [], None
            return stage.query(sql, params, **kwargs)

        t.query = route
        publication = make_dataclass("SyntheticPublication", list(a["base_publication"]))(
            **a["base_publication"]
        )
        with (
            patch("src.intelligence.live.runtime.BigQueryReadSession") as reader,
            patch("src.intelligence.live.runtime.DashboardService") as service,
            patch(
                "src.influence.identity.MemoryEvidenceIndex",
                side_effect=AssertionError("live must never collect links"),
            ),
        ):
            reader.return_value.reserved_bytes = 0
            service.return_value.publication = publication
            service.return_value.reader.calls = []

            def run():
                return materialize(
                    t,
                    p,
                    a["account"],
                    tenant="synthetic-tenant",
                    snapshot_at=a["source_snapshot_at"],
                    calculated_at=a["calculated_at"],
                    initialize_head=True,
                )

            with pytest.raises(ValueError, match="synthetic-evidence-read-failure"):
                run()
            assert stage.head == 0 and stage.receipts == []
            assert not any("/* intelligence_event_" in sql for sql in queries)
            fail = False
            stage.fail = "response"
            first = run()
            stage.fail = None
            assert run()["publication_id"] == first["publication_id"]
            assert len(stage.receipts) == 1 and stage.head == 1
        assert all(
            "/* intelligence_evidence_" in sql
            for sql in queries
            if ".up_core.identity_links`" in sql
        )
        assert not any("source_fact_id=@" in sql for sql in queries)


@pytest.mark.parametrize("bad", ["memory", "unsealed", "foreign_spool", "foreign_store", "cutoff"])
def test_live_hash_cannot_omit_or_mix_the_context_evidence_index(bad):
    p, s, a = fixture16("synthetic-brand")
    with Spool() as spool, Spool() as foreign:
        index = disk_index(foreign if bad == "foreign_spool" else spool, p, a)
        if bad != "unsealed":
            index.seal()
        if bad == "foreign_store":
            index.store_id = "other-store"
        if bad == "cutoff":
            index.history_from = index.as_of
        ctx = IdentityContext.build(
            s["customers"], s["orders"], MemoryEvidenceIndex([]) if bad == "memory" else index, []
        )
        with pytest.raises(ValueError, match="live_identity_evidence_index_required"):
            build_stream(
                p,
                {k: v for k, v in s.items() if k not in {"events", "identity_links"}},
                events=[],
                context=ctx,
                spool=spool,
                **a,
            )
