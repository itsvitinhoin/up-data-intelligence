"""Synthetic OPS only. Execute the actual proof SQL and transaction in SQLite.

BigQuery ASSERT is interpreted locally; COUNTIF uses a local aggregate; time travel
is removed. This proves invariants/CAS offline, not the live BigQuery dialect.
"""

import copy
import json
import logging
import re
import sqlite3
from contextlib import contextmanager, nullcontext
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.analytics.cloud.transport import CloudConfig, Transport, scalar
from src.bigquery.catalog import TABLES
from src.config.settings import Settings
from src.control_plane import recovery_cli
from src.control_plane.model import StoreConfig, Window
from src.control_plane.preflight import Prerequisites
from src.control_plane.recovery import CheckpointRecovery, RecoveryProof
from src.control_plane.recovery_queries import mutation_query, proof_query
from src.control_plane.recovery_repository import BigQueryRecovery
from src.control_plane.registry import Admin
from src.control_plane.worker import Actions
from src.domain.models import SafeError
from src.ingestion.checkpoints import TERMINAL_CHECKPOINT_STATUSES, checkpoint_pending
from src.ingestion.planning import incremental
from src.security.lease import cloud_lease
from src.utils.data import digest

STORE = "synthetic-store"
ORIGINAL = str(UUID(int=1))
REPLAY = str(UUID(int=101))
ADMIN = Admin("synthetic-operator", "ADMIN_UP")
WINDOW = Window(
    "2026-09-01",
    "2026-09-02",
    "2026-09-02T03:00:00Z",
    "2026-09-03T00:00:00Z",
    "2026-09-03T00:00:00Z",
)


class CountIf:
    def __init__(self):
        self.count = 0

    def step(self, value):
        self.count += int(bool(value))

    def finalize(self):
        return self.count


class OpsTransport(Transport):
    def __init__(self):
        super().__init__(Mock(), CloudConfig("synthetic-dev", "southamerica-east1", 10, 30, False))
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.create_aggregate("COUNTIF", 1, CountIf)
        for table in ("sync_checkpoints", "sync_runs"):
            columns = ",".join(
                f'"{k}" {"INTEGER" if t == "INT64" else "TEXT"}'
                for k, t in TABLES[table].fields.items()
            )
            self.db.execute(f"CREATE TABLE {table} ({columns})")
        self.calls = []
        self.before_write = None
        self.after_commit = None
        self.before_update = None
        self.rowcount_override = None

    def insert(self, table, row):
        self.db.execute(
            f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
            [
                json.dumps(value) if isinstance(value, (dict, list)) else value
                for value in row.values()
            ],
        )

    @staticmethod
    def adapt(sql):
        return (
            re.sub(r"`synthetic-dev\.up_ops\.(\w+)`", r"\1", sql)
            .replace(" FOR SYSTEM_TIME AS OF @snapshot", "")
            .replace("CURRENT_TIMESTAMP()", "CURRENT_TIMESTAMP")
        )

    def query(self, sql, parameters, **kwargs):
        values = {p.name: p.value for p in parameters}
        self.calls.append((sql, values))
        if not sql.startswith("BEGIN TRANSACTION;"):
            return [dict(r) for r in self.db.execute(self.adapt(sql), values)], None
        if self.before_write:
            self.before_write(self)
        affected = None
        try:
            self.db.execute("DROP TABLE IF EXISTS temp.recovery_proof")
            for statement in sql.split(";"):
                statement = statement.strip()
                if not statement:
                    continue
                if statement.startswith("ASSERT "):
                    condition = statement.removeprefix("ASSERT ").rsplit(" AS ", 1)[0]
                    if condition == "@@row_count=1":
                        valid = (
                            self.rowcount_override
                            if self.rowcount_override is not None
                            else affected
                        ) == 1
                    else:
                        valid = bool(
                            self.db.execute("SELECT " + self.adapt(condition), values).fetchone()[0]
                        )
                    if not valid:
                        raise BadRequest("synthetic ASSERT failure; never expose SQL or values")
                else:
                    if statement.startswith("UPDATE ") and self.before_update:
                        self.before_update(self)
                    cursor = self.db.execute(self.adapt(statement), values)
                    if statement.startswith("UPDATE "):
                        affected = cursor.rowcount
                    if statement == "COMMIT TRANSACTION" and self.after_commit:
                        self.after_commit()
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return [], None

    def all(self, table):
        return [dict(r) for r in self.db.execute(f"SELECT * FROM {table} ORDER BY row_key")]


