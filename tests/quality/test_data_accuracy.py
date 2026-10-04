from decimal import Decimal

import pytest

from src.quality.data_accuracy import compare


def parity(left, right):
    return compare(
        left,
        right,
        identity=("store_id", "order_id"),
        fields=("requested", "fulfilled"),
        numeric=frozenset({"requested", "fulfilled"}),
    )


def order(oid="synthetic-1", requested="10.12", fulfilled="8.00", store="synthetic-brand"):
    return {"store_id": store, "order_id": oid, "requested": requested, "fulfilled": fulfilled}


def test_exact_decimal_and_requested_fulfilled_semantics():
    result = parity([order()], [order(requested=Decimal("10.120000000"), fulfilled=Decimal("8"))])
    assert result["status"] == "PASS"
    assert result["expected_identity_digest"] == result["actual_identity_digest"]
    assert "synthetic-1" not in str(result)
    assert parity([order()], [order(requested="8", fulfilled="10.12")])["status"] == "FAIL"


def test_compensating_money_errors_cannot_pass():
    result = parity([order("a", "10"), order("b", "20")], [order("a", "20"), order("b", "10")])
    assert result["status"] == "FAIL"
    assert result["field_mismatch_counts"]["requested"] == 2


@pytest.mark.parametrize("value", [None, False])
def test_unknown_is_not_zero(value):
    result = compare(
        [{"id": "x", "value": value}],
        [{"id": "x", "value": 0}],
        identity=("id",),
        fields=("value",),
    )
    assert result["status"] == "FAIL"


def test_missing_different_identity_and_store_isolation():
    result = parity([order()], [order("other")])
    assert result["missing_identities"] == result["unexpected_identities"] == 1
    result = parity([order()], [order(store="other-brand")])
    assert result["status"] == "FAIL"


def test_duplicates_and_missing_required_identities_fail():
    result = parity([order()], [order(), order(), order(oid=None)])
    assert result["duplicate_target_identities"] == result["invalid_target_identities"] == 1
    assert result["status"] == "FAIL"


def test_float_and_nonfinite_money_are_rejected():
    for value in (10.12, "NaN", "Infinity"):
        with pytest.raises(ValueError):
            parity([order()], [order(requested=value)])


def test_order_does_not_change_aggregate_digest():
    assert parity([order("a"), order("b")], [order("b"), order("a")])["status"] == "PASS"


def test_empty_is_valid_only_when_both_layers_empty():
    assert parity([], [])["status"] == "PASS"
    assert parity([order()], [])["status"] == "FAIL"
