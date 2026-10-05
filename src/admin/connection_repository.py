"""Table-scoped existing-brand operations and exact source/Registry/binding CAS."""

import json
from typing import Any

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.admin.contracts import AdminError
from src.admin.repository import BigQueryOnboarding
from src.analytics.cloud.transport import scalar
from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.utils.data import digest, now

Row = dict[str, Any]
TABLE = "integration_operations"


class BigQueryConnections(BigQueryOnboarding):
    def snapshot(self, binding: Row, provider: str) -> tuple[StoreConfig, Row]:
        c = self.config(binding["store_id"])
        if c is None or c.store_id != binding["store_id"]:
            raise AdminError("integration_metadata_invalid", 503)
        connections = self.rows(
            "source_connections",
            "store_id=@store AND source_system=@provider",
            [scalar("store", "STRING", c.store_id), scalar("provider", "STRING", provider)],
        )
        if not connections:
            raise AdminError("integration_not_configured", 404)
        if len(connections) != 1 or connections[0]["connection_id"] != getattr(
            c, provider + "_connection_id"
        ):
            raise AdminError("integration_metadata_invalid", 503)
        return c, connections[0]

    def ensure_idle(self, binding: Row, config: StoreConfig, source: Row) -> None:
        rows, _ = self.transport.query(
            f"SELECT (SELECT COUNT(*) FROM {self.table('installation_plans')} WHERE store_id=@store AND status='COMPLETE') AS primary_complete, (SELECT COUNT(*) FROM {self.table('installation_work_units')} WHERE store_id=@store AND status!='COMPLETE') AS primary_pending, (SELECT COUNT(*) FROM {self.table('installation_extension_plans')} WHERE store_id=@store AND status!='COMPLETE') AS extensions, (SELECT COUNT(*) FROM {self.table('sync_checkpoints')} WHERE store_id=@store AND connection_id=@connection AND (status NOT IN ('complete','recovered') OR pending_raw_id IS NOT NULL)) AS pending",
            [
                scalar("store", "STRING", config.store_id),
                scalar("connection", "STRING", source["connection_id"]),
            ],
        )
        if len(rows) != 1 or rows[0] != {
            "primary_complete": 1,
            "primary_pending": 0,
            "extensions": 0,
            "pending": 0,
        }:
            raise AdminError("integration_work_requires_reconciliation")

    def operation(self, key: str) -> Row | None:
        found = self.rows(TABLE, "operation_id=@id", [scalar("id", "STRING", key)])
        if len(found) > 1:
            raise AdminError("integration_operation_conflict")
        if not found:
            return None
        result = found[0]
        for field in ("source_snapshot", "version_baseline"):
            if isinstance(result.get(field), str):
                result[field] = json.loads(result[field])
        return result

    def tx(self, sql: str, params: list[Any], operation: Row, step: str) -> None:
        try:
            self.transport.query(
                "BEGIN TRANSACTION; " + sql + " COMMIT TRANSACTION;",
                params,
                job_id="integration_"
                + digest([operation["operation_id"], operation["revision"], step]),
            )
        except (BadRequest, Forbidden, Unauthorized):
            raise AdminError("integration_write_rejected", 409) from None
        except Exception:
            raise SafeError("integration_write_outcome_unknown") from None

    def reserve_operation(self, operation: Row) -> Row:
        self.tx(
            f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table(TABLE)} WHERE operation_id=@id OR (store_id=@store AND provider=@provider AND status NOT IN ('COMPLETE','BLOCKED'))) AS 'integration_operation_conflict'; "
            + self.insert(TABLE, "rows"),
            [
                scalar("id", "STRING", operation["operation_id"]),
                scalar("store", "STRING", operation["store_id"]),
                scalar("provider", "STRING", operation["provider"]),
                self.json_parameter("rows", [operation]),
            ],
            operation,
            "reserve",
        )
        return operation

    def transition(self, operation: Row, **changes: Any) -> Row:
        if not set(changes) <= {
            "status",
            "current_step",
            "candidate_reference",
            "version_baseline",
            "error_code",
            "updated_at",
        }:
            raise ValueError("invalid_integration_transition")
        result = {**operation, **changes, "revision": operation["revision"] + 1}
        self.tx(
            self.cas_operation() + self.update(TABLE, "rows", "operation_id"),
            [
                scalar("id", "STRING", operation["operation_id"]),
                scalar("revision", "INT64", operation["revision"]),
                self.json_parameter("rows", [result]),
            ],
            operation,
            "transition",
        )
        return result

    def cas_operation(self) -> str:
        return f"ASSERT (SELECT COUNT(*) FROM {self.table(TABLE)} WHERE operation_id=@id AND revision=@revision)=1 AS 'integration_operation_conflict'; "

    def finalize_connection(
        self,
        operation: Row,
        binding: Row,
        config: StoreConfig,
        source: Row,
        updated_config: StoreConfig,
        updated_source: Row,
    ) -> Row:
        permitted_source = {"status", "secret_resource_name", "updated_at"}
        if any(v != updated_source.get(k) for k, v in source.items() if k not in permitted_source):
            raise AdminError("integration_identity_change_forbidden")
        complete = {
            **operation,
            "status": "COMPLETE",
            "current_step": "COMMITTED",
            "error_code": None,
            "revision": operation["revision"] + 1,
            "updated_at": now(),
            "completed_at": now(),
        }
        fields = self.projection("source_connections", "old_source")
        checks = " AND ".join(f"t.`{k}` IS NOT DISTINCT FROM s.`{k}`" for k in source)
        sql = (
            self.cas_operation()
            + f"ASSERT (SELECT COUNT(*) FROM {self.table('workspace_store_bindings')} WHERE tenant_id=@tenant AND workspace_operation_id=@workspace AND store_id=@store AND operation=@operation AND status='ACTIVE')=1 AS 'integration_binding_changed'; ASSERT (SELECT COUNT(*) FROM {self.table('store_runtime_config')} WHERE store_id=@store AND revision=@registry_revision)=1 AS 'integration_configuration_changed'; ASSERT (SELECT COUNT(*) FROM {self.table('source_connections')} t JOIN ({fields}) s ON t.row_key=s.row_key WHERE {checks})=1 AS 'integration_configuration_changed'; ASSERT NOT EXISTS(SELECT 1 FROM {self.table('installation_extension_plans')} WHERE store_id=@store AND status!='COMPLETE') AS 'integration_work_in_progress'; ASSERT NOT EXISTS(SELECT 1 FROM {self.table('sync_checkpoints')} WHERE store_id=@store AND connection_id=@connection AND (status NOT IN ('complete','recovered') OR pending_raw_id IS NOT NULL)) AS 'integration_work_in_progress'; "
        )
        params = [
            scalar("id", "STRING", operation["operation_id"]),
            scalar("revision", "INT64", operation["revision"]),
            scalar("tenant", "STRING", binding["tenant_id"]),
            scalar("workspace", "STRING", binding["workspace_operation_id"]),
            scalar("operation", "STRING", binding["operation"]),
            scalar("store", "STRING", config.store_id),
            scalar("connection", "STRING", source["connection_id"]),
            scalar("registry_revision", "INT64", config.revision),
            self.json_parameter("old_source", [source]),
            self.json_parameter("source_rows", [updated_source]),
            self.json_parameter("registry_rows", [updated_config.row()]),
            self.json_parameter("rows", [complete]),
        ]
        sql += self.update("source_connections", "source_rows", "row_key")
        if config != updated_config:
            sql += self.update("store_runtime_config", "registry_rows", "store_id")
        sql += self.update(TABLE, "rows", "operation_id")
        try:
            self.tx(sql, params, operation, "finalize")
        except SafeError as exc:
            if exc.code != "integration_write_outcome_unknown":
                raise
            # One read-only reconciliation. Never repeat a possibly committed DML.
            try:
                actual_config, actual_source = self.snapshot(binding, operation["provider"])
                actual_operation = self.operation(operation["operation_id"])
                exact = (
                    actual_config == updated_config
                    and self.equal(actual_source, updated_source)
                    and self.equal(actual_operation, complete)
                )
            except Exception:
                exact = False
            if not exact:
                raise
        return complete

    def addition_guards(self) -> str:
        # Every write rechecks source/account ownership and primary/extension state.
        return (
            f"ASSERT (SELECT COUNT(*) FROM {self.table('workspace_store_bindings')} WHERE tenant_id=@tenant AND workspace_operation_id=@workspace AND store_id=@store AND operation='B2B' AND status='ACTIVE')=1 AS 'integration_binding_changed'; "
            f"ASSERT (SELECT COUNT(*) FROM {self.table('store_runtime_config')} WHERE store_id=@store AND revision=@registry_revision AND status IN ('READY','ACTIVE') AND meta_enabled=FALSE AND meta_connection_id IS NULL AND meta_account_id IS NULL AND meta_api_version IS NULL)=1 AS 'integration_configuration_changed'; "
            f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('source_connections')} WHERE (store_id=@store AND source_system='meta') OR connection_id=@connection OR row_key=@source_key) AS 'connection_collision'; "
            f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('meta_account_bindings')} WHERE store_id=@store OR account_id=@account OR connection_id=@connection) AS 'meta_account_collision'; "
            f"ASSERT (SELECT COUNT(*) FROM {self.table('installation_plans')} WHERE store_id=@store AND status='COMPLETE')=1 AND NOT EXISTS(SELECT 1 FROM {self.table('installation_work_units')} WHERE store_id=@store AND status!='COMPLETE') AS 'integration_primary_installation_required'; "
            f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('installation_extension_plans')} WHERE store_id=@store AND status!='COMPLETE') AS 'integration_work_in_progress'; "
            f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('sync_checkpoints')} WHERE store_id=@store AND (connection_id=@connection OR status NOT IN ('complete','recovered') OR pending_raw_id IS NOT NULL)) AND NOT EXISTS(SELECT 1 FROM {self.table('sync_runs')} WHERE store_id=@store AND connection_id=@connection) AS 'integration_work_requires_reconciliation'; "
        )

    def addition_parameters(self, binding: Row, config: StoreConfig, account: Any) -> list[Any]:
        return [
            scalar("tenant", "STRING", binding["tenant_id"]),
            scalar("workspace", "STRING", binding["workspace_operation_id"]),
            scalar("store", "STRING", config.store_id),
            scalar("registry_revision", "INT64", config.revision),
            scalar("account", "STRING", account.account_id),
            scalar("connection", "STRING", account.connection_id),
            scalar("source_key", "STRING", digest([config.store_id, account.connection_id])),
        ]

    def ensure_addition(self, binding: Row, config: StoreConfig, account: Any) -> None:
        try:
            self.transport.query(
                self.addition_guards(), self.addition_parameters(binding, config, account)
            )
        except (BadRequest, Forbidden, Unauthorized):
            raise AdminError("integration_addition_prerequisites_failed") from None
        except Exception:
            raise AdminError("integration_addition_precheck_unavailable", 503) from None

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
    ) -> Row:
        from src.connectors.meta.config import Account
        from src.installation.extensions import validate_extension

        validate_extension(plan, updated, source)
        allowed = {
            "meta_enabled",
            "meta_connection_id",
            "meta_account_id",
            "meta_api_version",
            "revision",
            "updated_at",
        }
        if any(v != updated.row()[k] for k, v in old.row().items() if k not in allowed):
            raise AdminError("integration_identity_change_forbidden")
        if (
            operation["current_step"] != "VERIFIED"
            or not units
            or any(
                u["source"] != "meta" or u["status"] != "PENDING" or u["plan_id"] != plan["plan_id"]
                for u in units
            )
        ):
            raise AdminError("integration_addition_plan_invalid")
        account = Account(
            updated.store_id,
            updated.meta_account_id or "",
            updated.meta_connection_id or "",
            updated.meta_api_version or "",
            updated.timezone or "",
            updated.currency or "",
        )
        complete = {
            **operation,
            "status": "COMPLETE",
            "current_step": "COMMITTED",
            "revision": operation["revision"] + 1,
            "updated_at": now(),
            "completed_at": now(),
        }
        params = self.addition_parameters(binding, old, account) + [
            scalar("id", "STRING", operation["operation_id"]),
            scalar("revision", "INT64", operation["revision"]),
            scalar("plan", "STRING", plan["plan_id"]),
            self.json_parameter("source_rows", [source]),
            self.json_parameter("meta_rows", [account_binding]),
            self.json_parameter("registry_rows", [updated.row()]),
            self.json_parameter("plan_rows", [plan]),
            self.json_parameter("unit_rows", units),
            self.json_parameter("rows", [complete]),
        ]
        sql = (
            self.cas_operation()
            + self.addition_guards()
            + (
                f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table('installation_extension_plans')} WHERE plan_id=@plan) AND NOT EXISTS(SELECT 1 FROM {self.table('installation_extension_work_units')} WHERE plan_id=@plan) AS 'extension_plan_conflict'; "
            )
        )
        sql += (
            self.insert("source_connections", "source_rows")
            + self.insert("meta_account_bindings", "meta_rows")
            + self.update("store_runtime_config", "registry_rows", "store_id")
            + self.insert("installation_extension_plans", "plan_rows")
            + self.insert("installation_extension_work_units", "unit_rows")
            + self.update(TABLE, "rows", "operation_id")
        )
        try:
            self.tx(sql, params, operation, "add-source")
        except SafeError as exc:
            if exc.code != "integration_write_outcome_unknown":
                raise
            from src.installation.extension_repository import ExtensionLedger

            try:
                config, actual_source = self.snapshot(binding, "meta")
                actual_meta = self.rows(
                    "meta_account_bindings",
                    "store_id=@store",
                    [scalar("store", "STRING", old.store_id)],
                )
                ledger = ExtensionLedger(self.transport)
                plans = [p for p in ledger.plans(old.store_id) if p["plan_id"] == plan["plan_id"]]
                actual_units = ledger.units(plan["plan_id"])
                matched = (
                    config == updated
                    and self.equal(source, actual_source)
                    and len(actual_meta) == 1
                    and self.equal(actual_meta[0], account_binding)
                    and len(plans) == 1
                    and self.equal(plans[0], plan)
                    and len(actual_units) == len(units)
                    and all(
                        self.equal(a, b)
                        for a, b in zip(
                            sorted(actual_units, key=lambda r: r["work_unit_id"]),
                            sorted(units, key=lambda r: r["work_unit_id"]),
                            strict=True,
                        )
                    )
                    and self.equal(self.operation(operation["operation_id"]), complete)
                )
            except Exception:
                matched = False
            if not matched:
                raise
        return complete