def rows(index=1, count=32):
    original, replay = str(UUID(int=index)), str(UUID(int=index + 100))
    checkpoint = {
        "row_key": f"synthetic-plan-{index}",
        "store_id": STORE,
        "run_id": original,
        "resource": "customers",
        "connection_id": "synthetic-connection",
        "plan_key": f"synthetic-plan-{index}",
        "mode": "backfill",
        "status": "needs_review",
        "pending_raw_id": None,
        "filters": json.dumps({"start_date": f"2026-09-{index:02d}"}),
        "position": json.dumps({"cursor": "synthetic"}),
        "completed_to": "2026-09-05T00:00:00Z",
        "high_id": "100",
        "updated_at": "2026-09-05T00:00:00Z",
    }
    run = {
        "row_key": original,
        "store_id": STORE,
        "run_id": original,
        "source": "upzero",
        "resource": "customers",
        "mode": "backfill",
        "plan_key": checkpoint["plan_key"],
        "status": "completed_with_errors",
        "metrics_version": 2,
        "core_records_failed": 1,
        "core_records_processed": count,
        "finished_at": "2026-09-05T00:00:00Z",
    }
    replay_run = {
        **run,
        "row_key": replay,
        "run_id": replay,
        "mode": "replay",
        "plan_key": original,
        "status": "completed",
        "core_records_failed": 0,
        "source_records_read": 0,
        "raw_pages_written": 0,
        "replay_records_read": count,
        "core_records_inserted": 1,
        "core_records_updated": count - 1,
        "finished_at": "2026-09-30T00:00:00Z",
    }
    return checkpoint, run, replay_run


@pytest.fixture
def ops():
    transport = OpsTransport()
    cp, original, replay = rows()
    transport.insert("sync_checkpoints", cp)
    transport.insert("sync_runs", original)
    transport.insert("sync_runs", replay)
    yield transport
    transport.db.close()


def service(ops, lease=lambda _: nullcontext()):
    return CheckpointRecovery(BigQueryRecovery(ops), lease)


def test_valid_unique_metadata_proof_is_immutable(ops):
    proof = BigQueryRecovery(ops).proof(STORE, ORIGINAL, REPLAY)
    assert proof == RecoveryProof(STORE, "synthetic-plan-1", "customers", ORIGINAL, REPLAY)
    with pytest.raises(FrozenInstanceError):
        proof.resource = "orders"
    sql, parameters = ops.calls[0]
    assert "payload" not in sql and "filters" not in sql
    assert parameters == {"store": STORE, "original": ORIGINAL}


@pytest.mark.parametrize(
    "table,selector,field,value",
    [
        ("sync_checkpoints", ORIGINAL, "status", "complete"),
        ("sync_checkpoints", ORIGINAL, "status", "running"),
        ("sync_checkpoints", ORIGINAL, "status", "extracted"),
        ("sync_checkpoints", ORIGINAL, "pending_raw_id", "synthetic-pending"),
        ("sync_checkpoints", ORIGINAL, "pending_raw_id", ""),
        ("sync_checkpoints", ORIGINAL, "resource", "unsupported"),
        ("sync_checkpoints", ORIGINAL, "store_id", "other-store"),
        ("sync_runs", ORIGINAL, "source", "meta"),
        ("sync_runs", ORIGINAL, "resource", "orders"),
        ("sync_runs", ORIGINAL, "mode", "incremental"),
        ("sync_runs", ORIGINAL, "store_id", "other-store"),
        ("sync_runs", ORIGINAL, "status", "running"),
        ("sync_runs", ORIGINAL, "status", "failed"),
        ("sync_runs", ORIGINAL, "status", "completed"),
        ("sync_runs", ORIGINAL, "core_records_failed", 0),
        ("sync_runs", ORIGINAL, "core_records_failed", None),
        ("sync_runs", ORIGINAL, "core_records_processed", None),
        ("sync_runs", ORIGINAL, "core_records_processed", 31),
        ("sync_runs", ORIGINAL, "metrics_version", 3),
        ("sync_runs", REPLAY, "source", "meta"),
        ("sync_runs", REPLAY, "resource", "orders"),
        ("sync_runs", REPLAY, "store_id", "other-store"),
        ("sync_runs", REPLAY, "mode", "incremental"),
        ("sync_runs", REPLAY, "plan_key", "other-original"),
        ("sync_runs", REPLAY, "status", "failed"),
        ("sync_runs", REPLAY, "status", "running"),
        ("sync_runs", REPLAY, "core_records_failed", 1),
        ("sync_runs", REPLAY, "source_records_read", 1),
        ("sync_runs", REPLAY, "raw_pages_written", 1),
        ("sync_runs", REPLAY, "replay_records_read", 0),
        ("sync_runs", REPLAY, "replay_records_read", -1),
        ("sync_runs", REPLAY, "replay_records_read", None),
        ("sync_runs", REPLAY, "core_records_processed", 31),
        ("sync_runs", REPLAY, "source_records_read", None),
        ("sync_runs", REPLAY, "raw_pages_written", None),
        ("sync_runs", REPLAY, "core_records_failed", None),
    ],
)
def test_proof_rejects_invalid_or_missing_evidence(ops, table, selector, field, value):
    ops.db.execute(f"UPDATE {table} SET {field}=? WHERE run_id=?", (value, selector))
    before = ops.all("sync_checkpoints")
    with pytest.raises(SafeError):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert ops.all("sync_checkpoints") == before
    assert all(not sql.startswith("BEGIN") for sql, _ in ops.calls)


