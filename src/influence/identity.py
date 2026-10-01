"""Shared, temporal Customer→Fact resolver. No global identity union or fuzzy joins."""

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from src.analytics.engine import Row, instant
from src.utils.data import canonical, digest


def value(row: Mapping[str, Any], field: str) -> str | None:
    v = row.get(field)
    return v if isinstance(v, str) and v.strip() else None


def user_link(fact: Row, links: Iterable[Mapping[str, Any]]) -> str | None:
    for link in sorted(links, key=lambda r: str(r.get("link_id"))):
        if (
            link.get("source_fact_id") == fact["fact_id"]
            and value(fact, "version_id") is not None
            and link.get("source_version_id") == fact["version_id"]
            and link.get("confidence_type") == "DETERMINISTIC"
            and link.get("evidence_type") == "observed_cooccurrence"
            and link.get("left_namespace") == "session_id"
            and value(fact, "session_id") is not None
            and link.get("left_id") == fact["session_id"]
            and link.get("right_namespace") == "user_id"
            and value(fact, "user_id") is not None
            and link.get("right_id") == fact["user_id"]
            and link.get("occurred_at") is not None
            and instant(link["occurred_at"]) == instant(fact["occurred_at"])
        ):
            return value(link, "link_id")
    return None


@dataclass(frozen=True)
class Resolution:
    customer_id: str | None
    confidence_type: str | None
    paths: list[Row]
    reason: str


class AnchorIndex(Protocol):
    maximum_path_bytes: int | None

    def add(self, anchor: Row) -> None: ...
    def find(self, field: str, token: str, kind: str) -> Iterator[Row]: ...
    def owner_count(self, field: str, token: str) -> int: ...
    def seal(self) -> None: ...


class MemoryAnchors:
    maximum_path_bytes: int | None = None

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], list[Row]] = defaultdict(list)
        self.owners: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.sealed = False

    def add(self, anchor: Row) -> None:
        if self.sealed:
            raise ValueError("identity_context_is_immutable")
        for field in ("session_id", "visitor_id", "user_id"):
            if token := value(anchor["fact"], field):
                self.rows[field, token].append(deepcopy(anchor))
                self.owners[field, token].add(anchor["customer"])

    def find(self, field: str, token: str, kind: str) -> Iterator[Row]:
        return (deepcopy(a) for a in self.rows.get((field, token), []) if a["kind"] == kind)

    def owner_count(self, field: str, token: str) -> int:
        return len(self.owners.get((field, token), set()))

    def seal(self) -> None:
        self.sealed = True


