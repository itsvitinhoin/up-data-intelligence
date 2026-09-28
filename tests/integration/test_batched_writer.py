"""Offline BigQuery protocol model + durable SQLite oracle, no cloud calls.

Exercises the real writer and engine; the fake models session staging and atomic
commit, not BigQuery's SQL parser. SQL/session execution still needs DEV validation.
"""

import json
from collections import defaultdict
from types import SimpleNamespace

import httpx
import pytest
from google.api_core.exceptions import BadRequest, Forbidden, ServiceUnavailable

from src.bigquery.repository import BigQueryRepository, SQLiteRepository
from src.bigquery.writer import AtomicWriter, config_for, fragment_batches, request_bytes
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.domain.models import SafeError
from src.ingestion.engine import Engine
from src.utils.data import canonical

BUDGET = 150_000
FILTERS = {"from": "2026-09-25T12:00:00Z", "to": "2026-09-25T13:00:00Z"}


class Job:
    def __init__(self, client, sql, config, job_id):
        self.client, self.sql, self.config, self.job_id = client, sql, config, job_id
        self.state, self.error_result = "RUNNING", None
        self.session_info = None
        self.result_calls = 0

    def result(self, *, job_retry):
        assert job_retry is None
        self.result_calls += 1
        if self.state == "DONE":
            if self.error_result:
                raise BadRequest("synthetic terminal error")
            return []
        try:
            self.client.execute(self)
        except BadRequest:
            self.state, self.error_result = "DONE", {"reason": "invalidQuery"}
            raise
        self.state = "DONE"
        if self.client.lose_ack and self.client.lose_ack in self.sql:
            self.client.lose_ack = None
            raise ServiceUnavailable("synthetic ACK lost after commit")
        return []


class FakeClient:
    def __init__(self, durable):
        self.durable = durable
        self.jobs = {}
        self.sessions = {}
        self.calls = []
        self.fail_chunk = None
        self.chunk = 0
        self.fail_commit_table = None
        self.lose_ack = None
        self.before_commit = None

    def query(self, sql, *, job_config, job_id, location, job_retry):
        assert location == "southamerica-east1" and job_retry is None
        assert request_bytes(sql, job_config) <= BUDGET
        self.calls.append((sql, job_config, job_id))
        if job_id not in self.jobs:
            self.jobs[job_id] = Job(self, sql, job_config, job_id)
        return self.jobs[job_id]

    def get_job(self, job_id, *, location):
        assert location == "southamerica-east1"
        return self.jobs[job_id]

    def execute(self, job):
        sql, cfg = job.sql, job.config
        if cfg.create_session:
            session = f"s{len(self.sessions)}"
            self.sessions[session] = {"parts": {}, "records": []}
            job.session_info = SimpleNamespace(session_id=session)
            return
        session = cfg.connection_properties[0].value if cfg.connection_properties else None
        if sql.startswith("MERGE _SESSION.write_fragments"):
            self.chunk += 1
            if self.chunk == self.fail_chunk:
                self.fail_chunk = None
                raise BadRequest("synthetic staging failure")
            for value in cfg.query_parameters[0].values:
                p = json.loads(value)
                self.sessions[session]["parts"][(p["row"], p["part"])] = p["text"]
            return
        if sql.startswith("CREATE TEMP TABLE write_records"):
            rows = defaultdict(list)
            for (row, _part), text in sorted(self.sessions[session]["parts"].items()):
                rows[row].append(text)
            self.sessions[session]["records"] = ["".join(parts) for parts in rows.values()]
            return
        if sql.startswith("CALL BQ.ABORT_SESSION"):
            self.sessions.pop(session)
            return
        assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
        values = self.sessions[session]["records"] if session else cfg.query_parameters[0].values
        tables = defaultdict(list)
        for v in values:
            item = json.loads(v)
            tables[item["target_table"]].append(item["record"])
        if self.before_commit:
            self.before_commit(tables)
        # Simulates failure inside the SQL transaction: all durable tables roll back.
        if self.fail_commit_table in tables:
            self.fail_commit_table = None
            raise BadRequest("synthetic transaction rollback")
        self.durable.write(tables)


class CloudModel(BigQueryRepository):
    def __init__(self, durable):
        self.project, self.location = "example-project", "southamerica-east1"
        self.client = FakeClient(durable)
        self.durable = durable

    def read(self, *args, **kwargs):
        return self.durable.read(*args, **kwargs)

    def find(self, *args, **kwargs):
        return self.durable.find(*args, **kwargs)

    def iter_find(self, *args, **kwargs):
        return self.durable.iter_find(*args, **kwargs)


