"""Durable-evidence detector. Never ingests, repairs, activates or publishes data."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from src.analytics.cloud.transport import Transport, scalar
from src.control_plane.model import StoreConfig, Window, instant
from src.control_plane.preflight import Prerequisites
from src.control_plane.recurring import certified_window, monotonic
from src.domain.models import SafeError
from src.ingestion.checkpoints import checkpoint_pending
from src.installation.adoption import inspect, prefix
from src.utils.data import digest

RULES = (
    "registry_active",
    "sync_enabled",
    "source_connections_active",
    "no_pending_raw",
    "no_nonterminal_previous_day_runs",
    "upzero_customers_fresh",
    "upzero_orders_covered",
    "upzero_facts_covered",
    "meta_daily_covered",
    "meta_catalog_fresh",
    "analytics_head_valid",
    "analytics_cutoff_current",
    "analytics_window_monotonic",
    "intelligence_base_current",
    "dashboard_publication_resolves",
    "history_semantics_valid",
)
Row = dict[str, Any]


def primitive(value: Any) -> Any:
    """Lossless operational timestamps; no float conversion or PII projection."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [primitive(v) for v in value]
    return value


@dataclass(frozen=True)
class Finding:
    rule_id: str
    failed_count: int
    checked_count: int = 1
    severity: str = "alert"

    def row(self, store: str, cutoff: str, audit_id: str, at: str) -> Row:
        return {
            "row_key": digest([store, instant(cutoff).isoformat(), self.rule_id]),
            "store_id": store,
            "run_id": audit_id,
            "resource": "data_health",
            "rule_id": self.rule_id,
            "severity": self.severity,
            "record_id": None,
            "failed_count": self.failed_count,
            "checked_count": self.checked_count,
            "checked_at": at,
        }


def publication_history(config: StoreConfig, rows: list[Row], at: str) -> None:
    """Every completed receipt participates; equal-cutoff reruns may not shrink."""
    receipts = sorted(
        (r for r in rows if r.get("record_kind") == "RECEIPT" and r.get("status") == "completed"),
        key=lambda r: r["generation"],
    )
    if not receipts or len({r["generation"] for r in receipts}) != len(receipts):
        raise SafeError("health_publication_history_invalid")
    previous = None
    for r in receipts:
        if r.get("store_id") != config.store_id:
            raise SafeError("health_store_scope_mismatch")
        current = Window(str(r["report_from"]), str(r["report_to"]), str(r["as_of"]), at, at)
        if previous is not None:
            monotonic(previous, current)
        previous = current


def intelligence_current(rows: list[Row], base: Row, window: Window, config: StoreConfig) -> None:
    scoped = [r for r in rows if r.get("policy_hash") == base["policy_hash"]]
    heads = [r for r in scoped if r.get("record_kind") == "HEAD"]
    if len(heads) != 1 or heads[0].get("status") != "completed":
        raise SafeError("health_intelligence_head_invalid")
    head = heads[0]
    receipts = [
        r
        for r in scoped
        if r.get("record_kind") == "RECEIPT"
        and r.get("generation") == head.get("generation")
        and r.get("publication_id") == head.get("publication_id")
    ]
    if len(receipts) != 1:
        raise SafeError("health_intelligence_receipt_invalid")
    receipt = receipts[0]
    compared = set(receipt) - {"record_kind", "row_key"}
    if any(primitive(head.get(k)) != primitive(receipt[k]) for k in compared):
        raise SafeError("health_intelligence_receipt_mismatch")
    if (
        receipt.get("store_id") != config.store_id
        or receipt.get("base_generation") != base["generation"]
        or receipt.get("base_publication_id") != base["publication_id"]
        or str(receipt.get("report_from")) != window.report_from
        or str(receipt.get("report_to")) != window.report_to
        or instant(str(receipt.get("as_of"))) != instant(window.as_of)
        or receipt.get("history_complete") != config.history_complete
        or receipt.get("facts_complete") != config.facts_complete
        or receipt.get("meta_complete") is not True
    ):
        raise SafeError("health_intelligence_base_not_current")


