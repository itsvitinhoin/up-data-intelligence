"""Fail-closed WSGI handler; identity must come from an external verifier."""

import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import parse_qs, unquote

from src.dashboard.contracts import Grant, Principal, ReadError
from src.dashboard.service import DashboardService

ServiceFactory = Callable[[], DashboardService]
Authenticator = Callable[[Mapping[str, Any]], Principal | None]

STATUS = {
    200: "200 OK",
    400: "400 Bad Request",
    401: "401 Unauthorized",
    403: "403 Forbidden",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    424: "424 Failed Dependency",
    503: "503 Service Unavailable",
}


def _value(query: Mapping[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if values is None:
        return None
    if len(values) != 1 or not values[0]:
        raise ReadError(400, "invalid_query_parameter")
    return values[0]


def dispatch(
    service: DashboardService,
    method: str,
    path: str,
    query: Mapping[str, list[str]],
    principal: Principal | None,
) -> tuple[int, dict[str, Any]]:
    if method != "GET":
        raise ReadError(405, "method_not_allowed")
    intelligence_routes: dict[str, tuple[str, str | None]] = {
        "/v1/customers/influenced": ("influencedCustomers", None),
        "/v1/orders/influenced": ("influencedOrders", None),
        "/v1/performance": ("performance", None),
        "/v1/campaigns": ("campaigns", None),
    }
    match = re.fullmatch(r"/v1/customers/([^/]+)/(timeline|intelligence|products|campaigns)", path)
    if match:
        intelligence_routes[path] = (
            {
                "timeline": "timeline",
                "intelligence": "customer360",
                "products": "customerProducts",
                "campaigns": "customerCampaigns",
            }[match.group(2)],
            unquote(match.group(1)),
        )
    match = re.fullmatch(r"/v1/campaigns/([^/]+)(?:/(customers|orders))?", path)
    if match:
        intelligence_routes[path] = (
            {None: "campaign", "customers": "campaignCustomers", "orders": "campaignOrders"}[
                match.group(2)
            ],
            unquote(match.group(1)),
        )
    if path in intelligence_routes:
        from src.dashboard.intelligence import IntelligenceDashboardService

        if not isinstance(service, IntelligenceDashboardService):
            raise ReadError(424, "intelligence_publication_unavailable")
        allowed = {"tenant_id", "store_id", "operation", "from", "to", "page_size", "cursor"}
        if set(query) - allowed:
            raise ReadError(400, "unsupported_filter")
        intelligence_resource, entity = intelligence_routes[path]
        grant = Grant(
            _value(query, "tenant_id") or "",
            _value(query, "store_id") or "",
            _value(query, "operation") or "",
        )
        return 200, service.intelligence(
            principal,
            grant,
            intelligence_resource,
            entity=entity,
            size=_value(query, "page_size"),
            cursor=_value(query, "cursor"),
            from_day=_value(query, "from"),
            to_day=_value(query, "to"),
        )
    installation = re.fullmatch(r"/v1/stores/([^/]+)/installation", path)
    if installation:
        if set(query) - {"tenant_id", "operation"}:
            raise ReadError(400, "unsupported_filter")
        grant = Grant(
            _value(query, "tenant_id") or "",
            unquote(installation.group(1)),
            _value(query, "operation") or "",
        )
        return 200, service.installation(principal, grant)
    overview = re.fullmatch(r"/v1/stores/([^/]+)/overview", path)
    customer_contact = re.fullmatch(r"/v1/customers/([^/]+)/contact", path)
    customer_orders = re.fullmatch(r"/v1/customers/([^/]+)/orders", path)
    customer = re.fullmatch(r"/v1/customers/([^/]+)", path)
    order = re.fullmatch(r"/v1/orders/([^/]+)", path)
    product = re.fullmatch(r"/v1/products/([^/]+)", path)
    store: str | None
    resource: str
    if overview:
        resource, store = "overview", unquote(overview.group(1))
    elif customer_contact:
        resource, store = "customer_contact", _value(query, "store_id")
    elif customer_orders:
        resource, store = "customer_orders", _value(query, "store_id")
    elif customer:
        resource, store = "customer", _value(query, "store_id")
    elif order:
        resource, store = "order", _value(query, "store_id")
    elif product:
        resource, store = "product", _value(query, "store_id")
    elif path in {
        "/v1/orders",
        "/v1/acquisition",
        "/v1/customers",
        "/v1/retention",
        "/v1/products",
        "/v1/funnel",
        "/v1/geography",
        "/v1/creatives",
    }:
        resource, store = path.rsplit("/", 1)[-1], _value(query, "store_id")
    else:
        raise ReadError(404, "route_not_found")
    allowed = {"tenant_id", "operation"}
    if not overview:
        allowed.add("store_id")
    if resource in {
        "overview",
        "orders",
        "acquisition",
        "customers",
        "retention",
        "products",
        "funnel",
        "product",
        "geography",
        "creatives",
    }:
        allowed.update({"from", "to"})
    if resource in {"orders", "customers", "products", "customer_orders"}:
        allowed.update({"page_size", "cursor"})
    if resource == "orders":
        allowed.update({"status", "first_purchase"})
    if set(query) - allowed:
        raise ReadError(400, "unsupported_filter")
    tenant = _value(query, "tenant_id")
    operation = _value(query, "operation")
    if not tenant or not store or not operation:
        raise ReadError(400, "scope_required")
    grant = Grant(tenant, store, operation)
    if resource == "overview":
        result = service.overview(
            principal, grant, from_day=_value(query, "from"), to_day=_value(query, "to")
        )
    elif resource == "customers":
        result = service.customers(
            principal,
            grant,
            size=_value(query, "page_size"),
            cursor=_value(query, "cursor"),
            from_day=_value(query, "from"),
            to_day=_value(query, "to"),
        )
    elif resource == "orders":
        first_purchase = _value(query, "first_purchase")
        if first_purchase not in {None, "true", "false"}:
            raise ReadError(400, "invalid_first_purchase_filter")
        result = service.orders(
            principal,
            grant,
            size=_value(query, "page_size"),
            cursor=_value(query, "cursor"),
            from_day=_value(query, "from"),
            to_day=_value(query, "to"),
            status=_value(query, "status"),
            first_purchase=first_purchase == "true",
        )
    elif resource == "acquisition":
        result = service.acquisition(
            principal, grant, from_day=_value(query, "from"), to_day=_value(query, "to")
        )
    elif resource == "creatives":
        result = service.creatives(
            principal, grant, from_day=_value(query, "from"), to_day=_value(query, "to")
        )
    elif resource == "customer_contact":
        result = service.customer_contact(principal, grant, unquote(customer_contact.group(1)))  # type: ignore[union-attr]
    elif resource == "customer":
        result = service.customer(principal, grant, unquote(customer.group(1)))  # type: ignore[union-attr]
    elif resource == "order":
        result = service.order(principal, grant, unquote(order.group(1)))  # type: ignore[union-attr]
    elif resource == "product":
        result = service.product(
            principal,
            grant,
            unquote(product.group(1)),  # type: ignore[union-attr]
            from_day=_value(query, "from"),
            to_day=_value(query, "to"),
        )
    elif resource == "customer_orders":
        result = service.customer_orders(
            principal,
            grant,
            unquote(customer_orders.group(1)),  # type: ignore[union-attr]
            size=_value(query, "page_size"),
            cursor=_value(query, "cursor"),
        )
    elif resource == "retention":
        result = service.retention(
            principal, grant, from_day=_value(query, "from"), to_day=_value(query, "to")
        )
    elif resource == "products":
        result = service.products(
            principal,
            grant,
            from_day=_value(query, "from"),
            to_day=_value(query, "to"),
            size=_value(query, "page_size"),
            cursor=_value(query, "cursor"),
        )
    elif resource == "funnel":
        result = service.funnel(
            principal, grant, from_day=_value(query, "from"), to_day=_value(query, "to")
        )
    else:
        result = service.geography(
            principal, grant, from_day=_value(query, "from"), to_day=_value(query, "to")
        )
    return 200, result


def create_wsgi_app(
    service_factory: ServiceFactory, authenticate: Authenticator
) -> Callable[..., Iterable[bytes]]:
    """No default authenticator. The deployment must verify identity server-side."""

    def app(environ: Mapping[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        try:
            principal = authenticate(environ)
            if principal is None:
                raise ReadError(401, "unauthenticated")
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            status, result = dispatch(
                service_factory(),
                str(environ.get("REQUEST_METHOD", "")),
                str(environ.get("PATH_INFO", "")),
                query,
                principal,
            )
        except ReadError as exc:
            status, result = exc.status, {"error": {"code": exc.code}}
        except Exception:
            status, result = 503, {"error": {"code": "dashboard_read_failed"}}
        body = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
        start_response(
            STATUS[status],
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Cache-Control", "private, no-store"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return app
