"""Private IAM-protected APIs still independently verify every user session."""

import json
import re
from collections.abc import Callable, Iterable, Mapping
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from src.admin.contracts import AdminError, decode_body
from src.admin.http import create_wsgi_app as admin_app
from src.admin.service import OnboardingService
from src.dashboard.contracts import ReadError
from src.dashboard.http import dispatch
from src.dashboard.service import DashboardService
from src.product_auth.session import SESSION_SECONDS, Sessions

WSGI = Callable[..., Iterable[bytes]]


def response(
    start: Callable[..., Any], status: int, data: Any, cookie: str | None = None
) -> list[bytes]:
    body = json.dumps(data, default=str, separators=(",", ":")).encode()
    headers = [
        ("Content-Type", "application/json"),
        ("Cache-Control", "private, no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(body))),
    ]
    if cookie is not None:
        headers.append(("Set-Cookie", cookie))
    start(f"{status} {HTTPStatus(status).phrase}", headers)
    return [body]


def session_cookie(value: str, *, clear: bool = False) -> str:
    return f"__Host-up_session={value}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={0 if clear else SESSION_SECONDS}"


def one(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values or len(values) != 1 or not values[0]:
        raise ReadError(400, "scope_required")
    return values[0]


def create_read_app(
    sessions: Callable[[], Sessions], service: Callable[[str], DashboardService]
) -> WSGI:
    def app(environ: Mapping[str, Any], start: Callable[..., Any]) -> Iterable[bytes]:
        try:
            access = sessions().authenticate(str(environ.get("HTTP_X_UP_SESSION", "")))
            if environ.get("REQUEST_METHOD") != "GET":
                raise ReadError(405, "method_not_allowed")
            path = str(environ.get("PATH_INFO", ""))
            if path == "/v1/session":
                if environ.get("QUERY_STRING"):
                    raise ReadError(400, "unsupported_filter")
                return response(start, 200, access.catalog())
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            if "store_id" in query:
                raise ReadError(403, "technical_store_scope_forbidden")
            binding = access.binding(
                one(query, "tenant_id"),
                one(query, "workspace_operation_id"),
                one(query, "operation"),
            )
            if binding["operation"] != "B2B":
                raise ReadError(424, "coverage_not_certified")
            if not path.startswith("/v1/dashboard/"):
                raise ReadError(404, "route_not_found")
            resource = path.removeprefix("/v1/dashboard/")
            if resource in {"overview", "installation"}:
                path = f"/v1/stores/{binding['store_id']}/{resource}"
            elif re.fullmatch(
                r"(?:orders|acquisition|retention|products|funnel|geography|performance|customers|campaigns)(?:/[^/]{1,200}){0,2}",
                resource,
            ):
                path = "/v1/" + resource
                query["store_id"] = [binding["store_id"]]
            else:
                raise ReadError(404, "route_not_found")
            del query["workspace_operation_id"]
            # Business service/client is constructed only after scope authorization.
            status, data = dispatch(
                service(str(environ["HTTP_X_UP_SESSION"])), "GET", path, query, access.dashboard()
            )
            return response(start, status, data)
        except ReadError as exc:
            return response(start, exc.status, {"error": {"code": exc.code}})
        except Exception:
            return response(start, 503, {"error": {"code": "product_read_unavailable"}})

    return app


def create_admin_app(
    sessions: Callable[[], Sessions], service: Callable[[], OnboardingService]
) -> WSGI:
    def app(environ: Mapping[str, Any], start: Callable[..., Any]) -> Iterable[bytes]:
        try:
            path, method = environ.get("PATH_INFO"), environ.get("REQUEST_METHOD")
            session = sessions()
            cookie = str(environ.get("HTTP_X_UP_SESSION", ""))
            if path == "/v1/auth/session" and method == "POST":
                try:
                    length = int(environ.get("CONTENT_LENGTH", 0))
                except (ValueError, TypeError):
                    raise ReadError(400, "invalid_session_request") from None
                if (
                    not 0 < length <= 16384
                    or str(environ.get("CONTENT_TYPE", "")).split(";")[0] != "application/json"
                ):
                    raise ReadError(400, "invalid_session_request")
                value = decode_body(environ["wsgi.input"].read(length))
                if not isinstance(value, dict) or set(value) != {"id_token"}:
                    raise ReadError(400, "invalid_session_request")
                result = session.exchange(value["id_token"])
                return response(
                    start, 200, {"data": {"authenticated": True}}, session_cookie(result)
                )
            if path == "/v1/auth/logout" and method == "POST":
                session.logout(cookie)
                return response(
                    start, 200, {"data": {"authenticated": False}}, session_cookie("", clear=True)
                )
            access = session.authenticate(cookie)
            principal = access.admin()  # CLIENT_USER rejected before onboarding/Secret IO.
            secured = dict(environ)
            secured["wsgi.url_scheme"] = (
                "https"  # Service only accepts IAM-authenticated BFF calls.
            )
            return admin_app(service, lambda _: principal)(secured, start)
        except (ReadError, AdminError) as exc:
            return response(start, exc.status, {"error": {"code": exc.code}})
        except Exception:
            return response(start, 503, {"error": {"code": "product_admin_unavailable"}})

    return app
