"""Exact source catalog identities only; never derive attributes from SKU/name."""

from typing import Any

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
        if not isinstance(source.get("attributes"), list):
            raise ValueError("catalog_variant_attributes_required")
        for code in ("color", "size"):
            assigned = [
                a
                for a in source["attributes"]
                if isinstance(a, dict)
                and isinstance(a.get("attribute"), dict)
                and a["attribute"].get("code") == code
            ]
            if len(assigned) > 1:
                raise ValueError("catalog_attribute_ambiguous")
            term = assigned[0].get("term") if assigned else None
            if term is not None and not isinstance(term, dict):
                raise ValueError("catalog_term_invalid")
            data[code] = (term or {}).get("name")
            data[code + "_code"] = (term or {}).get("code")
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
    if resource in {"products", "variants"}:
        for field in ("created_at", "updated_at"):
            if source.get(field) is None:
                raise ValueError("catalog_timestamp_required")
    return table, {k: typed(data.get(k), typ) for k, typ in fields.items()}, None
