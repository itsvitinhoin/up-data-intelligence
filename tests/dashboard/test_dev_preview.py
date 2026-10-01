"""Offline tests for the loopback-only Overview server boundary."""

import json
import sys
from typing import Any
from unittest.mock import Mock

import pytest

from src.dashboard.dev_preview_server import create_dev_preview_app, main


def call(app: Any, path: str, *, method: str = "GET", token: str = "") -> tuple[str, Any]:
    statuses: list[str] = []
    body = b"".join(
        app(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "QUERY_STRING": "tenant_id=demo-up&operation=B2B",
                "HTTP_X_DASHBOARD_PREVIEW_TOKEN": token,
            },
            lambda status, headers: statuses.append(status),
        )
    )
    return statuses[0], json.loads(body)


def test_preview_exposes_only_overview_with_ephemeral_server_token():
    service = Mock()
    service.overview.return_value = {"data": {"requested_revenue": "10.00"}}
    token = "t" * 40
    factory = Mock(return_value=service)
    app = create_dev_preview_app(factory, tenant_id="demo-up", store_id="mx-fashion", token=token)
    path = "/v1/stores/mx-fashion/overview"
    assert call(app, path)[0] == "401 Unauthorized"
    assert call(app, path, token="wrong-token")[0] == "401 Unauthorized"
    assert factory.call_count == 0
    status, payload = call(app, path, token=token)
    assert status == "200 OK"
    assert payload["data"]["requested_revenue"] == "10.00"
    assert token not in json.dumps(payload)
    assert service.overview.call_args.args[1].store_id == "mx-fashion"
    assert call(app, "/v1/customers", token=token)[0] == "404 Not Found"
    assert call(app, path, method="POST", token=token)[0] == "405 Method Not Allowed"
    assert service.overview.call_count == 1


def test_preview_refuses_public_bind_and_missing_explicit_flag(monkeypatch: pytest.MonkeyPatch):
    token = "t" * 40
    monkeypatch.setenv("DASHBOARD_DEV_PREVIEW_TOKEN", token)
    required = [
        "preview",
        "--project",
        "up-data-intelligence-dev",
        "--location",
        "southamerica-east1",
        "--policy",
        "config/analytics/mx-fashion.dev.json",
        "--tenant-id",
        "demo-up",
        "--store-id",
        "mx-fashion",
        "--confirm-store",
        "mx-fashion",
    ]
    monkeypatch.setattr(sys, "argv", [*required, "--allow-bq-read", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        main()
    monkeypatch.setattr(sys, "argv", required)
    with pytest.raises(SystemExit):
        main()


@pytest.mark.parametrize(
    "path",
    [
        "/v1/orders",
        "/v1/acquisition",
        "/v1/customers",
        "/v1/customers/synthetic",
        "/v1/customers/synthetic/orders",
        "/v1/retention",
        "/v1/products",
        "/v1/funnel",
        "/v1/geography",
    ],
)
def test_preview_explicit_b2b_allowlist(path):
    service = Mock()
    for name in [
        "orders",
        "acquisition",
        "customers",
        "customer",
        "customer_orders",
        "retention",
        "products",
        "funnel",
        "geography",
    ]:
        getattr(service, name).return_value = {"data": []}
    factory = Mock(return_value=service)
    app = create_dev_preview_app(
        factory, tenant_id="demo-up", store_id="mx-fashion", token="t" * 40
    )

    def request(store, token):
        statuses = []
        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "GET",
                    "PATH_INFO": path,
                    "QUERY_STRING": f"tenant_id=demo-up&operation=B2B&store_id={store}",
                    "HTTP_X_DASHBOARD_PREVIEW_TOKEN": token,
                },
                lambda status, headers: statuses.append(status),
            )
        )
        return statuses[0], json.loads(body)

    assert request("other-store", "t" * 40)[0] == "404 Not Found"
    assert request("mx-fashion", "")[0] == "401 Unauthorized"
    assert factory.call_count == 0
    assert request("mx-fashion", "t" * 40)[0] == "200 OK"


@pytest.mark.parametrize(
    "path", ["/v1/performance", "/v1/admin", "/v1/meta", "/v1/stores/other-store/overview"]
)
def test_preview_rejects_unapproved_resources(path):
    factory = Mock()
    app = create_dev_preview_app(
        factory, tenant_id="demo-up", store_id="mx-fashion", token="t" * 40
    )
    assert call(app, path, token="t" * 40)[0] == "404 Not Found"
    assert factory.call_count == 0
