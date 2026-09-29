"""Offline, transactional readiness runner. No BigQuery/cloud adapter is registered.

SQLite is an isolated simulation of analytics publication, not a production sink.
The source snapshot is read-only. Full CORE snapshots here stand in for a future
bounded change feed + history/cohort lookups, never for a production full-scan job.
"""

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta

from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row, build, instant
from src.analytics.policy import LTV_DAYS
from src.analytics.quality import unique, validate_outputs
from src.analytics.schema import SCHEMAS
from src.analytics.serialization import encode_tables
from src.observability.logging import event
from src.utils.data import canonical, digest

DATE_FIELDS = {
    "analytics_store_daily": "order_date",
    "analytics_products_daily": "order_date",
    "analytics_funnel_daily": "event_date",
}
SCOPE_FIELDS = DATE_FIELDS | {
    "analytics_customer_metrics": "customer_id",
    "analytics_customer_purchase_sequence": "customer_id",
    "analytics_cohorts": "cohort_month",
    "analytics_purchase_distribution": "cohort_month",
}


@dataclass(frozen=True)
class CoreSnapshot:
    orders: list[Row]
    customers: list[Row]
    items: list[Row]
    events: list[Row]

    def scoped(self, policy: AnalyticsPolicy) -> "CoreSnapshot":
        def select(rows: list[Row]) -> list[Row]:
            return [r for r in rows if r.get("store_id") == policy.store_id]

        snapshot = CoreSnapshot(
            *(select(rows) for rows in (self.orders, self.customers, self.items, self.events))
        )
        for rows, key, rule in (
            (snapshot.orders, "order_id", "duplicate_order"),
            (snapshot.customers, "customer_id", "duplicate_customer"),
            (snapshot.events, "fact_id", "duplicate_fact"),
        ):
            unique(rows, key, rule)
        if any(
            r.get("source_system") != "upzero"
            for rows in (snapshot.orders, snapshot.customers, snapshot.items, snapshot.events)
            for r in rows
        ):
            raise ValueError("unsupported_analytics_source")
        if any(instant(r["created_at"]) < instant(policy.history_from) for r in snapshot.orders):
            raise ValueError("snapshot_outside_declared_history")
        return snapshot

    @property
    def revision(self) -> str:
        return digest(
            [
                sorted(canonical(r) for r in rows)
                for rows in (self.orders, self.customers, self.items, self.events)
            ]
        )


@dataclass
class Plan:
    scopes: dict[str, set[str] | None]  # None = complete store/policy slice, never other policies
    source_customers: set[str]
    days: set[str]
    cohorts: set[str]
    full: bool

    def contains(self, model: str, row: Row) -> bool:
        scope = self.scopes[model]
        return scope is None or row.get(SCOPE_FIELDS[model]) in scope


def days_between(start: str, end: str) -> set[str]:
    result = set()
    current = date.fromisoformat(start)
    while current < date.fromisoformat(end):
        result.add(current.isoformat())
        current += timedelta(days=1)
    return result


def histories(snapshot: CoreSnapshot, policy: AnalyticsPolicy) -> dict[str, list[Row]]:
    customers = {r["customer_id"] for r in snapshot.customers}
    grouped: dict[str, list[Row]] = defaultdict(list)
    for order in snapshot.orders:
        if (
            order.get("customer_id") in customers
            and order.get("order_status") in policy.qualifying_order_statuses
            and instant(order["created_at"]) < instant(policy.as_of)
        ):
            grouped[order["customer_id"]].append(order)
    for rows in grouped.values():
        rows.sort(key=lambda o: (instant(o["created_at"]), o["order_id"]))
    return grouped


def changes(old: list[Row], new: list[Row], key: str) -> list[Row]:
    left, right = ({str(r[key]): r for r in rows} for rows in (old, new))
    keys = {k for k in left.keys() | right.keys() if left.get(k) != right.get(k)}
    return [r for mapping in (left, right) for k, r in mapping.items() if k in keys]


