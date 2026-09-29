"""Contract fakes model atomic publication; they do NOT execute BigQuery SQL."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.analytics.cloud.reader import (
    BigQueryAnalyticsReader,
    SourceGeneration,
    expand_dependencies,
)
from src.analytics.cloud.transport import CloudConfig, Transport
from src.analytics.cloud.writer import (
    BigQueryAnalyticsWriter,
    Publication,
    commit_sql,
)
from src.analytics.materialization import calculate, plan_changes
from src.analytics.parity import load_fixture
from src.analytics.schema import SCHEMAS

FIXTURE = Path("tests/fixtures/analytics_readiness/synthetic.json")


class FakeClient:
    def __init__(self):
        self.calls = []
        self.rows = {m: [] for m in SCHEMAS}
        self.staging = {}
        self.receipts = {}
        self.generation = 0
        self.failure = None
        self.read_rows = []
        self.read_failure = False
        self.source = {}

    def query(self, sql, **kwargs):
        self.calls.append((sql, kwargs))
        cfg = kwargs["job_config"]
        params = {p.name: p.to_api_repr()["parameterValue"] for p in cfg.query_parameters}

        def get(key):
            return params[key].get("value")

        rows = []
        session = None
        error = None
        if sql.startswith("SELECT publication_id"):
            receipt = self.receipts.get(get("publication"))
            rows = [receipt] if receipt else []
        elif sql.startswith("CREATE TEMP TABLE stage_"):
            self.staging = {m: [] for m in SCHEMAS}
            session = "synthetic-session"
        elif sql.startswith("INSERT INTO _SESSION.stage_"):
            model = sql.split("_SESSION.stage_", 1)[1].split(" ", 1)[0]
            self.staging[model] += json.loads(get("rows"))
            if self.failure == "staging":
                error = RuntimeError("synthetic staging failure")
        elif sql.startswith("BEGIN TRANSACTION"):
            expected = int(get("expected"))
            if expected != self.generation or self.failure == "stale":
                error = ValueError("stale_publication_generation")
            else:
                proposed = deepcopy(self.rows)
                for n, model in enumerate(SCHEMAS):
                    from src.analytics.materialization import SCOPE_FIELDS

                    values = {r["value"] for r in params[f"scope_{n}"].get("arrayValues", [])}
                    full = get(f"full_{n}") == "true"
                    proposed[model] = [
                        r
                        for r in proposed[model]
                        if not (
                            r["store_id"] == get("store")
                            and r["policy_hash"] == get("policy")
                            and (full or r[SCOPE_FIELDS[model]] in values)
                        )
                    ] + deepcopy(self.staging[model])
                if self.failure == "transaction":
                    error = RuntimeError("synthetic rollback")
                else:
                    self.rows = proposed
                    self.generation += 1
                    self.receipts[get("publication")] = {
                        "publication_id": get("publication"),
                        "store_id": get("store"),
                        "policy_hash": get("policy"),
                        "generation": self.generation,
                        "status": "completed",
                        "source_watermark": get("watermark"),
                        "row_counts": {},
                        "bytes_processed": None,
                    }
                    if self.failure == "lost_ack":
                        error = RuntimeError("synthetic lost acknowledgement")
        elif sql.startswith("SELECT"):
            if self.read_failure:
                error = RuntimeError("synthetic read failure")
            rows = deepcopy(self.read_rows)
            for table, source in self.source.items():
                if ".up_core." + table + "`" in sql:
                    rows = deepcopy(source)

        def result(timeout):
            if error:
                raise error
            return rows

        return SimpleNamespace(
            result=result,
            total_bytes_processed=123,
            session_info=SimpleNamespace(session_id=session),
        )


@pytest.fixture
def setup():
    policy, snapshot = load_fixture(FIXTURE)
    fake = FakeClient()
    transport = Transport(
        fake, CloudConfig("synthetic-project", "southamerica-east1", 123456, 17, False)
    )
    plan = plan_changes(policy, snapshot, None, None)
    pub = Publication(
        policy, SourceGeneration("2026-04-02T13:00:00Z", "a" * 64, True), plan, 0, True
    )
    tables, findings, _ = calculate(policy, snapshot, plan)
    return policy, snapshot, fake, transport, pub, tables, findings


def test_reader_parameters_pruning_limits_and_columns(setup):
    p, s, f, t, *_ = setup
    f.read_rows = s.orders[:1]
    reader = BigQueryAnalyticsReader(t, p)
    gen = SourceGeneration(p.as_of, "a" * 64, True)
    assert reader.read("orders", gen, days={"2026-03-01"}) == s.orders[:1]
    sql, kw = f.calls[-1]
    assert "SELECT *" not in sql and "up_raw" not in sql
    assert "created_at>=TIMESTAMP(@min_day" in sql
    assert p.store_id not in sql and "store_id=@store" in sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at" in sql
    assert kw["location"] == "southamerica-east1" and kw["job_retry"] is None
    assert kw["timeout"] == 17 and kw["job_config"].maximum_bytes_billed == 123456
    assert kw["job_config"].use_query_cache is False
    assert t.bytes_processed == 123 and t.rows_read == 1
    f.read_rows = [{**s.orders[0], "store_id": "other"}]
    with pytest.raises(ValueError, match="source_store_mismatch"):
        reader.read("orders", gen, days={"2026-03-01"})


def test_reader_failure_unknown_scope_and_unsealed_generation(setup):
    p, s, f, t, pub, *_ = setup
    reader = BigQueryAnalyticsReader(t, p)
    with pytest.raises(ValueError, match="explicit_affected_scope"):
        reader.read("orders", pub.source)
    with pytest.raises(ValueError, match="not_allowed"):
        reader.read("upzero_orders", pub.source, full_refresh=True)
    with pytest.raises(ValueError, match="full_refresh_requires"):
        reader.snapshot(pub.source, pub.plan)
    f.read_failure = True
    with pytest.raises(RuntimeError, match="read failure"):
        reader.read("orders", pub.source, days=set())
    plan = plan_changes(p, s, s, p)
    with pytest.raises(ValueError, match="unsealed_source"):
        reader.snapshot(replace(pub.source, completeness_confirmed=False), plan)


def test_candidate_index_uses_observed_versions_not_creation(setup):
    p, _, f, t, pub, *_ = setup
    BigQueryAnalyticsReader(t, p).candidates(
        "orders",
        pub.source,
        observed_from="2026-04-01T00:00:00Z",
        observed_to="2026-04-02T00:00:00Z",
    )
    sql, _ = f.calls[-1]
    assert "orders_versions" in sql and "observed_at>=@low" in sql
    assert "created_at>=@low" not in sql


@pytest.mark.parametrize(
    "kind", ["duplicate", "policy", "currency", "grain", "null_key", "schema", "quality"]
)
def test_invalid_staging_never_queries(setup, kind):
    _, _, f, t, pub, tables, findings = setup
    rows = tables["analytics_store_daily"]
    if kind == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif kind == "policy":
        rows[0]["policy_hash"] = "wrong"
    elif kind == "currency":
        rows[0]["currency"] = "USD"
    elif kind == "grain":
        rows.append({**rows[0], "row_key": "different"})
    elif kind == "null_key":
        rows[0]["row_key"] = None
    elif kind == "schema":
        del rows[0]["orders_generated"]
    else:
        findings.append({"severity": "blocking", "rule_id": "test"})
    with pytest.raises(ValueError):
        BigQueryAnalyticsWriter(t).publish(pub, tables, findings=findings)
    assert f.calls == []


def test_publication_idempotent_lost_ack_and_chunking(setup):
    _, _, f, t, pub, tables, findings = setup
    f.failure = "lost_ack"
    writer = BigQueryAnalyticsWriter(t, max_chunk_bytes=2200)
    receipt = writer.publish(pub, tables, findings=findings)
    assert receipt["status"] == "completed" and f.generation == 1
    before = deepcopy(f.rows)
    assert writer.publish(pub, tables, findings=findings) == receipt
    assert f.generation == 1 and f.rows == before
    assert len([sql for sql, _ in f.calls if sql.startswith("INSERT INTO _SESSION.stage_")]) > 7
    commit = [kw for sql, kw in f.calls if sql.startswith("BEGIN TRANSACTION")][0]
    assert commit["job_id"].startswith("analytics_" + pub.publication_id)
    assert commit["job_retry"] is None


@pytest.mark.parametrize("failure", ["staging", "transaction", "stale"])
def test_rollback_and_retry(setup, failure):
    _, _, f, t, pub, tables, findings = setup
    f.failure = failure
    with pytest.raises((RuntimeError, ValueError)):
        BigQueryAnalyticsWriter(t).publish(pub, tables, findings=findings)
    assert not any(f.rows.values()) and not f.receipts and f.generation == 0
    f.failure = None
    BigQueryAnalyticsWriter(t).publish(pub, tables, findings=findings)
    assert f.generation == 1


@pytest.mark.parametrize("change", ["cancel", "old_order", "late_fact", "variant"])
def test_affected_replacement_and_obsolete_deletion(setup, change):
    p, s, f, t, pub, tables, findings = setup
    writer = BigQueryAnalyticsWriter(t)
    writer.publish(pub, tables, findings=findings)
    other = {**f.rows["analytics_store_daily"][0], "store_id": "other", "row_key": "other"}
    f.rows["analytics_store_daily"].append(other)
    other_policy = {**other, "store_id": p.store_id, "policy_hash": "other-policy"}
    f.rows["analytics_store_daily"].append(other_policy)
    current = deepcopy(s)
    if change == "cancel":
        current.orders[2]["order_status"] = "CANCELED"
    elif change == "old_order":
        current.orders.append(
            {**current.orders[0], "order_id": "older", "created_at": "2026-02-01T12:00:00Z"}
        )
    elif change == "late_fact":
        current.events.append(
            {**current.events[0], "fact_id": "late", "occurred_at": "2026-02-01T12:00:00Z"}
        )
    else:
        current.items[0]["variant_id"] = "new-variant"
    plan = expand_dependencies(p, current, s, p, history_closure_confirmed=True)
    newpub = Publication(p, replace(pub.source, generation="b" * 64), plan, 1)
    newtables, newfindings, _ = calculate(p, current, plan)
    writer.publish(newpub, newtables, findings=newfindings)
    assert (
        other in f.rows["analytics_store_daily"] and other_policy in f.rows["analytics_store_daily"]
    )
    if change == "cancel":
        assert {r["customer_id"] for r in f.rows["analytics_customer_metrics"]} == {"c1"}
        assert {r["customer_id"] for r in f.rows["analytics_customer_purchase_sequence"]} == {"c1"}
    elif change == "old_order":
        assert {r["cohort_month"] for r in f.rows["analytics_cohorts"]} == {
            "2026-02-01",
            "2026-03-01",
        }
    elif change == "late_fact":
        assert any(r["event_date"] == "2026-02-01" for r in f.rows["analytics_funnel_daily"])
    else:
        assert len(f.rows["analytics_products_daily"]) == 4
        assert any(r["variant_id"] == "new-variant" for r in f.rows["analytics_products_daily"])


def test_generation_scope_identity_and_untrusted_closure(setup):
    p, s, _, _, pub, *_ = setup
    with pytest.raises(ValueError, match="full_refresh_requires"):
        replace(pub, full_refresh_authorized=False)
    with pytest.raises(ValueError, match="dependency_closure_required"):
        expand_dependencies(p, s, s, p, history_closure_confirmed=False)
    assert replace(pub, expected_generation=100).publication_id == pub.publication_id
    assert (
        replace(pub, source=replace(pub.source, generation="b" * 64)).publication_id
        != pub.publication_id
    )


def test_sql_no_global_delete_no_core_write_and_receipt_atomic():
    sql = commit_sql("synthetic-project")
    assert (
        "TRUNCATE" not in sql
        and "CREATE OR REPLACE" not in sql
        and "up_core" not in sql
        and "up_raw" not in sql
    )
    deletes = [line for line in sql.splitlines() if line.startswith("DELETE")]
    assert len(deletes) == 7
    assert all("store_id=@store AND policy_hash=@policy AND (" in line for line in deletes)
    assert sql.startswith("BEGIN TRANSACTION") and sql.endswith("COMMIT TRANSACTION;")
    assert "generation=@expected+1" in sql and "@@row_count=1" in sql
    assert sql.index("SELECT 'RECEIPT'") < sql.index("COMMIT TRANSACTION")


def test_cli_unapproved_live_blocked_before_client_or_policy_read(tmp_path, monkeypatch):
    from src.analytics.job import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "job",
            "--store",
            "synthetic",
            "--policy",
            "does-not-exist",
            "--from",
            "2026-03-01",
            "--to",
            "2026-03-02",
            "--as-of",
            "2026-04-01T00:00:00Z",
            "--project",
            "synthetic-project",
            "--location",
            "southamerica-east1",
            "--maximum-bytes-billed",
            "1000",
            "--output",
            str(tmp_path),
            "--live",
            "--confirm-project",
            "synthetic-project",
            "--confirm-store",
            "synthetic",
        ],
    )
    with pytest.raises(SystemExit):
        main()
    assert not list(tmp_path.iterdir())


def test_composed_runner_and_safe_logs(setup, caplog):
    import logging

    from src.analytics.cloud.runner import materialize

    p, s, f, t, pub, tables, _ = setup
    f.source = dict(
        zip(
            ("orders", "customers", "order_items", "analytics_events"),
            (s.orders, s.customers, s.items, s.events),
            strict=True,
        )
    )
    with caplog.at_level(logging.INFO, logger="upzero"):
        materialize(BigQueryAnalyticsReader(t, p), BigQueryAnalyticsWriter(t), pub)
    for model in SCHEMAS:
        assert sorted(f.rows[model], key=lambda r: r["row_key"]) == sorted(
            tables[model], key=lambda r: r["row_key"]
        )
    logs = [json.loads(r.message) for r in caplog.records]
    finished = next(r for r in logs if r["event"] == "analytics_execution_finished")
    assert finished["bytes_processed"] == t.bytes_processed
    assert not any(
        k in row for row in logs for k in ("customer_id", "order_id", "payload", "api_key")
    )


def test_reader_limit_never_returns_partial_success(setup):
    p, s, f, t, pub, *_ = setup
    f.read_rows = s.orders
    limited = Transport(f, replace(t.config, maximum_rows=1))
    with pytest.raises(ValueError, match="unit_too_large"):
        BigQueryAnalyticsReader(limited, p).read("orders", pub.source, full_refresh=True)


def test_committed_sql_matches_generator():
    assert (
        Path("sql/analytics/cloud_proposed/publication.sql").read_text()
        == commit_sql("up-data-intelligence-dev") + "\n"
    )


def test_real_stale_generation_is_rejected_after_another_commit(setup):
    _, _, f, t, pub, tables, findings = setup
    writer = BigQueryAnalyticsWriter(t)
    writer.publish(pub, tables, findings=findings)
    next_pub = replace(pub, source=replace(pub.source, generation="b" * 64))
    with pytest.raises(ValueError, match="stale_publication_generation"):
        writer.publish(next_pub, tables, findings=findings)
    assert f.generation == 1 and len(f.receipts) == 1
