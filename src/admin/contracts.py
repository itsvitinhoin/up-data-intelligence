"""No credential in repr, hashes, persisted rows or public responses."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.analytics.policy import ORDER_STATUSES, VERSION
from src.control_plane.model import StoreConfig
from src.control_plane.registry import Admin
from src.domain.models import SafeError
from src.utils.data import digest

MAX_BODY = 32768


class AdminError(SafeError):
    status: int

    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.status = status


@dataclass(frozen=True)
class Principal(Admin):
    tenants: frozenset[str]

    def authorize_tenant(self, tenant: str) -> None:
        authorize(self)
        if tenant not in self.tenants:
            raise AdminError("tenant_forbidden", 403)


def authorize(principal: Principal | None) -> Principal:
    if principal is None:
        raise AdminError("unauthenticated", 401)
    if (
        not isinstance(principal, Principal)
        or not isinstance(principal.subject, str)
        or not principal.subject.strip()
    ):
        raise AdminError("admin_up_required", 403)
    try:
        principal.authorize()
    except SafeError:
        raise AdminError("admin_up_required", 403) from None
    return principal


def identity(subject: str, key: bytes) -> str:
    if len(key) < 32:
        raise ValueError("admin_subject_signing_key_required")
    return hmac.new(key, subject.encode(), hashlib.sha256).hexdigest()


def uuid_key(value: Any) -> str:
    try:
        if not isinstance(value, str) or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise AdminError("invalid_idempotency_key", 400) from None


def exact(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise AdminError("invalid_onboarding_request", 400)
    return value


def text(value: Any, maximum: int, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise AdminError("invalid_onboarding_request", 400)
    return value


def boolean(value: Any) -> bool:
    if type(value) is not bool:
        raise AdminError("invalid_onboarding_request", 400)
    return value


@dataclass(frozen=True)
class Request:
    tenant_id: str
    config: StoreConfig
    credential: str | None = field(repr=False)

    @property
    def request_hash(self) -> str:
        # Credential presence follows upzero_enabled. No credential digest is stored.
        return digest([self.tenant_id, self.config.row()])

    @property
    def brand_id(self) -> str:
        return "brand-" + self.config.store_id

    def bindings(self, at: str) -> list[dict[str, Any]]:
        return [
            {
                "row_key": digest([self.tenant_id, self.config.store_id + "-" + op.lower()]),
                "tenant_id": self.tenant_id,
                "brand_id": self.brand_id,
                "workspace_operation_id": self.config.store_id + "-" + op.lower(),
                "store_id": self.config.store_id,
                "operation": op,
                "status": "DRAFT",
                "created_at": at,
                "updated_at": at,
            }
            for op, enabled in (
                ("B2B", self.config.operation_b2b),
                ("B2C", self.config.operation_b2c),
            )
            if enabled
        ]


def parse_request(value: Any) -> Request:
    try:
        root = exact(value, {"tenant_id", "store", "sources"})
        tenant = text(root["tenant_id"], 100)
        if not tenant or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", tenant):
            raise ValueError
        s = exact(
            root["store"],
            {
                "name",
                "slug",
                "operation_b2b",
                "operation_b2c",
                "timezone",
                "currency",
                "history_from",
                "qualifying_order_statuses",
            },
        )
        sources = exact(root["sources"], {"upzero", "meta"})
        up = exact(sources["upzero"], {"enabled", "credential", "store_identifier"})
        meta = exact(sources["meta"], {"enabled", "account_id", "api_version"})
        up_enabled, meta_enabled = boolean(up["enabled"]), boolean(meta["enabled"])
        credential = text(up["credential"], 8192, nullable=not up_enabled)
        if credential is not None and any(not 33 <= ord(c) <= 126 for c in credential):
            raise ValueError
        if not up_enabled and (credential is not None or up["store_identifier"] is not None):
            raise ValueError
        if not meta_enabled and (meta["account_id"] is not None or meta["api_version"] is not None):
            raise ValueError
        slug = text(s["slug"], 80)
        timezone = text(s["timezone"], 100)
        local = text(s["history_from"], 10)
        if not local or date.fromisoformat(local).isoformat() != local:
            raise ValueError
        statuses = s["qualifying_order_statuses"]
        if (
            not isinstance(statuses, list)
            or any(not isinstance(v, str) for v in statuses)
            or len(set(statuses)) != len(statuses)
            or not set(statuses) <= ORDER_STATUSES - {"CANCELED"}
            or (boolean(s["operation_b2b"]) and not statuses)
            or (not s["operation_b2b"] and statuses)
        ):
            raise ValueError
        config = StoreConfig(
            store_id=slug or "",
            store_slug=slug,
            store_name=text(s["name"], 120),
            operation_b2b=boolean(s["operation_b2b"]),
            qualifying_order_statuses=tuple(statuses),
            policy_version=VERSION if s["operation_b2b"] else None,
            operation_b2c=boolean(s["operation_b2c"]),
            timezone=timezone,
            currency=text(s["currency"], 3),
            history_from=datetime.combine(
                date.fromisoformat(local), time(), ZoneInfo(timezone or "")
            )
            .astimezone(UTC)
            .isoformat(),
            upzero_enabled=up_enabled,
            upzero_connection_id=(slug or "") + "-upzero" if up_enabled else None,
            upzero_store_identifier=text(up["store_identifier"], 120, nullable=True),
            meta_enabled=meta_enabled,
            meta_connection_id=(slug or "") + "-meta" if meta_enabled else None,
            meta_account_id=text(meta["account_id"], 32, nullable=not meta_enabled),
            meta_api_version=text(meta["api_version"], 16, nullable=not meta_enabled),
        )
        config.ready()  # Existing authoritative timezone/currency/ID/operation rules.
        return Request(tenant, config, credential)
    except (SafeError, ValueError, TypeError, KeyError):
        raise AdminError("invalid_onboarding_request", 400) from None


def decode_body(body: bytes) -> Any:
    if len(body) > MAX_BODY:
        raise AdminError("request_body_too_large", 413)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        return json.loads(body, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise AdminError("invalid_onboarding_request", 400) from None
