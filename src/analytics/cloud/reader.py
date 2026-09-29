"""Minimal-column, time-consistent CORE reads with explicit bounded dependencies."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.analytics.cloud.transport import Transport, array, scalar
from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row
from src.analytics.materialization import CoreSnapshot, Plan, plan_changes
from src.analytics.sql_models import SOURCE_FIELDS
from src.utils.data import digest, timestamp


@dataclass(frozen=True)
class SourceGeneration:
    snapshot_at: str
    generation: str  # opaque, no entity IDs or PII
    completeness_confirmed: bool

    def __post_init__(self) -> None:
        timestamp(self.snapshot_at)
        if len(self.generation) != 64 or any(c not in "0123456789abcdef" for c in self.generation):
            raise ValueError("source_generation_must_be_digest")


class BigQueryAnalyticsReader:
    def __init__(self, transport: Transport, policy: AnalyticsPolicy):
        self.transport = transport
        self.policy = policy

    def read(
        self,
        table: str,
        generation: SourceGeneration,
        *,
        days: set[str] | None = None,
        customer_ids: set[str] | None = None,
        order_ids: set[str] | None = None,
        full_refresh: bool = False,
    ) -> list[Row]:
        if table not in SOURCE_FIELDS:
            raise ValueError("analytics_core_table_not_allowed")
        if not full_refresh and days is None and customer_ids is None and order_ids is None:
            raise ValueError("explicit_affected_scope_required")
        p = self.policy
        params = [
            scalar("store", "STRING", p.store_id),
            scalar("snapshot_at", "TIMESTAMP", generation.snapshot_at),
            scalar("history_from", "TIMESTAMP", p.history_from),
            scalar("as_of", "TIMESTAMP", p.as_of),
            scalar("timezone", "STRING", p.reporting_timezone),
        ]
        predicates = ["store_id=@store", "source_system='upzero'"]
        alternatives = []
        if days is not None and table != "customers":
            date_field = {
                "orders": "created_at",
                "order_items": "order_created_at",
                "analytics_events": "occurred_at",
            }[table]
            params.append(array("days", sorted(days)))
            alternatives.append(f"CAST(DATE({date_field},@timezone) AS STRING) IN UNNEST(@days)")
            # A range predicate allows pruning; exact dates above handle sparse sets.
            if days and not customer_ids and not order_ids:
                params += [
                    scalar("min_day", "DATE", min(days)),
                    scalar("max_day", "DATE", max(days)),
                ]
                predicates += [
                    f"{date_field}>=TIMESTAMP(@min_day,@timezone)",
                    f"{date_field}<TIMESTAMP(DATE_ADD(@max_day,INTERVAL 1 DAY),@timezone)",
                ]
        if customer_ids is not None:
            if table not in {"customers", "orders"}:
                raise ValueError("invalid_customer_dependency")
            params.append(array("customers", sorted(customer_ids)))
            alternatives.append("customer_id IN UNNEST(@customers)")
        if order_ids is not None:
            if table not in {"orders", "order_items"}:
                raise ValueError("invalid_order_dependency")
            params.append(array("orders", sorted(order_ids)))
            alternatives.append("order_id IN UNNEST(@orders)")
        if not full_refresh:
            predicates.append("(" + " OR ".join(alternatives or ["FALSE"]) + ")")
        if table == "orders":
            predicates += ["created_at>=@history_from", "created_at<@as_of"]
        columns = ",".join(f"`{f}`" for f in SOURCE_FIELDS[table])
        sql = (
            f"SELECT {columns} FROM `{self.transport.config.project}.up_core.{table}` FOR SYSTEM_TIME AS OF @snapshot_at WHERE "
            + " AND ".join(predicates)
        )
        rows, _ = self.transport.query(sql, params)
        # Client mocks and future changes cannot bypass tenant validation.
        if any(r.get("store_id") != p.store_id or r.get("source_system") != "upzero" for r in rows):
            raise ValueError("source_store_mismatch")
        return [
            {
                k: (
                    v.isoformat()
                    if isinstance(v, datetime)
                    else str(v)
                    if isinstance(v, Decimal)
                    else v
                )
                for k, v in r.items()
            }
            for r in rows
        ]

    def candidates(
        self, table: str, generation: SourceGeneration, *, observed_from: str, observed_to: str
    ) -> list[Row]:
        """Candidate index only: observed_at is NOT a commit watermark."""
        if table not in SOURCE_FIELDS:
            raise ValueError("analytics_core_table_not_allowed")
        if timestamp(observed_from) >= timestamp(observed_to):
            raise ValueError("invalid_observed_interval")
        fields = {
            "customers": ["customer_id"],
            "orders": ["order_id", "customer_id", "created_at"],
            "order_items": ["order_id", "item_id", "order_created_at"],
            "analytics_events": ["fact_id", "occurred_at", "session_id"],
        }[table]
        columns = ",".join(fields + ["observed_at", "version_id"])
        sql = f"SELECT {columns} FROM `{self.transport.config.project}.up_core.{table}_versions` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND source_system='upzero' AND observed_at>=@low AND observed_at<@high"
        rows, _ = self.transport.query(
            sql,
            [
                scalar("store", "STRING", self.policy.store_id),
                scalar("snapshot_at", "TIMESTAMP", generation.snapshot_at),
                scalar("low", "TIMESTAMP", observed_from),
                scalar("high", "TIMESTAMP", observed_to),
            ],
        )
        return rows

    def snapshot(
        self, generation: SourceGeneration, plan: Plan, *, full_refresh: bool = False
    ) -> CoreSnapshot:
        if plan.full and not full_refresh:
            raise ValueError("full_refresh_requires_authorization")
        if not generation.completeness_confirmed and not full_refresh:
            raise ValueError("unsealed_source_generation")
        days = plan.scopes["analytics_store_daily"] or set()
        orders = self.read(
            "orders",
            generation,
            days=days,
            customer_ids=plan.source_customers,
            full_refresh=full_refresh,
        )
        ids = {r["order_id"] for r in orders}
        customers = {r["customer_id"] for r in orders if r.get("customer_id")}
        return CoreSnapshot(
            orders,
            self.read("customers", generation, customer_ids=customers),
            self.read("order_items", generation, order_ids=ids),
            self.read(
                "analytics_events", generation, days=plan.scopes["analytics_funnel_daily"] or set()
            ),
        )


def expand_dependencies(
    policy: AnalyticsPolicy,
    current: CoreSnapshot,
    previous: CoreSnapshot,
    previous_policy: AnalyticsPolicy,
    *,
    history_closure_confirmed: bool,
) -> Plan:
    """Use approved planner on complete affected histories/cohort peers, not deltas alone.

    A future commit-index provider must supply both old/new dependency closures.
    Missing closure must fail rather than silently publish incomplete cohorts.
    """
    if not history_closure_confirmed:
        raise ValueError("dependency_closure_required")
    return plan_changes(
        policy, current.scoped(policy), previous.scoped(previous_policy), previous_policy
    )


def generation_id(snapshot_at: str, source_manifest: str) -> str:
    return digest([timestamp(snapshot_at), source_manifest])
