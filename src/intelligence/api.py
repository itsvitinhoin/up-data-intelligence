"""In-process API reference. No HTTP listener, SQL, CORE input, or credential discovery."""

import base64
import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.analytics.engine import Row, instant
from src.intelligence.schema import SCHEMAS
from src.utils.data import canonical, digest, numeric


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    stores: frozenset[str]


class ApiError(ValueError):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


def select(row: Row, fields: str) -> Row:
    result = {k: row.get(k) for k in fields.split()}
    if "campaigns" in result:
        result["campaigns"] = list(result["campaigns"] or [])[:100]
    if "influence_by_scope" in result:
        result["influence_by_scope"] = {
            scope: {
                "influenced": bool(value.get("influenced")),
                "campaigns": list(value.get("campaigns", []))[:100],
                "campaign_count": value.get("campaign_count", 0),
                "campaigns_truncated": len(value.get("campaigns", [])) > 100,
            }
            for scope, value in (result["influence_by_scope"] or {}).items()
            if scope in {"LIFETIME", "ACQUISITION", "REPEAT_PURCHASE"}
        }
    return result


PROFILE = "customer_id customer_type company_name trade_name state city first_order_at last_purchase_at total_orders total_requested_revenue total_fulfilled_revenue total_requested_quantity total_fulfilled_quantity first_purchase_requested_revenue first_purchase_fulfilled_revenue purchase_count has_repurchase days_since_last_purchase ltv_observed ltv_basis history_complete"
ORDER = "customer_id order_id purchase_number created_at order_status requested_total fulfilled_total requested_items_qty fulfilled_items_qty paid_media_influenced campaigns campaign_count first_campaign_id last_campaign_id evidence_type influence_scope influence_by_scope"
PRODUCT = "product_id product_key variant_id sku resolution_status orders_count requested_quantity fulfilled_quantity requested_revenue fulfilled_revenue first_purchase_at last_purchase_at revenue_basis"
JOURNEY = "first_touch_at first_paid_touch_at last_paid_touch_at first_campaign_id last_campaign_id total_events total_sessions total_products_viewed total_cart_events total_checkout_events timeline_start timeline_end"
TIMELINE = "event_name occurred_at channel campaign_id adset_id ad_id product_id variant_id order_id value quantity record_type order_status requested_total fulfilled_total requested_items_qty fulfilled_items_qty confidence_type"


