"""Verified identities resolve to explicit canonical workspace grants, never claims."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.admin.contracts import Principal as AdminPrincipal
from src.dashboard.contracts import Grant, Principal, ReadError
from src.utils.data import digest


@dataclass(frozen=True)
class Identity:
    uid: str = field(repr=False)
    identity_hash: str


def verified_identity(claims: Mapping[str, Any]) -> Identity:
    email, uid = claims.get("email"), claims.get("uid") or claims.get("sub")
    if claims.get("email_verified") is not True:
        raise ReadError(403, "verified_email_required")
    if not isinstance(email, str) or not isinstance(uid, str) or not uid:
        raise ReadError(401, "invalid_identity")
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+", normalized):
        raise ReadError(401, "invalid_identity")
    return Identity(uid, hashlib.sha256(normalized.encode()).hexdigest())


class AccessRepository(Protocol):
    def access(self, identity_hash: str) -> list[dict[str, Any]]: ...
    def bindings(self, tenants: frozenset[str]) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class Access:
    identity: Identity
    role: str
    tenants: frozenset[str]
    workspaces: tuple[dict[str, str], ...]

    def dashboard(self) -> Principal:
        return Principal(
            self.identity.identity_hash,
            self.role,
            frozenset(
                Grant(w["tenant_id"], w["store_id"], w["operation"]) for w in self.workspaces
            ),
        )

    def admin(self) -> AdminPrincipal:
        if self.role != "ADMIN_UP":
            raise ReadError(403, "admin_up_required")
        return AdminPrincipal(self.identity.identity_hash, "ADMIN_UP", self.tenants)

    def binding(self, tenant: str, workspace: str, operation: str) -> dict[str, str]:
        matches = [
            w
            for w in self.workspaces
            if (w["tenant_id"], w["workspace_operation_id"], w["operation"])
            == (tenant, workspace, operation)
        ]
        if len(matches) != 1:
            raise ReadError(403, "workspace_forbidden")
        return matches[0]

    def catalog(self) -> dict[str, Any]:
        # Technical store IDs, UID/email, secret references and source metadata are absent.
        return {
            "data": {
                "role": self.role,
                "tenants": sorted(self.tenants),
                "workspaces": [
                    {
                        k: w[k]
                        for k in ("tenant_id", "brand_id", "workspace_operation_id", "operation")
                    }
                    for w in self.workspaces
                ],
            }
        }


def resolve(identity: Identity, repository: AccessRepository) -> Access:
    rows = repository.access(identity.identity_hash)
    if not rows:
        raise ReadError(403, "access_not_provisioned")
    if len(rows) > 100:
        raise ReadError(403, "access_inventory_limit")
    roles = {r.get("role") for r in rows}
    if len(roles) != 1 or not roles <= {"ADMIN_UP", "CLIENT_USER"}:
        raise ReadError(403, "conflicting_access")
    role = str(next(iter(roles)))
    keys: set[tuple[str, str | None]] = set()
    for row in rows:
        tenant, workspace = row.get("tenant_id"), row.get("workspace_operation_id")
        if (
            row.get("identity_hash") != identity.identity_hash
            or row.get("status") != "ACTIVE"
            or not isinstance(tenant, str)
            or not tenant
            or (role == "CLIENT_USER" and (not isinstance(workspace, str) or not workspace))
            or (role == "ADMIN_UP" and workspace is not None)
            or row.get("row_key") != digest([identity.identity_hash, tenant, workspace])
            or (tenant, workspace) in keys
        ):
            raise ReadError(403, "access_disabled_or_invalid")
        keys.add((tenant, workspace))
    tenants = frozenset(t for t, _ in keys)
    bindings = repository.bindings(tenants)
    if len(bindings) > 1000:
        raise ReadError(503, "workspace_inventory_limit")
    seen: set[tuple[str, str]] = set()
    selected: list[dict[str, str]] = []
    fields = ("tenant_id", "brand_id", "workspace_operation_id", "store_id", "operation")
    for row in bindings:
        if any(not isinstance(row.get(k), str) or not row[k] for k in fields):
            raise ReadError(503, "workspace_binding_invalid")
        tenant, workspace = row["tenant_id"], row["workspace_operation_id"]
        if (
            tenant not in tenants
            or (tenant, workspace) in seen
            or row.get("row_key") != digest([tenant, workspace])
            or row.get("operation") not in {"B2B", "B2C"}
            or row.get("status") not in {"ACTIVE", "READY", "DRAFT"}
        ):
            raise ReadError(503, "workspace_binding_invalid")
        seen.add((tenant, workspace))
        if role == "ADMIN_UP" or (tenant, workspace) in keys:
            selected.append({k: row[k] for k in fields})
    if role == "CLIENT_USER" and keys != {
        (w["tenant_id"], w["workspace_operation_id"]) for w in selected
    }:
        raise ReadError(403, "workspace_binding_required")
    return Access(
        identity, role, tenants, tuple(sorted(selected, key=lambda w: tuple(w[k] for k in fields)))
    )
