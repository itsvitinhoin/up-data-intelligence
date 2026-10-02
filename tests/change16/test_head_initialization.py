"""Offline HEAD SQL and transaction regressions; synthetic publication data only.

SQLite executes the generated DML/SELECT guards after narrowly translating
BigQuery scripting/session syntax. This proves offline state/rollback behavior,
not live BigQuery compatibility; explicit singleton SQL checks cover that grammar.
"""

import json
import re
import sqlite3
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.control_plane.worker import Actions
from src.domain.models import SafeError
from src.intelligence.live.materialize import build
from src.intelligence.live.publication import Writer, commit_sql
from src.intelligence.live.schema import PUBLICATION, SCHEMAS
from src.utils.data import canonical
from tests.change16.test_stack import fixture16
from tests.control_plane.test_control_plane import WINDOW, config

PROJECT = "synthetic-dev"
PUB = f"`{PROJECT}.up_analytics.{PUBLICATION}`"
BASE = f"`{PROJECT}.up_analytics.analytics_publications`"


def assert_singleton_head_sql(sql):
    # Inspect the OUTER SELECT, not the FROM inside the NOT EXISTS subquery.
    prefix, predicate = sql.split("WHERE NOT EXISTS", 1)
    assert re.search(
        r"SELECT\s+@head,'HEAD',@store,@policy,0,'initialized'\s+FROM\s+UNNEST\(\[1\]\)\s*$",
        prefix,
    )
    assert "store_id=@store AND policy_hash=@policy" in predicate
    assert "SELECT @head,'HEAD',@store,@policy,0,'initialized' WHERE" not in sql


@pytest.fixture
def publication():
    policy, snapshot, args = fixture16("synthetic-brand")
    return build(policy, snapshot, **args)


class TransactionTransport:
    """Execute generated commit guards/DML in a local, rollback-capable database."""

    def __init__(self, publication):
        self.config = SimpleNamespace(project=PROJECT)
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.calls = []
        self.initialized_inside_transaction = []
        self.fail_after = None
        self.corrupt_stage = False
        for name, spec in SCHEMAS.items():
            columns = ",".join(
                f"`{field}` {'INTEGER' if typ in {'INT64', 'BOOL'} else 'TEXT'}"
                for field, typ in spec.fields.items()
            )
            self.db.execute(f"CREATE TABLE `{PROJECT}.up_analytics.{name}` ({columns})")
            self.db.execute(f"CREATE TABLE stage_{name} ({columns})")
        self.db.execute(
            f"CREATE TABLE {BASE} (record_kind,store_id,policy_hash,generation,publication_id,status)"
        )
        p = publication["publication"]
        self.db.execute(
            f"INSERT INTO {BASE} VALUES (?,?,?,?,?,?)",
            (
                "HEAD",
                p["store_id"],
                p["policy_hash"],
                p["base_generation"],
                p["base_publication_id"],
                "completed",
            ),
        )

    def insert(self, table, row):
        row = json.loads(canonical(row))
        fields = ",".join(f"`{key}`" for key in row)
        values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in row.values()]
        self.db.execute(
            f"INSERT INTO {table} ({fields}) VALUES ({','.join('?' for _ in row)})", values
        )

    def rows(self):
        result = []
        for raw in self.db.execute(f"SELECT * FROM {PUB}"):
            row = dict(raw)
            for name, typ in SCHEMAS[PUBLICATION].fields.items():
                if typ == "JSON" and row[name] is not None:
                    row[name] = json.loads(row[name])
            result.append(row)
        return result

    def query(self, sql, params, **kwargs):
        values = {param.name: param.value for param in params}
        self.calls.append((sql, values, kwargs))
        if sql.startswith("SELECT *"):
            return [
                r
                for r in self.rows()
                if r["record_kind"] == "RECEIPT"
                and r["store_id"] == values["store"]
                and r["policy_hash"] == values["policy"]
                and r["publication_id"] == values["publication"]
                and r["status"] == "completed"
            ], None
        if kwargs.get("create_session"):
            for name in SCHEMAS:
                self.db.execute(f"DELETE FROM stage_{name}")
            return [], "synthetic-session"
        if sql.startswith("CALL"):
            return [], None
        if sql.startswith("INSERT INTO _SESSION"):
            name = re.search(r"stage_(\w+)", sql)[1]
            for row in json.loads(values["rows"]):
                self.insert("stage_" + name, row)
            return [], None
        if sql.startswith("BEGIN TRANSACTION"):
            self.commit(sql, values)
            return [], None
        raise AssertionError("unexpected_offline_sql")

    def commit(self, sql, values):
        initialization = sql.splitlines()[1]
        assert_singleton_head_sql(initialization.split("; END IF;")[0])
        if self.corrupt_stage:
            self.db.execute("UPDATE stage_analytics_customer_timeline SET generation=-1")
        row_count = 0
        try:
            for line in sql.splitlines():
                if line.startswith("IF @initialize_head"):
                    if not values["initialize_head"]:
                        continue
                    line = re.fullmatch(r"IF @initialize_head THEN (.*); END IF;", line)[1]
                line = line.replace("FROM UNNEST([1])", "FROM (SELECT 1)")
                line = line.replace("_SESSION.", "").replace("JSON_VALUE(", "json_extract(")
                line = line.replace("@@row_count", str(row_count))
                line = line.replace(f"UPDATE {PUB} h SET", f"UPDATE {PUB} AS h SET")
                if line.startswith("ASSERT "):
                    expr, code = re.fullmatch(r"ASSERT (.*) AS '([^']+)';", line).groups()
                    if not self.db.execute("SELECT " + expr, values).fetchone()[0]:
                        raise ValueError(code)
                else:
                    row_count = self.db.execute(line, values).rowcount
                if "FROM (SELECT 1) WHERE NOT EXISTS" in line:
                    assert self.db.in_transaction
                    self.initialized_inside_transaction.append(deepcopy(self.rows()))
                if self.fail_after and line.startswith(self.fail_after):
                    raise RuntimeError("synthetic_commit_failure")
        except Exception as exc:
            self.last_error = exc
            self.failed_statement = line
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise


