"""ADMIN_UP application contract. Identity must come from the trusted server/CLI."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, fields, replace
from typing import Any, Protocol
from uuid import uuid4

from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.utils.data import now


class Registry(Protocol):
    def get(self, store: str) -> StoreConfig | None: ...
    def eligible(self, pipeline: str, limit: int) -> list[StoreConfig]: ...
    def save(self, config: StoreConfig, expected_revision: int | None) -> None: ...


@dataclass(frozen=True)
class Admin:
    subject: str
    role: str

    def authorize(self) -> None:
        if not self.subject or self.role != "ADMIN_UP":
            raise SafeError("admin_up_required")


class StoreAdmin:
    def __init__(
        self,
        registry: Registry,
        lease: Callable[[str], AbstractContextManager[None]],
        validate: Callable[[StoreConfig], None],
    ):
        self.registry, self.lease, self.validate = registry, lease, validate

    @staticmethod
    def editable(payload: dict[str, Any]) -> None:
        allowed = {f.name for f in fields(StoreConfig)} - {
            "status",
            "revision",
            "created_at",
            "updated_at",
            "sync_enabled",
        }
        if not payload.keys() <= allowed:
            raise SafeError("unsupported_registry_fields")

    def register(self, admin: Admin, payload: dict[str, Any]) -> StoreConfig:
        admin.authorize()
        self.editable(payload)
        config = StoreConfig.from_row(
            {
                **payload,
                "store_id": payload.get("store_id") or "store-" + uuid4().hex,
                "created_at": now(),
                "updated_at": now(),
            }
        )
        if not (config.operation_b2b or config.operation_b2c):
            raise SafeError("store_operation_required")
        # BigQuery uniqueness is NOT enforced by a declared primary key.
        with self.lease("store-registry-registration-global"), self.lease(config.store_id):
            if self.registry.get(config.store_id) is not None:
                raise SafeError("store_already_registered")
            self.registry.save(config, None)
        return config

    def read(self, admin: Admin, store: str) -> StoreConfig:
        admin.authorize()
        config = self.registry.get(store)
        if config is None:
            raise SafeError("store_not_registered")
        return config

    def change(
        self, admin: Admin, store: str, action: str, payload: dict[str, Any] | None = None
    ) -> StoreConfig:
        admin.authorize()
        with self.lease(store):
            current = self.read(admin, store)
            if action == "update-store":
                self.editable(payload or {})
                if "store_id" in (payload or {}):
                    raise SafeError("store_id_is_immutable")
                config = StoreConfig.from_row(
                    {**current.row(), **(payload or {}), "status": "DRAFT", "sync_enabled": False}
                )
                if not (config.operation_b2b or config.operation_b2c):
                    raise SafeError("store_operation_required")
            elif action in {"validate-store", "activate-store"}:
                if action == "activate-store" and current.status not in {"READY", "PAUSED"}:
                    raise SafeError("ready_store_required")
                current.ready()
                self.validate(current)
                config = replace(
                    current,
                    status="READY" if action == "validate-store" else "ACTIVE",
                    sync_enabled=action == "activate-store",
                )
            elif action == "pause-store":
                config = replace(current, status="PAUSED", sync_enabled=False)
            else:
                raise SafeError("invalid_registry_operation")
            config = replace(config, revision=current.revision + 1, updated_at=now())
            self.registry.save(config, current.revision)
            return config
