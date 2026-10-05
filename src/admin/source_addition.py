"""Existing-brand Meta admission; one verified source and its own V2 graph only.

Does not create stores, workspaces, onboarding operations, primary plans or secrets.
UP Zero needs a separate commercial adoption contract when absent; no fake form.
"""

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Any, Protocol

from src.admin.connections import ConnectionService
from src.admin.contracts import AdminError, Principal, authorize, exact, identity, uuid_key
from src.connectors.meta.config import Account, Insights, meta_id
from src.control_plane.model import StoreConfig
from src.domain.models import Page, SafeError
from src.installation.extensions import ExtensionPlanner, admissible
from src.utils.data import digest, now

Row = dict[str, Any]


def verify_meta_account(page: Page, account: Account) -> None:
    """Check exact candidate identity/config; never return or include its payload."""
    data = page.payload.get("data")
    if (
        page.pagination_error
        or not isinstance(data, list)
        or len(data) != 1
        or not isinstance(data[0], dict)
        or (
            data[0].get("account_id") != account.account_id
            or data[0].get("currency") != account.currency
            or data[0].get("timezone_name") != account.timezone
        )
    ):
        raise SafeError("meta_account_configuration_mismatch")


class AdditionRepository(Protocol):
    def config(self, store: str) -> StoreConfig | None: ...
    def operation(self, key: str) -> Row | None: ...
    def ensure_addition(self, binding: Row, config: StoreConfig, account: Account) -> None: ...
    def reserve_operation(self, operation: Row) -> Row: ...
    def transition(self, operation: Row, **changes: Any) -> Row: ...
    def finalize_addition(
        self,
        operation: Row,
        binding: Row,
        old: StoreConfig,
        updated: StoreConfig,
        source: Row,
        account_binding: Row,
        plan: Row,
        units: list[Row],
    ) -> Row: ...


