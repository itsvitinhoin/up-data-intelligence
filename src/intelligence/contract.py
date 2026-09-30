"""Generate an OpenAPI 3.1 proposal for the in-process consumer contract."""

import json
from pathlib import Path
from typing import Any

from src.influence.schema import SCHEMAS as INFLUENCE_SCHEMAS
from src.intelligence.api import JOURNEY, ORDER, PRODUCT, PROFILE, TIMELINE
from src.intelligence.schema import SCHEMAS


def contract() -> dict[str, Any]:
    specs = {**SCHEMAS, **INFLUENCE_SCHEMAS}

    def shape(table: str, fields: str) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        spec: dict[str, Any]
        for name in fields.split():
            typ = specs[table].fields[name]
            if typ == "NUMERIC":
                spec = {
                    "type": ["string", "null"],
                    "pattern": r"^-?[0-9]+(?:\.[0-9]+)?$",
                    "description": "Exact decimal; never a binary floating-point amount.",
                }
            elif typ == "TIMESTAMP":
                spec = {"type": ["string", "null"], "format": "date-time"}
            elif typ == "JSON":
                spec = {"type": ["object", "array", "null"]}
            else:
                spec = {
                    "type": [
                        {"STRING": "string", "BOOL": "boolean", "INT64": "integer"}[typ],
                        "null",
                    ]
                }
            properties[name] = spec
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": list(properties),
        }

    schemas: dict[str, Any] = {
        "Profile": shape("analytics_customer_360_profile", PROFILE),
        "CustomerListItem": shape(
            "analytics_customer_360_profile",
            PROFILE + " paid_media_influenced acquisition_influenced repeat_purchase_influenced",
        ),
        "Order": shape("analytics_customer_orders_summary", ORDER),
        "Product": shape("analytics_customer_products_summary", PRODUCT),
        "Journey": shape("analytics_customer_journey_summary", JOURNEY),
        "TimelineEvent": shape("analytics_customer_timeline", TIMELINE),
        "Commercial": shape(
            "analytics_customer_360_profile",
            "total_orders purchase_count total_requested_revenue total_fulfilled_revenue total_requested_quantity total_fulfilled_quantity ltv_observed ltv_basis",
        ),
        "Error": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {"code": {"type": "string"}},
                }
            },
        },
        "Metadata": {
            "type": "object",
            "required": [
                "store_id",
                "generation",
                "policy_hash",
                "as_of",
                "calculated_at",
                "timezone",
                "report_from",
                "report_to",
            ],
            "properties": {
                k: {"type": "string"}
                for k in "store_id generation policy_hash as_of calculated_at timezone report_from report_to".split()
            },
        },
        "Pagination": {
            "type": "object",
            "required": ["page", "page_size", "cursor"],
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "cursor": {
                    "type": ["string", "null"],
                    "description": "Signed next-page cursor; null at end.",
                },
            },
        },
    }
    for name in ("CustomerListItem", "Order", "Product", "TimelineEvent"):
        schemas[name + "Page"] = {
            "type": "object",
            "required": ["data", "pagination", "metadata"],
            "properties": {
                "data": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {"$ref": "#/components/schemas/" + name},
                },
                "pagination": {"$ref": "#/components/schemas/Pagination"},
                "metadata": {"$ref": "#/components/schemas/Metadata"},
            },
        }
    schemas["CustomerDetail"] = {
        "type": "object",
        "required": [
            "profile",
            "commercial",
            "journey",
            "marketing",
            "orders",
            "products",
            "metadata",
        ],
        "properties": {
            k: {"$ref": "#/components/schemas/" + v}
            for k, v in {
                "profile": "Profile",
                "commercial": "Commercial",
                "journey": "Journey",
                "orders": "OrderPage",
                "products": "ProductPage",
                "metadata": "Metadata",
            }.items()
        }
        | {
            "marketing": {
                "type": "object",
                "required": [
                    "paid_media_influenced",
                    "acquisition_influenced",
                    "repeat_purchase_influenced",
                    "campaigns",
                    "campaigns_truncated",
                ],
                "properties": {
                    k: {"type": "boolean"}
                    for k in (
                        "paid_media_influenced",
                        "acquisition_influenced",
                        "repeat_purchase_influenced",
                        "campaigns_truncated",
                    )
                }
                | {"campaigns": {"type": "array", "maxItems": 100, "items": {"type": "string"}}},
            }
        },
    }

    def parameter(name: str, *, path: bool = False) -> dict[str, Any]:
        schema: dict[str, Any]
        if name in {"page", "orders_page", "products_page", "page_size"}:
            schema = {"type": "integer", "minimum": 1, "default": 20 if name == "page_size" else 1}
            if name == "page_size":
                schema["maximum"] = 100
        elif name in {"paid_media_influenced", "has_repurchase"}:
            schema = {"type": "boolean"}
        else:
            schema = {"type": "string"}
            if name in {"first_purchase_date", "last_purchase_date", "date_from", "date_to"}:
                schema["format"] = "date"
            if name == "influence_scope":
                schema["enum"] = ["LIFETIME", "ACQUISITION", "REPEAT_PURCHASE"]
        return {
            "name": name,
            "in": "path" if path else "query",
            "required": path or name == "store_id",
            "schema": schema,
        }

    routes = {
        "/v1/customers": (
            "CustomerListItemPage",
            "customer_type state city paid_media_influenced has_repurchase first_purchase_date last_purchase_date min_requested_revenue max_requested_revenue page page_size cursor",
        ),
        "/v1/customers/{customer_id}": (
            "CustomerDetail",
            "page_size orders_page products_page orders_cursor products_cursor",
        ),
        "/v1/customers/{customer_id}/timeline": ("TimelineEventPage", "page page_size cursor"),
        "/v1/orders/influenced": (
            "OrderPage",
            "campaign_id customer_id date_from date_to min_requested_revenue max_requested_revenue influence_scope page page_size cursor",
        ),
    }
    paths = {}
    for path, (model, params) in routes.items():
        parameters = [parameter("store_id")] + [parameter(k) for k in params.split()]
        if "{customer_id}" in path:
            parameters.append(parameter("customer_id", path=True))
        responses = {
            str(status): {
                "description": "Request rejected without sensitive details",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }
            for status in (400, 401, 403, 404, 405)
        }
        responses["200"] = {
            "description": "Materialized-only response",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/" + model}}},
        }
        paths[path] = {
            "get": {
                "parameters": parameters,
                "responses": responses,
                "x-implementation-status": "offline-in-process",
            }
        }
    paths["/v1/campaigns/{campaign_id}/customers"] = {
        "get": {
            "x-implementation-status": "future",
            "description": "Future customer/order/requested/fulfilled campaign participation contract; currently returns501. No exclusive credit.",
            "parameters": [parameter("store_id"), parameter("campaign_id", path=True)],
            "responses": {
                "501": {
                    "description": "Not implemented in the offline adapter",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                    },
                }
            },
        }
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "UP Customer Intelligence — OFFLINE CONTRACT",
            "version": "0.1.0",
            "description": "No deployed server. HTTP authentication integration is future work. Trusted Principal required offline; store_id is not authorization.",
        },
        "security": [{"bearerAuth": []}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Future verified authentication; never trust request-supplied stores/role.",
                }
            },
            "schemas": schemas,
        },
    }


def generate(root: Path = Path(".")) -> None:
    target = root / "docs/openapi/data-intelligence.openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(contract(), indent=2) + "\n")


if __name__ == "__main__":
    generate()
