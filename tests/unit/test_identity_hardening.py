import copy
import json

import pytest

from src.normalization.entities import normalize
from src.normalization.identity import customer_identity, resolve_customer


@pytest.fixture
def customer():
    return {
        "id": "101",
        "email": "  Contact@EXAMPLE.invalid  ",
        "phone": "+55 (11) 00000-0000",
        "customer_type": "WHOLESALE",
        "status": "APPROVED",
        "seller": {"id": "007", "name": "Synthetic seller"},
        "external_ref": {"integration": "synthetic-erp", "external_id": "0009"},
        "wholesale_profile": {
            "cnpj": "00.000.000/0001-00",
            "company_name": "Synthetic company",
            "trade_name": "Synthetic",
            "address_city": "Test City",
            "address_state": "SP",
        },
        "retail_profile": {"cpf": "000.000.001-00"},
    }


def test_customer_originals_and_derivatives(customer):
    before = copy.deepcopy(customer)
    _, row, _ = normalize("customers", customer)
    assert customer == before
    assert row["email"] == customer["email"] and row["phone"] == customer["phone"]
    assert row["cnpj"] == "00.000.000/0001-00" and row["cpf"] == "000.000.001-00"
    assert row["cnpj_digits"] == "00000000000100" and row["cpf_digits"] == "00000000100"
    assert row["email_normalized"] == "contact@example.invalid"
    assert row["phone_normalized"] == "5511000000000" and row["phone_e164"] == "+5511000000000"
    assert row["seller_id"] == "007" and row["seller"] == customer["seller"]
    assert (row["state"], row["city"]) == ("SP", "Test City")
    assert row["company_name"] == "Synthetic company"
    assert row["external_ref"]["external_id"] == "0009"
    assert (
        not {"user_id", "created_at", "updated_at", "primary_cnae", "simples_optante"} & row.keys()
    )


@pytest.mark.parametrize(
    "phone,normalized,e164,issue",
    [
        ("(11) 00000-0000", "11000000000", None, "country_not_inferred"),
        ("0055 11 00000-0000", "005511000000000", None, "country_not_inferred"),
        ("+012345678", "012345678", None, "invalid_international_shape"),
        ("+55 11 00000-0000 ext 7", None, None, "ambiguous_extension_or_characters"),
        (None, None, None, None),
    ],
)
def test_phone_never_infers_country(phone, normalized, e164, issue):
    row = customer_identity({"phone": phone})
    assert (row["phone_normalized"], row["phone_e164"]) == (normalized, e164)
    assert row["identity_normalization_issues"].get("phone") == issue


@pytest.mark.parametrize(
    "value,expected,issue",
    [
        ("12", "12", "unexpected_length_not_a_validity_check"),
        ("00A.000/0001-00", None, "unsupported_characters_original_preserved"),
        (123, None, "unsupported_characters_original_preserved"),
        (None, None, None),
    ],
)
def test_cnpj_invalid_preserves_original(value, expected, issue):
    _, row, _ = normalize("customers", {"id": "1", "wholesale_profile": {"cnpj": value}})
    assert row["cnpj"] == (str(value) if value is not None else None)
    assert row["cnpj_digits"] == expected
    assert row["identity_normalization_issues"].get("cnpj") == issue


def test_email_and_geography_ambiguity(customer):
    customer["email"] = " no at sign "
    customer["customer_type"] = None
    row = customer_identity(customer)
    assert row["email_normalized"] == "no at sign"
    assert row["identity_normalization_issues"]["email"]
    assert row["city"] is None and row["state"] is None
    customer["customer_type"] = "RETAIL"
    customer["retail_profile"]["address_city"] = "Retail city"
    assert customer_identity(customer)["city"] == "Retail city"


def test_customer_secrets_are_redacted_recursively(customer):
    customer["password_hash"] = "SYNTHETIC_BLOCKED_HASH"
    customer["wholesale_profile"]["meta"] = {
        "access_token": "SYNTHETIC_BLOCKED_TOKEN",
        "business_data": {"label": "keep"},
        "embedded": '{"refresh_token":"SYNTHETIC_BLOCKED_REFRESH"}',
    }
    _, row, _ = normalize("customers", customer)
    assert "SYNTHETIC_BLOCKED" not in json.dumps(row)
    assert row["wholesale_profile"]["meta"]["business_data"] == {"label": "keep"}


def test_resolution_never_joins_user_to_customer_or_crosses_tenants():
    event = {"store_id": "A", "source_system": "upzero", "user_id": "101", "order_id": "9001"}
    order = {
        "store_id": "A",
        "source_system": "upzero",
        "order_id": "9001",
        "customer_id": "101",
        "version_id": "ov",
    }
    customer = {
        "store_id": "A",
        "source_system": "upzero",
        "customer_id": "101",
        "version_id": "cv",
    }
    assert resolve_customer(event, [order], [customer])["customer_id"] == "101"
    assert resolve_customer(event | {"order_id": None}, [order], [customer])["customer_id"] is None
    for orders, customers in [
        ([], [customer]),
        ([order], []),
        ([order, order], [customer]),
        ([order], [customer, customer]),
        ([order | {"store_id": "B"}], [customer]),
        ([order], [customer | {"source_system": "erp"}]),
    ]:
        assert resolve_customer(event, orders, customers)["customer_id"] is None


def test_order_commercial_values_and_existing_snapshots_preserved(customer):
    source = json.load(open("tests/fixtures/pilot.json"))["orders"][0]
    source.update(
        id="9001",
        customer=customer,
        order_status="RESERVED",
        payment_status="unpaid",
        requested_total="3600.00",
        fulfilled_total="1440.00",
        total="1440.00",
        requested_items_qty=12,
        fulfilled_items_qty=5,
        items_count=11,
        shipping_address={"full_address": "Synthetic restricted address"},
    )
    _, order, _ = normalize("orders", source)
    order.update(
        store_id="A",
        source_system="upzero",
        version_id="version-synthetic",
        raw_record_id="raw-synthetic",
    )
    assert (
        order["order_id"],
        order["customer_id"],
        order["order_status"],
        order["payment_status"],
    ) == ("9001", "101", "RESERVED", "unpaid")
    assert (order["requested_total"], order["fulfilled_total"], order["total"]) == (
        "3600.00",
        "1440.00",
        "1440.00",
    )
    assert (order["requested_items_qty"], order["fulfilled_items_qty"], order["items_count"]) == (
        12,
        5,
        11,
    )
    assert order["customer_snapshot"]["wholesale_profile"] == customer["wholesale_profile"]
    assert order["shipping_address"] == source["shipping_address"]
