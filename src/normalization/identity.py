"""Conservative, reversible identity derivatives. Never join identities by guessing."""

import re
from typing import Any

from src.utils.data import identifier

VERSION = "1.0.0"


def customer_identity(source: dict[str, Any]) -> dict[str, Any]:
    retail = source.get("retail_profile") or {}
    wholesale = source.get("wholesale_profile") or {}
    issues: dict[str, str] = {}

    def digits(value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(r"[0-9.\-/\s]+", value):
            issues[field] = "unsupported_characters_original_preserved"
            return None
        result = re.sub(r"[^0-9]", "", value)
        if len(result) != (14 if field == "cnpj" else 11):
            issues[field] = "unexpected_length_not_a_validity_check"
        return result or None

    email = source.get("email")
    email_normalized = email.strip().lower() if isinstance(email, str) else None
    if email_normalized and (
        email_normalized.count("@") != 1
        or re.search(r"\s", email_normalized)
        or any(not part for part in email_normalized.split("@"))
    ):
        issues["email"] = "invalid_format_not_for_automatic_matching"
    phone = source.get("phone")
    phone_normalized, phone_e164 = None, None
    if phone is not None:
        if isinstance(phone, str) and re.fullmatch(r"\+?[0-9() .\-\s]+", phone.strip()):
            phone_normalized = re.sub(r"[^0-9]", "", phone) or None
            if phone.strip().startswith("+") and phone_normalized:
                if re.fullmatch(r"[1-9][0-9]{7,14}", phone_normalized):
                    phone_e164 = "+" + phone_normalized
                else:
                    issues["phone"] = "invalid_international_shape"
            elif phone_normalized:
                issues["phone"] = "country_not_inferred"
        else:
            issues["phone"] = "ambiguous_extension_or_characters"
    if source.get("customer_type") == "WHOLESALE":
        profile = wholesale
    elif source.get("customer_type") == "RETAIL":
        profile = retail
    else:
        profile = {}
        if retail or wholesale:
            issues["geography"] = "customer_type_missing_or_unknown"
    seller = source.get("seller") or {}
    return {
        "email_normalized": email_normalized or None,
        "phone_normalized": phone_normalized,
        "phone_e164": phone_e164,
        "cnpj_digits": digits(wholesale.get("cnpj"), "cnpj"),
        "cpf_digits": digits(retail.get("cpf"), "cpf"),
        "seller_id": identifier(seller.get("id")),
        "state": profile.get("address_state"),
        "city": profile.get("address_city"),
        "external_ref": source.get("external_ref"),
        "identity_normalization_version": VERSION,
        "identity_normalization_issues": issues,
    }


def resolve_customer(
    event: dict[str, Any], orders: list[dict[str, Any]], customers: list[dict[str, Any]]
) -> dict[str, Any]:
    """Proposed resolved view semantics. No writes, transitive union, or user=id join.

    Result concerns the customer on the referenced order, NOT proof of who was logged
    in. A customer shared by two events does not merge their visitors/devices.
    """
    store = event.get("store_id")
    result: dict[str, Any] = {
        "customer_id": None,
        "resolution_status": "missing_order_id",
        "evidence_type": None,
        "order_version_id": None,
        "customer_version_id": None,
    }
    if not store or event.get("source_system") != "upzero":
        result["resolution_status"] = "unsupported_source_or_store"
        return result
    if not event.get("order_id"):
        return result
    matches = [
        o
        for o in orders
        if o.get("store_id") == store
        and o.get("source_system") == "upzero"
        and o.get("order_id") == event["order_id"]
    ]
    if len(matches) != 1:
        result["resolution_status"] = "order_missing_or_ambiguous"
        return result
    order = matches[0]
    result["order_version_id"] = order.get("version_id")
    customer = [
        c
        for c in customers
        if c.get("store_id") == store
        and c.get("source_system") == "upzero"
        and c.get("customer_id")
        and c["customer_id"] == order.get("customer_id")
    ]
    if len(customer) != 1:
        result["resolution_status"] = "customer_missing_or_ambiguous"
        return result
    return {
        "customer_id": customer[0]["customer_id"],
        "resolution_status": "resolved_via_order",
        "evidence_type": "observed_event_order_customer",
        "order_version_id": order.get("version_id"),
        "customer_version_id": customer[0].get("version_id"),
    }


def identity_evidence(
    meta: dict[str, Any],
    *,
    entity_type: str,
    entity_id: str,
    left: str,
    left_id: str,
    right: str,
    right_id: str,
    evidence_type: str,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    from src.utils.data import digest

    key = digest([meta["version_id"], left, right])
    return {
        **meta,
        "row_key": key,
        "link_id": key,
        "source_fact_id": entity_id if entity_type == "analytics_fact" else None,
        "source_entity_type": entity_type,
        "source_entity_id": entity_id,
        "source_version_id": meta["version_id"],
        "left_namespace": left,
        "left_id": left_id,
        "right_namespace": right,
        "right_id": right_id,
        "identifier_type_from": left,
        "identifier_value_from": left_id,
        "identifier_type_to": right,
        "identifier_value_to": right_id,
        "confidence_type": "DETERMINISTIC",
        "evidence_type": evidence_type,
        "occurred_at": occurred_at,
        # Bounds of this versioned evidence, not a global identity lifetime.
        "first_seen_at": meta["observed_at"],
        "last_seen_at": meta["observed_at"],
    }