class MaterializedAPI:
    def __init__(self, artifacts: list[Row], *, cursor_key: bytes):
        if len(cursor_key) < 32:
            raise ValueError("explicit_cursor_signing_key_required")
        self.key = cursor_key
        self.stores: dict[str, Row] = {}
        allowed = set(SCHEMAS) | {"analytics_customer_timeline"}
        for artifact in artifacts:
            store = artifact["metadata"]["store_id"]
            if store in self.stores or set(artifact["tables"]) != allowed:
                raise ValueError("only_one_materialized_generation_per_store")
            if any(
                r.get("store_id") != store for rows in artifact["tables"].values() for r in rows
            ):
                raise ValueError("materialized_tenant_mismatch")
            for name, rows in artifact["tables"].items():
                if len({r["row_key"] for r in rows}) != len(rows):
                    raise ValueError("duplicate_materialized_key")
                if any(r.get("policy_hash") != artifact["metadata"]["policy_hash"] for r in rows):
                    raise ValueError("materialized_policy_mismatch")
                if name in SCHEMAS and any(
                    r.get("generation") != artifact["metadata"]["generation"] for r in rows
                ):
                    raise ValueError("materialized_generation_mismatch")
            self.stores[store] = deepcopy(artifact)

    def _page(
        self, rows: list[Row], query: dict[str, str], context: Row, *, cursor_name: str = "cursor"
    ) -> Row:
        size, page = (
            int(query.get("page_size", "20")),
            int(
                query.get(
                    "page" if cursor_name == "cursor" else cursor_name.replace("cursor", "page"),
                    "1",
                )
            ),
        )
        if not 1 <= size <= 100 or page < 1:
            raise ApiError(400, "invalid_pagination")
        rows = sorted(
            rows, key=lambda r: (r.get("occurred_at", r.get("created_at", "")), r["row_key"])
        )
        binding = digest(
            [
                context,
                size,
                {
                    k: v
                    for k, v in query.items()
                    if k
                    not in {
                        "page",
                        "cursor",
                        "orders_cursor",
                        "products_cursor",
                        "orders_page",
                        "products_page",
                    }
                },
            ]
        )
        cursor = query.get(cursor_name)
        if cursor:
            if len(cursor) > 8192:
                raise ApiError(400, "invalid_cursor")
            try:
                encoded, signature = cursor.split(".")
                expected = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected, signature):
                    raise ValueError
                token = json.loads(base64.urlsafe_b64decode(encoded))
                if token["binding"] != binding or token["page"] != page:
                    raise ValueError
                positions = [i for i, r in enumerate(rows) if r["row_key"] == token["last"]]
                if len(positions) != 1:
                    raise ValueError
                rows = rows[positions[0] + 1 :]
            except (ValueError, KeyError, TypeError):
                raise ApiError(400, "invalid_cursor") from None
        elif page != 1:
            raise ApiError(400, "cursor_required_after_first_page")
        selected = rows[:size]
        nxt = None
        if len(rows) > size:
            data = base64.urlsafe_b64encode(
                canonical(
                    {"binding": binding, "page": page + 1, "last": selected[-1]["row_key"]}
                ).encode()
            ).decode()
            nxt = data + "." + hmac.new(self.key, data.encode(), hashlib.sha256).hexdigest()
        return {"data": selected, "pagination": {"page": page, "page_size": size, "cursor": nxt}}

    def handle(
        self, method: str, path: str, query: dict[str, str], principal: Principal | None
    ) -> tuple[int, Row]:
        try:
            return 200, self._handle(method, path, query, principal)
        except ApiError as exc:
            return exc.status, {"error": {"code": exc.code}}
        except (ValueError, TypeError, KeyError):
            return 400, {"error": {"code": "invalid_request"}}

    def _handle(
        self, method: str, path: str, q: dict[str, str], principal: Principal | None
    ) -> Row:
        if (
            principal is None
            or not principal.subject
            or principal.role not in {"viewer", "manager", "admin"}
        ):
            raise ApiError(401, "authenticated_principal_required")
        store = q.get("store_id")
        if not store:
            raise ApiError(400, "store_id_required")
        if store not in principal.stores:
            raise ApiError(403, "store_access_denied")
        if store not in self.stores:
            raise ApiError(404, "materialized_store_not_found")
        if method != "GET":
            raise ApiError(405, "method_not_allowed")
        artifact = self.stores[store]
        tables, meta = artifact["tables"], artifact["metadata"]
        profiles = tables["analytics_customer_360_profile"]
        common = {"store_id", "page", "page_size", "cursor"}
        context = {
            "path": path,
            "store": store,
            "generation": meta["generation"],
            "role": principal.role,
            "subject": principal.subject,
        }
        response_meta = select(
            meta,
            "store_id generation policy_hash as_of calculated_at timezone report_from report_to",
        )

        def page(rows: list[Row], fields: str, name: str = "cursor") -> Row:
            result = self._page(rows, q, {**context, "collection": name}, cursor_name=name)
            result["data"] = [select(r, fields) for r in result["data"]]
            result["metadata"] = response_meta
            return result

        def revenue(rows: list[Row], field: str) -> list[Row]:
            low = (
                Decimal(numeric(q["min_requested_revenue"]) or "0")
                if "min_requested_revenue" in q
                else None
            )
            high = (
                Decimal(numeric(q["max_requested_revenue"]) or "0")
                if "max_requested_revenue" in q
                else None
            )
            if (
                (low is not None and low < 0)
                or (high is not None and high < 0)
                or (low is not None and high is not None and low > high)
            ):
                raise ApiError(400, "invalid_revenue_range")
            return [
                r
                for r in rows
                if (low is None or r[field] is not None and Decimal(r[field]) >= low)
                and (high is None or r[field] is not None and Decimal(r[field]) <= high)
            ]

        def local_day(v: str) -> str:
            return instant(v).astimezone(ZoneInfo(meta["timezone"])).date().isoformat()

        parts = path.strip("/").split("/")
        if path == "/v1/customers":
            filters = {
                "customer_type",
                "state",
                "city",
                "paid_media_influenced",
                "has_repurchase",
                "first_purchase_date",
                "last_purchase_date",
                "min_requested_revenue",
                "max_requested_revenue",
            }
            if set(q) - common - filters:
                raise ApiError(400, "unsupported_filter")
            rows = list(profiles)
            for key in ("customer_type", "state", "city"):
                if key in q:
                    rows = [r for r in rows if r.get(key) == q[key]]
            for key in ("paid_media_influenced", "has_repurchase"):
                if key in q:
                    if q[key] not in {"true", "false"}:
                        raise ApiError(400, "invalid_boolean_filter")
                    rows = [r for r in rows if r[key] == (q[key] == "true")]
            for key, field in (
                ("first_purchase_date", "first_order_at"),
                ("last_purchase_date", "last_purchase_at"),
            ):
                if key in q:
                    day = date.fromisoformat(q[key]).isoformat()
                    rows = [r for r in rows if r.get(field) and local_day(r[field]) == day]
            return page(
                revenue(rows, "total_requested_revenue"),
                PROFILE
                + " paid_media_influenced acquisition_influenced repeat_purchase_influenced",
            )
        if path == "/v1/orders/influenced":
            if (
                set(q)
                - common
                - {
                    "campaign_id",
                    "customer_id",
                    "date_from",
                    "date_to",
                    "min_requested_revenue",
                    "max_requested_revenue",
                    "influence_scope",
                }
            ):
                raise ApiError(400, "unsupported_filter")
            scope = q.get("influence_scope", "LIFETIME")
            if scope not in {"LIFETIME", "ACQUISITION", "REPEAT_PURCHASE"}:
                raise ApiError(400, "invalid_influence_scope")
            rows = [
                {
                    **r,
                    **{
                        k: v for k, v in r["influence_by_scope"][scope].items() if k != "influenced"
                    },
                    "influence_scope": scope,
                }
                for r in tables["analytics_customer_orders_summary"]
                if r["influence_by_scope"][scope]["influenced"]
            ]
            if "customer_id" in q:
                rows = [r for r in rows if r["customer_id"] == q["customer_id"]]
            if "campaign_id" in q:
                rows = [r for r in rows if q["campaign_id"] in r["campaigns"]]
            dates = {
                k: date.fromisoformat(q[k]).isoformat() for k in ("date_from", "date_to") if k in q
            }
            if len(dates) == 2 and dates["date_from"] >= dates["date_to"]:
                raise ApiError(400, "invalid_date_range")
            rows = [
                r
                for r in rows
                if ("date_from" not in dates or local_day(r["created_at"]) >= dates["date_from"])
                and ("date_to" not in dates or local_day(r["created_at"]) < dates["date_to"])
            ]
            return page(revenue(rows, "requested_total"), ORDER)
        if len(parts) == 4 and parts[:2] == ["v1", "campaigns"] and parts[3] == "customers":
            raise ApiError(501, "future_contract_not_implemented")
        if len(parts) in {3, 4} and parts[:2] == ["v1", "customers"]:
            cid = parts[2]
            customer = next((r for r in profiles if r["customer_id"] == cid), None)
            if customer is None:
                raise ApiError(404, "customer_not_found")
            if len(parts) == 4 and parts[3] == "timeline":
                if set(q) - common:
                    raise ApiError(400, "unsupported_filter")
                return page(
                    [r for r in tables["analytics_customer_timeline"] if r["customer_id"] == cid],
                    TIMELINE,
                )
            if len(parts) == 4:
                raise ApiError(404, "route_not_found")
            if set(q) - {
                "store_id",
                "page_size",
                "orders_cursor",
                "products_cursor",
                "orders_page",
                "products_page",
            }:
                raise ApiError(400, "unsupported_filter")
            orders = [
                r for r in tables["analytics_customer_orders_summary"] if r["customer_id"] == cid
            ]
            products = [
                r for r in tables["analytics_customer_products_summary"] if r["customer_id"] == cid
            ]
            journey = next(
                r for r in tables["analytics_customer_journey_summary"] if r["customer_id"] == cid
            )
            return {
                "profile": select(customer, PROFILE),
                "commercial": select(
                    customer,
                    "total_orders purchase_count total_requested_revenue total_fulfilled_revenue total_requested_quantity total_fulfilled_quantity ltv_observed ltv_basis",
                ),
                "journey": select(journey, JOURNEY),
                "marketing": {
                    **select(
                        customer,
                        "paid_media_influenced acquisition_influenced repeat_purchase_influenced",
                    ),
                    "campaigns": sorted({c for r in orders for c in r["campaigns"]})[:100],
                    "campaigns_truncated": len({c for r in orders for c in r["campaigns"]}) > 100,
                },
                "orders": page(orders, ORDER, "orders_cursor"),
                "products": page(products, PRODUCT, "products_cursor"),
                "metadata": response_meta,
            }
        raise ApiError(404, "route_not_found")
