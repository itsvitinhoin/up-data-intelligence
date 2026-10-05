from datetime import UTC, datetime

import pytest

from src.admin.integration_reads import IntegrationReader
from src.dashboard.contracts import ReadError
from src.product_auth.http import create_read_app
from src.product_auth.session import Sessions
from src.utils.data import digest
from tests.product_auth.test_access import Repository, Verifier, call


class Reader:
    def __init__(self):
        self.calls = []
        self.rows = [
            {
                "store_id": "technical-a",
                "status": "ACTIVE",
                "sync_enabled": True,
                "facts_coverage_from": datetime(2026, 9, 1, tzinfo=UTC),
                "facts_coverage_to": datetime(2026, 10, 5, tzinfo=UTC),
                "sources": [
                    {"source_system": "upzero", "status": "active", "credential_configured": True},
                    {"source_system": "meta", "status": "pending", "credential_configured": False},
                ],
            }
        ]

    def query(self, query, **context):
        self.calls.append(query)
        return self.rows


def test_summary_single_bounded_query_safe_projection():
    repo, reader = Repository(), Reader()
    app = create_read_app(
        lambda: Sessions(Verifier(), repo),
        lambda _: None,
        lambda: IntegrationReader("test-project", reader),
    )
    status, value, headers = call(app, "/v1/admin/brands")
    assert status == 200
    assert len(reader.calls) == 1
    query = reader.calls[0]
    assert query.parameters == {"stores": ("STRING", '["technical-a"]')}
    assert "@stores" in query.sql and "LIMIT 1001" in query.sql
    assert "technical-a" not in query.sql
    row = value["data"][0]
    assert row["active_connections"] == 1
    assert row["pending_connections"] == 1
    assert row["created_at"] is None
    assert row["coverage_from"] == "2026-09-01T00:00:00+00:00"
    assert "technical-a" not in str(value)
    assert "secret_resource_name" not in str(value)
    assert headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize(
    "role,cookie,query,expected",
    [
        ("CLIENT_USER", "verified-cookie", "", 403),
        ("ADMIN_UP", "invalid", "", 401),
        ("ADMIN_UP", "verified-cookie", "tenant_id=other", 400),
        ("ADMIN_UP", "verified-cookie", "store_id=other", 400),
    ],
)
def test_no_reader_for_unauthorized_or_browser_scope(role, cookie, query, expected):
    repo = Repository(role, workspace="workspace-a" if role == "CLIENT_USER" else None)

    def forbidden():
        raise AssertionError("metadata reader must not be constructed")

    app = create_read_app(lambda: Sessions(Verifier(), repo), lambda _: None, forbidden)
    assert call(app, "/v1/admin/brands", query, cookie=cookie)[0] == expected


@pytest.mark.parametrize(
    "mutation", ["other_store", "duplicate_store", "missing_store", "duplicate_source"]
)
def test_inventory_mismatch_fail_closed(mutation):
    repo, reader = Repository(), Reader()
    if mutation == "other_store":
        reader.rows[0]["store_id"] = "another-store"
    elif mutation == "duplicate_store":
        reader.rows *= 2
    elif mutation == "missing_store":
        reader.rows = []
    else:
        reader.rows[0]["sources"] *= 2
    access = Sessions(Verifier(), repo).authenticate("verified-cookie")
    with pytest.raises(ReadError):
        IntegrationReader("test-project", reader).summary(access.admin(), access.workspaces)


def health_reader(monkeypatch):
    from src.quality.data_health import RULES

    monkeypatch.setattr("src.admin.integration_reads.now", lambda: "2026-10-05T12:00:00Z")
    reader = Reader()
    groups = {
        "registry": [
            {
                "store_id": "technical-a",
                "timezone": "America/Sao_Paulo",
                "status": "ACTIVE",
                "sync_enabled": True,
                "facts_coverage_from": "2026-09-01T03:00:00Z",
                "facts_coverage_to": "2026-10-05T03:00:00Z",
            }
        ],
        "source": [
            {
                "store_id": "technical-a",
                "connection_id": "up-a",
                "source_system": "upzero",
                "status": "active",
            }
        ],
        "checkpoint": [
            {
                "store_id": "technical-a",
                "connection_id": "up-a",
                "resource": "customers",
                "run_id": "r1",
                "plan_key": "p1",
                "status": "complete",
                "pending_raw": False,
            }
        ],
        "run": [
            {
                "store_id": "technical-a",
                "source": "upzero",
                "resource": "customers",
                "run_id": "r1",
                "plan_key": "p1",
                "status": "completed",
                "started_at": "2026-10-05T03:01:00Z",
                "finished_at": "2026-10-05T03:05:00Z",
                "core_records_failed": 0,
                "core_records_processed": 12,
                "core_pages_processed": 1,
            }
        ],
        "health": [
            {
                "store_id": "technical-a",
                "rule_id": rule,
                "row_key": digest(["technical-a", "2026-10-05T03:00:00+00:00", rule]),
                "severity": "alert",
                "failed_count": 0,
                "checked_count": 1,
                "checked_at": "2026-10-05T07:00:00Z",
            }
            for rule in RULES
        ],
    }
    import json

    reader.rows = [
        {"kind": kind, "payload": json.dumps(row)} for kind, rows in groups.items() for row in rows
    ]
    return reader, groups


