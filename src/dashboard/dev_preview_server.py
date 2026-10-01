"""Explicit, loopback-only Analytics V1 Overview preview; never production auth."""

import argparse
import hmac
import json
import os
import secrets
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, make_server

from google.cloud import bigquery

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal
from src.dashboard.http import create_wsgi_app
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
    allowed_path = f"/v1/stores/{store_id}/overview"

    def app(environ: Mapping[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        # The generic Read API has other routes; this local process exposes only Overview.
        if environ.get("PATH_INFO") != allowed_path or environ.get("REQUEST_METHOD") != "GET":
            code = (
                "404 Not Found"
                if environ.get("PATH_INFO") != allowed_path
                else "405 Method Not Allowed"
            )
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
    parser = argparse.ArgumentParser(description="Local-only B2B Overview DEV preview")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
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
        return DashboardService(
            args.project,
            {policy.store_id: policy},
            lambda: BigQueryReadSession(client, budget),
            cursor_key,
        )

    app = create_dev_preview_app(
        service_factory, tenant_id=args.tenant_id, store_id=args.store_id, token=token
    )
    with make_server(args.host, args.port, app, handler_class=QuietRequestHandler) as server:
        print("Dashboard Overview DEV preview listening on loopback; read-only", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
