"""Deterministic logical graph, with source-specific planning adapters."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from src.analytics.policy import VERSION as POLICY_VERSION
from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.ingestion.planning import filters_for
from src.installation.adoption import inspect, prefix
from src.installation.model import (
    DEFAULT_LIMITS,
    VERSION,
    Limits,
    Row,
    config_hash,
    interval,
    local_days,
    unit,
)
from src.utils.data import digest


class SourcePlanner(Protocol):
    def build(
        self, config: StoreConfig, plan: Row, days: list[tuple[str, str]], adopted: Row
    ) -> list[Row]: ...


class UpZeroPlanner:
    def build(
        self, config: StoreConfig, plan: Row, days: list[tuple[str, str]], adopted: Row
    ) -> list[Row]:
        rows: list[Row] = []
        cid = config.upzero_connection_id or ""
        verify = unit(plan, "upzero", cid, "verification", "VERIFY_SOURCE", {}, [], 0)
        rows.append(verify)
        for cp in adopted["pending"]:
            row = unit(
                plan,
                "upzero",
                cid,
                cp["resource"],
                "LEGACY_RESUME",
                cp["filters"],
                [verify["work_unit_id"]],
                1,
                mode=cp["mode"],
                checkpoint=cp,
            )
            row.update(
                records_processed=cp["records_processed"], pages_processed=cp["pages_processed"]
            )
            rows.append(row)
        if not adopted["customers_fresh"]:
            deps = [verify["work_unit_id"]] + [
                r["work_unit_id"] for r in rows if r["resource"] == "customers"
            ]
            rows.append(
                unit(
                    plan,
                    "upzero",
                    cid,
                    "customers",
                    "SYNC_SNAPSHOT",
                    {"limit": 200},
                    deps,
                    2,
                    mode="incremental",
                )
            )
        for index, (a, b) in enumerate(days):
            for resource in ("orders", "analytics_facts"):
                covered = adopted["coverage"][resource] + [
                    v
                    for cp in adopted["pending"]
                    if cp["resource"] == resource
                    and (v := interval(resource, cp["filters"], config.timezone or ""))
                ]
                if instant(prefix(a, b, covered)) >= instant(b):
                    continue
                deps = [verify["work_unit_id"]] + [
                    r["work_unit_id"]
                    for r in rows
                    if r["unit_kind"] == "LEGACY_RESUME" and r["resource"] == resource
                ]
                rows.append(
                    unit(
                        plan,
                        "upzero",
                        cid,
                        resource,
                        "SYNC_WINDOW",
                        filters_for(resource, instant(a), instant(b), config.timezone or ""),
                        deps,
                        10 + index * 10,
                    )
                )
        for row in rows:
            if row["unit_kind"] in {"SYNC_WINDOW", "SYNC_SNAPSHOT"}:
                row["checkpoint_plan_key"] = digest(
                    [config.store_id, cid, row["resource"], row["filters"], row["mode"]]
                )
        return rows


class MetaPlanner:
    def build(
        self, config: StoreConfig, plan: Row, days: list[tuple[str, str]], adopted: Row
    ) -> list[Row]:
        cid = config.meta_connection_id or ""
        rows = [unit(plan, "meta", cid, "verification", "VERIFY_SOURCE", {}, [], 0)]
        for index, resource in enumerate(("accounts", "campaigns", "adsets", "ads")):
            rows.append(
                unit(
                    plan,
                    "meta",
                    cid,
                    resource,
                    "META_CATALOG",
                    {},
                    [rows[-1]["work_unit_id"]],
                    3 + index,
                    mode="sync",
                )
            )
        for index, (a, b) in enumerate(days):
            zone = ZoneInfo(config.timezone or "")
            filters = {
                "since": instant(a).astimezone(zone).date().isoformat(),
                "until": instant(a).astimezone(zone).date().isoformat(),
                "as_of": b,
            }
            rows.append(
                unit(
                    plan,
                    "meta",
                    cid,
                    "insights",
                    "META_INSIGHTS",
                    filters,
                    [rows[4]["work_unit_id"]],
                    15 + index * 10,
                    mode="sync",
                )
            )
        return rows


class Planner:
    def __init__(
        self, limits: Limits = DEFAULT_LIMITS, adapters: dict[str, SourcePlanner] | None = None
    ):
        self.limits = limits
        self.adapters = adapters or {"upzero": UpZeroPlanner(), "meta": MetaPlanner()}

    def calculate(
        self,
        config: StoreConfig,
        target: str,
        now: str,
        *,
        operation: Row | None = None,
        adopt: bool = False,
        checkpoints: list[Row] | None = None,
        runs: list[Row] | None = None,
        certified_publication: Row | None = None,
    ) -> tuple[StoreConfig, Row, list[Row]]:
        if config.sync_enabled or (
            not adopt
            and (
                config.status != "DRAFT"
                or not operation
                or operation.get("status") != "INSTALLING"
                or operation.get("store_id") != config.store_id
            )
        ):
            raise SafeError("installation_store_not_admissible")
        if not (config.upzero_enabled or config.meta_enabled):
            raise SafeError("installation_source_required")
        if config.operation_b2b and (
            config.policy_version != POLICY_VERSION
            or not config.qualifying_order_statuses
            or not config.upzero_enabled
        ):
            raise SafeError("analytics_policy_required")
        config = replace(
            config, analytics_enabled=config.operation_b2b, status="DRAFT", sync_enabled=False
        )
        config.ready()
        if instant(target) > instant(now):
            raise SafeError("installation_target_not_closed")
        try:
            days = local_days(config.history_from or "", target, config.timezone or "")
        except SafeError as exc:
            if not adopt or exc.code != "closed_local_days_required":
                raise
            # Legacy range may begin mid-day. Preserve that instant; publish only full
            # local dates following it. Never mutate the canonical history_from.
            start, zone = instant(config.history_from or ""), ZoneInfo(config.timezone or "")
            next_day = start.astimezone(zone).date() + timedelta(days=1)
            boundary = datetime.combine(next_day, time(), zone).astimezone(UTC).isoformat()
            days = [(start.isoformat(), boundary)] + local_days(
                boundary, target, config.timezone or ""
            )

        identity = digest(
            [
                config.store_id,
                operation.get("operation_id") if operation else None,
                config.history_from,
                target,
                VERSION,
            ]
        )
        plan: Row = {
            "row_key": identity,
            "plan_id": identity,
            "onboarding_operation_id": operation.get("operation_id") if operation else None,
            "store_id": config.store_id,
            "status": "RUNNING",
            "revision": 1,
            "planner_version": VERSION,
            "registry_revision": config.revision,
            "config_hash": config_hash(config),
            "requested_from": config.history_from,
            "target_as_of": target,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "error_code": None,
            "priority": 0,
            "adopted_coverage": {},
        }
        try:
            evidence = inspect(config, checkpoints or [], runs or [], target)
        except SafeError as exc:
            plan.update(status="BLOCKED", error_code=exc.code)
            return config, plan, []
        plan["adopted_coverage"] = evidence["coverage"]
        # Meta legacy windows use the same checkpoint authority. Unsupported pinned
        # extraction configurations require review rather than a new parallel plan.
        meta_pending = [
            cp
            for cp in checkpoints or []
            if cp.get("connection_id") == config.meta_connection_id
            and cp.get("store_id") == config.store_id
            and (cp.get("status") not in {"complete", "recovered"} or cp.get("pending_raw_id"))
        ]
        if meta_pending:
            plan.update(status="BLOCKED", error_code="meta_pending_configuration_requires_recovery")
            return config, plan, []

        rows: list[Row] = []
        for source in self.adapters:
            if getattr(config, source + "_enabled", False):
                rows.extend(self.adapters[source].build(config, plan, days, evidence))
        if certified_publication:
            if certified_publication["store_id"] != config.store_id or instant(
                certified_publication["as_of"]
            ) > instant(target):
                raise SafeError("installation_publication_outside_range")
            plan["adopted_coverage"]["publication"] = certified_publication
        if config.operation_b2b:
            stops = sorted(
                set(
                    [
                        1,
                        *range(
                            1 + self.limits.publication_days,
                            len(days),
                            self.limits.publication_days,
                        ),
                        len(days),
                    ]
                )
            )
            zone = ZoneInfo(config.timezone or "")
            for stop in stops:
                end = days[stop - 1][1]
                if (
                    certified_publication
                    and stop != len(days)
                    and instant(end) <= instant(certified_publication["as_of"])
                ):
                    continue
                deps = []
                for row in rows:
                    if row["source"] != "upzero":
                        continue
                    bound = interval(row["resource"], row["filters"], config.timezone or "")
                    if not bound or instant(bound[0]) < instant(end):
                        deps.append(row["work_unit_id"])
                report_from = instant(days[0][0]).astimezone(zone).date()
                if instant(days[0][0]) != datetime.combine(report_from, time(), zone).astimezone(
                    UTC
                ):
                    report_from += timedelta(days=1)
                if report_from >= instant(end).astimezone(zone).date():
                    continue
                filters = {
                    "report_from": report_from.isoformat(),
                    "report_to": instant(end).astimezone(zone).date().isoformat(),
                    "as_of": end,
                    "facts_complete": stop == len(days),
                }
                rows.append(
                    unit(
                        plan,
                        "analytics",
                        "analytics",
                        "publication",
                        "PUBLISH_ANALYTICS",
                        filters,
                        deps,
                        11 + (stop - 1) * 10,
                        required=False,
                    )
                )
        if len(rows) > self.limits.max_units:
            raise SafeError("installation_plan_too_large")
        if len({r["work_unit_id"] for r in rows}) != len(rows):
            raise SafeError("installation_plan_conflict")
        return config, plan, rows
