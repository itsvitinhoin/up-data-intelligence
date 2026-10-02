"""DRAFT-only onboarding SAGA. No dispatcher, workers or external source verification."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.admin.contracts import (
    AdminError,
    Principal,
    Request,
    authorize,
    identity,
    parse_request,
    uuid_key,
)
from src.admin.repository import Repository, Row
from src.admin.secrets import SecretStore, pinned_reference
from src.domain.models import SafeError
from src.utils.data import digest, now


class OnboardingService:
    def __init__(
        self,
        repository: Repository,
        secrets: SecretStore,
        lease: Callable[[str], AbstractContextManager[None]],
        subject_key: bytes,
        clock: Callable[[], str] = now,
    ):
        identity("configuration-check", subject_key)
        self.repository, self.secrets, self.lease, self.subject_key, self.clock = (
            repository,
            secrets,
            lease,
            subject_key,
            clock,
        )

    def create(self, principal: Principal | None, key: str, body: Any) -> Row:
        admin = authorize(principal)
        request = parse_request(body)
        admin.authorize_tenant(request.tenant_id)
        key = uuid_key(key)
        subject = identity(admin.subject, self.subject_key)
        ambiguous: AdminError | None = None
        try:
            # Same registration/store locks as StoreAdmin; global uniqueness is not a BQ PK.
            with (
                self.lease("store-registry-registration-global"),
                self.lease(request.config.store_id),
            ):
                try:
                    return self.run(request, subject, key)
                except AdminError as exc:
                    if exc.code == "onboarding_write_outcome_unknown":
                        ambiguous = exc
                        # Existing cloud lease preserves locks for this known uncertain code.
                        raise SafeError("registry_write_outcome_unknown") from None
                    raise
        except SafeError as exc:
            if ambiguous:
                raise ambiguous from None
            if isinstance(exc, AdminError):
                raise
            raise AdminError("onboarding_lease_unavailable", 503) from None
        except Exception:
            raise AdminError("onboarding_failed", 503) from None

    def change(self, operation: Row, **changes: Any) -> Row:
        return self.repository.transition(operation, updated_at=self.clock(), **changes)

    def run(self, request: Request, subject: str, key: str) -> Row:
        operation = self.repository.lookup(subject, key)
        if operation:
            if (
                operation["request_hash"] != request.request_hash
                or operation["tenant_id"] != request.tenant_id
            ):
                raise AdminError("idempotency_conflict")
        else:
            at = self.clock()
            operation = self.repository.reserve(
                request,
                {
                    "row_key": digest([subject, key]),
                    "operation_id": str(uuid5(NAMESPACE_URL, digest([subject, key]))),
                    "idempotency_key": key,
                    "admin_subject_hash": subject,
                    "request_hash": request.request_hash,
                    "tenant_id": request.tenant_id,
                    "store_id": request.config.store_id,
                    "status": "RESERVED",
                    "current_step": "RESERVED",
                    "error_code": None,
                    "secret_version_name": None,
                    "revision": 1,
                    "created_at": at,
                    "updated_at": at,
                    "completed_at": None,
                },
            )
        try:
            if request.credential is not None:
                reference = operation.get("secret_version_name")
                if reference:
                    pinned_reference(reference, request.config.store_id)
                    self.secrets.compare(reference, request.credential)
                else:
                    step = operation["current_step"]
                    if step == "RESERVED":
                        operation = self.change(
                            operation,
                            status="SECRET_PENDING",
                            current_step="CONTAINER_INTENT",
                            error_code=None,
                        )
                        self.secrets.container(
                            request.config.store_id, operation["operation_id"], reconcile_only=False
                        )
                        operation = self.change(operation, current_step="CONTAINER_READY")
                    elif step == "CONTAINER_INTENT":
                        self.secrets.container(
                            request.config.store_id, operation["operation_id"], reconcile_only=True
                        )
                        operation = self.change(
                            operation, current_step="CONTAINER_READY", error_code=None
                        )
                    may_write = operation["current_step"] in {
                        "CONTAINER_READY",
                        "VERSION_RETRY_ALLOWED",
                    }
                    if may_write:
                        operation = self.change(
                            operation,
                            status="SECRET_PENDING",
                            current_step="VERSION_INTENT",
                            error_code=None,
                        )
                    reference = self.secrets.initial(
                        request.config.store_id,
                        operation["operation_id"],
                        request.credential,
                        reconcile_only=not may_write,
                    )
                    pinned_reference(reference, request.config.store_id)
                    operation = self.change(
                        operation,
                        status="SECRET_READY",
                        current_step="SECRET_READY",
                        secret_version_name=reference,
                        error_code=None,
                    )
            if operation["status"] == "INSTALLING":
                return self.public(operation)
            if operation["current_step"] == "FINALIZING":
                # An unresolved earlier finalization must never receive a second mutation.
                expected = {
                    **operation,
                    "revision": operation["revision"] + 1,
                    "status": "INSTALLING",
                    "current_step": "CONFIGURED",
                    "error_code": None,
                    "completed_at": operation["updated_at"],
                }
                try:
                    recovered = self.repository.exact_final(request, expected)
                except Exception:
                    recovered = False
                if recovered:
                    return self.public(expected)
                raise AdminError("onboarding_write_outcome_unknown", 503)
            operation = self.change(
                operation, status="FINALIZING", current_step="FINALIZING", error_code=None
            )
            operation = self.repository.finalize(request, operation)
            return self.public(operation)
        except AdminError as exc:
            # Do not mutate after any ambiguous BQ outcome. Its durable intent is the receipt.
            if exc.code == "onboarding_write_outcome_unknown":
                raise
            if operation["status"] == "INSTALLING":
                raise  # A rejected retry never downgrades an already committed operation.
            step = operation["current_step"]
            if exc.code == "secret_write_failed" and step == "VERSION_INTENT":
                step = "VERSION_RETRY_ALLOWED"  # Definite server rejection; no version committed.
            if exc.code == "registry_write_failed" and step == "FINALIZING":
                step = "FINALIZATION_RETRY_ALLOWED"  # Definite rollback, not ambiguous outcome.
            self.change(operation, status="BLOCKED", current_step=step, error_code=exc.code)
            raise

    def read(self, principal: Principal | None, operation_id: str) -> Row:
        admin = authorize(principal)
        operation = self.repository.get(uuid_key(operation_id))
        if operation is None or operation["admin_subject_hash"] != identity(
            admin.subject, self.subject_key
        ):
            raise AdminError("onboarding_operation_not_found", 404)
        admin.authorize_tenant(operation["tenant_id"])
        return self.public(operation)

    def public(self, operation: Row) -> Row:
        config = self.repository.config(operation["store_id"])
        if config is None:
            raise AdminError("onboarding_metadata_invalid", 503)
        bindings = self.repository.bindings(config.store_id)
        expected = [
            (config.store_id + "-" + op.lower(), op)
            for op, enabled in (("B2B", config.operation_b2b), ("B2C", config.operation_b2c))
            if enabled
        ]
        if (
            len(bindings) != len(expected)
            or {(b.get("workspace_operation_id"), b.get("operation")) for b in bindings}
            != set(expected)
            or any(
                b.get("tenant_id") != operation["tenant_id"]
                or b.get("store_id") != config.store_id
                or b.get("brand_id") != "brand-" + config.store_id
                for b in bindings
            )
        ):
            raise AdminError("onboarding_metadata_invalid", 503)
        return {
            "operation_id": operation["operation_id"],
            "store_id": config.store_id,
            "brand_id": "brand-" + config.store_id,
            "name": config.store_name,
            "tenant_id": operation["tenant_id"],
            "workspace_operations": [
                {"id": b["workspace_operation_id"], "operation": b["operation"]} for b in bindings
            ],
            "status": operation["status"],
            "current_step": operation["current_step"],
            "error_code": operation["error_code"],
            "created_at": operation["created_at"],
            "updated_at": operation["updated_at"],
            "sources": [
                {"source": source, "state": "PENDING"}
                for source, enabled in (
                    ("upzero", config.upzero_enabled),
                    ("meta", config.meta_enabled),
                )
                if enabled
            ],
        }
