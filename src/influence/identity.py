"""Shared, temporal Customer→Fact resolver. No global identity union or fuzzy joins."""

from collections import defaultdict
from dataclasses import dataclass

from src.analytics.engine import Row, instant
from src.utils.data import digest


def value(row: Row, field: str) -> str | None:
    v = row.get(field)
    return v if isinstance(v, str) and v.strip() else None


def user_link(fact: Row, links: list[Row]) -> str | None:
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


def resolve(
    events: list[Row], orders: list[Row], customers: list[Row], links: list[Row]
) -> dict[str, Resolution]:
    """Inputs already scoped/unique to one store and observation cutoff by the caller."""
    cids = {c["customer_id"] for c in customers}
    order_map = {o["order_id"]: o for o in orders if o.get("customer_id") in cids}
    known: dict[str, Resolution] = {}
    registration: dict[str, list[Row]] = defaultdict(list)
    for link in links:
        if link.get("source_fact_id"):
            registration[link["source_fact_id"]].append(link)
    anchors: list[Row] = []
    for fact in events:
        fid = fact["fact_id"]
        oid = value(fact, "order_id")
        if oid:
            order = order_map.get(oid)
            if order is None:
                known[fid] = Resolution(None, None, [], "explicit_order_unresolved")
                continue
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
            known[fid] = Resolution(order["customer_id"], "DIRECT", [path], "explicit_order")
            if fact.get("event_name") in {"purchase", "purchase_item"} and instant(
                fact["occurred_at"]
            ) >= instant(order["created_at"]):
                anchors.append(
                    {
                        "fact": fact,
                        "customer": order["customer_id"],
                        "kind": "purchase",
                        "path": path,
                    }
                )
            continue
        if fact.get("event_name") != "register_approved":
            continue
        # Optional evidence contract; current Foundation does NOT manufacture this link.
        verified = [
            link
            for link in registration[fid]
            if value(fact, "version_id") is not None
            and link.get("source_version_id") == fact["version_id"]
            and link.get("confidence_type") == "DETERMINISTIC"
            and link.get("evidence_type") == "observed_registration_customer"
            and link.get("left_namespace") == "fact_id"
            and link.get("left_id") == fid
            and link.get("right_namespace") == "customer_id"
            and link.get("right_id") in cids
            and link.get("occurred_at") is not None
            and instant(link["occurred_at"]) == instant(fact["occurred_at"])
        ]
        ids = {link["right_id"] for link in verified}
        if len(ids) == 1:
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
            known[fid] = Resolution(cid, "CUSTOMER_JOURNEY", [path], "explicit_registration")
            anchors.append({"fact": fact, "customer": cid, "kind": "registration", "path": path})
        elif len(ids) > 1:
            known[fid] = Resolution(None, None, [], "ambiguous_registration")
    index: dict[tuple[str, str], list[Row]] = defaultdict(list)
    owners: dict[tuple[str, str], set[str]] = defaultdict(set)
    for a in anchors:
        for field in ("session_id", "visitor_id", "user_id"):
            if token := value(a["fact"], field):
                index[field, token].append(a)
                owners[field, token].add(a["customer"])
    user_evidence = {f["fact_id"]: user_link(f, links) for f in events}
    result = dict(known)
    for fact in events:
        if fact["fact_id"] in result:
            continue
        # Registration precedence, then purchase-supported temporal journey.
        result[fact["fact_id"]] = Resolution(None, None, [], "insufficient_evidence")
        for kind in ("registration", "purchase"):
            candidates: dict[str, list[Row]] = defaultdict(list)
            conflict = False
            for field in ("session_id", "visitor_id", "user_id"):
                if kind == "registration" and field == "user_id":
                    continue
                token = value(fact, field)
                if token is None:
                    continue
                for a in index[field, token]:
                    anchor = a["fact"]
                    if a["kind"] != kind or instant(fact["occurred_at"]) >= instant(
                        anchor["occurred_at"]
                    ):
                        continue
                    if kind == "purchase" and instant(fact["occurred_at"]) >= instant(
                        order_map[anchor["order_id"]]["created_at"]
                    ):
                        continue
                    support = (
                        [user_evidence[fact["fact_id"]], user_evidence[anchor["fact_id"]]]
                        if field == "user_id"
                        else []
                    )
                    if field == "user_id" and not all(support):
                        continue
                    if len(owners[field, token]) != 1:
                        conflict = True
                        continue
                    candidates[a["customer"]].append(
                        {
                            **a["path"],
                            "via": field,
                            "anchor_kind": kind,
                            "identity_link_ids": a["path"]["identity_link_ids"] + support,
                            "event_fact_id": fact["fact_id"],
                            "event_version_id": fact.get("version_id"),
                        }
                    )
            if conflict or len(candidates) > 1:
                result[fact["fact_id"]] = Resolution(None, None, [], "ambiguous_temporal_identity")
                break
            if candidates:
                cid = next(iter(candidates))
                paths = sorted(candidates[cid], key=digest)
                level = (
                    "DIRECT"
                    if any(
                        p["via"] == "session_id" and p.get("anchor_kind") == "purchase"
                        for p in paths
                    )
                    else "SUPPORTED"
                    if all(p["via"] == "user_id" for p in paths)
                    else "CUSTOMER_JOURNEY"
                )
                result[fact["fact_id"]] = Resolution(cid, level, paths, "temporal_" + kind)
                break
    return result
