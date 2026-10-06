"""Synthetic contact-only projections; no PII fixture from a real customer."""

import pytest

from src.dashboard.contracts import Grant, ReadError
from src.dashboard.http import dispatch
from src.dashboard.queries import build
from src.dashboard.service import DashboardService
from tests.dashboard.test_read_api import (  # noqa: F401
    GRANT,
    KEY,
    PRINCIPAL,
    PROJECT,
    FakeReader,
)
from tests.dashboard.test_read_api import (
    policy as imported_policy,
)


@pytest.fixture
def test_policy():
    return imported_policy.__wrapped__()


@pytest.fixture
def setup(test_policy):
    policy = test_policy
    reader = FakeReader(policy)
    return DashboardService(PROJECT, {policy.store_id: policy}, lambda: reader, KEY), reader


def row():
    return {
        "store_id": "mx-fashion",
        "customer_id": "synthetic",
        "cpf": None,
        "cnpj": "00000000000000",
        "email": "test@example.invalid",
        "phone": None,
        "observed_at": "2026-09-01T00:00:00Z",
    }


def test_detail_contact_is_on_demand_scoped_and_nullable(setup):
    service, reader = setup
    reader.override["customer_contact"] = [row()]
    result = service.customer_contact(PRINCIPAL, GRANT, "synthetic")
    assert result["data"]["cpf"] is None
    assert result["data"]["email"] == "test@example.invalid"
    assert result["data"]["basis"] == "current_core_profile"
    assert "current_core_profile_not_historical_order_contact" in result["metadata"]["limitations"]
    assert [call.name for call in reader.calls] == ["head", "customer_contact"]
    query = reader.calls[-1]
    assert query.parameters["store"] == ("STRING", "mx-fashion")
    assert query.parameters["customer"] == ("STRING", "synthetic")
    assert "test@example.invalid" not in query.sql
    assert "FOR SYSTEM_TIME AS OF @snapshot_at" in query.sql


@pytest.mark.parametrize(
    "principal,grant",
    [
        (None, GRANT),
        (PRINCIPAL, Grant("other", "mx-fashion", "B2B")),
        (PRINCIPAL, Grant("tenant-test", "other-store", "B2B")),
    ],
)
def test_contact_unauthorized_before_reader(setup, principal, grant):
    service, reader = setup
    with pytest.raises(ReadError):
        service.customer_contact(principal, grant, "synthetic")
    assert reader.calls == []


@pytest.mark.parametrize(
    "rows,code",
    [
        ([], "customer_not_found"),
        ([row(), row()], "customer_contact_identity_ambiguous"),
        ([{**row(), "store_id": "other-store"}], "customer_contact_identity_invalid"),
        ([{**row(), "customer_id": "other"}], "customer_contact_identity_invalid"),
        ([{**row(), "email": {"payload": "denied"}}], "customer_contact_invalid"),
    ],
)
def test_contact_missing_ambiguous_or_other_store_fails_closed(setup, rows, code):
    service, reader = setup
    reader.override["customer_contact"] = rows
    with pytest.raises(ReadError, match=code):
        service.customer_contact(PRINCIPAL, GRANT, "synthetic")


def test_http_contact_rejects_bulk_filters(setup):
    service, reader = setup
    reader.override["customer_contact"] = [row()]
    query = {"tenant_id": [GRANT.tenant_id], "store_id": [GRANT.store_id], "operation": ["B2B"]}
    status, result = dispatch(service, "GET", "/v1/customers/synthetic/contact", query, PRINCIPAL)
    assert status == 200 and result["data"]["phone"] is None
    for field in ("cursor", "page_size", "from", "to"):
        with pytest.raises(ReadError, match="unsupported_filter"):
            dispatch(
                service,
                "GET",
                "/v1/customers/synthetic/contact",
                {**query, field: ["1"]},
                PRINCIPAL,
            )


def test_contact_sql_does_not_interpolate_customer_or_store():
    query = build(PROJECT, "customer_contact", store="evil'", customer="evil'", snapshot_at="now")
    assert "evil'" not in query.sql
    assert "store_id=@store" in query.sql and "customer_id=@customer" in query.sql
    assert "LIMIT 2" in query.sql and "payload" not in query.sql
