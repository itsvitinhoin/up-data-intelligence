"""Validated request, authorization and response contracts for Analytics V1."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.analytics.config import AnalyticsPolicy

CONTRACT_VERSION = "1.0.0"


class ReadError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Grant:
    tenant_id: str
    store_id: str
    operation: str


@dataclass(frozen=True)
class Principal:
    """Created only by a trusted server-side authenticator, never from query fields."""

    subject: str
    role: str
    grants: frozenset[Grant]

    def authorize(self, tenant_id: str, store_id: str, operation: str) -> None:
        if not self.subject or self.role not in {"ADMIN_UP", "CLIENT_USER"}:
            raise ReadError(401, "unauthenticated")
        if not tenant_id or not store_id or operation != "B2B":
            raise ReadError(400, "invalid_scope")
        if Grant(tenant_id, store_id, operation) not in self.grants:
            raise ReadError(403, "store_forbidden")


@dataclass(frozen=True)
class Publication:
    store_id: str
    policy_hash: str
    generation: int
    publication_id: str
    snapshot_at: str
    as_of: str
    report_from: str
    report_to: str

    def validate(self, policy: AnalyticsPolicy) -> None:
        try:
            as_of_matches = datetime.fromisoformat(
                self.as_of.replace("Z", "+00:00")
            ) == datetime.fromisoformat(policy.as_of.replace("Z", "+00:00"))
        except ValueError:
            as_of_matches = False
        if (
            self.store_id != policy.store_id
            or self.policy_hash != policy.policy_hash
            or not isinstance(self.generation, int)
            or self.generation < 1
            or not re.fullmatch(r"[a-f0-9]{64}", self.publication_id)
            or self.report_from != policy.report_from
            or self.report_to != policy.report_to
            or not as_of_matches
        ):
            raise ReadError(503, "invalid_publication")
        try:
            datetime.fromisoformat(self.snapshot_at.replace("Z", "+00:00"))
        except ValueError:
            raise ReadError(503, "invalid_publication") from None


def metadata(
    publication: Publication, policy: AnalyticsPolicy, limitations: list[str]
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "store_id": publication.store_id,
        "generation": publication.generation,
        "policy_hash": publication.policy_hash,
        "currency": policy.currency,
        "reporting_timezone": policy.reporting_timezone,
        "as_of": publication.as_of,
        "report_from": publication.report_from,
        "report_to": publication.report_to,
        "history_complete": policy.history_complete,
        "facts_complete": policy.facts_complete,
        "limitations": sorted(set(limitations)),
    }


def decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ReadError(503, "invalid_numeric_value")
    try:
        amount = Decimal(str(value))
    except Exception:
        raise ReadError(503, "invalid_numeric_value") from None
    if not amount.is_finite():
        raise ReadError(503, "invalid_numeric_value")
    return format(amount, "f")


def integer(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ReadError(503, "invalid_integer_value")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ReadError(503, "invalid_integer_value") from None
    if str(result) != str(value):
        raise ReadError(503, "invalid_integer_value")
    return result


def iso_date(value: Any) -> str:
    try:
        result = date.fromisoformat(str(value))
    except ValueError:
        raise ReadError(400, "invalid_date") from None
    return result.isoformat()


def page_size(value: str | None) -> int:
    try:
        size = 20 if value is None else int(value)
    except ValueError:
        raise ReadError(400, "invalid_page_size") from None
    if not 1 <= size <= 100:
        raise ReadError(400, "invalid_page_size")
    return size


class CursorCodec:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("cursor_signing_key_too_short")
        self._key = key

    def encode(self, context: dict[str, Any], last_key: str) -> str:
        payload = json.dumps(
            {"context": context, "last_key": last_key}, sort_keys=True, separators=(",", ":")
        ).encode()
        signature = hmac.digest(self._key, payload, "sha256")
        return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")

    def decode(self, token: str, context: dict[str, Any]) -> str:
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            payload, signature = raw[:-32], raw[-32:]
            data = json.loads(payload)
            if (
                not hmac.compare_digest(signature, hmac.digest(self._key, payload, "sha256"))
                or data["context"] != context
                or not re.fullmatch(
                    r"(?:[a-f0-9]{64}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z:[a-f0-9]{64})",
                    data["last_key"],
                )
            ):
                raise ValueError
            return str(data["last_key"])
        except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
            raise ReadError(400, "invalid_cursor") from None


def cursor_context(
    principal: Principal, grant: Grant, publication: Publication, resource: str, size: int
) -> dict[str, Any]:
    return {
        "subject": hashlib.sha256(principal.subject.encode()).hexdigest(),
        "role": principal.role,
        "tenant_id": grant.tenant_id,
        "store_id": grant.store_id,
        "operation": grant.operation,
        "policy_hash": publication.policy_hash,
        "generation": publication.generation,
        "resource": resource,
        "page_size": size,
    }
