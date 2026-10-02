"""Synthetic operational evidence; no external clients or real run/customer data."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal, ReadError
from src.dashboard.http import dispatch
from src.dashboard.installation import InstallationProgress, checkpoint_window
from src.dashboard.installation_queries import build_installation
from src.dashboard.queries import Query
from src.dashboard.service import DashboardService
from tests.dashboard.test_read_api import head

PROJECT = "up-data-intelligence-dev"
GRANT = Grant("synthetic-tenant", "mx-fashion", "B2B")
PRINCIPAL = Principal("synthetic-admin", "ADMIN_UP", frozenset({GRANT}))
AT = "2026-09-30T00:00:00Z"


class Reader:
    def __init__(self) -> None:
        self.policy = AnalyticsPolicy.from_dict(
            json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
        )
        self.calls: list[Query] = []
        self.registry: list[dict[str, Any]] = [
            {
                "store_id": "mx-fashion",
                "status": "ACTIVE",
                "operation_b2b": True,
                "history_complete": False,
                "facts_complete": False,
                "timezone": "America/Sao_Paulo",
                "currency": "BRL",
                "policy_version": "1.0.0",
                "upzero_enabled": True,
                "meta_enabled": False,
                "upzero_connection_id": "synthetic-connection",
                "meta_connection_id": None,
                "updated_at": AT,
                "snapshot_at": AT,
                "facts_coverage_from": None,
                "facts_coverage_to": None,
            }
        ]
        self.connections = [
            {
                "source_system": "upzero",
                "connection_id": "synthetic-connection",
                "status": "active",
                "updated_at": AT,
            }
        ]
        self.resources = [
            self.resource(name) for name in ("customers", "orders", "analytics_facts")
        ]
        self.heads = [head(self.policy)]

    def resource(self, name: str, status: str = "complete", **extra: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "source": "upzero",
            "connection_id": "synthetic-connection",
            "resource": name,
            "run_id": f"synthetic-{name}",
            "checkpoint_status": status,
            "mode": "backfill",
            "updated_at": AT,
            "last_success_at": AT,
            "filters": {},
            "pending_raw": False,
            "run_status": "completed",
            "metrics_version": 2,
            "source_records_read": 10,
            "core_records_processed": 10,
            "core_records_failed": 0,
            "blocked_count": 0,
            "pending_count": 0,
            "pending_raw_count": 0,
        }
        row.update(extra)
        return row

    def query(
        self, query: Query, *, request_id: str, store_id: str, generation: int | None
    ) -> list[dict[str, Any]]:
        assert store_id == GRANT.store_id
        assert query.parameters["store"] == ("STRING", GRANT.store_id)
        self.calls.append(query)
        return copy.deepcopy(
            {
                "installation_registry": self.registry,
                "installation_sources": self.connections,
                "installation_resources": self.resources,
                "head": self.heads,
            }[query.name]
        )


@pytest.fixture
def reader() -> Reader:
    return Reader()


def service(r: Reader) -> DashboardService:
    return DashboardService(
        PROJECT,
        {r.policy.store_id: r.policy},
        lambda: r,
        b"synthetic-signing-key-at-least-32-bytes",
    )


def read(r: Reader) -> dict[str, Any]:
    status, body = dispatch(
        service(r),
        "GET",
        "/v1/stores/mx-fashion/installation",
        {"tenant_id": [GRANT.tenant_id], "operation": ["B2B"]},
        PRINCIPAL,
    )
    assert status == 200
    return body["data"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "grant,principal,status",
    [
        (Grant("wrong", "mx-fashion", "B2B"), PRINCIPAL, 403),
        (Grant(GRANT.tenant_id, "another", "B2B"), PRINCIPAL, 403),
        (Grant(GRANT.tenant_id, "mx-fashion", "B2C"), PRINCIPAL, 400),
        (GRANT, None, 401),
    ],
)
def test_authorization_before_query(
    reader: Reader, grant: Grant, principal: Principal | None, status: int
) -> None:
    with pytest.raises(ReadError) as exc:
        service(reader).installation(principal, grant)
    assert exc.value.status == status
    assert not reader.calls


def test_store_missing_and_duplicate_registry(reader: Reader) -> None:
    reader.registry = []
    with pytest.raises(ReadError, match="store_not_configured"):
        read(reader)
    reader.registry = [{"store_id": "other"}]
    with pytest.raises(ReadError, match="installation_registry_invalid"):
        read(reader)


def test_b2c_only_registry_blocked(reader: Reader) -> None:
    reader.registry[0]["operation_b2b"] = False
    with pytest.raises(ReadError, match="store_operation_forbidden"):
        read(reader)


def test_partial_certified_window_not_history_claim(reader: Reader) -> None:
    row = read(reader)
    assert row["overall_state"] == "PARTIAL"
    assert row["history_complete"] is False and row["facts_complete"] is False
    assert row["recommended_preview_window"]["from"] == reader.policy.report_from
    assert row["recommended_preview_window"]["to"] == reader.policy.report_to
    assert row["progress"] == {
        "kind": "RECORDS",
        "processed": 30,
        "total": None,
        "percent": None,
        "eta_seconds": None,
    }
    assert len(reader.calls) == 4
    assert all(q.parameters.get("snapshot_at") == ("TIMESTAMP", AT) for q in reader.calls[1:])


@pytest.mark.parametrize(
    "checkpoint,run,pending,blocked,state",
    [
        ("complete", "completed", 0, 0, "COMPLETE"),
        ("running", "running", 1, 0, "RUNNING"),
        ("running", "failed", 1, 1, "BLOCKED"),
        ("needs_review", "completed_with_errors", 1, 1, "BLOCKED"),
        ("recovered", "completed_with_errors", 0, 0, "COMPLETE"),
        ("recovered", "failed", 0, 0, "COMPLETE"),
    ],
)
def test_resource_lifecycle(
    reader: Reader, checkpoint: str, run: str, pending: int, blocked: int, state: str
) -> None:
    reader.resources[0].update(
        checkpoint_status=checkpoint, run_status=run, pending_count=pending, blocked_count=blocked
    )
    row = read(reader)
    customer = next(r for r in row["resources"] if r["resource"] == "customers")
    assert customer["state"] == state
    assert customer["last_error_code"] == ("sync_requires_review" if blocked else None)
    assert row["overall_state"] == ("BLOCKED" if blocked else "PARTIAL")


@pytest.mark.parametrize("mode", ["backfill", "incremental", "open_orders", "replay", "reconcile"])
def test_orders_known_mode_is_preserved(reader: Reader, mode: str) -> None:
    next(r for r in reader.resources if r["resource"] == "orders")["mode"] = mode
    orders = next(r for r in read(reader)["resources"] if r["resource"] == "orders")
    assert orders["mode"] == mode


def test_pending_raw_is_boolean_without_raw_identifier(reader: Reader) -> None:
    reader.resources[2].update(pending_raw=True, pending_raw_count=1, pending_count=1)
    row = read(reader)
    assert (
        next(r for r in row["resources"] if r["resource"] == "analytics_facts")["pending_raw"]
        is True
    )
    assert "pending_raw_id" not in json.dumps(row)


def test_no_source_and_no_publication_installing(reader: Reader) -> None:
    reader.connections = []
    reader.resources = []
    reader.heads = []
    row = read(reader)
    assert row["overall_state"] == "INSTALLING"
    assert row["sources"][0]["configured"] is False
    assert row["sources"][0]["active"] is None
    assert row["recommended_preview_window"] is None
    assert row["progress"]["percent"] is None
    assert row["progress"]["kind"] == "UNKNOWN"


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "receipt", "currency", "policy_version"]
)
def test_no_safe_window_without_certification(reader: Reader, change: str) -> None:
    if change == "missing":
        reader.heads = []
    if change == "duplicate":
        reader.heads *= 2
    if change == "receipt":
        reader.heads[0]["receipt_status"] = "failed"
    if change in {"currency", "policy_version"}:
        reader.registry[0][change] = "unmatched"
    row = read(reader)
    assert row["recommended_preview_window"] is None
    assert row["available_window"] is None
    assert row["overall_state"] == ("INSTALLING" if change == "missing" else "BLOCKED")


def test_no_sensitive_information_in_projection(reader: Reader) -> None:
    secret = "synthetic-sensitive-do-not-export"
    reader.registry[0].update(
        secret=secret, email=secret, history_coverage={"confirmed_by": secret}
    )
    reader.connections[0]["secret_resource_name"] = secret
    reader.resources[0].update(
        error_summary=secret, pending_raw_id=secret, filters={"cursor": secret}
    )
    body = json.dumps(read(reader))
    assert secret not in body
    assert not any(
        word in body for word in ('"secret"', '"email"', '"cpf"', '"cnpj"', '"phone"', '"filters"')
    )


def test_queries_scope_and_real_catalog(reader: Reader) -> None:
    malicious = "store' OR 1=1"
    for name in ("installation_registry", "installation_sources", "installation_resources"):
        q = build_installation(PROJECT, name, malicious, AT)
        assert malicious not in q.sql and q.parameters["store"][1] == malicious
        assert "@store" in q.sql
        assert "up_raw" not in q.sql and "secret_resource_name" not in q.sql
    sql = build_installation(PROJECT, "installation_resources", "mx-fashion", AT).sql
    assert "up_core.source_connections" in sql and "up_ops.sync_checkpoints" in sql
    assert "AS c FOR SYSTEM_TIME" in sql
    assert "r.store_id=c.store_id" in sql and "r.source=s.source_system" in sql
    assert "('complete','recovered')" in sql
    assert "SUM(" not in sql  # No sum across overlapping backfill/replay attempts.


def test_unknown_legacy_counters_do_not_fallback(reader: Reader) -> None:
    reader.resources[0].update(metrics_version=None, records_written=999)
    row = read(reader)
    assert row["resources"][1]["records_processed"] is None  # alphabetical: customers
    assert row["progress"]["processed"] is None
    with pytest.raises(ValueError, match="denominator"):
        InstallationProgress("RECORDS", percent=68, processed=344000)


def test_known_progress_contract() -> None:
    assert InstallationProgress("CHUNKS", percent=50, processed=1, total=2).percent == 50


def test_exact_checkpoint_window_no_min_max_bridging(reader: Reader) -> None:
    r = reader.resource("orders", filters={"start_date": "2026-09-01", "end_date": "2026-09-01"})
    assert checkpoint_window(r, "America/Sao_Paulo") == (
        "2026-09-01T03:00:00Z",
        "2026-09-02T03:00:00Z",
    )
    assert checkpoint_window(reader.resource("customers"), "America/Sao_Paulo") == (None, None)
    r["pending_raw_count"] = 1
    assert checkpoint_window(r, "America/Sao_Paulo") == (None, None)


def test_other_connection_does_not_grant_coverage(reader: Reader) -> None:
    reader.connections[0]["connection_id"] = "old-connection"
    row = read(reader)
    assert not row["sources"][0]["configured"]
    assert all(r["state"] == "PENDING" for r in row["resources"])


def test_read_only_filter_allowlist(reader: Reader) -> None:
    with pytest.raises(ReadError, match="unsupported_filter"):
        dispatch(
            service(reader),
            "GET",
            "/v1/stores/mx-fashion/installation",
            {"secret": ["synthetic"]},
            PRINCIPAL,
        )
    assert not reader.calls


def test_ready_requires_both_registry_and_publication_completeness(reader: Reader) -> None:
    from dataclasses import replace

    from src.analytics.policy import HistoryCoverage

    reader.registry[0].update(history_complete=True, facts_complete=True)
    assert read(reader)["overall_state"] == "PARTIAL"  # Publication still has partial history.
    proof = HistoryCoverage(
        reader.policy.store_id,
        reader.policy.history_from,
        reader.policy.as_of,
        "synthetic-proof",
        "synthetic-verifier",
        True,
        True,
    )
    reader.policy = replace(
        reader.policy, history_complete=True, facts_complete=True, history_coverage=proof
    )
    reader.heads = [head(reader.policy)]
    assert read(reader)["overall_state"] == "READY"


def test_other_sources_are_generic_and_missing_status_stays_unknown(reader: Reader) -> None:
    reader.connections.append(
        {"source_system": "erp", "connection_id": "synthetic-erp", "status": None}
    )
    data = read(reader)
    source = next(s for s in data["sources"] if s["source"] == "erp")
    assert source["active"] is None
    assert source["last_error_code"] == "source_status_unknown"
    assert data["overall_state"] == "BLOCKED"


def test_four_recovered_checkpoints_do_not_create_active_failure(reader: Reader) -> None:
    reader.resources[0].update(
        checkpoint_status="recovered",
        run_status="completed_with_errors",
        core_records_failed=4,
        blocked_count=0,
        pending_count=0,
    )
    data = read(reader)
    customers = next(r for r in data["resources"] if r["resource"] == "customers")
    assert customers["records_failed"] == 4  # Historical attempt counter is not rewritten.
    assert customers["state"] == "COMPLETE" and customers["last_error_code"] is None


def test_one_reader_budget_session_and_consistent_snapshot(reader: Reader) -> None:
    from unittest.mock import Mock

    factory = Mock(return_value=reader)
    api = DashboardService(
        PROJECT,
        {reader.policy.store_id: reader.policy},
        factory,
        b"synthetic-signing-key-at-least-32-bytes",
    )
    api.installation(PRINCIPAL, GRANT)
    factory.assert_called_once()
    assert len({q.parameters.get("snapshot_at") for q in reader.calls[1:]}) == 1


def test_draft_pending_onboarding_is_installing_not_blocked(reader: Reader) -> None:
    reader.registry[0]["status"] = "DRAFT"
    reader.connections[0]["status"] = "pending"
    reader.resources = []
    reader.heads = []
    data = read(reader)
    assert data["overall_state"] == "INSTALLING"
    assert data["recommended_preview_window"] is None
    assert data["sources"][0]["configured"] is True
    assert data["sources"][0]["active"] is None
    assert data["sources"][0]["state"] == "PENDING"
    assert data["sources"][0]["last_error_code"] is None
    assert all(r["state"] == "PENDING" for r in data["resources"])


@pytest.mark.parametrize("status", ["inactive", "disabled", "error", "arbitrary-unknown"])
def test_non_pending_invalid_source_remains_blocked(reader: Reader, status: str) -> None:
    reader.connections[0]["status"] = status
    assert read(reader)["overall_state"] == "BLOCKED"
