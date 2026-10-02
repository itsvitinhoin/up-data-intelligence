"""Parameterized ledger transactions. Reservations serialize across *all* stores.

Global lease is required by callers. SQL also asserts store admission and exact CAS.
Uncertain mutation retains the existing non-expiring lease; never repeat the write.
"""

import json
from datetime import datetime
from typing import Any, Protocol

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.admin.repository import BigQueryOnboarding
from src.analytics.cloud.transport import Transport, scalar
from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.installation.model import ACTIVE, Limits, Row
from src.observability.logging import event
from src.utils.data import digest


class Ledger(Protocol):
    def plans(self, store: str | None = None) -> list[Row]: ...
    def units(self, plan: str | None = None) -> list[Row]: ...
    def config(self, store: str) -> StoreConfig: ...
    def create(self, config: StoreConfig, plan: Row, units: list[Row]) -> None: ...
    def transition(self, old: Row, **changes: Any) -> Row: ...
    def reserve(self, old: Row, token: str, at: str, limits: Limits) -> Row: ...
    def update_plan(self, old: Row, config: StoreConfig | None = None, **changes: Any) -> Row: ...
    def verified(self, old: Row, source: Row, at: str, *, success: bool = True) -> Row: ...


class BigQueryLedger:
    def __init__(self, transport: Transport):
        self.transport = transport
        self.sql = BigQueryOnboarding(transport)

    def rows(
        self, name: str, predicate: str, params: list[Any], *, limit: int = 10001
    ) -> list[Row]:
        try:
            rows, _ = self.transport.query(
                f"SELECT * FROM {self.sql.table(name)} WHERE {predicate} LIMIT {limit}", params
            )
            if len(rows) >= limit:
                raise SafeError("installation_ledger_read_limit")
            result = []
            for row in rows:
                parsed = {
                    k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()
                }
                for key in ("filters", "dependencies", "adopted_coverage"):
                    if isinstance(parsed.get(key), str):
                        parsed[key] = json.loads(parsed[key])
                result.append(parsed)
            return result
        except SafeError:
            raise
        except Exception:
            raise SafeError("installation_read_failed") from None

    def plans(self, store: str | None = None) -> list[Row]:
        return self.rows(
            "installation_plans",
            "store_id=@store" if store else "status IN ('RUNNING','PARTIAL','OUTCOME_UNKNOWN')",
            [scalar("store", "STRING", store)] if store else [],
        )

    def units(self, plan: str | None = None) -> list[Row]:
        # Orchestrator bounds its read to the active plan set, never all historical units.
        return self.rows(
            "installation_work_units",
            "plan_id=@plan"
            if plan
            else f"plan_id IN (SELECT plan_id FROM {self.sql.table('installation_plans')} WHERE status IN ('RUNNING','PARTIAL','OUTCOME_UNKNOWN'))",
            [scalar("plan", "STRING", plan)] if plan else [],
        )

    def config(self, store: str) -> StoreConfig:
        result = self.sql.registry.get(store)
        if result is None:
            raise SafeError("installation_store_missing")
        return result

    def transaction(self, sql: str, params: list[Any], identity: Row, step: str) -> None:
        try:
            self.transport.query(
                "BEGIN TRANSACTION; " + sql + " COMMIT TRANSACTION;",
                params,
                job_id="installation_"
                + digest(
                    [
                        identity.get("work_unit_id", identity.get("plan_id")),
                        identity["revision"],
                        step,
                    ]
                ),
            )
        except (BadRequest, Forbidden, Unauthorized):
            raise SafeError("installation_work_conflict") from None
        except Exception:
            # Existing lease policy preserves locks on this exact canonical ambiguity code.
            raise SafeError("bigquery_write_outcome_unknown") from None

    def assertion(self, name: str, old: Row, identity: str) -> tuple[str, list[Any]]:
        clause = "status=@status AND revision=@revision"
        params = [
            scalar("id", "STRING", old[identity]),
            scalar("status", "STRING", old["status"]),
            scalar("revision", "INT64", old["revision"]),
        ]
        if name == "installation_work_units":
            clause += " AND store_id=@store AND plan_id=@plan AND dispatch_token IS NOT DISTINCT FROM @token"
            params.extend(
                [
                    scalar("store", "STRING", old["store_id"]),
                    scalar("plan", "STRING", old["plan_id"]),
                    scalar("token", "STRING", old.get("dispatch_token")),
                ]
            )
        sql = f"ASSERT (SELECT COUNT(*) FROM {self.sql.table(name)} WHERE {identity}=@id)=1 AS 'installation_work_conflict'; ASSERT (SELECT COUNT(*) FROM {self.sql.table(name)} WHERE {identity}=@id AND {clause})=1 AS 'installation_work_conflict'; "
        return sql, params

    def create(self, config: StoreConfig, plan: Row, units: list[Row]) -> None:
        saved = self.plans(config.store_id)
        if saved:
            if len(saved) == 1 and saved[0]["plan_id"] == plan["plan_id"]:
                return  # immutable identity: never reinterpret an already persisted graph
            raise SafeError("installation_plan_conflict")
        old = self.config(config.store_id)
        if old.revision != config.revision:
            raise SafeError("installation_configuration_changed")
        sql = f"ASSERT NOT EXISTS(SELECT 1 FROM {self.sql.table('installation_plans')} WHERE store_id=@store) AS 'installation_plan_conflict'; ASSERT (SELECT COUNT(*) FROM {self.sql.table('store_runtime_config')} WHERE store_id=@store AND revision=@registry_revision AND sync_enabled=false)=1 AS 'installation_configuration_changed'; "
        sql += (
            self.sql.update("store_runtime_config", "registry", "store_id")
            + self.sql.insert("installation_plans", "plan_rows")
            + self.sql.insert("installation_work_units", "unit_rows")
        )
        from dataclasses import replace

        config = replace(config, revision=old.revision + 1, updated_at=plan["updated_at"])
        plan["registry_revision"] = config.revision
        self.transaction(
            sql,
            [
                scalar("store", "STRING", config.store_id),
                scalar("registry_revision", "INT64", old.revision),
                self.sql.json_parameter("registry", [config.row()]),
                self.sql.json_parameter("plan_rows", [plan]),
                self.sql.json_parameter("unit_rows", units),
            ],
            plan,
            "create",
        )

        event(
            "installation_plan_created",
            store_id=config.store_id,
            plan_id=plan["plan_id"],
            status=plan["status"],
        )

    def transition(self, old: Row, **changes: Any) -> Row:
        new = {**old, **changes, "revision": old["revision"] + 1}
        sql, params = self.assertion("installation_work_units", old, "work_unit_id")
        self.transaction(
            sql + self.sql.update("installation_work_units", "new", "work_unit_id"),
            params + [self.sql.json_parameter("new", [new])],
            old,
            "transition",
        )
        return new

    def reserve(self, old: Row, token: str, at: str, limits: Limits) -> Row:
        sql, params = self.assertion("installation_work_units", old, "work_unit_id")
        active = ",".join("'" + s + "'" for s in sorted(ACTIVE))
        table = self.sql.table("installation_work_units")
        plans = self.sql.table("installation_plans")
        sql += f"ASSERT @status IN ('PENDING','DEFERRED') AS 'installation_work_conflict'; ASSERT (SELECT COUNT(*) FROM {plans} WHERE plan_id=@plan AND store_id=@store AND status IN ('RUNNING','PARTIAL'))=1 AS 'installation_plan_conflict'; ASSERT NOT EXISTS(SELECT 1 FROM {table} WHERE store_id=@store AND status IN ({active})) AS 'installation_store_busy'; ASSERT (SELECT COUNT(DISTINCT store_id) FROM {table} WHERE status IN ({active}))<@capacity AS 'installation_capacity'; ASSERT NOT EXISTS(SELECT 1 FROM {table} u WHERE u.work_unit_id IN UNNEST(JSON_VALUE_ARRAY(@dependencies)) AND (u.store_id!=@store OR u.plan_id!=@plan OR u.status!='COMPLETE')) AS 'installation_dependencies'; ASSERT (SELECT COUNT(*) FROM {table} WHERE store_id=@store AND plan_id=@plan AND work_unit_id IN UNNEST(JSON_VALUE_ARRAY(@dependencies)))=ARRAY_LENGTH(JSON_VALUE_ARRAY(@dependencies)) AS 'installation_dependencies'; ASSERT (SELECT COUNT(*) FROM {self.sql.table('store_runtime_config')} WHERE store_id=@store AND revision=@config_revision AND sync_enabled=false)=1 AS 'installation_configuration_changed'; ASSERT (SELECT next_eligible_at IS NULL OR next_eligible_at<=@at FROM {table} WHERE work_unit_id=@id) AS 'installation_deferred'; "
        plan = [p for p in self.plans(old["store_id"]) if p["plan_id"] == old["plan_id"]]
        if len(plan) != 1:
            raise SafeError("installation_plan_conflict")
        new = {
            **old,
            "status": "DISPATCHING",
            "revision": old["revision"] + 1,
            "attempt_count": old["attempt_count"] + 1,
            "reservation_revision": old["revision"] + 1,
            "dispatch_token": token,
            "dispatch_operation_name": None,
            "execution_name": None,
            "updated_at": at,
            "next_eligible_at": None,
        }
        params += [
            scalar("capacity", "INT64", limits.global_parallel_store_limit),
            scalar("dependencies", "STRING", json.dumps(old["dependencies"])),
            scalar("config_revision", "INT64", plan[0]["registry_revision"]),
            scalar("at", "TIMESTAMP", at),
            self.sql.json_parameter("new", [new]),
        ]
        self.transaction(
            sql + self.sql.update("installation_work_units", "new", "work_unit_id"),
            params,
            old,
            "reserve",
        )
        return new

    def update_plan(self, old: Row, config: StoreConfig | None = None, **changes: Any) -> Row:
        new = {**old, **changes, "revision": old["revision"] + 1}
        sql, params = self.assertion("installation_plans", old, "plan_id")
        if config:
            sql += f"ASSERT (SELECT COUNT(*) FROM {self.sql.table('store_runtime_config')} WHERE store_id=@config_store AND revision=@config_revision AND sync_enabled=false)=1 AS 'installation_configuration_changed'; "
            params += [
                scalar("config_store", "STRING", config.store_id),
                scalar("config_revision", "INT64", old["registry_revision"]),
                self.sql.json_parameter("registry", [config.row()]),
            ]
            new["registry_revision"] = config.revision
            sql += self.sql.update("store_runtime_config", "registry", "store_id")
        self.transaction(
            sql + self.sql.update("installation_plans", "new", "plan_id"),
            params + [self.sql.json_parameter("new", [new])],
            old,
            "plan",
        )
        return new

    def verified(self, old: Row, source: Row, at: str, *, success: bool = True) -> Row:
        sql, params = self.assertion("installation_work_units", old, "work_unit_id")
        sql += f"ASSERT (SELECT COUNT(*) FROM {self.sql.table('source_connections')} WHERE row_key=@source_key AND store_id=@store AND connection_id=@connection AND status=@source_status AND updated_at IS NOT DISTINCT FROM @source_updated)=1 AS 'source_verification_conflict'; "
        new = {
            **old,
            "status": "COMPLETE" if success else "BLOCKED",
            "last_error_code": None if success else "source_verification_failed",
            "revision": old["revision"] + 1,
            "updated_at": at,
            "finished_at": at,
        }
        params += [
            scalar("source_key", "STRING", source["row_key"]),
            scalar("connection", "STRING", old["connection_id"]),
            scalar("source_status", "STRING", source["status"]),
            scalar("source_updated", "TIMESTAMP", source.get("updated_at")),
            self.sql.json_parameter(
                "source_row",
                [{**source, "status": "active" if success else "error", "updated_at": at}],
            ),
            self.sql.json_parameter("new", [new]),
        ]
        self.transaction(
            sql
            + self.sql.update("source_connections", "source_row", "row_key")
            + self.sql.update("installation_work_units", "new", "work_unit_id"),
            params,
            old,
            "verify",
        )
        return new