def plan_changes(
    policy: AnalyticsPolicy,
    current: CoreSnapshot,
    previous: CoreSnapshot | None,
    previous_policy: AnalyticsPolicy | None,
) -> Plan:
    daily = days_between(policy.report_from, policy.report_to)
    if (
        previous is None
        or previous_policy is None
        or previous_policy.policy_hash != policy.policy_hash
    ):
        return Plan(
            {m: set(daily) if m in DATE_FIELDS else None for m in SCHEMAS},
            set(),
            daily,
            set(),
            True,
        )
    if (
        policy.history_from != previous_policy.history_from
        or policy.history_complete != previous_policy.history_complete
        or policy.facts_complete != previous_policy.facts_complete
    ):
        raise ValueError("coverage_changed_requires_explicit_full_refresh")
    cfg = policy.reference()
    order_changes = changes(previous.orders, current.orders, "order_id")
    customer_changes = changes(previous.customers, current.customers, "customer_id")
    item_changes = changes(
        [{**r, "identity": digest([r.get("order_id"), r.get("item_id")])} for r in previous.items],
        [{**r, "identity": digest([r.get("order_id"), r.get("item_id")])} for r in current.items],
        "identity",
    )
    affected_orders = {r["order_id"] for r in order_changes + item_changes}
    affected_customers = {r["customer_id"] for r in customer_changes}
    affected_customers |= {r["customer_id"] for r in order_changes if r.get("customer_id")}
    for order in previous.orders + current.orders:
        if order["order_id"] in affected_orders and order.get("customer_id"):
            affected_customers.add(order["customer_id"])
    old_hist, new_hist = histories(previous, previous_policy), histories(current, policy)
    affected_customers |= {
        cid for cid in old_hist.keys() | new_hist.keys() if old_hist.get(cid) != new_hist.get(cid)
    }
    # Window maturity can change with no source change. Recompute only crossing customers.
    for cid, orders in new_hist.items():
        if any(
            instant(previous_policy.as_of)
            < instant(orders[0]["created_at"]) + timedelta(days=n)
            <= instant(policy.as_of)
            for n in LTV_DAYS
        ):
            affected_customers.add(cid)
    cohort_months = {
        cfg.local_date(h[cid][0]["created_at"])[:7] + "-01"
        for h in (old_hist, new_hist)
        for cid in affected_customers
        if cid in h
    }
    # Close/open calendar cohort periods once per local month transition.
    if cfg.local_date(previous_policy.as_of)[:7] != cfg.local_date(policy.as_of)[:7]:
        cohort_months |= {
            cfg.local_date(orders[0]["created_at"])[:7] + "-01" for orders in new_hist.values()
        }
    for order in previous.orders + current.orders:
        if order["order_id"] in affected_orders or order.get("customer_id") in affected_customers:
            day = cfg.local_date(order["created_at"])
            if day < cfg.local_date(policy.as_of):
                daily.add(day)
    fact_days = days_between(policy.report_from, policy.report_to)
    for fact in changes(previous.events, current.events, "fact_id"):
        day = cfg.local_date(fact["occurred_at"])
        if day < cfg.local_date(policy.as_of):
            fact_days.add(day)
    scopes: dict[str, set[str] | None] = {m: set(daily) for m in DATE_FIELDS}
    scopes["analytics_funnel_daily"] = fact_days
    for m in ("analytics_customer_metrics", "analytics_customer_purchase_sequence"):
        scopes[m] = affected_customers
    for m in ("analytics_cohorts", "analytics_purchase_distribution"):
        scopes[m] = cohort_months
    # Expand dependency closure: complete customer history and entire affected cohorts,
    # plus every customer buying on daily slices, not just the changed order/customer.
    required = set(affected_customers)
    required |= {
        cid
        for cid, orders in new_hist.items()
        if cfg.local_date(orders[0]["created_at"])[:7] + "-01" in cohort_months
    }
    required |= {
        o["customer_id"]
        for o in current.orders
        if o.get("customer_id") and cfg.local_date(o["created_at"]) in daily
    }
    return Plan(scopes, required, daily | fact_days, cohort_months, False)


