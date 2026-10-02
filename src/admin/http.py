"""Injected trusted authenticator. HTTPS by default; explicit loopback DEV exception."""

import hmac
import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from src.admin.contracts import MAX_BODY, AdminError, Principal, authorize, decode_body
from src.admin.service import OnboardingService


def create_wsgi_app(
    service_factory: Callable[[], OnboardingService],
    authenticate: Callable[[Mapping[str, Any]], Principal | None],
    *,
    allow_loopback_dev: bool = False,
) -> Callable[..., Iterable[bytes]]:
    def app(environ: Mapping[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        try:
            principal = authorize(authenticate(environ))
            if environ.get("wsgi.url_scheme") != "https" and not (
                allow_loopback_dev and environ.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}
            ):
                raise AdminError("https_required", 403)
            path, method = environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "")
            match = re.fullmatch(r"/v1/admin/onboarding/([a-f0-9-]{36})", path)
            if environ.get("QUERY_STRING"):
                raise AdminError("unsupported_query", 400)
            if method == "POST" and path == "/v1/admin/onboarding":
                if (
                    str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].strip()
                    != "application/json"
                ):
                    raise AdminError("content_type_required", 415)
                try:
                    length = int(environ.get("CONTENT_LENGTH", ""))
                except (TypeError, ValueError):
                    raise AdminError("content_length_required", 411) from None
                if not 0 < length <= MAX_BODY:
                    raise AdminError("request_body_too_large", 413)
                body = environ["wsgi.input"].read(length)
                if len(body) != length:
                    raise AdminError("invalid_onboarding_request", 400)
                result = service_factory().create(
                    principal, environ.get("HTTP_IDEMPOTENCY_KEY", ""), decode_body(body)
                )
                status = 201
            elif method == "GET" and match:
                result = service_factory().read(principal, match.group(1))
                status = 200
            else:
                raise AdminError("admin_route_unavailable", 404)
        except AdminError as exc:
            status, result = exc.status, {"error": {"code": exc.code}}
        except Exception:
            status, result = 503, {"error": {"code": "onboarding_temporarily_unavailable"}}
        body = json.dumps(result, default=str, separators=(",", ":")).encode()
        reasons = {
            200: "OK",
            201: "Created",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            409: "Conflict",
            411: "Length Required",
            413: "Payload Too Large",
            415: "Unsupported Media Type",
            503: "Service Unavailable",
        }
        start_response(
            f"{status} {reasons[status]}",
            [
                ("Content-Type", "application/json"),
                ("Cache-Control", "private, no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return app


def create_dev_admin_app(
    service_factory: Callable[[], OnboardingService], token: str, principal: Principal
) -> Callable[..., Iterable[bytes]]:
    # Explicit composition only; no automatic env/credential discovery or server startup.
    if len(token) < 32:
        raise ValueError("admin_dev_token_required")
    authorize(principal)

    def authenticate(environ: Mapping[str, Any]) -> Principal | None:
        if environ.get("REMOTE_ADDR") != "127.0.0.1":
            return None
        value = str(environ.get("HTTP_X_UP_ADMIN_PREVIEW_TOKEN", ""))
        return principal if hmac.compare_digest(value, token) else None

    return create_wsgi_app(service_factory, authenticate, allow_loopback_dev=True)
