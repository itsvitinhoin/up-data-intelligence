"""Exact UP Zero attribute codes, including the observed Portuguese contract.

These are explicit source codes, not translated labels or SKU/name heuristics.
Stored attributes also let readers interpret already-certified snapshot versions
without rewriting CORE or replaying their source requests.
"""

from typing import Any

from src.utils.data import identifier

ATTRIBUTE_CODES = {"color": ("color", "cor"), "size": ("size", "tamanho")}


def dimensions(attributes: Any) -> dict[str, str | None]:
    if not isinstance(attributes, list):
        raise ValueError("catalog_variant_attributes_required")
    result: dict[str, str | None] = {}
    for dimension, codes in ATTRIBUTE_CODES.items():
        assigned = [
            value
            for value in attributes
            if isinstance(value, dict)
            and isinstance(value.get("attribute"), dict)
            and value["attribute"].get("code") in codes
        ]
        if len(assigned) > 1:
            raise ValueError("catalog_attribute_ambiguous")
        term = assigned[0].get("term") if assigned else None
        if term is not None and not isinstance(term, dict):
            raise ValueError("catalog_term_invalid")
        result[dimension] = identifier((term or {}).get("name"))
        result[dimension + "_code"] = identifier((term or {}).get("code"))
    return result