def calculate(
    policy: AnalyticsPolicy, snapshot: CoreSnapshot, plan: Plan
) -> tuple[dict[str, list[Row]], list[Row], int]:
    cfg = policy.reference()
    if plan.full:
        orders, customers, items, events = (
            snapshot.orders,
            snapshot.customers,
            snapshot.items,
            snapshot.events,
        )
    else:
        orders = [
            o
            for o in snapshot.orders
            if o.get("customer_id") in plan.source_customers
            or cfg.local_date(o["created_at"]) in (plan.scopes["analytics_store_daily"] or set())
        ]
        ids = {o["order_id"] for o in orders}
        customers = [
            c
            for c in snapshot.customers
            if c["customer_id"] in {o.get("customer_id") for o in orders}
        ]
        items = [i for i in snapshot.items if i.get("order_id") in ids]
        events = [
            e
            for e in snapshot.events
            if cfg.local_date(e["occurred_at"]) in (plan.scopes["analytics_funnel_daily"] or set())
        ]
    effective = replace(
        cfg,
        report_from=min(plan.days),
        report_to=(date.fromisoformat(max(plan.days)) + timedelta(days=1)).isoformat(),
    )
    output = build(effective, orders=orders, customers=customers, items=items, events=events)
    encoded = encode_tables(output["tables"])
    selected = {m: [r for r in rows if plan.contains(m, r)] for m, rows in encoded.items()}
    return selected, output["quality"], sum(map(len, (orders, customers, items, events)))


