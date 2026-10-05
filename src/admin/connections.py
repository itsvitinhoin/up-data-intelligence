"""Existing-brand connection SAGA. Secrets never enter hashes, ledgers or responses."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Any, Protocol

from src.admin.contracts import AdminError, Principal, authorize, exact, identity, uuid_key
from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.utils.data import digest, now

Row = dict[str, Any]


class ConnectionsRepository(Protocol):
    def snapshot(self, binding: Row, provider: str) -> tuple[StoreConfig, Row]: ...
    def operation(self, key: str) -> Row | None: ...
    def ensure_idle(self, binding: Row, config: StoreConfig, source: Row) -> None: ...
    def reserve_operation(self, operation: Row) -> Row: ...
    def transition(self, operation: Row, **changes: Any) -> Row: ...
    def finalize_connection(
        self,
        operation: Row,
        binding: Row,
        config: StoreConfig,
        source: Row,
        updated_config: StoreConfig,
        updated_source: Row,
    ) -> Row: ...


class RotationSecrets(Protocol):
    def versions(self, reference: str) -> list[str]: ...
    def rotate(
        self, reference: str, baseline: list[str], credential: str, *, reconcile_only: bool
    ) -> str: ...
    def compare(self, reference: str, credential: str) -> None: ...


class ConnectionService:
    def __init__(
        self,
        repository: ConnectionsRepository,
        secrets: RotationSecrets,
        probe: Callable[[StoreConfig, str, str | None], None],
        lease: Callable[[str], AbstractContextManager[None]],
        subject_key: bytes,
        clock: Callable[[], str] = now,
        addition: Callable[[Principal, Row, str, Any], Row] | None = None,
    ):
        self.repo, self.secrets, self.probe, self.lease, self.key, self.clock = (
            repository,
            secrets,
            probe,
            lease,
            subject_key,
            clock,
        )
        self.addition = addition

    def read(self, principal: Principal, binding: Row) -> Row:
        admin = authorize(principal)
        admin.authorize_tenant(binding["tenant_id"])
        rows = []
        for provider in ("upzero", "meta"):
            try:
                c, s = self.repo.snapshot(binding, provider)
            except AdminError as exc:
                if exc.code == "integration_not_configured":
                    rows.append(
                        {
                            "provider": provider,
                            "status": "not_configured",
                            "credential_configured": False,
                            "connection_id": None,
                            "store_identifier": None,
                            "account_id": None,
                            "api_version": None,
                        }
                    )
                    continue
                raise
            rows.append(
                {
                    "provider": provider,
                    "status": s["status"],
                    "credential_configured": bool(s.get("secret_resource_name"))
                    if provider == "upzero"
                    else c.meta_enabled,
                    "connection_id": s["connection_id"],
                    "store_identifier": c.upzero_store_identifier if provider == "upzero" else None,
                    "account_id": c.meta_account_id if provider == "meta" else None,
                    "api_version": c.meta_api_version if provider == "meta" else None,
                }
            )
        return {
            "data": {
                "tenant_id": binding["tenant_id"],
                "workspace_operation_id": binding["workspace_operation_id"],
                "providers": rows,
            }
        }

    def mutate(self, principal: Principal, binding: Row, key: str, value: Any) -> Row:
        admin = authorize(principal)
        admin.authorize_tenant(binding["tenant_id"])
        if isinstance(value, dict) and value.get("action") == "add":
            if self.addition is None:
                raise AdminError("integration_source_addition_unavailable", 424)
            return self.addition(principal, binding, key, value)
        payload = exact(value, {"provider", "action", "credential"})
        provider, action, credential = payload["provider"], payload["action"], payload["credential"]
        if provider not in {"upzero", "meta"} or action not in {"rotate", "disable", "enable"}:
            raise AdminError("integration_operation_invalid", 400)
        needs_secret = provider == "upzero" and action in {"rotate", "enable"}
        if needs_secret:
            if (
                not isinstance(credential, str)
                or not 1 <= len(credential) <= 8192
                or any(not 33 <= ord(c) <= 126 for c in credential)
            ):
                raise AdminError("integration_credential_required", 400)
        elif credential is not None:
            raise AdminError("integration_credential_forbidden", 400)
        if provider == "meta" and action == "rotate":
            raise AdminError("meta_global_credential_only", 400)
        subject = identity(admin.subject, self.key)
        operation_key = digest([subject, uuid_key(key)])
        request_hash = digest(
            [binding["tenant_id"], binding["workspace_operation_id"], provider, action]
        )
        ambiguous: SafeError | None = None
        try:
            with self.lease("store-dispatch-global"), self.lease(binding["store_id"]):
                try:
                    return self.run(
                        binding, provider, action, credential, operation_key, subject, request_hash
                    )
                except SafeError as exc:
                    if exc.code in {
                        "secret_write_outcome_unknown",
                        "source_verification_outcome_unknown",
                        "integration_write_outcome_unknown",
                    }:
                        ambiguous = exc
                        # Preserve single-writer locks until explicit reconciliation.
                        raise SafeError("registry_write_outcome_unknown") from None
                    raise
        except SafeError:
            if ambiguous:
                raise AdminError(ambiguous.code, 503) from None
            raise

    def run(
        self,
        binding: Row,
        provider: str,
        action: str,
        credential: str | None,
        key: str,
        subject: str,
        request_hash: str,
    ) -> Row:
        c, source = self.repo.snapshot(binding, provider)
        if c.status not in {"ACTIVE", "READY"} or (
            action == "rotate" and source["status"] != "active"
        ):
            raise AdminError("integration_installed_source_required")
        self.repo.ensure_idle(binding, c, source)
        op = self.repo.operation(key)
        if op:
            if (
                op["request_hash"] != request_hash
                or op["tenant_id"] != binding["tenant_id"]
                or op["store_id"] != c.store_id
            ):
                raise AdminError("idempotency_conflict")
            if op["status"] == "COMPLETE":
                if credential is not None:
                    self.secrets.compare(op["candidate_reference"], credential)
                return self.public(op)
            if op["source_snapshot"] != source or op["registry_revision"] != c.revision:
                raise AdminError("integration_configuration_changed")
            if op["status"] == "BLOCKED":
                raise AdminError(op["error_code"] or "integration_blocked")
        else:
            at = self.clock()
            op = self.repo.reserve_operation(
                dict(
                    row_key=key,
                    operation_id=key,
                    tenant_id=binding["tenant_id"],
                    workspace_operation_id=binding["workspace_operation_id"],
                    store_id=c.store_id,
                    provider=provider,
                    action=action,
                    admin_subject_hash=subject,
                    request_hash=request_hash,
                    status="RESERVED",
                    current_step="RESERVED",
                    registry_revision=c.revision,
                    source_snapshot=source,
                    version_baseline=None,
                    candidate_reference=None,
                    error_code=None,
                    revision=1,
                    created_at=at,
                    updated_at=at,
                    completed_at=None,
                )
            )
        reference = source.get("secret_resource_name")
        if credential is not None:
            if not reference:
                raise AdminError("integration_secret_adoption_required")
            candidate = op["candidate_reference"]
            if candidate:
                self.secrets.compare(candidate, credential)
            else:
                if op["current_step"] == "RESERVED":
                    baseline = self.secrets.versions(reference)
                    op = self.repo.transition(
                        op,
                        status="SECRET_PENDING",
                        current_step="VERSION_INTENT",
                        version_baseline=baseline,
                        updated_at=self.clock(),
                    )
                    may_write = True
                else:
                    may_write = False
                try:
                    candidate = self.secrets.rotate(
                        reference, op["version_baseline"], credential, reconcile_only=not may_write
                    )
                except AdminError as exc:
                    if exc.code == "integration_secret_write_rejected":
                        self.repo.transition(
                            op, status="BLOCKED", error_code=exc.code, updated_at=self.clock()
                        )
                    raise
                op = self.repo.transition(
                    op,
                    status="SECRET_READY",
                    current_step="SECRET_READY",
                    candidate_reference=candidate,
                    updated_at=self.clock(),
                )
            reference = candidate
        if action != "disable":
            # Credential is used only here server-side; response payload is discarded.
            # Known ambiguous probe does not get an automatic retry on resubmission.
            if op["current_step"] == "PROBE_INTENT":
                raise SafeError("source_verification_outcome_unknown")
            if op["current_step"] != "VERIFIED":
                op = self.repo.transition(op, current_step="PROBE_INTENT", updated_at=self.clock())
                try:
                    self.probe(c, provider, reference)
                except SafeError as exc:
                    if exc.code.endswith("outcome_unknown") or exc.code in {
                        "retry_exhausted",
                        "invalid_response",
                    }:
                        raise SafeError("source_verification_outcome_unknown") from None
                    self.repo.transition(
                        op, status="BLOCKED", error_code=exc.code, updated_at=self.clock()
                    )
                    raise AdminError(exc.code) from None
                except Exception:
                    raise SafeError("source_verification_outcome_unknown") from None
                op = self.repo.transition(
                    op, status="VERIFIED", current_step="VERIFIED", updated_at=self.clock()
                )
        at = self.clock()
        updated_source = {
            **source,
            "status": "disabled" if action == "disable" else "active",
            "secret_resource_name": reference if provider == "upzero" else None,
            "updated_at": at,
        }
        if action == "rotate":
            updated_config = c
        else:
            changes: Row = {provider + "_enabled": action == "enable"}
            # Disable only dependent pipelines. Do not delete historical evidence or
            # auto-enable Analytics/Intelligence without their own certified gates.
            if action == "disable":
                changes["intelligence_enabled"] = False
                if provider == "upzero":
                    changes["analytics_enabled"] = False
            updated_config = replace(c, **changes, revision=c.revision + 1, updated_at=at)
            updated_config.ready()
        result = self.repo.finalize_connection(
            op, binding, c, source, updated_config, updated_source
        )
        return self.public(result)

    @staticmethod
    def public(operation: Row) -> Row:
        return {
            "data": {
                k: operation[k]
                for k in (
                    "operation_id",
                    "provider",
                    "action",
                    "status",
                    "error_code",
                    "updated_at",
                )
            }
        }
