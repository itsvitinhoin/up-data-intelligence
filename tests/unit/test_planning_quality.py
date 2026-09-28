from datetime import timedelta

import pytest

from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.domain.models import SafeError
from src.ingestion.planning import filters_for, incremental, instant, open_order_windows, windows
from src.quality.rules import purchase_severity, stale
from src.security.lease import local_lease
from src.utils.data import numeric


def settings():
    return Settings("A", "A", "a", "America/Sao_Paulo", "conn", "2026-09-01T00:00:00Z")


def test_temporal_bounds_and_local_order_dates():
    a = instant("2026-09-01")
    b = a + timedelta(days=1)
    assert filters_for("analytics_facts", a, b, "America/Sao_Paulo")["to"] == b.isoformat()
    assert filters_for("orders", a, b, "America/Sao_Paulo")["start_date"] == "2026-08-31"
    assert len(windows("analytics_facts", "2026-09-01", "2026-09-04", "UTC")) == 3


def test_incremental_customers_high_id_and_facts_lookback(tmp_path):
    r = SQLiteRepository(str(tmp_path / "db"))
    c = settings()
    r.write(
        {
            "sync_checkpoints": [
                {
                    "row_key": "a",
                    "store_id": "A",
                    "resource": "customers",
                    "mode": "incremental",
                    "status": "complete",
                    "updated_at": "2026-09-20T00:00:00Z",
                    "high_id": "100",
                },
                {
                    "row_key": "b",
                    "store_id": "A",
                    "resource": "analytics_facts",
                    "mode": "incremental",
                    "status": "complete",
                    "updated_at": "2026-09-20T00:00:00Z",
                    "completed_to": "2026-09-20T00:00:00Z",
                },
            ]
        }
    )
    assert incremental(r, c, "customers", "2026-09-21T00:00:00Z") == ({"limit": 200}, 100)
    assert incremental(r, c, "analytics_facts", "2026-09-21T00:00:00Z")[0]["from"].startswith(
        "2026-09-17"
    )


def test_open_order_list_windows(tmp_path):
    r = SQLiteRepository(str(tmp_path / "db"))
    r.write(
        {
            "orders": [
                {
                    "row_key": "x",
                    "store_id": "A",
                    "order_id": "8",
                    "order_status": "PROCESSING",
                    "created_at": "2025-01-01T15:00:00Z",
                }
            ]
        }
    )
    assert open_order_windows(r, settings()) == [
        {"start_date": "2025-01-01", "end_date": "2025-01-01", "limit": 200}
    ]


@pytest.mark.parametrize(
    "effective,expected",
    [(None, "warning"), ("2026-09-02T00:00:00Z", "warning"), ("2026-09-01T00:00:00Z", "alert")],
)
def test_purchase_capability(effective, expected):
    assert purchase_severity("2026-09-01T00:00:00Z", effective) == expected


def test_freshness_not_event_age():
    assert not stale("2026-09-01T00:00:00Z", "2026-09-01T00:10:00Z", 60)
    assert stale(None, "2026-09-01T00:10:00Z", 60)
    assert stale("2026-09-01T00:00:00Z", "2026-09-02T00:10:00Z", 60)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "not number", "1e30", "0.0000000001", True])
def test_bad_numeric(value):
    with pytest.raises(ValueError):
        numeric(value)


def test_exact_decimal():
    assert numeric("12345678901234567890.123456789") == "12345678901234567890.123456789"


def test_store_writer_mutex(tmp_path):
    with local_lease(str(tmp_path / "lock")):
        with pytest.raises(SafeError, match="store_busy"):
            with local_lease(str(tmp_path / "lock")):
                pass