@pytest.mark.parametrize(
    "table,selector",
    [("sync_checkpoints", ORIGINAL), ("sync_runs", ORIGINAL), ("sync_runs", REPLAY)],
)
@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_and_duplicate_rows_fail_closed(ops, table, selector, duplicate):
    if duplicate:
        ops.db.execute(f"INSERT INTO {table} SELECT * FROM {table} WHERE run_id=?", (selector,))
    else:
        ops.db.execute(f"DELETE FROM {table} WHERE run_id=?", (selector,))
    with pytest.raises(SafeError):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)


@pytest.mark.parametrize("legacy_version", [None, 1])
def test_legacy_original_does_not_invent_v2_count_but_requires_all_replay_counters(
    ops, legacy_version
):
    ops.db.execute(
        "UPDATE sync_runs SET metrics_version=?,core_records_processed=NULL WHERE run_id=?",
        (legacy_version, ORIGINAL),
    )
    assert service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY).replay_run_id == REPLAY


def test_two_successful_replays_are_ambiguous_and_explicit_id_is_not_a_selector(ops):
    second = rows()[2]
    second.update(run_id=str(UUID(int=201)), row_key=str(UUID(int=201)))
    ops.insert("sync_runs", second)
    with pytest.raises(SafeError, match="checkpoint_recovery_replay_ambiguous"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)


def test_unsuccessful_replay_does_not_mask_unique_success(ops):
    second = rows()[2]
    second.update(run_id=str(UUID(int=201)), row_key=str(UUID(int=201)), status="failed")
    ops.insert("sync_runs", second)
    assert BigQueryRecovery(ops).proof(STORE, ORIGINAL, REPLAY).replay_run_id == REPLAY
    with pytest.raises(SafeError, match="checkpoint_recovery_replay_mismatch"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, second["run_id"])


def test_explicit_replay_must_match_unique_success(ops):
    with pytest.raises(SafeError, match="checkpoint_recovery_replay_mismatch"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, str(UUID(int=999)))