class SourceAddition:
    def __init__(
        self,
        repository: AdditionRepository,
        publication: Callable[[StoreConfig], Row],
        probe: Callable[[StoreConfig, str, str | None], None],
        lease: Callable[[str], AbstractContextManager[None]],
        key: bytes,
        clock: Callable[[], str] = now,
    ):
        self.repo, self.publication, self.probe = repository, publication, probe
        self.lease, self.key, self.clock = lease, key, clock

    def create(self, principal: Principal, binding: Row, key: str, value: Any) -> Row:
        admin = authorize(principal)
        admin.authorize_tenant(binding["tenant_id"])
        payload = exact(value, {"provider", "action", "account_id", "api_version"})
        if (
            payload["provider"] != "meta"
            or payload["action"] != "add"
            or binding.get("operation") != "B2B"
        ):
            raise AdminError("integration_source_addition_unavailable", 400)
        if not all(isinstance(payload[k], str) for k in ("account_id", "api_version")):
            raise AdminError("integration_configuration_invalid", 400)
        subject = identity(admin.subject, self.key)
        operation_id = digest([subject, uuid_key(key)])
        request_hash = digest([binding["tenant_id"], binding["workspace_operation_id"], payload])
        # Validate syntax before any IO; never accept a browser connection/store ID.
        meta_id(payload["account_id"])
        if not re.fullmatch(r"v[0-9]+\.0", payload["api_version"]):
            raise AdminError("integration_configuration_invalid", 400)
        ambiguous: SafeError | None = None
        try:
            with (
                self.lease("store-dispatch-global"),
                self.lease("installation-orchestrator-global"),
                self.lease(binding["store_id"]),
            ):
                try:
                    return self.run(binding, payload, operation_id, subject, request_hash)
                except SafeError as exc:
                    if exc.code.endswith("outcome_unknown"):
                        ambiguous = exc
                        raise SafeError("registry_write_outcome_unknown") from None
                    raise
        except SafeError:
            if ambiguous:
                raise AdminError(ambiguous.code, 503) from None
            raise

    def run(self, binding: Row, payload: Row, key: str, subject: str, request_hash: str) -> Row:
        op = self.repo.operation(key)
        if op:
            if (
                op["request_hash"] != request_hash
                or op["store_id"] != binding["store_id"]
                or op["tenant_id"] != binding["tenant_id"]
            ):
                raise AdminError("idempotency_conflict")
            if op["status"] == "COMPLETE":
                return ConnectionService.public(op)
            if op["status"] == "BLOCKED":
                raise AdminError(op["error_code"] or "integration_blocked")
            if op["current_step"] == "PROBE_INTENT":
                raise SafeError("source_verification_outcome_unknown")
        c = self.repo.config(binding["store_id"])
        if c is None:
            raise AdminError("integration_metadata_invalid", 503)
        admissible(c)
        if (
            c.meta_enabled
            or c.meta_connection_id
            or c.meta_account_id
            or c.meta_api_version
            or not c.upzero_enabled
            or not c.analytics_enabled
        ):
            raise AdminError("integration_existing_source_requires_management")
        if op and op["source_snapshot"]["registry"] != c.row():
            raise AdminError("integration_configuration_changed")
        at = op["created_at"] if op else self.clock()
        updated = replace(
            c,
            meta_enabled=True,
            meta_connection_id=c.store_id + "-meta",
            meta_account_id=payload["account_id"],
            meta_api_version=payload["api_version"],
            revision=c.revision + 1,
            updated_at=at,
        )
        updated.ready()
        account = Account(
            c.store_id,
            updated.meta_account_id or "",
            updated.meta_connection_id or "",
            updated.meta_api_version or "",
            c.timezone or "",
            c.currency or "",
        )
        self.repo.ensure_addition(binding, c, account)
        source = dict(
            row_key=digest([c.store_id, account.connection_id]),
            store_id=c.store_id,
            connection_id=account.connection_id,
            source_system="meta",
            secret_resource_name=None,
            status="active",
            created_at=at,
            updated_at=at,
        )
        published = self.publication(c)
        plan, units = ExtensionPlanner().calculate(
            updated,
            source,
            "META_SOURCE_ADDITION",
            published["report_from"],
            published["report_to"],
            at,
            requested_by_hash=subject,
            checkpoints=[],
            runs=[],
            publication=published,
            account=account,
            reporting=Insights(
                published["report_from"],
                published["report_from"],
                "impression",
                ("7d_click",),
                None,
            ),
        )
        if not op:
            op = self.repo.reserve_operation(
                dict(
                    row_key=key,
                    operation_id=key,
                    tenant_id=binding["tenant_id"],
                    workspace_operation_id=binding["workspace_operation_id"],
                    store_id=c.store_id,
                    provider="meta",
                    action="add",
                    admin_subject_hash=subject,
                    request_hash=request_hash,
                    status="RESERVED",
                    current_step="RESERVED",
                    registry_revision=c.revision,
                    source_snapshot={"registry": c.row(), "plan_id": plan["plan_id"]},
                    version_baseline=None,
                    candidate_reference=None,
                    error_code=None,
                    revision=1,
                    created_at=at,
                    updated_at=at,
                    completed_at=None,
                )
            )
        elif op["source_snapshot"]["plan_id"] != plan["plan_id"]:
            raise AdminError("integration_publication_changed")
        if op["current_step"] != "VERIFIED":
            op = self.repo.transition(op, current_step="PROBE_INTENT", updated_at=self.clock())
            try:
                self.probe(updated, "meta-add", None)
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
        meta = dict(
            row_key=digest([c.store_id, "meta_account_binding"]),
            store_id=c.store_id,
            account_id=account.account_id,
            connection_id=account.connection_id,
            api_version=account.api_version,
            source_timezone=account.timezone,
            currency=account.currency,
            configuration_hash=None,
            configured_at=at,
        )
        result = self.repo.finalize_addition(op, binding, c, updated, source, meta, plan, units)
        return ConnectionService.public(result)
