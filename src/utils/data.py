import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def now() -> str:
    return datetime.now(UTC).isoformat()


def timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_timestamp")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone_required")
    return d.astimezone(UTC).isoformat()


def stable_numbers(value: Any) -> Any:
    # BigQuery JSON canonicalizes 25.0 to 25. Treat these equal numeric values identically.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: stable_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [stable_numbers(v) for v in value]
    return value


def canonical(value: Any) -> str:
    return json.dumps(
        stable_numbers(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value: Any, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError("missing_id")
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ValueError("invalid_id")
    return str(value)


def numeric(value: Any) -> str | None:
    if value is None:
        return None
    try:
        n = Decimal(str(value))
        if not n.is_finite() or abs(n) >= Decimal("1e29") or n.as_tuple().exponent < -9:  # type: ignore[operator]
            raise ValueError
        return format(n, "f")
    except Exception:
        raise ValueError("invalid_numeric") from None
