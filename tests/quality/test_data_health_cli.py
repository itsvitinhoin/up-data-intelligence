import sys
from unittest.mock import patch

import pytest

from src.control_plane.model import Window
from src.quality.data_health import Finding
from src.quality.data_health_cli import main
from tests.quality.test_data_health import AT, store

ARGS = [
    "health",
    "--live",
    "--project",
    "up-data-intelligence-dev",
    "--confirm-project",
    "up-data-intelligence-dev",
    "--store-id",
    "brand-one",
    "--confirm-store",
    "brand-one",
]


@pytest.mark.parametrize(
    "severity,failed,exit_code",
    [("alert", 0, 0), ("alert", 1, 1), ("warning", 1, 0), ("error", 1, 1)],
)
def test_health_exit_is_real_and_warning_does_not_hide_blocking_failure(
    monkeypatch, severity, failed, exit_code
):
    monkeypatch.setattr(sys, "argv", ARGS)
    with (
        patch("google.cloud.bigquery.Client"),
        patch("src.quality.data_health_cli.Transport") as transport,
        patch("src.quality.data_health_cli.DataHealth") as checker,
    ):
        transport.return_value.query.return_value = ([store().row()], None)
        checker.return_value.check.return_value = (
            Window.previous_closed_day(store().timezone, AT),
            [Finding("no_pending_raw", failed, severity=severity)],
        )
        assert main() == exit_code
        rows = checker.return_value.persist.call_args.args[0]
        assert rows[0]["record_id"] is None
        assert rows[0]["failed_count"] == failed


def test_invalid_gate_fails_before_client_construction(monkeypatch):
    monkeypatch.setattr(sys, "argv", [x for x in ARGS if x != "--live"])
    with patch("google.cloud.bigquery.Client") as client:
        assert main() == 1
        client.assert_not_called()


def test_missing_store_never_returns_green(monkeypatch):
    monkeypatch.setattr(sys, "argv", ARGS)
    with (
        patch("google.cloud.bigquery.Client"),
        patch("src.quality.data_health_cli.Transport") as transport,
    ):
        transport.return_value.query.return_value = ([], None)
        assert main() == 1


def test_unknown_write_is_not_retried(monkeypatch):
    monkeypatch.setattr(sys, "argv", ARGS)
    with (
        patch("google.cloud.bigquery.Client"),
        patch("src.quality.data_health_cli.Transport") as transport,
        patch("src.quality.data_health_cli.DataHealth") as checker,
    ):
        transport.return_value.query.return_value = ([store().row()], None)
        checker.return_value.check.return_value = (
            Window.previous_closed_day(store().timezone, AT),
            [Finding("no_pending_raw", 0)],
        )
        checker.return_value.persist.side_effect = TimeoutError()
        assert main() == 1
        checker.return_value.persist.assert_called_once()


def test_global_scope_is_bounded_and_detects_duplicate_stores(monkeypatch):
    monkeypatch.setattr(sys, "argv", ARGS[:6] + ["--all-stores", "--max-stores", "1"])
    with (
        patch("google.cloud.bigquery.Client"),
        patch("src.quality.data_health_cli.Transport") as transport,
    ):
        transport.return_value.query.return_value = ([store().row(), store().row()], None)
        assert main() == 1
        sql, parameters = transport.return_value.query.call_args.args
        assert "LIMIT @limit" in sql and "FOR SYSTEM_TIME AS OF @snapshot" in sql


def test_help_never_discovers_credentials(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["health", "--help"])
    with patch("google.cloud.bigquery.Client") as client, pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 0
    client.assert_not_called()