def test_mutation_only_changes_status_timestamp_and_second_call_is_explicit(ops):
    before = copy.deepcopy(ops.all("sync_checkpoints")[0])
    runs = ops.all("sync_runs")
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    after = ops.all("sync_checkpoints")[0]
    assert after["status"] == "recovered" and after["updated_at"] != before["updated_at"]
    assert {k: v for k, v in after.items() if k not in {"status", "updated_at"}} == {
        k: v for k, v in before.items() if k not in {"status", "updated_at"}
    }
    with pytest.raises(SafeError, match="checkpoint_already_recovered"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert ops.all("sync_checkpoints")[0] == after
    assert ops.all("sync_runs") == runs
    assert sum(sql.startswith("BEGIN") for sql, _ in ops.calls) == 1


@pytest.mark.parametrize(
    "target,statement,parameters",
    [
        ("status", "UPDATE sync_checkpoints SET status=?", ("running",)),
        ("pending", "UPDATE sync_checkpoints SET pending_raw_id=?", ("new-pending",)),
        ("original", "UPDATE sync_runs SET status=? WHERE run_id=?", ("failed", ORIGINAL)),
        ("replay", "UPDATE sync_runs SET core_records_failed=1 WHERE run_id=?", (REPLAY,)),
        ("ambiguous", "INSERT INTO sync_runs SELECT * FROM sync_runs WHERE run_id=?", (REPLAY,)),
        ("duplicate", "INSERT INTO sync_checkpoints SELECT * FROM sync_checkpoints", ()),
        ("deleted", "DELETE FROM sync_checkpoints", ()),
        ("key", "UPDATE sync_checkpoints SET row_key=?", ("changed-key",)),
    ],
)
def test_transaction_revalidates_against_toctou_after_preread(ops, target, statement, parameters):
    ops.before_write = lambda t: t.db.execute(statement, parameters)
    with pytest.raises(SafeError, match="^checkpoint_recovery_failed$"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert not any(cp["status"] == "recovered" for cp in ops.all("sync_checkpoints"))


@pytest.mark.parametrize("count", [0, 2])
def test_transaction_asserts_exactly_one_affected_row_and_rolls_back(ops, count):
    before = ops.all("sync_checkpoints")
    ops.rowcount_override = count
    with pytest.raises(SafeError, match="^checkpoint_recovery_failed$"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert ops.all("sync_checkpoints") == before


@pytest.mark.parametrize(
    "statement",
    ["DELETE FROM sync_checkpoints", "INSERT INTO sync_checkpoints SELECT * FROM sync_checkpoints"],
)
def test_real_update_zero_or_two_rows_is_detected_inside_transaction(ops, statement):
    before = ops.all("sync_checkpoints")
    ops.before_update = lambda t: t.db.execute(statement)
    with pytest.raises(SafeError, match="^checkpoint_recovery_failed$"):
        service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert ops.all("sync_checkpoints") == before


@pytest.mark.parametrize(
    "admin", [Admin("subject", "CLIENT_USER"), Admin("subject", ""), Admin("", "ADMIN_UP")]
)
def test_authorization_precedes_every_io_including_lease(admin):
    repository, lease = Mock(), Mock()
    with pytest.raises(SafeError, match="admin_up_required"):
        CheckpointRecovery(repository, lease).recover(admin, STORE, ORIGINAL, REPLAY)
    repository.proof.assert_not_called()
    repository.recover.assert_not_called()
    lease.assert_not_called()


def test_store_specific_lease_wraps_proof_and_mutation(ops):
    calls = []

    @contextmanager
    def lease(store):
        calls.append(("acquire", store, len(ops.calls)))
        yield
        calls.append(("release", store, len(ops.calls)))

    service(ops, lease).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert calls == [("acquire", STORE, 0), ("release", STORE, 2)]


def test_store_busy_prevents_reads_and_mutation(ops):
    @contextmanager
    def lease(_):
        raise SafeError("store_busy")
        yield

    with pytest.raises(SafeError, match="store_busy"):
        service(ops, lease).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert ops.calls == []


@pytest.mark.parametrize(
    "exception",
    [
        BadRequest("PRIVATE"),
        Forbidden("PRIVATE"),
        Unauthorized("PRIVATE"),
        TimeoutError("PRIVATE"),
        ConnectionError("PRIVATE"),
        RuntimeError("PRIVATE"),
    ],
)
def test_write_errors_sanitized_and_unknown_outcome_retains_store_lease(
    ops, monkeypatch, exception
):
    import google.cloud.storage as storage

    storage_client = Mock()
    monkeypatch.setattr(storage, "Client", lambda: storage_client)
    ops.before_write = Mock(side_effect=exception)
    definitive = isinstance(exception, (BadRequest, Forbidden, Unauthorized))
    code = "checkpoint_recovery_failed" if definitive else "checkpoint_recovery_outcome_unknown"
    with pytest.raises(SafeError, match=f"^{code}$") as result:
        service(ops, lambda store: cloud_lease("synthetic-bucket", store)).recover(
            ADMIN, STORE, ORIGINAL, REPLAY
        )
    assert "PRIVATE" not in str(result.value)
    blob = storage_client.bucket.return_value.blob.return_value
    if definitive:
        blob.delete.assert_called_once()
    else:
        blob.delete.assert_not_called()
    assert ops.before_write.call_count == 1  # No ambiguous mutation retries.


def test_sql_has_only_ops_projection_store_scope_parameters_and_atomic_assertions():
    sql = mutation_query("synthetic-dev")
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    assert "CREATE TEMP TABLE recovery_proof AS " + proof_query("synthetic-dev") in sql
    assert sql.count("store_id=@store") == 4
    assert "successful_replay_id=@replay" in sql and "checkpoint_key=@checkpoint" in sql
    assert "ASSERT @@row_count=1" in sql
    update = sql.split("UPDATE ", 1)[1].split(";", 1)[0]
    assert "SET status='recovered', updated_at=CURRENT_TIMESTAMP()" in update
    assert "AND status='needs_review' AND pending_raw_id IS NULL" in update
    assert not any(
        name in sql
        for name in ("up_raw", "up_core", "quality_results", "payload", "email", "phone", "filters")
    )
    historical = proof_query("synthetic-dev", snapshot=True)
    assert historical.count("FOR SYSTEM_TIME AS OF @snapshot") == 3


def test_all_user_values_bound_not_interpolated_and_query_budget_preserved():
    sdk = Mock()
    job = sdk.query.return_value
    job.result.return_value = []
    job.total_bytes_processed = job.total_bytes_billed = 0
    job.job_id = "synthetic-query"
    transport = Transport(
        sdk,
        CloudConfig(
            "synthetic-dev",
            "southamerica-east1",
            1073741824,
            30,
            False,
            maximum_total_bytes_billed=137438953472,
        ),
    )
    malicious = "synthetic' OR TRUE --"
    BigQueryRecovery(transport).recover(
        RecoveryProof(malicious, malicious, "customers", malicious, malicious)
    )
    sql = sdk.query.call_args.args[0]
    kwargs = sdk.query.call_args.kwargs
    assert malicious not in sql
    config = kwargs["job_config"]
    assert config.maximum_bytes_billed == 1073741824
    assert {p.name: p.value for p in config.query_parameters} == {
        **dict.fromkeys(["store", "original", "replay", "checkpoint"], malicious),
        "resource": "customers",
    }
    assert kwargs["job_retry"] is None


@pytest.mark.parametrize(
    "status,raw,pending",
    [
        ("complete", None, False),
        ("recovered", None, False),
        ("needs_review", None, True),
        ("running", None, True),
        ("extracted", None, True),
        ("recovered", "pending", True),
        ("recovered", "", True),
    ],
)
def test_canonical_checkpoint_pending(status, raw, pending):
    assert TERMINAL_CHECKPOINT_STATUSES == {"complete", "recovered"}
    assert checkpoint_pending({"status": status, "pending_raw_id": raw}) is pending


def test_incremental_never_uses_recovery_or_replay_as_latest_collection():
    repo = Mock()
    repo.read.return_value = [
        {
            "resource": "customers",
            "mode": "incremental",
            "status": "complete",
            "updated_at": "2026-09-01",
            "high_id": "100",
        },
        {
            "resource": "customers",
            "mode": "incremental",
            "status": "recovered",
            "updated_at": "2026-09-30",
            "high_id": "999",
        },
        {
            "resource": "customers",
            "mode": "replay",
            "status": "complete",
            "updated_at": "2026-09-30",
            "high_id": "888",
        },
    ]
    cfg = Settings(STORE, "Synthetic", STORE, "UTC", "connection", "2026-09-01T00:00:00Z")
    assert incremental(repo, cfg, "customers", WINDOW.as_of) == ({"limit": 200}, 100)
    repo.read.return_value = repo.read.return_value[1:]
    assert incremental(repo, cfg, "customers", WINDOW.as_of) == ({"limit": 200}, None)


def test_four_historical_blockers_recover_without_touching_originals_replays_or_data():
    transport = OpsTransport()
    for index, count in enumerate((32, 20, 12, 25), 1):
        cp, original, replay = rows(index, count)
        transport.insert("sync_checkpoints", cp)
        transport.insert("sync_runs", original)
        transport.insert("sync_runs", replay)
    assert sum(checkpoint_pending(cp) for cp in transport.all("sync_checkpoints")) == 4
    runs = copy.deepcopy(transport.all("sync_runs"))
    for table in ("upzero_customers", "customers", "quality_results"):
        transport.db.execute(f"CREATE TABLE {table} (id TEXT, payload TEXT)")
        transport.db.execute(f"INSERT INTO {table} VALUES ('synthetic', 'original-snapshot')")

    def data():
        return {
            table: [tuple(row) for row in transport.db.execute(f"SELECT * FROM {table}")]
            for table in ("upzero_customers", "customers", "quality_results")
        }

    before_data = data()
    for index in range(1, 5):
        service(transport).recover(ADMIN, STORE, str(UUID(int=index)), str(UUID(int=index + 100)))
    assert sum(checkpoint_pending(cp) for cp in transport.all("sync_checkpoints")) == 0
    assert all(cp["status"] == "recovered" for cp in transport.all("sync_checkpoints"))
    assert transport.all("sync_runs") == runs and data() == before_data
    assert {r["status"] for r in runs} == {"completed_with_errors", "completed"}
    assert sum(r["core_records_processed"] for r in runs if r["mode"] == "replay") == 89
    transport.db.close()


def current_config():
    return StoreConfig(
        STORE,
        operation_b2b=True,
        timezone="America/Sao_Paulo",
        currency="BRL",
        history_from="2026-09-01T00:00:00Z",
        upzero_enabled=True,
        upzero_connection_id="synthetic-connection",
    )


def add_complete_sources(ops, *, customers=True, fresh=True):
    resources = (
        ("customers", "orders", "analytics_facts") if customers else ("orders", "analytics_facts")
    )
    for index, resource in enumerate(resources, 300):
        filters = {
            "customers": {"limit": 200},
            "orders": {"start_date": "2026-08-31", "end_date": "2026-09-02", "limit": 200},
            "analytics_facts": {"from": "2026-09-01T00:00:00Z", "to": WINDOW.as_of, "limit": 1000},
        }[resource]
        run_id = str(UUID(int=index))
        ops.insert(
            "sync_checkpoints",
            {
                "row_key": "complete-" + resource,
                "store_id": STORE,
                "run_id": run_id,
                "resource": resource,
                "connection_id": "synthetic-connection",
                "mode": "incremental",
                "status": "complete",
                "pending_raw_id": None,
                "filters": json.dumps(filters),
            },
        )
        ops.insert(
            "sync_runs",
            {
                "row_key": run_id,
                "store_id": STORE,
                "run_id": run_id,
                "resource": resource,
                "mode": "incremental",
                "source": "upzero",
                "status": "completed",
                "core_records_failed": 0,
                "finished_at": WINDOW.as_of if fresh else "2026-09-01T00:00:00Z",
            },
        )


def test_preflight_recovered_valid_customers_no_longer_block_real_complete_scan(ops):
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    add_complete_sources(ops)
    Prerequisites(ops).upzero_complete(current_config(), WINDOW)
    proof_reads = [
        (sql, params)
        for sql, params in ops.calls
        if sql.startswith("SELECT * FROM (\nWITH checkpoint_rows")
    ]
    assert len(proof_reads) == 2
    assert proof_reads[-1][1]["snapshot"] == WINDOW.source_snapshot_at
    assert "FOR SYSTEM_TIME AS OF @snapshot" in proof_reads[-1][0]


@pytest.mark.parametrize(
    "freshness",
    [
        "no-collection",
        "old-collection",
        "replay-as-collection",
        "recovery-updated-at",
        "filtered-scan",
    ],
)
def test_preflight_recovery_and_replay_cannot_invent_source_freshness(ops, freshness):
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    add_complete_sources(ops, customers=freshness != "no-collection", fresh=False)
    if freshness == "replay-as-collection":
        ops.db.execute(
            "UPDATE sync_runs SET mode='replay',finished_at=? WHERE mode='incremental' AND resource='customers'",
            (WINDOW.as_of,),
        )
    if freshness == "filtered-scan":
        ops.db.execute(
            "UPDATE sync_runs SET finished_at=? WHERE mode='incremental' AND resource='customers'",
            (WINDOW.as_of,),
        )
        ops.db.execute(
            "UPDATE sync_checkpoints SET filters=? WHERE status='complete' AND resource='customers'",
            (json.dumps({"start_date": "2026-09-01"}),),
        )
    ops.db.execute(
        "UPDATE sync_checkpoints SET updated_at='2099-01-01T00:00:00Z' WHERE status='recovered'"
    )
    ops.db.execute("UPDATE sync_runs SET finished_at='2099-01-01T00:00:00Z' WHERE mode='replay'")
    with pytest.raises(
        SafeError, match="upzero_complete_checkpoint_required|customers_complete_scan_required"
    ):
        Prerequisites(ops).upzero_complete(current_config(), WINDOW)


@pytest.mark.parametrize(
    "problem",
    ["needs-review", "failed-replay", "ambiguous-replay", "pending-raw", "unsupported-resource"],
)
def test_preflight_recovery_must_have_valid_proof_and_supported_coverage(ops, problem):
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    add_complete_sources(ops)
    if problem == "needs-review":
        ops.db.execute(
            "UPDATE sync_checkpoints SET status='needs_review' WHERE run_id=?", (ORIGINAL,)
        )
    elif problem == "failed-replay":
        ops.db.execute("UPDATE sync_runs SET status='failed' WHERE run_id=?", (REPLAY,))
    elif problem == "ambiguous-replay":
        ops.db.execute("INSERT INTO sync_runs SELECT * FROM sync_runs WHERE run_id=?", (REPLAY,))
    elif problem == "pending-raw":
        ops.db.execute(
            "UPDATE sync_checkpoints SET pending_raw_id='pending' WHERE run_id=?", (ORIGINAL,)
        )
    else:
        ops.db.execute("UPDATE sync_checkpoints SET resource='orders' WHERE run_id=?", (ORIGINAL,))
    with pytest.raises(SafeError):
        Prerequisites(ops).upzero_complete(current_config(), WINDOW)


@pytest.mark.parametrize(
    "status,pending,expected",
    [
        ("recovered", None, None),
        ("complete", None, None),
        ("needs_review", None, "run_needs_review_use_replay_or_refresh"),
        ("running", None, None),
        ("extracted", None, None),
        ("recovered", "pending-raw", "run_recovered_use_refresh"),
    ],
)
def test_actions_upzero_resumes_only_pending_checkpoints(status, pending, expected):
    cp = rows()[0]
    cp.update(status=status, pending_raw_id=pending, filters={"limit": 200})
    cp["plan_key"] = digest([STORE, cp["connection_id"], cp["resource"], cp["filters"], cp["mode"]])
    repo = Mock()
    repo.read.side_effect = lambda table, *args: [cp] if table == "sync_checkpoints" else []
    pre = Mock()
    pre.source.return_value = {"secret_resource_name": "synthetic-reference"}
    ops = OpsTransport()
    ops.insert("sync_checkpoints", cp)
    for run in rows()[1:]:
        ops.insert("sync_runs", run)
    action = Actions(ops, pre, lease_bucket="synthetic-bucket")
    action.repository = lambda: repo
    with (
        patch("src.control_plane.worker.Engine") as engine,
        patch("src.control_plane.worker.UpZeroConnector") as connector,
        patch("src.control_plane.worker.resolve_secret", return_value="SYNTHETIC"),
        patch("src.control_plane.worker.incremental", return_value=({"limit": 200}, None)),
        patch("src.control_plane.worker.open_order_windows", return_value=[]),
    ):

        def run(resource, filters, **kwargs):
            if kwargs.get("mode") == "backfill" and expected:
                raise SafeError(expected)
            return {"status": "completed", "core_records_failed": 0}

        engine.return_value.run.side_effect = run
        if expected:
            with pytest.raises(SafeError, match=expected):
                action.upzero(current_config(), WINDOW)
        else:
            action.upzero(current_config(), WINDOW)
        calls = engine.return_value.run.call_args_list
        resumed = [call for call in calls if call.kwargs.get("mode") == "backfill"]
        assert len(resumed) == int(checkpoint_pending(cp))
        if status in {"complete", "recovered"} and pending is None:
            assert len(calls) == 3 and all(call.kwargs["refresh"] is True for call in calls)
        connector.return_value.close.assert_called_once()


def cli_args():
    return [
        "recovery",
        "--live",
        "--project",
        "up-data-intelligence-dev",
        "--confirm-project",
        "up-data-intelligence-dev",
        "--location",
        "southamerica-east1",
        "--lease-bucket",
        "synthetic-bucket",
        "--store-id",
        STORE,
        "--confirm-store",
        STORE,
        "--original-run-id",
        ORIGINAL,
        "--replay-run-id",
        REPLAY,
    ]


@pytest.mark.parametrize(
    "option,value",
    [
        ("--live", None),
        ("--project", "wrong-project"),
        ("--confirm-project", "wrong-project"),
        ("--confirm-store", "wrong-store"),
        ("--location", "wrong-region"),
        ("--original-run-id", "not-uuid"),
        ("--replay-run-id", "not-uuid"),
    ],
)
def test_cli_gates_fail_before_clients_or_credentials(monkeypatch, option, value):
    args = cli_args()
    index = args.index(option)
    if value is None:
        del args[index]
    else:
        args[index + 1] = value
    monkeypatch.setattr("sys.argv", args)
    with patch.object(recovery_cli, "clients") as clients:
        assert recovery_cli.main() == 1
        clients.assert_not_called()


@pytest.mark.parametrize(
    "option", ["--store-id", "--confirm-store", "--original-run-id", "--replay-run-id"]
)
def test_cli_requires_all_explicit_target_arguments(monkeypatch, option):
    args = cli_args()
    index = args.index(option)
    del args[index : index + 2]
    monkeypatch.setattr("sys.argv", args)
    with patch.object(recovery_cli, "clients") as clients, pytest.raises(SystemExit) as failure:
        recovery_cli.main()
    assert failure.value.code == 2
    clients.assert_not_called()


def test_valid_cli_invokes_recovery_once_with_internal_admin_and_store_lease(monkeypatch):
    monkeypatch.setattr("sys.argv", cli_args())
    with (
        patch.object(recovery_cli, "clients", return_value=(Mock(), Mock())),
        patch.object(recovery_cli, "CheckpointRecovery") as recovery,
        patch.object(recovery_cli, "cloud_lease") as lease,
    ):
        assert recovery_cli.main() == 0
        recovery.return_value.recover.assert_called_once_with(
            Admin("adc-internal-operator", "ADMIN_UP"), STORE, ORIGINAL, REPLAY
        )
        recovery.call_args.args[1](STORE)
        lease.assert_called_once_with("synthetic-bucket", STORE)


def test_recovery_logs_are_sanitized_without_ids_or_payloads(ops, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    entries = [json.loads(record.message) for record in caplog.records]
    assert [r["event"] for r in entries] == [
        "checkpoint_recovery_started",
        "checkpoint_recovery_completed",
    ]
    assert all(set(r) <= {"event", "store_id", "resource", "status"} for r in entries)
    assert ORIGINAL not in caplog.text and REPLAY not in caplog.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_id", "foreign"),
        ("original_run_id", "foreign"),
        ("checkpoint_count", True),
        ("checkpoint_count", None),
        ("pending_count", -1),
        ("checkpoint_key", ""),
        ("resource", "meta"),
        ("checkpoint_status", "running"),
    ],
)
def test_malformed_or_foreign_proof_dto_fails_closed(ops, field, value):
    data, _ = ops.query(
        proof_query("synthetic-dev"),
        [scalar("store", "STRING", STORE), scalar("original", "STRING", ORIGINAL)],
    )
    data[0][field] = value
    with pytest.raises(SafeError):
        RecoveryProof.from_row(data[0], STORE, ORIGINAL, REPLAY)


def test_read_error_is_sanitized_and_never_mutates():
    transport = Mock(config=SimpleNamespace(project="synthetic-dev"))
    transport.query.side_effect = RuntimeError("PRIVATE")
    with pytest.raises(SafeError, match="^checkpoint_recovery_read_failed$") as error:
        service = CheckpointRecovery(BigQueryRecovery(transport), lambda _: nullcontext())
        service.recover(ADMIN, STORE, ORIGINAL, REPLAY)
    assert "PRIVATE" not in str(error.value) and transport.query.call_count == 1


def test_proof_row_count_must_be_one():
    transport = Mock(config=SimpleNamespace(project="synthetic-dev"))
    transport.query.return_value = ([], None)
    with pytest.raises(SafeError, match="checkpoint_recovery_invalid_proof"):
        BigQueryRecovery(transport).proof(STORE, ORIGINAL, REPLAY)
    transport.query.return_value = ([{}, {}], None)
    with pytest.raises(SafeError, match="checkpoint_recovery_invalid_proof"):
        BigQueryRecovery(transport).proof(STORE, ORIGINAL, REPLAY)


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_id", "other-store"),
        ("status", "complete"),
        ("pending_raw_id", "pending"),
        ("row_key", "other-checkpoint"),
        ("resource", "orders"),
        ("run_id", "other-run"),
    ],
)
def test_runtime_recovered_helper_revalidates_scope_identity_and_pending(ops, field, value):
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    cp = ops.all("sync_checkpoints")[0]
    cp[field] = value
    with pytest.raises(SafeError):
        BigQueryRecovery(ops).recovered(cp, STORE)


