"""Bounded process-local aggregate cache. Never stores authorization or entity rows.

Publication is freshly resolved before every lookup. CORE-backed aggregates expire
after 30 seconds even if the Analytics generation stays unchanged. Replicas may miss
independently; this cache is an optimization, never a publication authority.
"""

from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from threading import Lock
from time import monotonic
from typing import Any

from src.dashboard.contracts import Publication
from src.dashboard.queries import Query
from src.utils.data import digest

RESOURCES = frozenset(
    {
        "overview_details",
        "retention_details",
        "customer_period",
        "funnel_daily",
        "retention_exact_stages",
    }
)
PRIVATE_FIELDS = frozenset(
    "customer_id order_id fact_id user_id session_id visitor_id name trade_name company_name cpf cnpj email phone document address payload raw credential token secret_resource_name identity_path".split()
)


def aggregate_only(value: Any) -> bool:
    if isinstance(value, dict):
        return not PRIVATE_FIELDS.intersection(value) and all(
            aggregate_only(child) for child in value.values()
        )
    if isinstance(value, (list, tuple)):
        return all(aggregate_only(child) for child in value)
    return True


def cache_key(
    project: str,
    workspace: tuple[str, str, str, str],
    publication: Publication,
    query: Query,
    coverage: tuple[bool, bool],
) -> str | None:
    tenant, operation_id, store, operation = workspace
    if (
        query.name not in RESOURCES
        or not tenant
        or not operation_id
        or operation != "B2B"
        or store != publication.store_id
    ):
        return None
    identity = asdict(publication)
    # Query read clock changes each request. The certified publication identity,
    # scope, policy, selected period and TTL determine reuse, never a caller clock.
    identity.pop("snapshot_at")
    parameters = {k: v for k, v in query.parameters.items() if k != "snapshot_at"}
    return digest([project, workspace, identity, coverage, query.name, query.sql, parameters])


class AggregateCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 30,
        max_entries: int = 128,
        max_bytes: int = 16 * 1024 * 1024,
        clock: Callable[[], float] = monotonic,
    ):
        if ttl_seconds <= 0 or max_entries < 1 or max_bytes < 1:
            raise ValueError("aggregate_cache_limits_invalid")
        self.ttl, self.max_entries, self.max_bytes, self.clock = (
            ttl_seconds,
            max_entries,
            max_bytes,
            clock,
        )
        self.entries: OrderedDict[str, tuple[float, list[dict[str, Any]], int]] = OrderedDict()
        self.bytes = 0
        self.lock = Lock()

    def get(self, key: str) -> list[dict[str, Any]] | None:
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            if self.clock() - entry[0] >= self.ttl:
                self.bytes -= self.entries.pop(key)[2]
                return None
            self.entries.move_to_end(key)
            return deepcopy(entry[1])

    def put(self, key: str, rows: list[dict[str, Any]]) -> None:
        if not aggregate_only(rows):
            return
        size = len(repr(rows).encode())
        if size > self.max_bytes:
            return
        with self.lock:
            previous = self.entries.pop(key, None)
            if previous:
                self.bytes -= previous[2]
            self.entries[key] = (self.clock(), deepcopy(rows), size)
            self.bytes += size
            while len(self.entries) > self.max_entries or self.bytes > self.max_bytes:
                self.bytes -= self.entries.popitem(last=False)[1][2]
