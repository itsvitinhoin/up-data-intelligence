"""Authenticated metadata projections. No secrets, source API or business payloads."""

import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from src.admin.contracts import Principal, authorize
from src.dashboard.contracts import ReadError
from src.dashboard.queries import Query, table
from src.dashboard.repository import Reader
from src.utils.data import digest, now


def timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


SUPPORTED = frozenset({"upzero", "meta"})
HEALTH_STATES = frozenset(
    {"HEALTHY", "SYNCING", "PARTIAL", "STALE", "ERROR", "DISABLED", "NOT_CONFIGURED"}
)


class IntegrationReader:
    def __init__(self, project: str, reader: Reader):
        table(project, "up_analytics", "analytics_publications")
        self.project, self.reader, self.request_id = project, reader, uuid4().hex

    def query(
        self, name: str, sql: str, parameters: dict[str, tuple[str, object]]
    ) -> list[dict[str, Any]]:
        return self.reader.query(
            Query(name, sql, parameters),
            request_id=self.request_id,
            store_id="admin-metadata",
            generation=None,
        )

    def summary(self, principal: Principal, bindings: Sequence[dict[str, str]]) -> dict[str, Any]:
        authorize(principal)
        if len(bindings) > 1000:
            raise ReadError(503, "brand_inventory_limit")
        for binding in bindings:
            principal.authorize_tenant(binding["tenant_id"])
        stores = sorted({b["store_id"] for b in bindings})
        if not stores:
            return {"data": [], "metadata": {"as_of": now(), "basis": "operational_metadata"}}
        rows = self.query(
            "admin_brand_summaries",
            f"""WITH scoped_registry AS (
 SELECT store_id,status,sync_enabled,created_at,facts_coverage_from,facts_coverage_to
 FROM `{self.project}.up_ops.store_runtime_config`
 WHERE store_id IN (SELECT JSON_VALUE(v) FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@stores))) v)
), source_summary AS (
 SELECT c.store_id,ARRAY_AGG(STRUCT(c.source_system,c.status,
 c.secret_resource_name IS NOT NULL AS credential_configured)
 ORDER BY c.source_system,c.connection_id) AS sources
 FROM `{self.project}.up_core.source_connections` c
 WHERE c.store_id IN (SELECT store_id FROM scoped_registry)
 GROUP BY c.store_id
)
SELECT r.*,IFNULL(s.sources,[]) AS sources FROM scoped_registry r
LEFT JOIN source_summary s ON s.store_id=r.store_id
ORDER BY r.store_id LIMIT 1001""",
            {"stores": ("STRING", json.dumps(stores))},
        )
        if (
            len(rows) != len(stores)
            or len({r.get("store_id") for r in rows}) != len(rows)
            or any(r.get("store_id") not in stores for r in rows)
        ):
            raise ReadError(503, "brand_inventory_mismatch")
        by_store = {r["store_id"]: r for r in rows}
        result = []
        for binding in bindings:
            row = by_store[binding["store_id"]]
            sources = row.get("sources")
            if not isinstance(sources, list) or len(
                {s.get("source_system") for s in sources}
            ) != len(sources):
                raise ReadError(503, "connection_inventory_ambiguous")
            result.append(
                {
                    **{
                        k: binding[k]
                        for k in ("tenant_id", "brand_id", "workspace_operation_id", "operation")
                    },
                    "status": row["status"],
                    "sync_enabled": row["sync_enabled"],
                    "created_at": timestamp(
                        row.get("created_at")
                    ),  # No binding-adoption timestamp fallback.
                    "coverage_from": timestamp(row.get("facts_coverage_from")),
                    "coverage_to": timestamp(row.get("facts_coverage_to")),
                    "active_connections": sum(s["status"] == "active" for s in sources),
                    "pending_connections": sum(s["status"] == "pending" for s in sources),
                    "attention_connections": sum(
                        s["status"] not in {"active", "pending", "disabled", "inactive"}
                        for s in sources
                    ),
                    "sources": [
                        {
                            "provider": s["source_system"],
                            "status": s["status"],
                            "credential_configured": s["credential_configured"],
                        }
                        for s in sources
                    ],
                }
            )
        return {"data": result, "metadata": {"as_of": now(), "basis": "operational_metadata"}}

    def health(self, principal: Principal, binding: dict[str, str]) -> dict[str, Any]:
        """On-demand safe metadata. No cursor, filters, errors or credential refs transported."""
        principal.authorize_tenant(binding["tenant_id"])
        store = binding["store_id"]
        rows = self.query(
            "admin_integration_health",
            f"""WITH scoped_runs AS (
 SELECT store_id,run_id,source,resource,status,plan_key,started_at,finished_at,
 core_records_processed,core_pages_processed,core_records_failed
 FROM `{self.project}.up_ops.sync_runs` WHERE store_id=@store ORDER BY started_at DESC LIMIT 1001
), scoped_checkpoints AS (
 SELECT store_id,connection_id,resource,run_id,plan_key,status,pending_raw_id IS NOT NULL pending_raw
 FROM `{self.project}.up_ops.sync_checkpoints` WHERE store_id=@store LIMIT 1001
), latest_health AS (
 SELECT row_key,store_id,rule_id,severity,failed_count,checked_count,checked_at FROM `{self.project}.up_ops.quality_results`
 WHERE store_id=@store AND resource='data_health' AND record_id IS NULL
 QUALIFY checked_at=MAX(checked_at) OVER ()
)
SELECT 'registry' kind,TO_JSON_STRING(STRUCT(store_id,timezone,status,sync_enabled,facts_coverage_from,facts_coverage_to)) payload
FROM `{self.project}.up_ops.store_runtime_config` WHERE store_id=@store
UNION ALL SELECT 'source',TO_JSON_STRING(STRUCT(store_id,connection_id,source_system,status)) FROM `{self.project}.up_core.source_connections` WHERE store_id=@store
UNION ALL SELECT 'run',TO_JSON_STRING(r) FROM scoped_runs r
UNION ALL SELECT 'checkpoint',TO_JSON_STRING(c) FROM scoped_checkpoints c
UNION ALL SELECT 'health',TO_JSON_STRING(h) FROM latest_health h""",
            {"store": ("STRING", store)},
        )
        from src.control_plane.model import Window, instant
        from src.quality.data_health import ENRICHMENT_RULES, RULES

        groups: dict[str, list[dict[str, Any]]] = {
            k: [] for k in ("registry", "source", "run", "checkpoint", "health")
        }
        for row in rows:
            value = json.loads(row["payload"])
            if row["kind"] not in groups or value.get("store_id") != store:
                raise ReadError(503, "integration_health_scope_mismatch")
            groups[row["kind"]].append(value)
        if len(groups["registry"]) != 1 or any(
            len(groups[k]) >= 1001 for k in ("run", "checkpoint")
        ):
            raise ReadError(503, "integration_health_inventory_limit")
        registry = groups["registry"][0]
        at = now()
        expected = Window.previous_closed_day(registry["timezone"], at)
        findings = groups["health"]
        checks = {r["rule_id"]: r for r in findings}
        if len(checks) != len(findings):
            raise ReadError(503, "integration_health_ambiguous")
        enrichment = bool(set(checks) & set(ENRICHMENT_RULES))
        expected_rules = set(RULES) | (set(ENRICHMENT_RULES) if enrichment else set())
        evidence_current = set(checks) == expected_rules and all(
            instant(r["checked_at"]) >= instant(expected.as_of)
            and r.get("row_key")
            == digest([store, instant(expected.as_of).isoformat(), r["rule_id"]])
            for r in findings
        )
        sources = []
        connection_ids: set[str] = set()
        for source in groups["source"]:
            provider = source["source_system"]
            if provider not in SUPPORTED or provider in connection_ids:
                raise ReadError(503, "connection_inventory_ambiguous")
            connection_ids.add(provider)
            runs = [r for r in groups["run"] if r["source"] == provider]
            checkpoints = [
                c for c in groups["checkpoint"] if c["connection_id"] == source["connection_id"]
            ]
            rules = (
                {"upzero_customers_fresh", "upzero_orders_covered", "upzero_facts_covered"}
                if provider == "upzero"
                else {"meta_daily_covered", "meta_catalog_fresh"}
            )
            if enrichment:
                rules |= {
                    "upzero_catalog_certified"
                    if provider == "upzero"
                    else "meta_creative_daily_covered"
                }
            applicable = [checks[r] for r in rules if r in checks]
            certified = (
                evidence_current
                and len(applicable) == len(rules)
                and all(r["failed_count"] == 0 and r["checked_count"] > 0 for r in applicable)
            )
            state = "PARTIAL"
            if source["status"] in {"disabled", "inactive"}:
                state = "DISABLED"
            elif source["status"] == "error" or any(
                c["status"] == "needs_review" for c in checkpoints
            ):
                state = "ERROR"
            elif source["status"] == "active":
                if any(
                    c["pending_raw"] or c["status"] not in {"complete", "recovered"}
                    for c in checkpoints
                ):
                    state = "PARTIAL"
                elif certified:
                    state = "HEALTHY"
                elif not evidence_current:
                    state = "STALE"
            successful = [
                r
                for r in runs
                if r["status"] == "completed"
                and r["core_records_failed"] == 0
                and r["finished_at"]
                and any(
                    c["run_id"] == r["run_id"]
                    and c["plan_key"] == r["plan_key"]
                    and c["status"] == "complete"
                    and not c["pending_raw"]
                    for c in checkpoints
                )
            ]
            resources = []
            for resource in sorted({r["resource"] for r in runs if r["resource"]}):
                selected = [r for r in runs if r["resource"] == resource]
                last = max(selected, key=lambda r: r["started_at"] or "")
                complete = [
                    r
                    for r in successful
                    if r["resource"] == resource
                    and any(
                        c["run_id"] == r["run_id"]
                        and c["plan_key"] == r["plan_key"]
                        and c["status"] == "complete"
                        and not c["pending_raw"]
                        for c in checkpoints
                    )
                ]
                success = max(complete, key=lambda r: r["finished_at"]) if complete else None
                resources.append(
                    {
                        "resource": resource,
                        "ledger_status": last["status"],
                        "last_attempt_at": last["started_at"],
                        "last_success_at": success["finished_at"] if success else None,
                        "records_processed": last["core_records_processed"],
                        "pages_processed": last["core_pages_processed"],
                        "failed_records": last["core_records_failed"],
                    }
                )
            sources.append(
                {
                    "provider": provider,
                    "connection_status": source["status"],
                    "health": state,
                    "last_success_at": max((r["finished_at"] for r in successful), default=None),
                    "last_attempt_at": max(
                        (r["started_at"] for r in runs if r["started_at"]), default=None
                    ),
                    "coverage_certified": certified,
                    "resources": resources,
                }
            )
        return {
            "data": {
                "tenant_id": binding["tenant_id"],
                "brand_id": binding["brand_id"],
                "workspace_operation_id": binding["workspace_operation_id"],
                "next_sync_at": None,
                "expected_cutoff": expected.as_of,
                "health_checked_at": max((r["checked_at"] for r in findings), default=None),
                "health_evidence_current": evidence_current,
                "blocking_findings": None
                if not findings
                else sum(
                    r["failed_count"] for r in findings if r["severity"] in {"alert", "error"}
                ),
                "warning_findings": None
                if not findings
                else sum(r["failed_count"] for r in findings if r["severity"] == "warning"),
                "sources": sources,
            },
            "metadata": {"as_of": at, "basis": "durable_operational_evidence"},
        }