def fixture(tmp_path, monkeypatch, count=12, width=900):
    import src.bigquery.repository as module

    monkeypatch.setattr(
        module,
        "AtomicWriter",
        lambda c, loc: AtomicWriter(c, loc, budget=BUDGET, sleep=lambda _: None),
    )
    durable = SQLiteRepository(str(tmp_path / "durable.sqlite"))
    repo = CloudModel(durable)
    rows = [
        {
            "id": i,
            "event_id": f"evt-{i}",
            "event_name": "view_item",
            "occurred_at": "2026-09-25T12:01:00Z",
            "landing_url": "https://example.invalid/?padding=" + '😀\\"' * width,
            "anonymous_id": f"a-{i}",
            "visitor_id": f"v-{i}",
            "session_id": f"s-{i}",
            "user_id": i,
        }
        for i in range(1, count + 1)
    ]
    calls = []

    def handler(req):
        calls.append(dict(req.url.params))
        if "cursor" in req.url.params:
            assert req.url.params["cursor"] == "next-opaque"
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(200, json={"data": rows, "next_cursor": "next-opaque"})

    connector = UpZeroConnector("SYNTHETIC", httpx.MockTransport(handler))
    settings = Settings("A", "Synthetic", "a", "America/Sao_Paulo", "c", FILTERS["from"])
    engine = Engine(settings, repo, connector)
    return engine, repo, calls, rows


def assert_complete(repo, count):
    assert len(repo.read("analytics_events", "A")) == count
    assert len(repo.read("analytics_events_versions", "A")) == count
    assert len(repo.read("touchpoints", "A")) == count
    assert len(repo.read("event_order_links", "A")) == count
    assert len(repo.read("identity_links", "A")) == count * 3
    cp = repo.read("sync_checkpoints", "A")[0]
    assert cp["status"] == "complete" and cp["pending_raw_id"] is None


@pytest.mark.parametrize("count,width", [(1, 0), (40, 500), (1000, 8), (1000, 800)])
def test_page_sizes_cursor_replay_and_all_events(tmp_path, monkeypatch, count, width):
    e, r, calls, rows = fixture(tmp_path, monkeypatch, count, width)
    result = e.run("analytics_facts", FILTERS)
    assert result["records_read"] == count and result["pages"] == 2
    assert calls[0]["limit"] == "1000" and calls[1]["cursor"] == "next-opaque"
    assert_complete(r, count)
    # Same completed plan and RAW replay never duplicate durable facts or history.
    assert e.run("analytics_facts", FILTERS)["run_id"] == result["run_id"]
    e.replay("analytics_facts", result["run_id"])
    assert_complete(r, count)
    assert (
        next(raw for raw in r.read("upzero_analytics_facts", "A") if raw["payload"]["data"])[
            "payload"
        ]["data"]
        == rows
    )


def test_failure_mid_raw_staging_does_not_publish_or_advance(tmp_path, monkeypatch):
    e, r, calls, rows = fixture(tmp_path, monkeypatch, count=30)
    r.client.fail_chunk = 2
    with pytest.raises(SafeError, match="bigquery_write_failed"):
        e.run("analytics_facts", FILTERS)
    assert not r.read("upzero_analytics_facts", "A")
    assert not r.read("analytics_events", "A")
    cp = r.read("sync_checkpoints", "A")[0]
    assert cp["position"] == {} and cp["pending_raw_id"] is None
    result = e.run("analytics_facts", FILTERS)
    assert result["records_read"] == len(rows)
    assert_complete(r, len(rows))
    assert len(calls) == 3  # The uncommitted RAW page is fetched again, then next cursor.


def test_raw_success_core_failure_resumes_saved_raw(tmp_path, monkeypatch):
    e, r, calls, rows = fixture(tmp_path, monkeypatch)
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError, match="bigquery_write_failed"):
        e.run("analytics_facts", FILTERS)
    assert len(r.read("upzero_analytics_facts", "A")) == 1
    assert not r.read("analytics_events", "A")
    assert not r.read("touchpoints", "A")
    cp = r.read("sync_checkpoints", "A")[0]
    assert cp["pending_raw_id"] and cp["position"] == {}
    e.run("analytics_facts", FILTERS)
    assert len(calls) == 2  # Retry uses RAW, only requests the next cursor.
    assert_complete(r, len(rows))