@pytest.fixture
def transport(publication):
    t = TransactionTransport(publication)
    try:
        yield t
    finally:
        t.db.close()


def seed_head(t, p, generation=0):
    t.insert(
        PUB,
        {
            "row_key": "synthetic-head",
            "record_kind": "HEAD",
            "store_id": p["store_id"],
            "policy_hash": p["policy_hash"],
            "generation": generation,
            "status": "initialized",
        },
    )


def test_intelligence_sql_singleton_and_transaction_order():
    sql = commit_sql(PROJECT)
    assert_singleton_head_sql(sql.splitlines()[1].split("; END IF;")[0])
    required = [
        "BEGIN TRANSACTION;",
        "IF @initialize_head",
        "intelligence_head_required",
        "intelligence_generation_changed",
        "intelligence_sequence_changed",
        "analytics_base_changed",
        "intelligence_stage_count_mismatch",
        "invalid_intelligence_stage",
        "duplicate_stage",
        "generation_already_exists",
        "INSERT INTO `synthetic-dev.up_analytics.analytics_paid_touchpoints`",
        "intelligence_receipt_stage_required",
        "invalid_intelligence_receipt_stage",
        f"INSERT INTO {PUB} (`",
        f"UPDATE {PUB} h SET",
        "ASSERT @@row_count=1",
        "COMMIT TRANSACTION;",
    ]
    positions = [sql.index(fragment) for fragment in required]
    assert positions == sorted(positions)
    assert sql.count("BEGIN TRANSACTION;") == sql.count("COMMIT TRANSACTION;") == 1


def test_first_initialization_is_atomic_and_repeated_reconcile_idempotent(transport, publication):
    assert transport.rows() == []
    writer = Writer(transport)
    saved = writer.publish(publication, 0, initialize_head=True)
    assert saved == publication["publication"]
    assert [r["generation"] for r in transport.initialized_inside_transaction[0]] == [0]
    rows = transport.rows()
    assert sorted((r["record_kind"], r["generation"], r["status"]) for r in rows) == [
        ("HEAD", 1, "completed"),
        ("RECEIPT", 1, "completed"),
    ]
    commits = sum(sql.startswith("BEGIN") for sql, _, _ in transport.calls)
    assert writer.publish(publication, 1, initialize_head=True) == saved
    assert transport.rows() == rows
    assert sum(sql.startswith("BEGIN") for sql, _, _ in transport.calls) == commits == 1


def test_missing_head_without_initialization_fails_without_writes(transport, publication):
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        Writer(transport).publish(publication, 0, initialize_head=False)
    assert str(transport.last_error) == "intelligence_head_required"
    assert transport.rows() == []
    assert transport.initialized_inside_transaction == []


def test_existing_head_is_not_duplicated_by_initialization(transport, publication):
    seed_head(transport, publication["publication"])
    Writer(transport).publish(publication, 0, initialize_head=True)
    assert sum(r["record_kind"] == "HEAD" for r in transport.rows()) == 1
    assert len(transport.initialized_inside_transaction[0]) == 1