@pytest.mark.parametrize("resource", ["customers", "orders", "analytics_facts"])
def test_admin_supported_resources_preserve_mode_and_connection(ops, resource):
    ops.db.execute("UPDATE sync_checkpoints SET resource=?", (resource,))
    ops.db.execute("UPDATE sync_runs SET resource=?", (resource,))
    assert service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY).resource == resource
    cp = ops.all("sync_checkpoints")[0]
    assert cp["mode"] == "backfill" and cp["connection_id"] == "synthetic-connection"


def test_result_lost_after_commit_keeps_lease_for_operator_reconciliation(ops, monkeypatch):
    import google.cloud.storage as storage

    client = Mock()
    monkeypatch.setattr(storage, "Client", lambda: client)
    ops.after_commit = Mock(side_effect=TimeoutError("PRIVATE"))
    runs = ops.all("sync_runs")
    with pytest.raises(SafeError, match="checkpoint_recovery_outcome_unknown"):
        service(ops, lambda store: cloud_lease("synthetic-bucket", store)).recover(
            ADMIN, STORE, ORIGINAL, REPLAY
        )
    client.bucket.return_value.blob.return_value.delete.assert_not_called()
    assert ops.all("sync_checkpoints")[0]["status"] == "recovered"
    assert ops.all("sync_runs") == runs and ops.after_commit.call_count == 1
    assert sum(sql.startswith("BEGIN") for sql, _ in ops.calls) == 1