def test_checkpoint_only_moves_in_final_atomic_commit(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    promotions = []

    def check(tables):
        if "analytics_events" in tables:
            cp = r.read("sync_checkpoints", "A")[0]
            assert cp["pending_raw_id"] and cp["position"] == {}
            assert not r.read("analytics_events", "A")
            assert "sync_checkpoints" in tables and "sync_runs" in tables
            promotions.append(True)

    r.client.before_commit = check
    e.run("analytics_facts", FILTERS)
    assert promotions == [True]
    assert_complete(r, len(rows))


@pytest.mark.parametrize("phase", ["MERGE _SESSION.write_fragments", "BEGIN TRANSACTION;"])
def test_lost_ack_reattaches_without_duplicate_commit(tmp_path, monkeypatch, phase):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    r.client.lose_ack = phase
    e.run("analytics_facts", FILTERS)
    assert_complete(r, len(rows))
    assert r.client.lose_ack is None
    assert len(r.client.jobs) == len(r.client.calls)


def test_large_single_raw_record_split_without_loss(tmp_path, monkeypatch):
    _, r, _, _ = fixture(tmp_path, monkeypatch)
    # One RAW row exceeds the OLD 8 MB check. It cannot be split by row count.
    row = {
        "row_key": "raw",
        "store_id": "A",
        "raw_record_id": "raw",
        "payload": {"data": [{"id": i, "body": "x" * 9000} for i in range(1000)]},
    }
    assert (
        len(
            canonical(
                [canonical({"target_table": "upzero_analytics_facts", "record": row})]
            ).encode()
        )
        > 8_000_000
    )
    r.write({"upzero_analytics_facts": [row]})
    assert r.read("upzero_analytics_facts", "A") == [row]
    assert r.client.chunk > 1


def test_fragment_reconstruction_and_wire_budget():
    records = [canonical({"data": '\\"\n😀' * 90000}), canonical({"id": 2})]
    rebuilt = defaultdict(list)
    for batch in fragment_batches(records, BUDGET):
        from src.bigquery.writer import STAGE

        assert request_bytes(STAGE, config_for(batch, parameter="parts", session="s")) <= BUDGET
        for part in batch:
            p = json.loads(part)
            rebuilt[p["row"]].append((p["part"], p["text"]))
    assert ["".join(t for _, t in sorted(parts)) for parts in rebuilt.values()] == records


def test_failure_in_middle_of_core_chunks_retains_raw_checkpoint(tmp_path, monkeypatch):
    e, r, calls, rows = fixture(tmp_path, monkeypatch, count=30)

    def arm_after_raw(tables):
        if "upzero_analytics_facts" in tables:
            r.client.fail_chunk = r.client.chunk + 2
            r.client.before_commit = None

    r.client.before_commit = arm_after_raw
    with pytest.raises(SafeError, match="bigquery_write_failed"):
        e.run("analytics_facts", FILTERS)
    cp = r.read("sync_checkpoints", "A")[0]
    assert cp["pending_raw_id"] and cp["position"] == {}
    assert len(r.read("upzero_analytics_facts", "A")) == 1
    assert not r.read("analytics_events", "A")
    assert not r.read("analytics_events_versions", "A")
    assert not r.read("identity_links", "A")
    e.run("analytics_facts", FILTERS)
    assert len(calls) == 2
    assert_complete(r, len(rows))


def test_configurable_api_limit_and_cursor(tmp_path, monkeypatch):
    from dataclasses import replace

    e, r, calls, _ = fixture(tmp_path, monkeypatch, count=7, width=0)
    e.cfg = replace(e.cfg, page_limit=7)
    e.run("analytics_facts", FILTERS)
    assert [c["limit"] for c in calls] == ["7", "7"]
    assert calls[1]["cursor"] == "next-opaque"
    assert_complete(r, 7)


def test_unresolved_job_preserves_checkpoint_and_does_not_write_failure(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    original_query = r.client.query
    original_get = r.client.get_job
    unresolved_ids = set()

    def query(sql, **kwargs):
        job = original_query(sql, **kwargs)
        if "MERGE `example-project.up_core.analytics_events`" in sql:
            unresolved_ids.add(job.job_id)
            job.result = lambda **_: (_ for _ in ()).throw(ServiceUnavailable("unresolved"))
        return job

    def get(job_id, **kwargs):
        if job_id in unresolved_ids:
            raise ServiceUnavailable("unresolved")
        return original_get(job_id, **kwargs)

    r.client.query, r.client.get_job = query, get
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        e.run("analytics_facts", FILTERS)
    assert r.read("sync_checkpoints", "A")[0]["pending_raw_id"]
    assert r.read("sync_runs", "A")[0]["status"] == "running"
    assert not r.read("analytics_events", "A")
    # No cleanup/abort of a possibly running transaction.
    assert any(s["records"] for s in r.client.sessions.values())


def test_submission_ack_lost_resolves_same_job(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    original_query = r.client.query
    lost = False

    def query(sql, **kwargs):
        nonlocal lost
        job = original_query(sql, **kwargs)
        if not lost:
            lost = True
            job.result(job_retry=None)
            raise ServiceUnavailable("submission ACK lost")
        return job

    r.client.query = query
    e.run("analytics_facts", FILTERS)
    assert_complete(r, len(rows))
    assert len(r.client.jobs) == len(r.client.calls)


def test_cleanup_failure_does_not_undo_committed_data(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    original_query = r.client.query

    def query(sql, **kwargs):
        if sql.startswith("CALL BQ.ABORT_SESSION"):
            raise BadRequest("synthetic cleanup rejection")
        return original_query(sql, **kwargs)

    r.client.query = query
    assert e.run("analytics_facts", FILTERS)["status"] == "completed"
    assert_complete(r, len(rows))


def test_oversized_logical_row_fails_before_any_submission(monkeypatch):
    from unittest.mock import Mock

    import src.bigquery.writer as module

    monkeypatch.setattr(module, "MAX_RECORD_BYTES", 64)
    client = Mock()
    with pytest.raises(SafeError, match="bigquery_record_exceeds_safe_row_limit"):
        AtomicWriter(client, "southamerica-east1").write(["x" * 65], "sql", "sql")
    client.query.assert_not_called()


def test_unclassified_submission_failure_is_not_declared_rolled_back():
    from unittest.mock import Mock

    client = Mock()
    client.query.side_effect = OSError("synthetic socket ambiguity")
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        AtomicWriter(client, "southamerica-east1").execute("SELECT 1", config_for(), "test")


@pytest.mark.parametrize("error", [BadRequest("invalid"), Forbidden("denied")])
def test_definitive_submission_rejection_does_not_retry(error):
    from unittest.mock import Mock

    client = Mock()
    client.query.side_effect = error
    with pytest.raises(SafeError, match="bigquery_write_failed"):
        AtomicWriter(client, "southamerica-east1").execute("SELECT 1", config_for(), "test")
    assert client.query.call_count == 1
    client.get_job.assert_not_called()


def test_stage_metrics_survive_core_failure_and_retry_without_double_count(tmp_path, monkeypatch):
    from src.utils.data import canonical

    e, r, _, rows = fixture(tmp_path, monkeypatch)
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError, match="bigquery_write_failed"):
        e.run("analytics_facts", FILTERS)
    raw = r.read("upzero_analytics_facts", "A")[0]
    failed = r.read("sync_runs", "A")[0]
    assert failed["metrics_version"] == 2
    assert failed["source_records_read"] == failed["records_read"] == len(rows)
    assert failed["raw_pages_written"] == failed["pages"] == 1
    assert failed["raw_payload_bytes"] == len(canonical(raw["payload"]).encode())
    assert failed["source_bytes_read"] == failed["bytes"] == raw["bytes_read"]
    assert failed["core_records_inserted"] == failed["records_written"] == 0
    assert failed["core_records_processed"] == failed["core_pages_processed"] == 0
    assert failed["records_failed"] == 0  # Infrastructure failure is not a rejected fact.
    result = e.run("analytics_facts", FILTERS)
    assert result["source_records_read"] == len(rows)
    assert result["raw_pages_written"] == 2  # Includes the empty terminal API page.
    assert result["core_records_processed"] == result["core_records_inserted"] == len(rows)
    assert result["core_pages_processed"] == 2
    replay = e.replay("analytics_facts", result["run_id"])
    assert replay["source_records_read"] == replay["records_read"] == 0
    assert replay["raw_pages_written"] == replay["pages"] == 0
    assert replay["replay_records_read"] == len(rows)
    assert replay["core_records_processed"] == len(rows)
    assert replay["core_records_inserted"] == replay["records_written"] == 0
    assert r.read("sync_runs", "A", [result["run_id"]])[0] == result


def test_legacy_failed_run_recovers_raw_counts_on_authorized_resume(tmp_path, monkeypatch):
    from src.ingestion.metrics import COUNTERS

    e, r, calls, rows = fixture(tmp_path, monkeypatch)
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError):
        e.run("analytics_facts", FILTERS)
    failed = r.read("sync_runs", "A")[0]
    # Model the audited old version: RAW committed, all old counters still zero.
    for key in (*COUNTERS, "metrics_version"):
        failed.pop(key)
    failed.update(
        records_read=0, records_written=0, records_updated=0, records_failed=0, pages=0, bytes=0
    )
    r.durable.write({"sync_runs": [failed]})
    result = e.run("analytics_facts", FILTERS)
    assert result["run_id"] == failed["run_id"]
    assert result["source_records_read"] == result["records_read"] == len(rows)
    assert result["raw_pages_written"] == 2
    assert result["core_records_inserted"] == len(rows)
    assert len(calls) == 2  # No refetch of the persisted RAW page.
    assert_complete(r, len(rows))


def test_failed_raw_capture_does_not_commit_source_counters(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch, count=30)
    r.client.fail_chunk = 2
    with pytest.raises(SafeError):
        e.run("analytics_facts", FILTERS)
    failed = r.read("sync_runs", "A")[0]
    assert failed["source_records_read"] == 0
    assert failed["raw_pages_written"] == failed["source_bytes_read"] == 0
    assert failed["raw_payload_bytes"] == 0
    assert not r.read("upzero_analytics_facts", "A")
    assert e.run("analytics_facts", FILTERS)["source_records_read"] == len(rows)


def test_infrastructure_failure_after_raw_ack_loss_does_not_duplicate_metrics(
    tmp_path, monkeypatch
):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    r.client.lose_ack = "MERGE `example-project.up_raw.upzero_analytics_facts`"
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError):
        e.run("analytics_facts", FILTERS)
    run = r.read("sync_runs", "A")[0]
    assert run["source_records_read"] == len(rows) and run["raw_pages_written"] == 1
    result = e.run("analytics_facts", FILTERS)
    assert result["source_records_read"] == len(rows) and result["raw_pages_written"] == 2


def test_duplicate_source_entries_are_not_core_inserts(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch, count=1, width=0)
    e.connector = UpZeroConnector(
        "SYNTHETIC",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": rows * 2, "next_cursor": None})
        ),
    )
    result = e.run("analytics_facts", FILTERS)
    assert result["source_records_read"] == result["core_records_processed"] == 2
    assert result["raw_pages_written"] == 1
    assert result["core_records_inserted"] == result["records_written"] == 1


