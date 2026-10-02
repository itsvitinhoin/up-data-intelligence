"""Serialized parameterized SAGA transactions; ambiguous writes reconcile, never replay."""

import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.admin.contracts import AdminError, Request
from src.admin.schema import BINDINGS
from src.admin.secrets import pinned_reference
from src.analytics.cloud.transport import Transport, scalar
from src.bigquery.catalog import TABLES
from src.control_plane.model import REGISTRY_FIELDS, StoreConfig
from src.control_plane.repository import BigQueryRegistry
from src.utils.data import digest

Row = dict[str, Any]
ERRORS = {
    "store_already_registered",
    "workspace_binding_conflict",
    "connection_collision",
    "meta_account_collision",
    "registry_revision_conflict",
    "onboarding_revision_conflict",
}


class Repository(Protocol):
    def lookup(self, subject: str, key: str) -> Row | None: ...
    def get(self, operation_id: str) -> Row | None: ...
    def reserve(self, request: Request, operation: Row) -> Row: ...
    def transition(self, operation: Row, **changes: Any) -> Row: ...
    def finalize(self, request: Request, operation: Row) -> Row: ...
    def config(self, store: str) -> StoreConfig | None: ...
    def bindings(self, store: str) -> list[Row]: ...
    def exact_final(self, request: Request, operation: Row) -> bool: ...


def final_rows(request: Request, operation: Row) -> tuple[StoreConfig, list[Row], list[Row]]:
    if request.config.upzero_enabled:
        pinned_reference(operation.get("secret_version_name"), request.config.store_id)
    config = replace(
        request.config,
        revision=2,
        created_at=operation["created_at"],
        updated_at=operation["updated_at"],
    )
    sources: list[Row] = []
    meta: list[Row] = []
    for source, cid in (
        ("upzero", config.upzero_connection_id),
        ("meta", config.meta_connection_id),
    ):
        if cid is not None:
            sources.append(
                {
                    "row_key": digest([config.store_id, cid]),
                    "store_id": config.store_id,
                    "connection_id": cid,
                    "source_system": source,
                    "secret_resource_name": operation.get("secret_version_name")
                    if source == "upzero"
                    else None,
                    "status": "pending",
                    "created_at": operation["created_at"],
                    "updated_at": operation["updated_at"],
                }
            )
    if config.meta_enabled:
        # No reporting window/insights definition has been verified yet. Hash stays NULL.
        meta.append(
            {
                "row_key": digest([config.store_id, "meta_account_binding"]),
                "store_id": config.store_id,
                "account_id": config.meta_account_id,
                "connection_id": config.meta_connection_id,
                "api_version": config.meta_api_version,
                "source_timezone": config.timezone,
                "currency": config.currency,
                "configuration_hash": None,
                "configured_at": operation["updated_at"],
            }
        )
    return config, sources, meta