def test_worker_invalid_recovered_proof_blocks_before_incremental_scan(ops):
    service(ops).recover(ADMIN, STORE, ORIGINAL, REPLAY)
    cp = ops.all("sync_checkpoints")[0]
    cp["filters"] = json.loads(cp["filters"])
    ops.db.execute("UPDATE sync_runs SET status='failed' WHERE run_id=?", (REPLAY,))
    repo = Mock()
    repo.read.side_effect = lambda table, *args: [cp] if table == "sync_checkpoints" else []
    pre = Mock()
    pre.source.return_value = {"secret_resource_name": "synthetic-reference"}
    action = Actions(ops, pre, lease_bucket="synthetic-bucket")
    action.repository = lambda: repo
    with (
        patch("src.control_plane.worker.Engine") as engine,
        patch("src.control_plane.worker.UpZeroConnector") as connector,
        patch("src.control_plane.worker.resolve_secret", return_value="SYNTHETIC"),
        patch("src.control_plane.worker.incremental") as incremental_call,
    ):
        with pytest.raises(SafeError, match="checkpoint_recovery_replay_missing"):
            action.upzero(current_config(), WINDOW)
        incremental_call.assert_not_called()
        engine.return_value.run.assert_not_called()
        connector.return_value.close.assert_called_once()


def test_failed_metadata_read_is_never_classified_as_unknown_mutation():
    from src.control_plane.budget import BoundedClient

    sdk = Mock()
    sdk.query.side_effect = TimeoutError("PRIVATE")
    config = CloudConfig(
        "synthetic-dev", "southamerica-east1", 10, 30, False, maximum_total_bytes_billed=100
    )
    client = BoundedClient(sdk, config)
    with pytest.raises(SafeError, match="checkpoint_recovery_read_failed"):
        BigQueryRecovery(Transport(client, config)).proof(STORE, ORIGINAL, REPLAY)
    assert not client.mutation_outcome_unknown
    assert sdk.query.call_args.args[0].startswith("SELECT ")


@pytest.mark.parametrize("row", [None, []])
def test_proof_requires_a_metadata_record(row):
    with pytest.raises(SafeError, match="checkpoint_recovery_invalid_proof"):
        RecoveryProof.from_row(row, STORE, ORIGINAL, REPLAY)
