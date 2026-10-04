"""Parameterized ledger transactions. Reservations serialize across *all* stores.

Global lease is required by callers. SQL also asserts store admission and exact CAS.
Uncertain mutation retains the existing non-expiring lease; never repeat the write.
"""

import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.admin.contracts import AdminError
from src.admin.repository import BigQueryOnboarding
from src.analytics.cloud.transport import Transport, scalar
from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.installation.model import ACTIVE, Limits, Row, require_creatable_plan
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
    def activate(self, plan: Row, config: StoreConfig, at: str) -> Row: ...


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
            "store_id=@store"
            if store
            else f"(status IN ('RUNNING','PARTIAL','OUTCOME_UNKNOWN') OR (status='COMPLETE' AND onboarding_operation_id IN (SELECT operation_id FROM {self.sql.table('onboarding_operations')} WHERE status='INSTALLING')))",
            [scalar("store", "STRING", store)] if store else [],
        )

    def units(self, plan: str | None = None) -> list[Row]:
        # Orchestrator bounds its read to the active plan set, never all historical units.
        return self.rows(
            "installation_work_units",
            "plan_id=@plan"
            if plan
            else f"plan_id IN (SELECT plan_id FROM {self.sql.table('installation_plans')} WHERE status IN ('RUNNING','PARTIAL','OUTCOME_UNKNOWN') OR (status='COMPLETE' AND onboarding_operation_id IN (SELECT operation_id FROM {self.sql.table('onboarding_operations')} WHERE status='INSTALLING')))",
            [scalar("plan", "STRING", plan)] if plan else [],
        )

    def onboardings(self, limit: int, store: str | None = None) -> list[Row]:
        from src.control_plane.repository import decoded

        table = self.sql.table("onboarding_operations")
        rows, _ = self.transport.query(
            f"SELECT * FROM {table} o WHERE status='INSTALLING' AND NOT EXISTS (SELECT 1 FROM {self.sql.table('installation_plans')} p WHERE p.store_id=o.store_id)"
            + (" AND store_id=@store" if store else "")
            + " ORDER BY created_at,store_id,operation_id LIMIT @limit",
            [scalar("limit", "INT64", limit), scalar("store", "STRING", store)],
        )
        return [
            {k: v.isoformat() if isinstance(v, datetime) else v for k, v in decoded(r).items()}
            for r in rows
        ]

    def evidence(self, store: str) -> tuple[list[Row], list[Row]]:
        params = [scalar("store", "STRING", store)]
        return (
            self.rows("sync_checkpoints", "store_id=@store", params),
            self.rows("sync_runs", "store_id=@store", params),
        )

    def block_onboarding(self, operation: Row, code: str, at: str) -> None:
        try:
            self.sql.transition(
                operation,
                status="BLOCKED",
                current_step="INSTALLATION_PLANNING",
                error_code=code,
                updated_at=at,
            )
        except AdminError as exc:
            if exc.code == "onboarding_write_outcome_unknown":
                raise SafeError("bigquery_write_outcome_unknown") from None
            raise

    def activate(self, plan: Row, c: StoreConfig, at: str) -> Row:
        if plan["status"] != "COMPLETE" or c.status != "READY" or c.sync_enabled:
            raise SafeError("installation_activation_required")
        c.ready()
        sql, params = self.assertion("installation_plans", plan, "plan_id")
        sql += f"ASSERT NOT EXISTS(SELECT 1 FROM {self.sql.table('installation_work_units')} WHERE plan_id=@id AND status!='COMPLETE') AS 'installation_not_complete'; ASSERT NOT EXISTS(SELECT 1 FROM {self.sql.table('sync_checkpoints')} WHERE store_id=@config_store AND (status NOT IN ('complete','recovered') OR pending_raw_id IS NOT NULL)) AS 'activation_source_not_complete'; ASSERT (SELECT COUNT(*) FROM {self.sql.table('store_runtime_config')} WHERE store_id=@config_store AND status='READY' AND sync_enabled=false AND revision=@config_revision)=1 AS 'installation_configuration_changed'; "
        for system in ("upzero", "meta"):
            if getattr(c, system + "_enabled"):
                sql += f"ASSERT (SELECT COUNT(*) FROM {self.sql.table('source_connections')} WHERE store_id=@config_store AND source_system='{system}')=1 AND (SELECT COUNT(*) FROM {self.sql.table('source_connections')} WHERE store_id=@config_store AND source_system='{system}' AND connection_id=@{system}_connection AND status='active')=1 AS 'source_verification_required'; "
                params.append(
                    scalar(system + "_connection", "STRING", getattr(c, system + "_connection_id"))
                )
        new_config = replace(
            c, status="ACTIVE", sync_enabled=True, revision=c.revision + 1, updated_at=at
        )
        new = {
            **plan,
            "revision": plan["revision"] + 1,
            "registry_revision": new_config.revision,
            "updated_at": at,
        }
        params += [
            scalar("config_store", "STRING", c.store_id),
            scalar("config_revision", "INT64", c.revision),
            self.sql.json_parameter("registry", [new_config.row()]),
            self.sql.json_parameter("new", [new]),
        ]
        if plan.get("onboarding_operation_id"):
            op = self.sql.get(plan["onboarding_operation_id"])
            if not op or op["store_id"] != c.store_id or op["status"] != "INSTALLING":
                raise SafeError("installation_onboarding_required")
            params += [
                scalar("operation", "STRING", op["operation_id"]),
                scalar("onboarding_revision", "INT64", op["revision"]),
                self.sql.json_parameter(
                    "onboarding",
                    [
                        {
                            **op,
                            "revision": op["revision"] + 1,
                            "status": "READY",
                            "current_step": "ACTIVE",
                            "updated_at": at,
                            "completed_at": at,
                            "error_code": None,
                        }
                    ],
                ),
            ]
            sql += f"ASSERT (SELECT COUNT(*) FROM {self.sql.table('onboarding_operations')} WHERE operation_id=@operation AND store_id=@config_store AND revision=@onboarding_revision AND status='INSTALLING')=1 AS 'onboarding_revision_conflict'; "
            sql += self.sql.update("onboarding_operations", "onboarding", "operation_id")
        sql += self.sql.update("store_runtime_config", "registry", "store_id") + self.sql.update(
            "installation_plans", "new", "plan_id"
        )
        self.transaction(sql, params, plan, "activate")
        return new

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
        require_creatable_plan(plan)
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