class SQLiteAnalyticsSink:
    """Test-only publication adapter: one transaction for all seven slices + receipt.

    No source rows are stored here. IDs only exist in analytic output, not logs.
    Concurrency uses compare-and-swap on a store/policy generation.
    """

    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS analytics_rows(model TEXT,store TEXT,policy TEXT,key TEXT,body TEXT,PRIMARY KEY(model,store,policy,key));
          CREATE TABLE IF NOT EXISTS analytics_heads(store TEXT,policy TEXT,generation INTEGER,revision TEXT,config TEXT,PRIMARY KEY(store,policy));
          CREATE TABLE IF NOT EXISTS analytics_receipts(execution TEXT PRIMARY KEY,body TEXT);
        """)

    def close(self) -> None:
        self.db.close()

    def rows(self, model: str, store: str, policy_hash: str) -> list[Row]:
        if model not in SCHEMAS:
            raise ValueError("invalid_analytics_model")
        return [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT body FROM analytics_rows WHERE model=? AND store=? AND policy=? ORDER BY key",
                (model, store, policy_hash),
            )
        ]

    def head(self, policy: AnalyticsPolicy) -> tuple[int, str, AnalyticsPolicy] | None:
        row = self.db.execute(
            "SELECT generation,revision,config FROM analytics_heads WHERE store=? AND policy=?",
            (policy.store_id, policy.policy_hash),
        ).fetchone()
        return (row[0], row[1], AnalyticsPolicy.from_dict(json.loads(row[2]))) if row else None

    def receipt(self, execution: str) -> Row | None:
        row = self.db.execute(
            "SELECT body FROM analytics_receipts WHERE execution=?", (execution,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def publish(
        self,
        execution: str,
        policy: AnalyticsPolicy,
        snapshot: CoreSnapshot,
        plan: Plan,
        tables: dict[str, list[Row]],
        generation: int,
    ) -> Row:
        report: Row = {
            "execution_id": execution,
            "policy_hash": policy.policy_hash,
            "status": "completed",
            "models": {},
        }
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            saved = self.receipt(execution)
            if saved:
                return saved
            head = self.head(policy)
            if (head[0] if head else 0) != generation:
                raise ValueError("analytics_concurrent_publication_retry")
            for model, rows in tables.items():
                old = {
                    r["row_key"]: r
                    for r in self.rows(model, policy.store_id, policy.policy_hash)
                    if plan.contains(model, r)
                }
                new = {r["row_key"]: r for r in rows}
                if len(new) != len(rows):
                    raise ValueError("analytics_materialization_duplicate_key")
                if any(
                    r["store_id"] != policy.store_id
                    or r["policy_hash"] != policy.policy_hash
                    or not plan.contains(model, r)
                    for r in rows
                ):
                    raise ValueError("policy_hash_mismatch")
                for key in old.keys() - new.keys():
                    self.db.execute(
                        "DELETE FROM analytics_rows WHERE model=? AND store=? AND policy=? AND key=?",
                        (model, policy.store_id, policy.policy_hash, key),
                    )
                for key, row in new.items():
                    self.db.execute(
                        "INSERT OR REPLACE INTO analytics_rows VALUES(?,?,?,?,?)",
                        (model, policy.store_id, policy.policy_hash, key, canonical(row)),
                    )
                report["models"][model] = {
                    "rows_generated": len(rows),
                    "rows_inserted": len(new.keys() - old.keys()),
                    "rows_updated": sum(old[k] != new[k] for k in old.keys() & new.keys()),
                    "rows_deleted": len(old.keys() - new.keys()),
                    "rows_failed": 0,
                    "bytes_processed": None,
                }
                self.after_model(model)  # injectable fault point used only by tests
            self.db.execute(
                "INSERT OR REPLACE INTO analytics_heads VALUES(?,?,?,?,?)",
                (
                    policy.store_id,
                    policy.policy_hash,
                    generation + 1,
                    snapshot.revision,
                    canonical(policy.to_dict()),
                ),
            )
            self.db.execute(
                "INSERT INTO analytics_receipts VALUES(?,?)", (execution, canonical(report))
            )
        return report

    def after_model(self, model: str) -> None:
        pass


def run(
    policy: AnalyticsPolicy | None,
    current: CoreSnapshot,
    sink: SQLiteAnalyticsSink,
    *,
    previous: CoreSnapshot | None = None,
    full_refresh: bool = False,
) -> Row:
    if policy is None:
        raise ValueError("policy_missing")
    current = current.scoped(policy)
    execution = digest([policy.to_dict(), current.revision, full_refresh])
    if cached := sink.receipt(execution):
        return cached
    head = sink.head(policy)
    metadata = {
        "run_id": execution,
        "store_id": policy.store_id,
        "policy_hash": policy.policy_hash,
        "report_from": policy.report_from,
        "report_to": policy.report_to,
        "as_of": policy.as_of,
    }
    event("analytics_execution_started", **metadata)
    try:
        if head and instant(policy.as_of) < instant(head[2].as_of):
            raise ValueError("analytics_model_stale")
        if head and not full_refresh:
            if previous is None or previous.scoped(policy).revision != head[1]:
                raise ValueError("analytics_previous_snapshot_required")
        plan = plan_changes(
            policy,
            current,
            None if full_refresh else previous.scoped(policy) if previous else None,
            head[2] if head else None,
        )
        if full_refresh and head:
            # Explicit rebuild also covers previously published daily partitions.
            for model in DATE_FIELDS:
                dates = {
                    r[DATE_FIELDS[model]]
                    for r in sink.rows(model, policy.store_id, policy.policy_hash)
                }
                plan.scopes[model] = (plan.scopes[model] or set()) | dates
                plan.days |= dates
        for model in SCHEMAS:
            event("analytics_model_started", model=model, **metadata)
        tables, findings, read = calculate(policy, current, plan)
        for code in ([] if policy.history_complete else ["history_coverage_unknown"]) + (
            [] if policy.currency else ["currency_missing"]
        ):
            findings.append({"rule_id": code, "severity": "warning", "failed_count": 1})
        for finding in findings:
            event("analytics_quality", **finding, **metadata)
        # Validate complete selected customer sequences and all proposed grains.
        if any(q["severity"] == "blocking" for q in validate_outputs(tables)):
            raise ValueError("analytics_materialization_quality_failed")
        report = sink.publish(execution, policy, current, plan, tables, head[0] if head else 0)
        for model, stats in report["models"].items():
            event("analytics_model_finished", model=model, **stats, **metadata)
        event(
            "analytics_execution_finished",
            status="completed",
            rows_read=read,
            rows_generated=sum(len(r) for r in tables.values()),
            rows_inserted=sum(m["rows_inserted"] for m in report["models"].values()),
            rows_updated=sum(m["rows_updated"] for m in report["models"].values()),
            rows_failed=0,
            bytes_processed=None,
            **metadata,
        )
        return report
    except Exception:
        event(
            "analytics_execution_finished",
            status="failed",
            rows_failed=None,
            bytes_processed=None,
            **metadata,
        )
        raise
