"""V2 extension CAS ledger. Never changes the primary plan or Registry lifecycle."""

from typing import Any

from src.admin.repository import BigQueryOnboarding
from src.analytics.cloud.transport import Transport, scalar
from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.installation.extensions import validate_extension
from src.installation.model import ACTIVE, Limits, Row
from src.installation.repository import BigQueryLedger

TABLE_MAP = {
    "installation_plans": "installation_extension_plans",
    "installation_work_units": "installation_extension_work_units",
}


class ExtensionSql(BigQueryOnboarding):
    def table(self, name: str) -> str:
        return super().table(TABLE_MAP.get(name, name))

    def projection(self, name: str, param: str) -> str:
        return super().projection(TABLE_MAP.get(name, name), param)

    def insert(self, name: str, param: str) -> str:
        return super().insert(TABLE_MAP.get(name, name), param)

    def update(self, name: str, param: str, identity: str) -> str:
        return super().update(TABLE_MAP.get(name, name), param, identity)


class ExtensionLedger(BigQueryLedger):
    def __init__(self, transport: Transport):
        super().__init__(transport)
        self.sql = ExtensionSql(transport)

    def source(self, plan: Row) -> Row:
        contract = plan.get("adopted_coverage", {}).get("extension", {})
        rows = self.rows(
            "source_connections",
            "store_id=@store AND source_system=@source AND connection_id=@connection",
            [
                scalar("store", "STRING", plan["store_id"]),
                scalar("source", "STRING", contract.get("source")),
                scalar("connection", "STRING", contract.get("connection_id")),
            ],
            limit=3,
        )
        if len(rows) != 1:
            raise SafeError("extension_source_not_active")
        return rows[0]

    def guard(self, plan: Row) -> tuple[StoreConfig, Row]:
        c, source = self.config(plan["store_id"]), self.source(plan)
        validate_extension(plan, c, source)
        return c, source

    def admission(self, c: StoreConfig, source: Row) -> tuple[str, list[Any]]:
        primary = BigQueryOnboarding.table(self.sql, "installation_plans")
        primary_units = BigQueryOnboarding.table(self.sql, "installation_work_units")
        sql = f"ASSERT (SELECT COUNT(*) FROM {self.sql.table('store_runtime_config')} WHERE store_id=@config_store AND revision=@config_revision AND status=@config_status AND sync_enabled=@config_sync)=1 AS 'extension_configuration_changed'; ASSERT (SELECT COUNT(*) FROM {primary} WHERE store_id=@config_store AND status='COMPLETE')=1 AND NOT EXISTS(SELECT 1 FROM {primary_units} WHERE store_id=@config_store AND status!='COMPLETE') AS 'extension_primary_installation_required'; ASSERT (SELECT COUNT(*) FROM {self.sql.table('source_connections')} WHERE store_id=@config_store AND source_system=@source_system AND connection_id=@source_connection)=1 AS 'extension_source_not_active'; ASSERT (SELECT COUNT(*) FROM {self.sql.table('source_connections')} WHERE row_key=@source_key AND store_id=@config_store AND connection_id=@source_connection AND status='active' AND secret_resource_name IS NOT DISTINCT FROM @source_reference AND updated_at IS NOT DISTINCT FROM @source_updated)=1 AS 'extension_configuration_changed'; "
        params = [
            scalar("config_store", "STRING", c.store_id),
            scalar("config_revision", "INT64", c.revision),
            scalar("config_status", "STRING", c.status),
            scalar("config_sync", "BOOL", c.sync_enabled),
            scalar("source_system", "STRING", source["source_system"]),
            scalar("source_connection", "STRING", source["connection_id"]),
            scalar("source_key", "STRING", source["row_key"]),
            scalar("source_reference", "STRING", source.get("secret_resource_name")),
            scalar("source_updated", "TIMESTAMP", source.get("updated_at")),
        ]
        return sql, params

    def create(self, config: StoreConfig, plan: Row, units: list[Row]) -> None:
        c, source = self.guard(plan)
        if (
            c.revision != config.revision
            or plan["status"] not in {"RUNNING", "COMPLETE"}
            or any(
                u["plan_id"] != plan["plan_id"]
                or u["store_id"] != c.store_id
                or u["status"] != "PENDING"
                for u in units
            )
        ):
            raise SafeError("extension_plan_invalid")
        saved = [p for p in self.plans(c.store_id) if p["plan_id"] == plan["plan_id"]]
        if saved:
            if len(saved) != 1:
                raise SafeError("extension_plan_conflict")
            return  # Existing immutable graph is authoritative, never replace/replan.
        sql, params = self.admission(c, source)
        sql += f"ASSERT NOT EXISTS(SELECT 1 FROM {self.sql.table('installation_plans')} WHERE plan_id=@plan_id) AS 'extension_plan_conflict'; ASSERT NOT EXISTS(SELECT 1 FROM {self.sql.table('installation_work_units')} WHERE plan_id=@plan_id) AS 'extension_plan_conflict'; "
        params += [
            scalar("plan_id", "STRING", plan["plan_id"]),
            self.sql.json_parameter("plan_rows", [plan]),
            self.sql.json_parameter("unit_rows", units),
        ]
        sql += self.sql.insert("installation_plans", "plan_rows") + self.sql.insert(
            "installation_work_units", "unit_rows"
        )
        self.transaction(sql, params, plan, "extension-create")

    def reserve(self, old: Row, token: str, at: str, limits: Limits) -> Row:
        plans = [p for p in self.plans(old["store_id"]) if p["plan_id"] == old["plan_id"]]
        if len(plans) != 1:
            raise SafeError("extension_plan_conflict")
        c, source = self.guard(plans[0])
        sql, params = self.assertion("installation_work_units", old, "work_unit_id")
        admission, guards = self.admission(c, source)
        sql += admission
        params += guards
        table = self.sql.table("installation_work_units")
        plans_table = self.sql.table("installation_plans")
        primary_units = BigQueryOnboarding.table(self.sql, "installation_work_units")
        active = ",".join("'" + s + "'" for s in sorted(ACTIVE))
        sql += f"ASSERT @status IN ('PENDING','DEFERRED') AS 'installation_work_conflict'; ASSERT (SELECT COUNT(*) FROM {plans_table} WHERE plan_id=@plan AND store_id=@store AND status IN ('RUNNING','PARTIAL'))=1 AS 'extension_plan_conflict'; ASSERT NOT EXISTS(SELECT 1 FROM {table} WHERE store_id=@store AND status IN ({active})) AND NOT EXISTS(SELECT 1 FROM {primary_units} WHERE store_id=@store AND status IN ({active})) AS 'installation_store_busy'; ASSERT (SELECT COUNT(DISTINCT store_id) FROM (SELECT store_id FROM {table} WHERE status IN ({active}) UNION ALL SELECT store_id FROM {primary_units} WHERE status IN ({active})))<@capacity AS 'installation_capacity'; ASSERT (SELECT COUNT(*) FROM {table} WHERE store_id=@store AND plan_id=@plan AND status='COMPLETE' AND work_unit_id IN UNNEST(JSON_VALUE_ARRAY(@dependencies)))=ARRAY_LENGTH(JSON_VALUE_ARRAY(@dependencies)) AS 'installation_dependencies'; ASSERT (SELECT next_eligible_at IS NULL OR next_eligible_at<=@at FROM {table} WHERE work_unit_id=@id) AS 'installation_deferred'; "
        new = {
            **old,
            "status": "DISPATCHING",
            "revision": old["revision"] + 1,
            "reservation_revision": old["revision"] + 1,
            "attempt_count": old["attempt_count"] + 1,
            "dispatch_token": token,
            "dispatch_operation_name": None,
            "execution_name": None,
            "updated_at": at,
            "next_eligible_at": None,
        }
        import json

        params += [
            scalar("capacity", "INT64", limits.global_parallel_store_limit),
            scalar("dependencies", "STRING", json.dumps(old["dependencies"])),
            scalar("at", "TIMESTAMP", at),
            self.sql.json_parameter("new", [new]),
        ]
        self.transaction(
            sql + self.sql.update("installation_work_units", "new", "work_unit_id"),
            params,
            old,
            "extension-reserve",
        )
        return new

    def update_plan(self, old: Row, config: StoreConfig | None = None, **changes: Any) -> Row:
        if config is not None:
            raise SafeError("extension_registry_mutation_forbidden")
        return super().update_plan(old, None, **changes)

    def verified(self, old: Row, source: Row, at: str, *, success: bool = True) -> Row:
        raise SafeError("extension_verification_mutation_forbidden")

    def activate(self, plan: Row, config: StoreConfig, at: str) -> Row:
        raise SafeError("extension_activation_forbidden")
