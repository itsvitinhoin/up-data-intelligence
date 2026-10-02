"""SQL guards, transport budgets and sanitization with injected fake clients only."""

import json
from pathlib import Path

import pytest
from google.api_core.exceptions import BadRequest

from src.analytics.cloud.transport import CloudConfig
from src.domain.models import SafeError
from src.installation.model import Limits
from src.installation.repository import BigQueryLedger
from tests.installation.test_planner import NOW, graph


class Transport:
    config = CloudConfig("synthetic-dev", "southamerica-east1", 1073741824, 30, False)

    def __init__(self):
        self.calls = []
        self.result = []
        self.error = None

    def query(self, sql, params, **kwargs):
        self.calls.append((sql, params, kwargs))
        if self.error:
            raise self.error
        return self.result, None


def test_cas_and_reservation_sql_scopes_dependencies_capacity_and_parameters():
    c, p, units = graph(1)
    transport = Transport()
    ledger = BigQueryLedger(transport)
    ledger.plans = lambda store=None: [p]
    row = ledger.reserve(units[0], "synthetic-dispatch-token", NOW, Limits())
    sql, params, kwargs = transport.calls[-1]
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    assert "revision=@revision" in sql and "dispatch_token IS NOT DISTINCT FROM @token" in sql
    assert "COUNT(DISTINCT store_id)" in sql and "@capacity" in sql
    assert "UNNEST(JSON_VALUE_ARRAY(@dependencies))" in sql and "ARRAY_LENGTH" in sql
    assert "revision=@config_revision AND sync_enabled=false" in sql
    assert c.store_id not in sql and "synthetic-dispatch-token" not in sql
    assert row["reservation_revision"] == row["revision"] == 2
    assert kwargs["job_id"].startswith("installation_")
    ledger.transition(row, status="RUNNING")
    assert "status=@status AND revision=@revision" in transport.calls[-1][0]


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError("synthetic sensitive"), "bigquery_write_outcome_unknown"),
        (BadRequest("synthetic sensitive"), "installation_work_conflict"),
    ],
)
def test_mutation_outcome_sanitized_never_retry(error, code):
    _, _, units = graph(1)
    transport = Transport()
    transport.error = error
    with pytest.raises(SafeError, match=code):
        BigQueryLedger(transport).transition(units[0], status="RUNNING")
    assert len(transport.calls) == 1 and "sensitive" not in code


def test_source_verification_cas_has_no_value_and_updates_unit_atomically():
    _, _, units = graph(1)
    transport = Transport()
    ledger = BigQueryLedger(transport)
    source = {
        "row_key": "synthetic-source",
        "store_id": "synthetic-mx",
        "connection_id": "synthetic-mx-upzero",
        "source_system": "upzero",
        "status": "pending",
        "secret_resource_name": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    for success in (True, False):
        result = ledger.verified(units[0], source, NOW, success=success)
        assert result["status"] == ("COMPLETE" if success else "BLOCKED")
        sql = transport.calls[-1][0]
        assert (
            "updated_at IS NOT DISTINCT FROM @source_updated" in sql
            and "connection_id=@connection" in sql
            and "store_id=@store" in sql
        )
        assert sql.count("MERGE") == 2


def test_schemas_only_two_new_tables_existing_are_unchanged():
    root = Path("infra/terraform")
    active = json.loads((root / "tables.json").read_text())
    for name in ("installation_plans", "installation_work_units"):
        assert active[name]["dataset"] == "up_ops"
        assert active[name]["cluster"][:2] == ["store_id", "status"]
        schema = json.loads((root / "schemas" / (name + ".json")).read_text())
        assert any(f["name"] == "revision" and f["mode"] == "REQUIRED" for f in schema)
        assert not {"credential", "secret_data", "payload", "position", "cursor"} & {
            f["name"] for f in schema
        }
    terraform = (root / "installation.tf").read_text()
    assert "google_cloud_scheduler" not in terraform and "secretAccessor" not in terraform
    assert 'timeout         = "3600s"' in terraform and "max_retries     = 0" in terraform
    assert "google_service_account.control_plane[each.key].email" in terraform