class DataHealth:
    def __init__(self, transport: Transport):
        self.transport = transport
        self.pre = Prerequisites(transport)

    def check(self, config: StoreConfig, at: str) -> tuple[Window, list[Finding]]:
        daily = Window.previous_closed_day(config.timezone or "", at)
        findings: list[Finding] = []

        def guard(rule: str, action: Callable[[], object], *, enabled: bool = True) -> None:
            if not enabled:
                findings.append(Finding(rule, 0, 0))  # Explicitly not applicable, not fresh.
                return
            try:
                outcome = action()
                failed = outcome is False
            except (SafeError, ValueError, KeyError, TypeError, IndexError):
                failed = True
            # Transport/unknown failures propagate: do not disguise failed reads as evidence.
            findings.append(Finding(rule, int(failed)))

        checkpoints = primitive(self.pre.rows(config.store_id, "up_ops.sync_checkpoints", "*", at))
        runs = primitive(self.pre.rows(config.store_id, "up_ops.sync_runs", "*", at))
        sources = self.pre.rows(
            config.store_id, "up_core.source_connections", "source_system,connection_id,status", at
        )
        guard("registry_active", lambda: config.status == "ACTIVE")
        guard("sync_enabled", lambda: config.sync_enabled is True)

        def source_active() -> bool:
            for system in ("upzero", "meta"):
                if getattr(config, system + "_enabled"):
                    selected = [r for r in sources if r["source_system"] == system]
                    if (
                        len(selected) != 1
                        or selected[0]["status"] != "active"
                        or selected[0]["connection_id"]
                        != getattr(config, system + "_connection_id")
                    ):
                        return False
            return True

        guard("source_connections_active", source_active)
        guard("no_pending_raw", lambda: not any(r.get("pending_raw_id") for r in checkpoints))
        guard(
            "no_nonterminal_previous_day_runs",
            lambda: (
                not any(checkpoint_pending(r) for r in checkpoints)
                and not any(
                    r.get("status") in {"running", "queued", "extracted"}
                    and instant(r["started_at"]) <= instant(at)
                    for r in runs
                )
            ),
        )

        def evidence() -> Row:
            return inspect(config, checkpoints, runs, daily.as_of)

        guard(
            "upzero_customers_fresh",
            lambda: evidence()["customers_fresh"] is True,
            enabled=config.upzero_enabled,
        )
        for resource, rule in (
            ("orders", "upzero_orders_covered"),
            ("analytics_facts", "upzero_facts_covered"),
        ):

            def covered(resource: str = resource) -> bool:
                return instant(
                    prefix(config.history_from or "", daily.as_of, evidence()["coverage"][resource])
                ) >= instant(daily.as_of)

            guard(
                rule,
                covered,
                enabled=config.upzero_enabled,
            )
        window = daily
        heads: list[Row] = []

        def resolve() -> None:
            nonlocal window, heads
            heads = self.pre.publication(config, daily)
            window = certified_window(config, heads, at)

        guard("analytics_head_valid", resolve, enabled=config.analytics_enabled)
        guard(
            "analytics_cutoff_current",
            lambda: (
                bool(heads)
                and window.report_to == daily.report_to
                and instant(window.as_of) == instant(daily.as_of)
                and config.facts_complete is True
                and instant(config.facts_coverage_to or "") >= instant(daily.as_of)
            ),
            enabled=config.analytics_enabled,
        )
        guard(
            "meta_daily_covered",
            lambda: self.pre.meta_complete(config, window),
            enabled=config.meta_enabled,
        )
        # The canonical Meta preflight validates independent fresh catalog runs as well.
        guard(
            "meta_catalog_fresh",
            lambda: self.pre.meta_complete(config, window),
            enabled=config.meta_enabled,
        )
        guard(
            "analytics_window_monotonic",
            lambda: publication_history(
                config,
                [
                    r
                    for r in self.pre.rows(
                        config.store_id, "up_analytics.analytics_publications", "*", at
                    )
                    if heads and r.get("policy_hash") == heads[0]["policy_hash"]
                ],
                at,
            ),
            enabled=config.analytics_enabled,
        )
        guard(
            "intelligence_base_current",
            lambda: intelligence_current(
                self.pre.rows(
                    config.store_id, "up_analytics.analytics_intelligence_publications", "*", at
                ),
                heads[0],
                window,
                config,
            ),
            enabled=config.intelligence_enabled,
        )
        guard("dashboard_publication_resolves", resolve, enabled=config.analytics_enabled)

        def history_semantics() -> bool:
            config.policy(window).reference()  # Lifetime=true requires documented proof.
            if not config.analytics_enabled:
                return True
            rows, _ = self.transport.query(
                f"SELECT COUNT(*) AS checked, COUNTIF(history_complete IS DISTINCT FROM @history OR (@history=false AND new_customers IS NOT NULL)) AS failed FROM `{self.transport.config.project}.up_analytics.analytics_store_daily` FOR SYSTEM_TIME AS OF @snapshot WHERE store_id=@store AND policy_hash=@policy",
                [
                    scalar("history", "BOOL", config.history_complete),
                    scalar("store", "STRING", config.store_id),
                    scalar("policy", "STRING", config.policy(window).policy_hash),
                    scalar("snapshot", "TIMESTAMP", at),
                ],
            )
            return len(rows) == 1 and rows[0]["checked"] > 0 and rows[0]["failed"] == 0

        guard("history_semantics_valid", history_semantics)
        return daily, findings

    def persist(self, rows: list[Row]) -> None:
        """Idempotent aggregate-only MERGE into the existing quality table."""
        import json

        if not rows or any(
            r.get("resource") != "data_health" or r.get("record_id") is not None for r in rows
        ):
            raise ValueError("health_aggregate_rows_required")
        if len({r["row_key"] for r in rows}) != len(rows):
            raise ValueError("duplicate_health_rule")
        table = f"`{self.transport.config.project}.up_ops.quality_results`"
        fields = "row_key store_id run_id resource rule_id severity record_id failed_count checked_count checked_at".split()
        expressions = [
            f"CAST(JSON_VALUE(r,'$.{k}') AS {'INT64' if k.endswith('_count') else 'TIMESTAMP' if k == 'checked_at' else 'STRING'}) `{k}`"
            for k in fields
        ]
        stage = (
            "SELECT "
            + ",".join(expressions)
            + " FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@rows))) r"
        )
        updates = ",".join(f"`{k}`=s.`{k}`" for k in fields if k != "row_key")
        sql = f"BEGIN TRANSACTION; ASSERT NOT EXISTS(SELECT row_key FROM {table} WHERE row_key IN (SELECT row_key FROM ({stage})) GROUP BY row_key HAVING COUNT(*)>1) AS 'duplicate_health_result'; MERGE {table} t USING ({stage}) s ON t.row_key=s.row_key WHEN MATCHED THEN UPDATE SET {updates} WHEN NOT MATCHED THEN INSERT ({','.join(fields)}) VALUES ({','.join('s.' + k for k in fields)}); COMMIT TRANSACTION;"
        try:
            self.transport.query(sql, [scalar("rows", "STRING", json.dumps(rows))])
        except Exception:
            raise SafeError("health_write_outcome_unknown") from None
