import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.analytics.provisioning import ACTIVE_ANALYTICS_TABLES
from src.bigquery.catalog import TABLES
from src.bigquery.repository import BigQueryRepository, merge_sql
from src.domain.models import SafeError


def test_generated_schemas_match_catalog():
    for name, spec in TABLES.items():
        fields = json.loads(Path(f"infra/terraform/schemas/{name}.json").read_text())
        assert {f["name"]: f["type"] for f in fields} == spec.fields
        if name != "write_buffer":
            assert "store_id" in spec.fields
    manifest = json.loads(Path("infra/terraform/tables.json").read_text())
    proposed = json.loads(Path("infra/terraform/meta_tables.proposed.json").read_text())
    assert not set(manifest) & set(proposed)
    assert set(manifest) | set(proposed) == set(TABLES) | ACTIVE_ANALYTICS_TABLES
    assert not any(s.dataset == "up_analytics" for s in TABLES.values())


def repo():
    r = object.__new__(BigQueryRepository)
    r.project = "example-project"
    r.location = "US"
    r.client = Mock()
    return r


def test_bq_batch_atomic_and_json_object():
    r = repo()
    row = {"row_key": "k", "store_id": "A", "customer_id": "1"}
    r.write({"customers": [row, row], "customers_versions": [row | {"row_key": "v"}]})
    parameters = r.client.query.call_args.kwargs["job_config"].query_parameters
    data = [json.loads(v) for v in parameters[0].values]
    assert len(data) == 2
    assert data[0]["record"] == row
    sql = r.client.query.call_args.args[0]
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    assert "T.store_id=S.store_id" in sql
    assert sql.count("MERGE ") == 2


def test_bq_parameterized_reads_and_redacted_errors():
    r = repo()
    r.client.query.return_value.result.return_value = [
        SimpleNamespace(body='{"row_key":"k","store_id":"A"}')
    ]
    assert r.read("customers", "A", ["not SQL"]) == [{"row_key": "k", "store_id": "A"}]
    q = r.client.query.call_args.args[0]
    assert "@store" in q and "not SQL" not in q
    r.client.query.side_effect = RuntimeError("REAL_SECRET")
    with pytest.raises(SafeError, match="bigquery_read_failed") as e:
        r.read("customers", "A")
    assert "REAL_SECRET" not in str(e.value)


def test_sql_uses_cast_not_silent_safe_cast():
    q = merge_sql("example-project", "orders")
    assert "SAFE_CAST" not in q and "AS NUMERIC" in q
    assert "QUALIFY ROW_NUMBER()" in q


def test_schema_contains_required_commerce_and_tracking():
    assert {
        "requested_total",
        "fulfilled_total",
        "total",
        "requested_items_qty",
        "fulfilled_items_qty",
        "total_items_qty",
    } <= TABLES["orders"].fields.keys()
    assert {
        "fbclid",
        "fbc",
        "fbp",
        "gclid",
        "landing_url",
        "referrer",
        "meta_campaign_id",
        "parse_status",
        "order_id",
    } <= TABLES["analytics_events"].fields.keys()


def test_raw_json_numeric_canonicalization_and_exact_money():
    from src.bigquery.repository import decode_row
    from src.utils.data import digest

    raw = decode_row(
        '{"payload":{"data":[{"id":1,"value":25,"quantity":2,"event_id":"x"}]}}',
        "upzero_analytics_facts",
    )
    assert digest(raw["payload"]) == digest(
        {"data": [{"id": 1, "value": 25.0, "quantity": 2, "event_id": "x"}]}
    )
    order = decode_row('{"total":12345678901234567890.123456789}', "orders")
    assert order["total"] == "12345678901234567890.123456789"


def test_bigquery_streamed_replay_uses_bound_scope():
    r = repo()
    r.client.query.return_value.result.return_value = iter(
        [SimpleNamespace(body='{"store_id":"A","payload":{"data":[]}}')]
    )
    assert list(r.iter_find("upzero_customers", "A", "run_id", ["run"]))[0]["store_id"] == "A"
    sql = r.client.query.call_args.args[0]
    assert "@store" in sql and "@values" in sql and "ORDER BY `ingested_at`" in sql
