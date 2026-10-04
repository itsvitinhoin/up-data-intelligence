"""Exact, identity-aware acceptance; only aggregate evidence leaves the comparator."""

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.utils.data import digest, timestamp

Row = dict[str, Any]


def exact(value: Any, *, money: bool = False) -> Any:
    if isinstance(value, float):
        raise ValueError("accuracy_float_not_allowed")
    if value is None:
        return None
    if isinstance(value, bool):
        if money:
            raise ValueError("accuracy_boolean_not_numeric")
        return ("BOOL", value)  # Python False == 0 must not erase contract types.
    if money:
        parsed = Decimal(value)
        if not parsed.is_finite():
            raise ValueError("accuracy_nonfinite_number")
        return parsed
    if isinstance(value, datetime):
        return timestamp(value.isoformat())
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: exact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [exact(v) for v in value]
    return value


def compare(
    expected: Iterable[Row],
    actual: Iterable[Row],
    *,
    identity: tuple[str, ...],
    fields: tuple[str, ...],
    numeric: frozenset[str] = frozenset(),
) -> Row:
    """Equal totals cannot hide missing IDs or compensating per-entity differences.

    Caller supplies an approved minimal projection, never raw/customer PII. NULL is
    compared directly; it is never coalesced into zero or false. No IDs are returned.
    """

    def indexed(rows: Iterable[Row]) -> tuple[dict[tuple[Any, ...], Row], int, int, int]:
        result: dict[tuple[Any, ...], Row] = {}
        keys: Counter[tuple[Any, ...]] = Counter()
        invalid, count = 0, 0
        for row in rows:
            count += 1
            key = tuple(exact(row.get(k)) for k in identity)
            if any(v is None or v == "" for v in key):
                invalid += 1
                continue
            keys[key] += 1
            result[key] = {k: exact(row[k], money=k in numeric) for k in fields}
        return result, sum(n - 1 for n in keys.values()), invalid, count

    left, left_duplicates, left_invalid, left_count = indexed(expected)
    right, right_duplicates, right_invalid, right_count = indexed(actual)
    missing, unexpected = left.keys() - right.keys(), right.keys() - left.keys()
    shared = left.keys() & right.keys()
    differences = {
        field: sum(left[k][field] != right[k][field] for k in shared) for field in fields
    }
    failures = (
        left_duplicates
        + right_duplicates
        + left_invalid
        + right_invalid
        + len(missing)
        + len(unexpected)
        + sum(differences.values())
    )
    return {
        "expected_count": left_count,
        "actual_count": right_count,
        "count_delta": right_count - left_count,
        "expected_identity_digest": digest(sorted(digest(k) for k in left)),
        "actual_identity_digest": digest(sorted(digest(k) for k in right)),
        "duplicate_source_identities": left_duplicates,
        "duplicate_target_identities": right_duplicates,
        "invalid_source_identities": left_invalid,
        "invalid_target_identities": right_invalid,
        "missing_identities": len(missing),
        "unexpected_identities": len(unexpected),
        "field_mismatch_counts": differences,
        "status": "FAIL" if failures else "PASS",
    }
