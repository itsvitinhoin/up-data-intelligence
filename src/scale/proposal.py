"""Executable design only: no clients, storage, credentials or live activation."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from src.utils.data import digest


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime


def fast_window(
    initial: datetime, completed_to: datetime | None, at: datetime, *, safety_margin: timedelta
) -> Window | None:
    # Margin is explicitly supplied, not an undocumented completeness guarantee.
    if safety_margin < timedelta(0) or any(t.tzinfo is None for t in (initial, at)):
        raise ValueError("explicit_aware_times_and_nonnegative_margin_required")
    start = max(initial, completed_to or initial)
    end = at - safety_margin
    return Window(start, end) if end > start else None


def reconciliation_window(initial: datetime, at: datetime, *, lookback: timedelta) -> Window:
    if lookback <= timedelta(0) or at <= initial:
        raise ValueError("invalid_reconciliation_window")
    return Window(max(initial, at - lookback), at)


@dataclass(frozen=True)
class Work:
    store: str
    source: str
    mode: Literal["fast", "reconcile"]
    window: Window


@dataclass
class Admission:
    """In-memory single-dispatcher model; production needs atomic durable reservations."""

    global_limit: int
    source_limits: dict[str, int]
    active: dict[str, Work] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.global_limit < 1 or any(n < 1 for n in self.source_limits.values()):
            raise ValueError("positive_concurrency_required")

    def acquire(self, work: Work) -> bool:
        if work.source not in self.source_limits:
            raise ValueError("source_limit_required")
        if work.store in self.active or len(self.active) >= self.global_limit:
            return False
        if (
            sum(w.source == work.source for w in self.active.values())
            >= self.source_limits[work.source]
        ):
            return False
        self.active[work.store] = work
        return True

    def release(self, work: Work) -> None:
        if self.active.get(work.store) != work:
            raise ValueError("lease_owner_mismatch")
        del self.active[work.store]


@dataclass
class Budget:
    """Reservation model; reserve before IO. No refund for ambiguous failures."""

    byte_limit: int
    page_limit: int
    reserved_bytes: int = 0
    reserved_pages: int = 0
    state: str = "ready"

    def reserve(self, byte_ceiling: int, pages: int) -> bool:
        if min(self.byte_limit, self.page_limit, byte_ceiling, pages) < 0:
            raise ValueError("negative_budget")
        if (
            self.reserved_bytes + byte_ceiling > self.byte_limit
            or self.reserved_pages + pages > self.page_limit
        ):
            self.state = "deferred_budget_alert_required"
            return False
        self.reserved_bytes += byte_ceiling
        self.reserved_pages += pages
        return True


def safe_job_labels(store: str, component: str, resource: str, run: str) -> dict[str, str]:
    """Proposed BigQuery labels: bounded hashes, never customer IDs or arbitrary text."""
    if component not in {"ingestion", "quality", "analytics"} or resource not in {
        "analytics_facts",
        "orders",
        "customers",
        "all",
    }:
        raise ValueError("label_not_allowlisted")
    return {
        "store": digest(store)[:32],
        "component": component,
        "resource": resource,
        "run": digest(run)[:32],
    }


@dataclass(frozen=True)
class Fact:
    store: str
    fact_id: str
    at: datetime
    order_id: str | None
    invalid_parser: bool = False


def links(facts: list[Fact], orders: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    return {
        (f.store, f.fact_id): "missing_order_id"
        if f.order_id is None
        else "matched"
        if (f.store, f.order_id) in orders
        else "pending"
        for f in facts
    }


def affected_facts(
    facts: list[Fact],
    store: str,
    changed_facts: set[str],
    changed_orders: set[str],
    pending: set[str],
) -> list[Fact]:
    return [
        f
        for f in facts
        if f.store == store
        and (f.fact_id in changed_facts or f.order_id in changed_orders or f.fact_id in pending)
    ]


def quality(facts: list[Fact], store: str, affected: set[str] | None = None) -> dict[str, int]:
    # All historical peers for affected IDs, not just recent rows: duplicates survive scope.
    rows = [f for f in facts if f.store == store and (affected is None or f.fact_id in affected)]
    counts = Counter(f.fact_id for f in rows)
    return {
        "duplicate_facts": sum(n - 1 for n in counts.values()),
        "invalid_meta_parser": sum(f.invalid_parser for f in rows),
    }


@dataclass
class ShadowStore:
    """Synthetic transaction oracle; NOT a replacement for the production Engine."""

    core: dict[tuple[str, str], Fact] = field(default_factory=dict)
    completed: dict[str, datetime] = field(default_factory=dict)
    evidence: list[tuple[str, str, int]] = field(default_factory=list)

    def run(self, work: Work, source: list[Fact], *, budget: Budget, fail: bool = False) -> bool:
        rows = [
            f
            for f in source
            if f.store == work.store and work.window.start <= f.at < work.window.end
        ]
        if not budget.reserve(len(rows) * 100, 1) or fail:
            return False  # durable production pending interval must remain queued
        self.core.update({(f.store, f.fact_id): f for f in rows})
        self.evidence.append((work.store, work.mode, len(rows)))
        if work.mode == "fast":
            self.completed[work.store] = work.window.end
        return True