def health_call(reader):
    repo = Repository()
    app = create_read_app(
        lambda: Sessions(Verifier(), repo),
        lambda _: None,
        lambda: IntegrationReader("test-project", reader),
    )
    return call(
        app,
        "/v1/admin/integrations/health",
        "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B",
    )


def test_health_current_certified_evidence_not_installation_complete(monkeypatch):
    reader, _ = health_reader(monkeypatch)
    status, envelope, _ = health_call(reader)
    assert status == 200
    source = envelope["data"]["sources"][0]
    assert source["health"] == "HEALTHY"
    assert source["coverage_certified"] is True
    assert source["last_success_at"] == "2026-10-05T03:05:00Z"
    assert envelope["data"]["next_sync_at"] is None
    assert envelope["data"]["blocking_findings"] == 0
    assert len(reader.calls) == 1
    assert "@store" in reader.calls[0].sql
    for forbidden in ("secret_resource_name", "error_summary", "position", "filters", "high_id"):
        assert forbidden not in reader.calls[0].sql


@pytest.mark.parametrize(
    "change,expected",
    [
        ("stale", "STALE"),
        ("gap", "PARTIAL"),
        ("review", "ERROR"),
        ("pending", "PARTIAL"),
        ("disabled", "DISABLED"),
        ("failed", "PARTIAL"),
    ],
)
def test_health_fail_closed_and_last_attempt_not_success(monkeypatch, change, expected):
    reader, groups = health_reader(monkeypatch)
    if change == "stale":
        for row in groups["health"]:
            row["checked_at"] = "2026-10-04T07:00:00Z"
    elif change == "gap":
        groups["health"][0]["failed_count"] = 1
        next(r for r in groups["health"] if r["rule_id"] == "upzero_orders_covered")[
            "failed_count"
        ] = 1
    elif change == "review":
        groups["checkpoint"][0]["status"] = "needs_review"
    elif change == "pending":
        groups["checkpoint"][0]["pending_raw"] = True
    elif change == "disabled":
        groups["source"][0]["status"] = "disabled"
    else:
        groups["run"][0]["status"] = "failed"
        next(r for r in groups["health"] if r["rule_id"] == "upzero_customers_fresh")[
            "failed_count"
        ] = 1
    import json

    reader.rows = [
        {"kind": kind, "payload": json.dumps(row)} for kind, rows in groups.items() for row in rows
    ]
    status, value, _ = health_call(reader)
    assert status == 200
    source = value["data"]["sources"][0]
    assert source["health"] == expected
    if change in {"failed", "pending", "review"}:
        assert source["last_success_at"] is None


def test_health_wrong_workspace_no_io():
    repo = Repository()

    def forbidden():
        raise AssertionError("Unauthorized metadata IO")

    app = create_read_app(lambda: Sessions(Verifier(), repo), lambda _: None, forbidden)
    assert (
        call(
            app,
            "/v1/admin/integrations/health",
            "tenant_id=tenant-a&workspace_operation_id=other&operation=B2B",
        )[0]
        == 403
    )


def test_recent_health_execution_for_old_cutoff_is_not_current(monkeypatch):
    import json

    reader, groups = health_reader(monkeypatch)
    for row in groups["health"]:
        row["row_key"] = digest(["technical-a", "2026-10-04T03:00:00+00:00", row["rule_id"]])
    reader.rows = [
        {"kind": kind, "payload": json.dumps(row)} for kind, rows in groups.items() for row in rows
    ]
    status, value, _ = health_call(reader)
    assert status == 200
    assert value["data"]["health_evidence_current"] is False
    assert value["data"]["sources"][0]["health"] == "STALE"


@pytest.mark.parametrize("issue", [None, "missing", "failed"])
def test_enrichment_health_requires_complete_current_extended_rule_set(monkeypatch, issue):
    import json

    from src.quality.data_health import ENRICHMENT_RULES

    reader, groups = health_reader(monkeypatch)
    for rule in ENRICHMENT_RULES:
        if issue == "missing" and rule == ENRICHMENT_RULES[-1]:
            continue
        groups["health"].append(
            dict(
                groups["health"][0],
                rule_id=rule,
                row_key=digest(["technical-a", "2026-10-05T03:00:00+00:00", rule]),
                failed_count=int(issue == "failed" and rule == "upzero_catalog_certified"),
            )
        )
    reader.rows = [
        {"kind": k, "payload": json.dumps(row)} for k, rows in groups.items() for row in rows
    ]
    status, value, _ = health_call(reader)
    assert status == 200
    assert (
        value["data"]["sources"][0]["health"]
        == ({None: "HEALTHY", "missing": "STALE", "failed": "PARTIAL"}[issue])
    )