class BigQueryOnboarding:
    def __init__(self, transport: Transport):
        self.transport = transport
        self.registry = BigQueryRegistry(transport)

    def table(self, name: str) -> str:
        spec = TABLES[name]
        return f"`{self.transport.config.project}.{spec.dataset}.{name}`"

    def rows(self, name: str, predicate: str, parameters: list[Any]) -> list[Row]:
        try:
            rows, _ = self.transport.query(
                f"SELECT * FROM {self.table(name)} WHERE {predicate} LIMIT 101", parameters
            )
            return [
                {
                    key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in row.items()
                }
                for row in rows
            ]
        except Exception:
            raise AdminError("onboarding_read_failed", 503) from None

    def one(self, rows: list[Row]) -> Row | None:
        if len(rows) > 1:
            raise AdminError("onboarding_metadata_invalid", 503)
        return rows[0] if rows else None

    def lookup(self, subject: str, key: str) -> Row | None:
        return self.one(
            self.rows(
                "onboarding_operations",
                "admin_subject_hash=@subject AND idempotency_key=@key",
                [scalar("subject", "STRING", subject), scalar("key", "STRING", key)],
            )
        )

    def get(self, operation_id: str) -> Row | None:
        return self.one(
            self.rows(
                "onboarding_operations",
                "operation_id=@operation",
                [scalar("operation", "STRING", operation_id)],
            )
        )

    def config(self, store: str) -> StoreConfig | None:
        try:
            return self.registry.get(store)
        except Exception:
            raise AdminError("onboarding_read_failed", 503) from None

    def bindings(self, store: str) -> list[Row]:
        return self.rows(
            "workspace_store_bindings", "store_id=@store", [scalar("store", "STRING", store)]
        )

    def projection(self, name: str, param: str) -> str:
        fields = TABLES[name].fields
        expressions = [
            f"JSON_QUERY(r,'$.{k}')" if typ == "JSON" else f"CAST(JSON_VALUE(r,'$.{k}') AS {typ})"
            for k, typ in fields.items()
        ]
        return (
            "SELECT "
            + ",".join(f"{expr} `{k}`" for k, expr in zip(fields, expressions, strict=True))
            + f" FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@{param}))) r"
        )

    def insert(self, name: str, param: str) -> str:
        return f"INSERT INTO {self.table(name)} ({','.join(TABLES[name].fields)}) {self.projection(name, param)};"

    def update(self, name: str, param: str, identity: str) -> str:
        return (
            f"MERGE {self.table(name)} t USING ({self.projection(name, param)}) s ON t.{identity}=s.{identity} WHEN MATCHED THEN UPDATE SET "
            + ",".join(f"`{k}`=s.`{k}`" for k in TABLES[name].fields if k != identity)
            + ";"
        )

    def transaction(self, sql: str, parameters: list[Any], operation: Row, step: str) -> None:
        try:
            self.transport.query(
                "BEGIN TRANSACTION; " + sql + " COMMIT TRANSACTION;",
                parameters,
                job_id="onboarding_"
                + digest([operation["operation_id"], operation["revision"], step]),
            )
        except (BadRequest, Forbidden, Unauthorized) as exc:
            code = next(
                (code for code in sorted(ERRORS) if code in str(exc)), "registry_write_failed"
            )
            raise AdminError(code, 409 if code in ERRORS else 503) from None
        except Exception:
            raise AdminError("onboarding_write_outcome_unknown", 503) from None

    @staticmethod
    def json_parameter(name: str, rows: list[Row]) -> Any:
        return scalar(name, "STRING", json.dumps(rows, default=str, separators=(",", ":")))

    def reserve(self, request: Request, operation: Row) -> Row:
        c = replace(
            request.config, created_at=operation["created_at"], updated_at=operation["created_at"]
        )
        bindings = request.bindings(operation["created_at"])
        params = [
            scalar("store", "STRING", c.store_id),
            scalar("subject", "STRING", operation["admin_subject_hash"]),
            scalar("key", "STRING", operation["idempotency_key"]),
            self.json_parameter("registry", [c.row()]),
            self.json_parameter("bindings", bindings),
            self.json_parameter("ledger", [operation]),
        ]
        sql = f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('store_runtime_config')} WHERE store_id=@store) AS 'store_already_registered'; ASSERT NOT EXISTS(SELECT 1 FROM {self.table('onboarding_operations')} WHERE admin_subject_hash=@subject AND idempotency_key=@key) AS 'onboarding_revision_conflict'; ASSERT NOT EXISTS(SELECT 1 FROM {self.table('workspace_store_bindings')} WHERE store_id=@store OR workspace_operation_id IN (SELECT workspace_operation_id FROM ({self.projection('workspace_store_bindings', 'bindings')}))) AS 'workspace_binding_conflict';"
        sql += (
            self.insert("store_runtime_config", "registry")
            + self.insert("workspace_store_bindings", "bindings")
            + self.insert("onboarding_operations", "ledger")
        )
        try:
            self.transaction(sql, params, operation, "reserve")
        except AdminError as exc:
            if exc.code != "onboarding_write_outcome_unknown":
                raise
            try:
                recovered = self.exact_reservation(request, operation)
            except Exception:
                recovered = False
            if not recovered:
                raise exc from None
        return operation

    def exact_reservation(self, request: Request, operation: Row) -> bool:
        current = self.get(operation["operation_id"])
        c = self.config(request.config.store_id)
        expected = replace(
            request.config, created_at=operation["created_at"], updated_at=operation["created_at"]
        )
        return (
            self.equal(current, operation)
            and c == expected
            and self.same_rows(
                self.bindings(expected.store_id), request.bindings(operation["created_at"])
            )
            and not self.rows(
                "source_connections",
                "store_id=@store",
                [scalar("store", "STRING", expected.store_id)],
            )
            and not self.rows(
                "meta_account_bindings",
                "store_id=@store",
                [scalar("store", "STRING", expected.store_id)],
            )
        )

    @staticmethod
    def equal(actual: Row | None, expected: Row) -> bool:
        if actual is None:
            return False

        def primitive(value: Any) -> Any:
            return value.isoformat() if isinstance(value, datetime) else value

        return all(primitive(actual.get(k)) == primitive(v) for k, v in expected.items())

    def same_rows(self, actual: list[Row], expected: list[Row]) -> bool:
        return (
            len(actual) == len(expected)
            and all(any(self.equal(a, e) for a in actual) for e in expected)
            and len({a.get("row_key") for a in actual}) == len(actual)
        )

    def cas(self, operation: Row) -> str:
        t = self.table("onboarding_operations")
        return f"ASSERT (SELECT COUNT(*) FROM {t} WHERE operation_id=@operation)=1 AND (SELECT revision FROM {t} WHERE operation_id=@operation)=@revision AS 'onboarding_revision_conflict';"

    def transition(self, operation: Row, **changes: Any) -> Row:
        if not changes.keys() <= {
            "status",
            "current_step",
            "error_code",
            "secret_version_name",
            "updated_at",
            "completed_at",
        }:
            raise ValueError("unsupported_onboarding_transition")
        expected = {**operation, **changes, "revision": operation["revision"] + 1}
        params = [
            scalar("operation", "STRING", operation["operation_id"]),
            scalar("revision", "INT64", operation["revision"]),
            self.json_parameter("ledger", [expected]),
        ]
        try:
            self.transaction(
                self.cas(operation)
                + self.update("onboarding_operations", "ledger", "operation_id"),
                params,
                operation,
                "transition",
            )
        except AdminError as exc:
            if exc.code != "onboarding_write_outcome_unknown":
                raise
            try:
                recovered = self.equal(self.get(operation["operation_id"]), expected)
            except Exception:
                recovered = False
            if not recovered:
                raise exc from None
        return expected

    def finalize(self, request: Request, operation: Row) -> Row:
        if request.config.upzero_enabled:
            pinned_reference(
                operation.get("secret_version_name"),
                request.config.store_id,
                project=self.transport.config.project,
            )
        c, sources, meta = final_rows(request, operation)
        expected = {
            **operation,
            "revision": operation["revision"] + 1,
            "status": "INSTALLING",
            "current_step": "CONFIGURED",
            "error_code": None,
            "completed_at": operation["updated_at"],
        }
        params = [
            scalar("operation", "STRING", operation["operation_id"]),
            scalar("revision", "INT64", operation["revision"]),
            scalar("store", "STRING", c.store_id),
            scalar("account", "STRING", c.meta_account_id),
            self.json_parameter("registry", [c.row()]),
            self.json_parameter("sources", sources),
            self.json_parameter("meta", meta),
            self.json_parameter("bindings", request.bindings(operation["created_at"])),
            self.json_parameter("ledger", [expected]),
        ]
        reserved = replace(
            request.config, created_at=operation["created_at"], updated_at=operation["created_at"]
        )
        # Compare every configuration field, not only revision, before finalizing.
        params.append(self.json_parameter("reserved", [reserved.row()]))
        comparisons = " AND ".join(
            f"TO_JSON_STRING(t.`{k}`) IS NOT DISTINCT FROM TO_JSON_STRING(s.`{k}`)"
            if typ == "JSON"
            else f"t.`{k}` IS NOT DISTINCT FROM s.`{k}`"
            for k, typ in REGISTRY_FIELDS.items()
        )
        sql = (
            self.cas(operation)
            + f"ASSERT (SELECT COUNT(*) FROM {self.table('store_runtime_config')} t JOIN ({self.projection('store_runtime_config', 'reserved')}) s ON {comparisons})=1 AS 'registry_revision_conflict';"
        )
        binding_match = " AND ".join(f"t.`{k}` IS NOT DISTINCT FROM s.`{k}`" for k in BINDINGS)
        sql += f"ASSERT (SELECT COUNT(*) FROM {self.table('workspace_store_bindings')} WHERE store_id=@store)=(SELECT COUNT(*) FROM ({self.projection('workspace_store_bindings', 'bindings')})) AND (SELECT COUNT(*) FROM {self.table('workspace_store_bindings')} t JOIN ({self.projection('workspace_store_bindings', 'bindings')}) s ON {binding_match})=(SELECT COUNT(*) FROM ({self.projection('workspace_store_bindings', 'bindings')})) AND NOT EXISTS(SELECT 1 FROM {self.table('workspace_store_bindings')} t JOIN ({self.projection('workspace_store_bindings', 'bindings')}) s ON t.workspace_operation_id=s.workspace_operation_id WHERE t.store_id!=s.store_id OR t.tenant_id!=s.tenant_id OR t.operation!=s.operation OR t.brand_id!=s.brand_id) AS 'workspace_binding_conflict';"
        sql += f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('source_connections')} WHERE store_id=@store OR connection_id IN (SELECT connection_id FROM ({self.projection('source_connections', 'sources')}))) AS 'connection_collision'; ASSERT NOT EXISTS(SELECT 1 FROM {self.table('meta_account_bindings')} WHERE store_id=@store OR (@account IS NOT NULL AND account_id=@account)) AS 'meta_account_collision';"
        sql += (
            self.insert("source_connections", "sources")
            + self.insert("meta_account_bindings", "meta")
            + self.update("store_runtime_config", "registry", "store_id")
            + self.update("workspace_store_bindings", "bindings", "row_key")
            + self.update("onboarding_operations", "ledger", "operation_id")
        )
        try:
            self.transaction(sql, params, operation, "finalize")
        except AdminError as exc:
            if exc.code != "onboarding_write_outcome_unknown":
                raise
            try:
                recovered = self.exact_final(request, expected)
            except Exception:
                recovered = False
            if not recovered:
                raise exc from None
        return expected

    def exact_final(self, request: Request, operation: Row) -> bool:
        c, sources, meta = final_rows(request, operation)
        return (
            self.equal(self.get(operation["operation_id"]), operation)
            and self.config(c.store_id) == c
            and self.same_rows(self.bindings(c.store_id), request.bindings(operation["created_at"]))
            and self.same_rows(
                self.rows(
                    "source_connections", "store_id=@store", [scalar("store", "STRING", c.store_id)]
                ),
                sources,
            )
            and self.same_rows(
                self.rows(
                    "meta_account_bindings",
                    "store_id=@store",
                    [scalar("store", "STRING", c.store_id)],
                ),
                meta,
            )
        )