@dataclass(frozen=True)
class IdentityContext:
    customers: frozenset[str]
    orders: Mapping[str, Mapping[str, Any]]
    links: Mapping[str, tuple[Mapping[str, Any], ...]]
    index: AnchorIndex

    @classmethod
    def build(
        cls,
        customers: list[Row],
        orders: list[Row],
        links: list[Row],
        anchors: Iterable[Row],
        *,
        index: AnchorIndex | None = None,
    ) -> "IdentityContext":
        cids = frozenset(c["customer_id"] for c in customers)
        grouped: dict[str, list[Row]] = defaultdict(list)
        for link in links:
            if link.get("source_fact_id"):
                grouped[link["source_fact_id"]].append(deepcopy(link))
        context = cls(
            cids,
            MappingProxyType(
                {
                    o["order_id"]: MappingProxyType(deepcopy(o))
                    for o in orders
                    if o.get("customer_id") in cids
                }
            ),
            MappingProxyType(
                {k: tuple(MappingProxyType(v) for v in rows) for k, rows in grouped.items()}
            ),
            index if index is not None else MemoryAnchors(),
        )
        for fact in anchors:
            _, anchor = context.explicit(fact)
            if anchor is not None:
                context.index.add(anchor)
        context.index.seal()
        return context

    def user_evidence(self, fact: Row) -> str | None:
        return user_link(fact, list(self.links.get(fact["fact_id"], ())))

    def explicit(self, fact: Row) -> tuple[Resolution | None, Row | None]:
        fid, oid = fact["fact_id"], value(fact, "order_id")
        if oid:
            order = self.orders.get(oid)
            if order is None:
                return Resolution(None, None, [], "explicit_order_unresolved"), None
            path = {
                "via": "order_id",
                "anchor_fact_id": fid,
                "anchor_fact_version_id": fact.get("version_id"),
                "anchor_at": fact["occurred_at"],
                "anchor_order_id": oid,
                "customer_id": order["customer_id"],
                "order_version_id": order.get("version_id"),
                "identity_link_ids": [],
            }
            resolution = Resolution(order["customer_id"], "DIRECT", [path], "explicit_order")
            anchor = {
                "fact": fact,
                "customer": order["customer_id"],
                "kind": "purchase",
                "path": path,
            }
            return resolution, anchor if fact.get("event_name") in {
                "purchase",
                "purchase_item",
            } and instant(fact["occurred_at"]) >= instant(order["created_at"]) else None
        if fact.get("event_name") != "register_approved":
            return None, None
        verified = [
            link
            for link in self.links.get(fid, ())
            if value(fact, "version_id") is not None
            and link.get("source_version_id") == fact["version_id"]
            and link.get("confidence_type") == "DETERMINISTIC"
            and link.get("evidence_type") == "observed_registration_customer"
            and link.get("left_namespace") == "fact_id"
            and link.get("left_id") == fid
            and link.get("right_namespace") == "customer_id"
            and link.get("right_id") in self.customers
            and link.get("occurred_at") is not None
            and instant(link["occurred_at"]) == instant(fact["occurred_at"])
        ]
        ids = {link["right_id"] for link in verified}
        if len(ids) > 1:
            return Resolution(None, None, [], "ambiguous_registration"), None
        if not ids:
            return None, None
        cid = next(iter(ids))
        path = {
            "via": "register_approved",
            "anchor_fact_id": fid,
            "anchor_fact_version_id": fact["version_id"],
            "anchor_at": fact["occurred_at"],
            "anchor_order_id": None,
            "customer_id": cid,
            "identity_link_ids": sorted(link["link_id"] for link in verified),
        }
        return Resolution(cid, "CUSTOMER_JOURNEY", [path], "explicit_registration"), {
            "fact": fact,
            "customer": cid,
            "kind": "registration",
            "path": path,
        }

    def resolve_event(self, fact: Row) -> Resolution:
        explicit, _ = self.explicit(fact)
        if explicit is not None:
            return explicit

        # Determine ambiguity before allocating paths; an ambiguous journey stays unresolved.
        for kind in ("registration", "purchase"):
            customers = set()
            for cid, path in self.temporal_matches(fact, kind):
                if path is None:
                    return Resolution(None, None, [], "ambiguous_temporal_identity")
                customers.add(cid)
                if len(customers) > 1:
                    return Resolution(None, None, [], "ambiguous_temporal_identity")
            if not customers:
                continue
            paths = []
            size = 2
            for _, path in self.temporal_matches(fact, kind):
                assert path is not None
                size += len(canonical(path).encode()) + 1
                if (
                    self.index.maximum_path_bytes is not None
                    and size > self.index.maximum_path_bytes
                ):
                    raise ValueError("intelligence_row_too_large")
                paths.append(path)
            paths.sort(key=digest)
            level = (
                "DIRECT"
                if any(
                    p["via"] == "session_id" and p.get("anchor_kind") == "purchase" for p in paths
                )
                else "SUPPORTED"
                if all(p["via"] == "user_id" for p in paths)
                else "CUSTOMER_JOURNEY"
            )
            return Resolution(next(iter(customers)), level, paths, "temporal_" + kind)
        return Resolution(None, None, [], "insufficient_evidence")

    def temporal_matches(self, fact: Row, kind: str) -> Iterator[tuple[str, Row | None]]:
        for field in ("session_id", "visitor_id", "user_id"):
            if kind == "registration" and field == "user_id":
                continue
            token = value(fact, field)
            if token is None:
                continue
            for anchor_row in self.index.find(field, token, kind):
                anchor = anchor_row["fact"]
                if instant(fact["occurred_at"]) >= instant(anchor["occurred_at"]):
                    continue
                if kind == "purchase" and instant(fact["occurred_at"]) >= instant(
                    self.orders[anchor["order_id"]]["created_at"]
                ):
                    continue
                support = (
                    [self.user_evidence(fact), self.user_evidence(anchor)]
                    if field == "user_id"
                    else []
                )
                if field == "user_id" and not all(support):
                    continue
                if self.index.owner_count(field, token) != 1:
                    yield anchor_row["customer"], None
                    continue
                yield (
                    anchor_row["customer"],
                    {
                        **anchor_row["path"],
                        "via": field,
                        "anchor_kind": kind,
                        "identity_link_ids": anchor_row["path"]["identity_link_ids"] + support,
                        "event_fact_id": fact["fact_id"],
                        "event_version_id": fact.get("version_id"),
                    },
                )


def resolve_event(context: IdentityContext, fact: Row) -> Resolution:
    return context.resolve_event(fact)


def resolve(
    events: list[Row], orders: list[Row], customers: list[Row], links: list[Row]
) -> dict[str, Resolution]:
    """Compatible bounded reference API over the same incremental identity context."""
    context = IdentityContext.build(customers, orders, links, events)
    return {f["fact_id"]: context.resolve_event(f) for f in events}