@pytest.mark.parametrize("problem", ["duplicate_head", "generation", "sequence", "base", "stage"])
def test_commit_guards_still_block_invalid_domains_and_rollback(transport, publication, problem):
    p = publication["publication"]
    if problem == "duplicate_head":
        seed_head(transport, p)
        seed_head(transport, p)
    elif problem == "generation":
        seed_head(transport, p, generation=1)
    elif problem == "sequence":
        seed_head(transport, p)
        transport.insert(PUB, {**p, "publication_id": "synthetic-old", "generation": 2})
    elif problem == "base":
        transport.db.execute(f"UPDATE {BASE} SET publication_id='synthetic-other'")
    elif problem == "stage":
        transport.corrupt_stage = True
    before = transport.rows()
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        Writer(transport).publish(publication, 0, initialize_head=True)
    assert (
        str(transport.last_error)
        == {
            "duplicate_head": "intelligence_head_required",
            "generation": "intelligence_generation_changed",
            "sequence": "intelligence_sequence_changed",
            "base": "analytics_base_changed",
            "stage": "invalid_intelligence_stage",
        }[problem]
    )
    assert transport.rows() == before
    for name in SCHEMAS:
        if name != PUBLICATION:
            assert (
                transport.db.execute(
                    f"SELECT COUNT(*) FROM `{PROJECT}.up_analytics.{name}`"
                ).fetchone()[0]
                == 0
            )


@pytest.mark.parametrize("phase", ["first_model", "receipt", "head_update"])
def test_failure_after_inserts_or_head_update_rolls_back_initial_head_and_all_rows(
    transport, publication, phase
):
    transport.fail_after = {
        "first_model": "INSERT INTO `synthetic-dev.up_analytics.analytics_paid_touchpoints`",
        "receipt": f"INSERT INTO {PUB} (`",
        "head_update": f"UPDATE {PUB} AS h SET",
    }[phase]
    with pytest.raises(SafeError, match="bigquery_write_outcome_unknown"):
        Writer(transport).publish(publication, 0, initialize_head=True)
    assert str(transport.last_error) == "synthetic_commit_failure"
    assert transport.failed_statement.startswith(transport.fail_after)
    assert transport.initialized_inside_transaction[0][0]["generation"] == 0
    assert transport.rows() == []
    for name in SCHEMAS:
        assert (
            transport.db.execute(
                f"SELECT COUNT(*) FROM `{PROJECT}.up_analytics.{name}`"
            ).fetchone()[0]
            == 0
        )
    transport.fail_after = None
    Writer(transport).publish(publication, 0, initialize_head=True)
    assert sorted(r["generation"] for r in transport.rows()) == [1, 1]


class AnalyticsHeadTransport:
    def __init__(self, c, *, existing=False):
        self.config = SimpleNamespace(project=PROJECT)
        self.c = c
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            f"CREATE TABLE {BASE} (row_key TEXT,record_kind TEXT,store_id TEXT,policy_hash TEXT,"
            "generation INTEGER,status TEXT,publication_id TEXT,as_of TEXT)"
        )
        if existing:
            self.db.execute(
                f"INSERT INTO {BASE}(row_key,record_kind,store_id,policy_hash,generation,status) "
                "VALUES ('synthetic-head','HEAD',?,?,0,'initialized')",
                (c.store_id, c.policy(WINDOW).policy_hash),
            )
        self.calls = []

    @property
    def rows(self):
        return [dict(row) for row in self.db.execute(f"SELECT * FROM {BASE}")]

    def query(self, sql, params):
        values = {p.name: p.value for p in params}
        self.calls.append((sql, values))
        assert values["store"] == self.c.store_id
        assert values["policy"] == self.c.policy(WINDOW).policy_hash
        if sql.startswith("SELECT"):
            return [dict(row) for row in self.db.execute(sql, values)], None
        assert sql.startswith("INSERT INTO ")
        assert_singleton_head_sql(sql)
        self.db.execute(sql.replace("FROM UNNEST([1])", "FROM (SELECT 1)"), values)
        return [], None


@pytest.mark.parametrize("existing", [False, True])
def test_control_plane_initializes_valid_head_sql_and_preserves_existing_head(existing):
    c = config(upzero_enabled=True, analytics_enabled=True, upzero_connection_id="synthetic-up")
    transport = AnalyticsHeadTransport(c, existing=existing)
    try:
        action = Actions(transport, Mock(), lease_bucket="synthetic")
        with patch("src.control_plane.worker.analytics_materialize") as materialize:
            action.analytics(c, WINDOW)
            action.analytics(c, WINDOW)
        assert len(transport.rows) == 1 and transport.rows[0]["generation"] == 0
        initializers = [sql for sql, _ in transport.calls if sql.startswith("INSERT")]
        assert len(initializers) == (0 if existing else 1)
        for sql in initializers:
            assert_singleton_head_sql(sql)
        assert materialize.call_count == 2
        for call in materialize.call_args_list:
            assert call.args[2].expected_generation == 0
            assert call.args[2].full_refresh_authorized
    finally:
        transport.db.close()


def test_sql_regression_guard_rejects_original_invalid_bigquery_initializer():
    line = commit_sql(PROJECT).splitlines()[1].split("; END IF;")[0]
    with pytest.raises(AssertionError):
        assert_singleton_head_sql(line.replace(" FROM UNNEST([1])", ""))
