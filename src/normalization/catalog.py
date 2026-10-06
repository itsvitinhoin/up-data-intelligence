"""Exact source catalog identities only; never derive attributes from SKU/name."""

from typing import Any
from urllib.parse import urlsplit

from src.connectors.upzero.catalog_attributes import dimensions
from src.connectors.upzero.catalog_schema import RESOURCES
from src.normalization.entities import typed
from src.utils.data import identifier


def normalize_catalog(resource: str, source: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    table, fields, key = RESOURCES[resource]
    identity = identifier(source.get("id"), True)
    data = {**source, key: identity}
    if resource == "products" and identifier(source.get("product_id"), True) != identity:
        raise ValueError("catalog_product_identity_mismatch")
    if resource == "variants":
        identifier(source.get("product_id"), True)
        if type(source.get("active")) is not bool:
            raise ValueError("catalog_variant_active_required")
        data.update(dimensions(source.get("attributes")))
    if resource == "attributes" and not isinstance(source.get("terms"), list):
        raise ValueError("catalog_terms_required")
    if resource == "inventory":
        if identifier(source.get("variant_id"), True) != identity or not isinstance(
            source.get("totals"), dict
        ):
            raise ValueError("inventory_identity_or_totals_invalid")
        data.update(source["totals"])
        if any(data.get(k) is None for k in ("qty_total", "qty_reserved", "qty_available")):
            raise ValueError("inventory_totals_required")
    if resource == "images":
        identifier(source.get("product_id"), True)
        url = source.get("image_url")
        parsed = urlsplit(url) if isinstance(url, str) else None
        variants = source.get("variant_ids")
        if (
            not isinstance(url, str)
            or parsed is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or len(url) > 2048
            or type(source.get("is_primary")) is not bool
            or type(source.get("display_order")) is not int
            or source["display_order"] < 0
            or not isinstance(variants, list)
            or len(variants) > 10000
            or any(not isinstance(v, str) or not v.strip() for v in variants)
            or len(set(variants)) != len(variants)
        ):
            raise ValueError("catalog_image_contract_invalid")
    if resource in {"products", "variants", "images"}:
        for field in ("created_at", "updated_at"):
            if source.get(field) is None:
                raise ValueError("catalog_timestamp_required")
    return table, {k: typed(data.get(k), typ) for k, typ in fields.items()}, None
