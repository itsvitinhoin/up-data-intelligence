import copy

import pytest

from src.normalization.entities import normalize, typed


@pytest.mark.parametrize("field", ["state", "city"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_geography_is_null(field, value):
    source = {
        "id": "001",
        "customer_type": "WHOLESALE",
        "wholesale_profile": {"address_" + field: value},
    }
    original = copy.deepcopy(source)
    _, customer, _ = normalize("customers", source)
    assert customer[field] is None
    assert customer["wholesale_profile"] == original["wholesale_profile"]
    assert source == original


def test_valid_geography_no_inference():
    _, row, _ = normalize(
        "customers",
        {
            "id": "1",
            "customer_type": "WHOLESALE",
            "wholesale_profile": {"address_state": "SP", "address_city": "Synthetic city"},
        },
    )
    assert (row["state"], row["city"]) == ("SP", "Synthetic city")
    _, row, _ = normalize(
        "customers",
        {"id": "1", "customer_type": "WHOLESALE", "retail_profile": {"address_state": "SP"}},
    )
    assert row["state"] is None


@pytest.mark.parametrize("value", ["", "   ", None, True])
def test_customer_id_remains_required(value):
    with pytest.raises(ValueError):
        normalize("customers", {"id": value})


@pytest.mark.parametrize("value", ["", "   ", None])
def test_optional_contacts_and_seller(value):
    source = {
        "id": "1",
        "email": value,
        "phone": value,
        "name": value,
        "status": value,
        "seller": {"id": value},
        "external_ref": {"integration": value, "external_id": value},
        "retail_profile": {"cpf": value, "meta": {"optional_id": value}},
        "wholesale_profile": {"cnpj": value, "company_name": value, "trade_name": value},
    }
    original = copy.deepcopy(source)
    _, row, _ = normalize("customers", source)
    for field in (
        "email",
        "phone",
        "name",
        "status",
        "seller_id",
        "cpf",
        "cnpj",
        "company_name",
        "trade_name",
        "email_normalized",
        "phone_normalized",
        "phone_e164",
        "cnpj_digits",
        "cpf_digits",
    ):
        assert row[field] is None
    for field in ("seller", "external_ref", "retail_profile", "wholesale_profile"):
        assert row[field] == original[field]
    assert source == original


def test_original_json_and_nonempty_scalar_values_preserved():
    source = {
        "id": "001",
        "email": " Contact@EXAMPLE.invalid ",
        "phone": "(11) 00000-0000",
        "seller": {"id": 7},
        "external_ref": {"external_id": "0007"},
        "retail_profile": {"cpf": "000.000.001-00", "meta": {"arbitrary_id": ""}},
    }
    _, row, _ = normalize("customers", source)
    assert row["email"] == source["email"]
    assert row["email_normalized"] == "contact@example.invalid"
    assert row["phone"] == source["phone"] and row["phone_e164"] is None
    assert row["cpf_digits"] == "00000000100"
    assert row["seller_id"] == "7" and row["seller"]["id"] == 7
    assert row["external_ref"] == source["external_ref"]


def test_no_generic_identifier_relaxation():
    with pytest.raises(ValueError):
        typed("", "STRING")
    with pytest.raises(ValueError):
        normalize("customers", {"id": "1", "seller": {"id": {}}})


@pytest.mark.parametrize("value", ["", "   ", None])
def test_absent_external_reference_container(value):
    source = {"id": "1", "external_ref": value}
    _, row, _ = normalize("customers", source)
    assert row["external_ref"] is None
    assert source["external_ref"] == value