def test_invalid_fact_counts_are_separate_from_raw_and_infrastructure_failure(
    tmp_path, monkeypatch
):
    e, r, _, rows = fixture(tmp_path, monkeypatch, count=1, width=0)
    e.connector = UpZeroConnector(
        "SYNTHETIC",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": rows + [{"id": None}], "next_cursor": None})
        ),
    )
    result = e.run("analytics_facts", FILTERS)
    assert result["source_records_read"] == result["core_records_processed"] == 2
    assert result["raw_pages_written"] == 1
    assert result["core_records_inserted"] == 1
    assert result["core_records_failed"] == result["records_failed"] == 1
    assert result["status"] == "completed_with_errors"
    assert r.read("sync_checkpoints", "A")[0]["status"] == "needs_review"


def test_failed_replay_report_does_not_claim_source_capture(tmp_path, monkeypatch):
    e, r, _, rows = fixture(tmp_path, monkeypatch)
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError):
        e.run("analytics_facts", FILTERS)
    original = r.read("sync_runs", "A")[0]
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError):
        e.replay("analytics_facts", original["run_id"])
    replay = next(x for x in r.read("sync_runs", "A") if x["mode"] == "replay")
    assert replay["status"] == "failed"
    assert replay["source_records_read"] == replay["raw_pages_written"] == 0
    assert replay["core_records_inserted"] == replay["core_records_processed"] == 0
    assert r.read("sync_runs", "A", [original["run_id"]])[0] == original


def test_diagnostic_only_emits_metadata_not_raw_content(tmp_path, monkeypatch):
    from scripts.audit_failed_facts import audit

    e, r, _, rows = fixture(tmp_path, monkeypatch)
    r.client.fail_commit_table = "analytics_events"
    with pytest.raises(SafeError):
        e.run("analytics_facts", FILTERS)
    raw = r.read("upzero_analytics_facts", "A")[0]
    report = audit(raw, r.read("sync_runs", "A")[0], r.read("sync_checkpoints", "A")[0])
    assert report["fact_count"] == len(rows)
    assert report["checkpoint_points_to_raw"]
    assert report["reconstructed_core_batch_rows"]["analytics_events"] == len(rows)
    text = json.dumps(report)
    assert "https://example.invalid" not in text and "next-opaque" not in text
    assert rows[0]["anonymous_id"] not in text
