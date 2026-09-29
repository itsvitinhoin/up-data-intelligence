"""Bounded Fact transport, day closure, and disk-backed ordered funnel reduction.

Only the final daily aggregates leave this component. No publication takes place.
"""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from src.analytics.engine import Row, instant, ratio, stamped
from src.analytics.policy import Policy


class FactSpool:
    """Private execution-local staging. Primary key catches duplicates across days/leaves.

    Keep every projected field; normalized sort timestamp is additional metadata.
    The day index supplies session/time/fact ordering without a Python event list.
    """

    def __init__(self, path: Path, policy: Policy, *, maximum_bytes: int = 512 * 1024 * 1024):
        self.policy = policy
        self.maximum_bytes = maximum_bytes
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.executescript("""
            PRAGMA cache_size=-2048;
            PRAGMA temp_store=FILE;
            CREATE TABLE facts (
                fact_id TEXT PRIMARY KEY,store_id TEXT,source_system TEXT,
                session_id TEXT,event_name TEXT,occurred_at TEXT,
                day TEXT,session_key TEXT,sort_at TEXT
            );
            CREATE INDEX day_session ON facts(day,session_key,sort_at,fact_id);
        """)
        self.rows = 0
        self.completed_days: set[str] = set()

    def close(self) -> None:
        self.db.close()

    def add(self, day: str, rows: list[Row]) -> None:
        if day in self.completed_days:
            raise ValueError("analytics_fact_day_already_closed")

        def values() -> Iterable[tuple[object, ...]]:
            for row in rows:
                if (
                    row.get("store_id") != self.policy.store_id
                    or row.get("source_system") != "upzero"
                ):
                    raise ValueError("source_store_mismatch")
                fact = row.get("fact_id")
                if not isinstance(fact, str) or not fact.strip():
                    raise ValueError("invalid_fact_key")
                at = row["occurred_at"]
                if self.policy.local_date(at) != day or instant(at) >= instant(self.policy.as_of):
                    raise ValueError("analytics_fact_day_mismatch")
                session = row.get("session_id")
                if session is not None and not isinstance(session, str):
                    raise ValueError("analytics_fact_session_type")
                yield (
                    fact,
                    row["store_id"],
                    row["source_system"],
                    session,
                    row.get("event_name"),
                    at,
                    day,
                    session if session and session.strip() else None,
                    instant(at).isoformat(timespec="microseconds"),
                )

        try:
            with self.db:
                self.db.executemany("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?)", values())
                size = (
                    self.db.execute("PRAGMA page_count").fetchone()[0]
                    * self.db.execute("PRAGMA page_size").fetchone()[0]
                )
                if size > self.maximum_bytes:
                    raise ValueError("analytics_fact_spool_budget_exceeded")
        except sqlite3.IntegrityError:
            raise ValueError("duplicate_fact") from None
        self.rows += len(rows)

    def finish_day(self, day: str, expected: int) -> Row:
        actual = self.db.execute("SELECT COUNT(*) FROM facts WHERE day=?", (day,)).fetchone()[0]
        if actual != expected or day in self.completed_days:
            raise ValueError("analytics_fact_day_incomplete")
        self.completed_days.add(day)
        counts = dict.fromkeys(
            (
                "sessions",
                "product_views",
                "add_to_cart",
                "checkout_started",
                "purchase",
                "sessions_with_cart",
                "sessions_cart_then_checkout",
                "sessions_cart_checkout_purchase",
                "sessions_with_purchase",
                "events_without_session",
            ),
            0,
        )
        last = None
        cart = checkout = purchased = converted = False

        def finish_session() -> None:
            counts["sessions_with_cart"] += int(cart)
            counts["sessions_cart_then_checkout"] += int(checkout)
            counts["sessions_cart_checkout_purchase"] += int(purchased)
            counts["sessions_with_purchase"] += int(converted)

        # The entire session-day is present and sorted, even when a session crossed leaves.
        for session, name in self.db.execute(
            "SELECT session_key,event_name FROM facts WHERE day=? ORDER BY session_key,sort_at,fact_id",
            (day,),
        ):
            counter = {
                "product_view": "product_views",
                "add_to_cart": "add_to_cart",
                "checkout_started": "checkout_started",
                "purchase": "purchase",
            }.get(name)
            if counter:
                counts[counter] += 1
            if session is None:
                counts["events_without_session"] += 1
                continue
            if session != last:
                if last is not None:
                    finish_session()
                counts["sessions"] += 1
                last = session
                cart = checkout = purchased = converted = False
            if name == "add_to_cart":
                cart = True
            if name == "checkout_started" and cart:
                checkout = True
            if name == "purchase":
                converted = True
                if checkout:
                    purchased = True
        if last is not None:
            finish_session()

        def rate(numerator: str, denominator: str) -> object:
            return (
                ratio(counts[numerator], counts[denominator])
                if self.policy.facts_complete
                else None
            )

        return stamped(
            self.policy,
            ["funnel", day],
            event_date=day,
            **counts,
            observation_complete=self.policy.facts_complete,
            session_to_cart_rate=rate("sessions_with_cart", "sessions"),
            cart_to_checkout_rate=rate("sessions_cart_then_checkout", "sessions_with_cart"),
            checkout_to_purchase_rate=rate(
                "sessions_cart_checkout_purchase", "sessions_cart_then_checkout"
            ),
            session_conversion_rate=rate("sessions_with_purchase", "sessions"),
            cost_per_session=None,
            cost_per_add_to_cart=None,
            cost_per_checkout=None,
        )
