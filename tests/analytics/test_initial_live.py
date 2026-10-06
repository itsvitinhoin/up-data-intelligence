"""Live entrypoint exercised only with mocked clients/transport; never Google APIs."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.analytics.cloud.initial import (
    LOCATION,
    POLICY_HASH,
    PROJECT,
    STORE,
    initial_generation,
    preflight,
    run_initial,
)
from src.analytics.cloud.transport import CloudConfig, Transport
from src.analytics.config import AnalyticsPolicy
from src.analytics.job import main
from src.utils.data import digest, timestamp

POLICY_PATH = Path("config/analytics/mx-fashion.dev.json")


def policy():
    return AnalyticsPolicy.from_dict(json.loads(POLICY_PATH.read_text()))


def args():
    return [
        "job",
        "--live",
        "--confirm-project",
        PROJECT,
        "--confirm-store",
        STORE,
        "--store",
        STORE,
        "--policy",
        str(POLICY_PATH),
        "--from",
        "2026-09-01",
        "--to",
        "2026-09-28",
        "--as-of",
        "2026-09-28T03:00:00Z",
        "--project",
        PROJECT,
        "--location",
        LOCATION,
        "--maximum-bytes-billed",
        "1000000000",
        "--maximum-total-bytes-billed",
        "100000000000",
        "--timeout-seconds",
        "300",
        "--full-refresh",
        "--confirm-backfill-complete",
    ]


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--project", "other-project"),
        ("--confirm-project", "other-project"),
        ("--store", "other-store"),
        ("--confirm-store", "other-store"),
        ("--location", "US"),
        ("--from", "2026-09-02"),
        ("--to", "2026-09-29"),
        ("--as-of", "2026-09-29T03:00:00Z"),
        ("--maximum-bytes-billed", "0"),
        ("--maximum-total-bytes-billed", "1"),
    ],
)
def test_guards_before_credential_discovery(monkeypatch, flag, value):
    argv = args()
    argv[argv.index(flag) + 1] = value
    monkeypatch.setattr("sys.argv", argv)
    client = Mock()
    monkeypatch.setattr("google.cloud.bigquery.Client", client)
    with pytest.raises((SystemExit, ValueError)):
        main()
    client.assert_not_called()


@pytest.mark.parametrize("flag", ["--live", "--full-refresh", "--confirm-backfill-complete"])
def test_mandatory_opt_in(monkeypatch, flag):
    argv = args()
    argv.remove(flag)
    monkeypatch.setattr("sys.argv", argv)
    client = Mock()
    monkeypatch.setattr("google.cloud.bigquery.Client", client)
    with pytest.raises(SystemExit):
        main()
    client.assert_not_called()


def test_policy_mismatch_before_client(tmp_path, monkeypatch):
    altered = json.loads(POLICY_PATH.read_text())
    altered["facts_complete"] = False
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(altered))
    argv = args()
    argv[argv.index("--policy") + 1] = str(path)
    monkeypatch.setattr("sys.argv", argv)
    client = Mock()
    monkeypatch.setattr("google.cloud.bigquery.Client", client)
    with pytest.raises(ValueError, match="unapproved_initial_policy"):
        main()
    client.assert_not_called()


def test_live_entrypoint_uses_only_bigquery(monkeypatch):
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr("google.cloud.bigquery.Client", factory)
    runner = Mock(return_value={"publication_id": "synthetic", "status": "completed"})
    monkeypatch.setattr("src.analytics.job.run_initial", runner)
    monkeypatch.setattr("sys.argv", args())
    main()
    factory.assert_called_once_with(project=PROJECT, location=LOCATION)
    assert runner.call_args.kwargs == {"full_refresh": True, "backfill_confirmed": True}
    client.close.assert_called_once()


def completed_receipt():
    return {
        "publication_id": "synthetic-publication",
        "store_id": STORE,
        "policy_hash": POLICY_HASH,
        "generation": 1,
        "as_of": policy().as_of,
        "report_from": policy().report_from,
        "report_to": policy().report_to,
        "status": "completed",
        "analytics_version": "1.0.0",
        "source_watermark": "a" * 64,
    }


def transport(heads=None, receipts=None, populated=False):
    t = Transport(Mock(), CloudConfig(PROJECT, LOCATION, 1000000000, 300, False))
    if heads is None:
        heads = [{"generation": 0, "publication_id": None, "source_watermark": None}]

    def query(sql, params, **kwargs):
        if "record_kind='HEAD'" in sql:
            return deepcopy(heads), None
        if "record_kind='RECEIPT'" in sql:
            return deepcopy(receipts or []), None
        if "COUNT(*) AS row_count" in sql:
            return [{"row_count": int(populated)}], None
        raise AssertionError("unexpected non-preflight query")

    t.query = Mock(side_effect=query)
    return t


@pytest.mark.parametrize(
    "heads,receipts,match",
    [
        ([], [], "head_missing"),
        ([{"generation": 0}, {"generation": 0}], [], "duplicate_head"),
        ([{"generation": 2}], [], "generation_already_advanced"),
        ([{"generation": 1}], [], "generation_already_advanced"),
        ([{"generation": 0}], [completed_receipt()], "head_inconsistent"),
    ],
)
def test_head_guards(heads, receipts, match):
    with pytest.raises(ValueError, match=match):
        preflight(transport(heads, receipts), policy())


def test_generation_zero_existing_rows_blocks():
    with pytest.raises(ValueError, match="target_not_empty"):
        preflight(transport(populated=True), policy())


def test_receipt_reconciled_without_core_read_or_write(monkeypatch):
    receipt = completed_receipt()
    head = {k: receipt[k] for k in ("publication_id", "generation", "source_watermark")}
    t = transport([head], [receipt])
    runner = Mock()
    monkeypatch.setattr("src.analytics.cloud.initial.materialize", runner)
    assert run_initial(t, policy(), full_refresh=True, backfill_confirmed=True) == receipt
    runner.assert_not_called()
    assert all("up_analytics.analytics_publications" in c.args[0] for c in t.query.call_args_list)
    bad = {**receipt, "report_to": "2026-09-29"}
    with pytest.raises(ValueError, match="receipt_mismatch"):
        preflight(transport([head], [bad]), policy())


def test_explicit_initial_generation_and_first_retry(monkeypatch):
    t = transport()
    captured = []

    def materialize(reader, writer, publication):
        captured.append(publication)
        assert reader.transport is writer.transport is t
        return completed_receipt()

    monkeypatch.setattr("src.analytics.cloud.initial.materialize", materialize)
    monkeypatch.setattr("src.analytics.cloud.initial.now", lambda: "2026-09-30T12:00:00Z")
    first = run_initial(t, policy(), full_refresh=True, backfill_confirmed=True)
    second = run_initial(t, policy(), full_refresh=True, backfill_confirmed=True)
    assert first == second and captured[0].publication_id == captured[1].publication_id
    publication = captured[0]
    assert publication.expected_generation == 0 and publication.full_refresh_authorized
    assert publication.source.completeness_confirmed is False
    assert publication.source.generation == digest(
        {
            "store": STORE,
            "policy_hash": POLICY_HASH,
            "snapshot_at": timestamp("2026-09-30T12:00:00Z"),
            "mode": "full_refresh_initial",
        }
    )
    assert initial_generation(policy(), "2026-09-30T12:00:00+00:00") == publication.source
    assert all(
        "up_raw" not in c.args[0] and c.args[0].startswith("SELECT") for c in t.query.call_args_list
    )


def test_paid_metrics_unchanged_for_approved_policy():
    from src.analytics.engine import build

    output = build(policy().reference(), orders=[], customers=[], items=[], events=[])
    assert len(output["tables"]["analytics_store_daily"]) == 27
    assert len(output["tables"]["analytics_funnel_daily"]) == 27
    for rows in output["tables"].values():
        for row in rows:
            for key in ("revenue_paid", "average_order_value_paid", "roas_paid", "ltv_paid"):
                if key in row:
                    assert row[key] is None


def test_container_and_terraform_contract():
    docker = Path("Dockerfile").read_text()
    assert (
        "COPY --chown=0:10001 config/analytics/mx-fashion.dev.json ./config/analytics/mx-fashion.dev.json"
        in docker
    )
    assert "!config/analytics/mx-fashion.dev.json" in Path(".dockerignore").read_text()
    tf = Path("infra/terraform/analytics_runtime.tf").read_text()
    for banned in (
        "google_cloud_scheduler",
        "secret_manager",
        "up_raw",
        "_versions",
        "roles/owner",
        "roles/editor",
        "artifactregistry.writer",
    ):
        assert banned not in tf
    assert 'dataset_id = "up_core"' in tf and "roles/bigquery.dataViewer" in tf
    assert 'dataset_id = "up_analytics"' in tf and "roles/bigquery.dataEditor" in tf
    assert "max_retries     = 0" in tf and "var.analytics_image" in tf
    assert "var.image" not in tf


def test_head_initialization_sql_no_overwrite_or_receipt():
    import re

    sql = Path("sql/analytics/cloud_proposed/initialize_head.sql").read_text()
    executable = "\n".join(line for line in sql.splitlines() if not line.startswith("--"))
    assert re.search(r"\)\s*<=\s*1\s+AS", executable)
    assert re.search(r"\)\s*=\s*1\s+AS", executable)
    assert "WHERE NOT EXISTS" in executable
    assert "UPDATE " not in executable and "DELETE " not in executable
    assert "'RECEIPT'" not in executable
    assert re.search(
        r"SELECT\s+'HEAD'\s*,\s*@store\s*,\s*@policy\s*,\s*0\s*,\s*'initialized'",
        executable,
    )


def test_live_exception_does_not_expose_query_payload(monkeypatch, caplog, capsys):
    import logging

    monkeypatch.setattr("sys.argv", args())
    client = Mock()
    monkeypatch.setattr("google.cloud.bigquery.Client", Mock(return_value=client))
    monkeypatch.setattr(
        "src.analytics.job.run_initial",
        Mock(side_effect=RuntimeError("synthetic-sensitive-customer-value")),
    )
    with caplog.at_level(logging.INFO, logger="upzero"), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "synthetic-sensitive-customer-value" not in caplog.text + capsys.readouterr().err
    assert "analytics_initial_failed" in caplog.text
    client.close.assert_called_once()


def test_live_requires_aggregate_budget_before_credentials(monkeypatch):
    argv = args()
    index = argv.index("--maximum-total-bytes-billed")
    del argv[index : index + 2]
    monkeypatch.setattr("sys.argv", argv)
    client = Mock()
    monkeypatch.setattr("google.cloud.bigquery.Client", client)
    with pytest.raises(SystemExit):
        main()
    client.assert_not_called()
