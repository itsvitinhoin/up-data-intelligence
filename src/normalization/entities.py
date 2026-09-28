from typing import Any

from src.bigquery.catalog import CUSTOMER, EVENT, ITEM, ORDER
from src.normalization.meta_url import parse_meta_url
from src.utils.data import identifier, numeric, timestamp

VERSION = "1.0.0"


def normalize_json_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: identifier(v)
            if (k == "id" or k.endswith("_id")) and v is not None
            else normalize_json_ids(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [normalize_json_ids(v) for v in value]
    return value


def typed(value: Any, typ: str) -> Any:
    if value is None:
        return None
    if typ == "NUMERIC":
        return numeric(value)
    if typ == "TIMESTAMP":
        return timestamp(value)
    if typ == "INT64":
        if isinstance(value, bool) or not isinstance(value, int) or not -(2**63) <= value < 2**63:
            raise ValueError("invalid_integer")
        return value
    if typ == "STRING":
        return identifier(value)
    return normalize_json_ids(value) if typ == "JSON" else value


def normalize(
    resource: str, source: dict[str, Any]
) -> tuple[str, dict[str, Any], list[dict[str, Any]] | None]:
    identifier(source.get("id"), True)
    items = None
    if resource == "customers":
        retail, wholesale = (
            source.get("retail_profile") or {},
            source.get("wholesale_profile") or {},
        )
        data = {
            **source,
            "customer_id": source["id"],
            "cpf": retail.get("cpf"),
            "cnpj": wholesale.get("cnpj"),
            "company_name": wholesale.get("company_name"),
            "trade_name": wholesale.get("trade_name"),
        }
        fields, table = CUSTOMER, "customers"
    elif resource == "orders":
        data = {
            **source,
            "order_id": source["id"],
            "customer_id": (source.get("customer") or {}).get("id"),
            "customer_snapshot": source.get("customer"),
        }
        for required in (
            "order_status",
            "payment_status",
            "subtotal",
            "discount",
            "shipping",
            "total",
            "requested_total",
            "fulfilled_total",
            "total_items_qty",
            "requested_items_qty",
            "fulfilled_items_qty",
            "items_count",
            "created_at",
            "updated_at",
        ):
            if source.get(required) is None:
                raise ValueError("missing_order_field")
        fields, table = ORDER, "orders"
        if "items" in source:
            if not isinstance(source["items"], list):
                raise ValueError("invalid_items")
            items = []
            for item in source["items"]:
                identifier(item.get("id"), True)
                row = {
                    **item,
                    "item_id": item["id"],
                    "order_id": source["id"],
                    "order_created_at": source.get("created_at"),
                    "present_in_latest_snapshot": True,
                }
                items.append(
                    {
                        k: typed(row.get(k), typ)
                        for k, typ in ITEM.items()
                        if k != "parent_order_version_id"
                    }
                )
    else:
        for k in ("event_id", "event_name", "occurred_at"):
            if not source.get(k):
                raise ValueError("missing_fact_field")
        data = {**source, "fact_id": source["id"], **parse_meta_url(source.get("landing_url"))}
        fields, table = EVENT, "analytics_events"
    return table, {k: typed(data.get(k), typ) for k, typ in fields.items()}, items
