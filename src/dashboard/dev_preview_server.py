"""Explicit, loopback-only B2B Analytics V1 preview; never production auth."""

import argparse
import hmac
import json
import os
import re
import secrets
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, make_server

from google.cloud import bigquery

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal
from src.dashboard.http import create_wsgi_app
from src.dashboard.intelligence import IntelligenceDashboardService
from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.dashboard.service import DashboardService


def create_dev_preview_app(
    service_factory: Callable[[], DashboardService],
    *,
    tenant_id: str,
    store_id: str,
    token: str,
) -> Callable[..., Iterable[bytes]]:
    if not tenant_id or not store_id or len(token) < 32:
        raise ValueError("invalid_dev_preview_configuration")
    grant = Grant(tenant_id, store_id, "B2B")
    principal = Principal("local-dev-preview", "ADMIN_UP", frozenset({grant}))

    def authenticate(environ: Mapping[str, Any]) -> Principal | None:
        supplied = str(environ.get("HTTP_X_DASHBOARD_PREVIEW_TOKEN", ""))
        return principal if hmac.compare_digest(supplied, token) else None

    protected = create_wsgi_app(service_factory, authenticate)
    allowed_paths = {
        f"/v1/stores/{store_id}/overview",
        f"/v1/stores/{store_id}/installation",
        "/v1/orders",
        "/v1/acquisition",
        "/v1/customers",
        "/v1/retention",
        "/v1/products",
        "/v1/funnel",
        "/v1/geography",
        "/v1/performance",
        "/v1/orders/influenced",
        "/v1/customers/influenced",
        "/v1/campaigns",
    }

    def app(environ: Mapping[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", ""))
        allowed = (
            path in allowed_paths
            or re.fullmatch(r"/v1/campaigns/[^/]{1,200}(?:/(?:customers|orders))?", path)
            is not None
            or re.fullmatch(
                r"/v1/customers/[^/]{1,200}(?:/(?:orders|timeline|intelligence|products))?", path
            )
            is not None
        )
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        if path not in {
            f"/v1/stores/{store_id}/overview",
            f"/v1/stores/{store_id}/installation",
        } and query.get("store_id") != [store_id]:
            allowed = False
        if not allowed or environ.get("REQUEST_METHOD") != "GET":
            code = "404 Not Found" if not allowed else "405 Method Not Allowed"
            body = b'{"error":{"code":"preview_route_unavailable"}}'
            start_response(
                code,
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Cache-Control", "private, no-store"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]
        return protected(environ, start_response)

    return app


class QuietRequestHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Do not log paths, query strings or request headers from the preview.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-only B2B Analytics V1 DEV preview")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument(
        "--installation-v2",
        action="store_true",
        help="Resolve certified installation publication policy server-side; requires ledger tables",
    )
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--confirm-store", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-bq-read", action="store_true", required=True)
    args = parser.parse_args()
    if args.host != "127.0.0.1" or not args.project.endswith("-dev"):
        parser.error("loopback_and_dev_project_required")
    if args.store_id != args.confirm_store or not 1 <= args.port <= 65535:
        parser.error("store_confirmation_or_port_invalid")
    token = os.environ.get("DASHBOARD_DEV_PREVIEW_TOKEN", "")
    if len(token) < 32:
        parser.error("DASHBOARD_DEV_PREVIEW_TOKEN_required_min_32_chars")
    policy = AnalyticsPolicy.from_dict(json.loads(args.policy.read_text()))
    if policy.store_id != args.store_id:
        parser.error("policy_store_mismatch")
    client = bigquery.Client(project=args.project, location=args.location)
    budget = ReadBudget(args.project, args.location)
    cursor_key = secrets.token_bytes(32)

    def service_factory() -> DashboardService:
        return IntelligenceDashboardService(
            args.project,
            {policy.store_id: policy},
            lambda: BigQueryReadSession(client, budget),
            cursor_key,
            installation_v2=args.installation_v2,
        )

    app = create_dev_preview_app(
        service_factory, tenant_id=args.tenant_id, store_id=args.store_id, token=token
    )
    with make_server(args.host, args.port, app, handler_class=QuietRequestHandler) as server:
        print("Dashboard B2B Analytics V1 DEV preview listening on loopback; read-only", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
