"""One event pass, disk-backed touches/timeline/matches, unchanged three-scope rules."""

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator

from src.analytics.engine import Row, amount, instant, total
from src.analytics.policy import ORDER_STATUSES, Policy
from src.influence.engine import (
    RANK,
    Evidence,
    InfluenceScope,
    _media,
    _one,
    _timeline,
    paid_markers,
)
from src.influence.identity import IdentityContext
from src.intelligence.live.spool import PaidLookup, Spool, clock
from src.utils.data import canonical, digest, timestamp


def bounded(rows: Iterable[Row], ceiling: int = 32 * 1024 * 1024) -> list[Row]:
    result = []
    size = 2
    for row in rows:
        size += len(canonical(row).encode()) + 1
        if size > ceiling:
            raise ValueError("intelligence_row_too_large")
        result.append(row)
    return result


class InfluenceStream:
    def __init__(
        self,
        spool: Spool,
        policy: Policy,
        customers: list[Row],
        orders: list[Row],
        context: IdentityContext,
        calculated_at: str,
    ):
        self.spool, self.policy, self.context = spool, policy, context
        self.cids = {c["customer_id"] for c in customers}
        self.customers = customers
        self.orders = [o for o in orders if instant(o["created_at"]) < instant(policy.as_of)]
        if any(o.get("order_status") not in ORDER_STATUSES for o in self.orders):
            raise ValueError("unknown_order_status")
        self.base: Row = {
            "store_id": policy.store_id,
            "calculated_at": timestamp(calculated_at),
            "policy_hash": policy.key,
            "currency": policy.currency,
            "history_complete": policy.history_complete,
            "facts_complete": policy.facts_complete,
            "as_of": timestamp(policy.as_of),
        }
        self.commerce = {
            o["order_id"]: o
            for o in self.orders
            if o.get("customer_id") in self.cids and o["order_status"] in policy.purchase_statuses
        }
        self.by_customer: dict[str, list[Row]] = defaultdict(list)
        for o in self.commerce.values():
            self.by_customer[o["customer_id"]].append(o)
        self.sequence: dict[str, int] = {}
        self.previous: dict[str, str] = {}
        for orders_for_customer in self.by_customer.values():
            orders_for_customer.sort(key=lambda o: (instant(o["created_at"]), o["order_id"]))
            for i, o in enumerate(orders_for_customer):
                self.sequence[o["order_id"]] = i + 1
                if i:
                    self.previous[o["order_id"]] = orders_for_customer[i - 1]["created_at"]
        self.selected = self.resolved = self.unresolved_paid = 0

    def consume(self, fact: Row) -> None:
        p = self.policy
        if fact.get("store_id") != p.store_id or fact.get("source_system") != "upzero":
            raise ValueError("mixed_intelligence_store")
        if fact.get("observed_at") and instant(fact["observed_at"]) > instant(
            self.base["calculated_at"]
        ):
            raise ValueError("snapshot_observation_after_calculation")
        if instant(fact["occurred_at"]) >= instant(p.as_of):
            raise ValueError("intelligence_event_after_cutoff")
        self.selected += 1
        resolution = self.context.resolve_event(fact)
        timeline = _timeline(self.base, [fact], [], {fact["fact_id"]: resolution}, self.cids)
        for row in timeline:
            self.spool.put(
                "timeline",
                row,
                sorter=canonical([row["customer_id"], clock(row["occurred_at"]), row["row_key"]]),
            )
            self.resolved += 1
        markers = paid_markers(fact)
        if not markers:
            return
        touch = {
            **self.base,
            "row_key": digest([p.store_id, "paid-touch", fact["fact_id"]]),
            **{
                k: fact.get(k)
                for k in (
                    "fact_id",
                    "event_id",
                    "session_id",
                    "visitor_id",
                    "user_id",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                )
            },
            **_media(fact),
            "occurred_at": timestamp(fact["occurred_at"]),
            "touch_type": "PAID_TRACKING",
            "evidence_type": Evidence.SUPPORTED.value
            if resolution.reason == "explicit_order"
            else resolution.confidence_type,
            "paid_signal_types": markers,
            "identity_path": resolution.paths,
        }
        self.spool.put(
            "paid", touch, sorter=canonical([clock(touch["occurred_at"]), touch["fact_id"]])
        )
        if resolution.customer_id is None:
            self.unresolved_paid += 1
            return
        for o in self.by_customer[resolution.customer_id]:
            oid = o["order_id"]
            if not p.report_from <= p.local_date(o["created_at"]) < p.report_to or instant(
                fact["occurred_at"]
            ) >= instant(o["created_at"]):
                continue
            paths = []
            for path in resolution.paths:
                same_order = path.get("anchor_order_id") == oid
                if not same_order and instant(path["anchor_at"]) > instant(o["created_at"]):
                    continue
                level = (
                    Evidence.DIRECT
                    if same_order and path["via"] == "session_id"
                    else Evidence.SUPPORTED
                    if path["via"] in {"user_id", "order_id"}
                    else Evidence.CUSTOMER_JOURNEY
                )
                paths.append(
                    {
                        **path,
                        "level": level.value,
                        "paid_fact_id": fact["fact_id"],
                        "paid_fact_version_id": fact.get("version_id"),
                        "order_id": oid,
                    }
                )
            if not paths:
                continue
            best = min(paths, key=lambda row: (RANK[Evidence(row["level"])], digest(row)))
            for scope in InfluenceScope:
                if scope == InfluenceScope.ACQUISITION and self.sequence[oid] != 1:
                    continue
                if scope == InfluenceScope.REPEAT_PURCHASE and (
                    oid not in self.previous
                    or instant(fact["occurred_at"]) < instant(self.previous[oid])
                ):
                    continue
                self.spool.db.execute(
                    "INSERT INTO matches VALUES(?,?,?,?,?,?)",
                    (
                        scope.value,
                        oid,
                        canonical(touch["campaign_id"]),
                        fact["fact_id"],
                        clock(touch["occurred_at"]),
                        canonical(best),
                    ),
                )

    def finish(self, source_hash: str) -> Row:
        for row in _timeline(self.base, [], self.orders, {}, self.cids):
            self.spool.put(
                "timeline",
                row,
                sorter=canonical([row["customer_id"], clock(row["occurred_at"]), row["row_key"]]),
            )
        result = {}
        paid = PaidLookup(self.spool)
        common_hashes = {
            "analytics_paid_touchpoints": self.spool.rows("paid").content_hash(),
            "analytics_customer_timeline": self.spool.rows("timeline").content_hash(),
        }
        for scope in InfluenceScope:
            order_name, customer_name = "orders:" + scope.value, "customers:" + scope.value
            groups = self.spool.db.execute(
                "SELECT oid,campaign FROM matches WHERE scope=? GROUP BY oid,campaign ORDER BY oid,CASE WHEN campaign='null' THEN '' ELSE campaign END",
                (scope.value,),
            )
            for oid, encoded_campaign in groups:
                records = self.spool.db.execute(
                    "SELECT fact,data FROM matches WHERE scope=? AND oid=? AND campaign=? ORDER BY at,fact",
                    (scope.value, oid, encoded_campaign),
                )
                matches = bounded(
                    ({"touch": paid[fid], "path": json.loads(data)} for fid, data in records)
                )
                ts, paths = [m["touch"] for m in matches], [m["path"] for m in matches]
                campaign, o = json.loads(encoded_campaign), self.commerce[oid]
                row = {
                    **self.base,
                    "row_key": digest([self.policy.store_id, "order-paid", oid, campaign]),
                    "order_id": oid,
                    "customer_id": o["customer_id"],
                    "purchase_number": self.sequence[oid],
                    "influence_scope": scope.value,
                    "campaign_id": campaign,
                    "adset_id": _one(ts, "adset_id"),
                    "ad_id": _one(ts, "ad_id"),
                    "first_paid_touch_at": ts[0]["occurred_at"],
                    "last_paid_touch_at": ts[-1]["occurred_at"],
                    "touch_count": len(ts),
                    **{
                        k: amount(o.get(k))
                        for k in (
                            "requested_total",
                            "fulfilled_total",
                            "requested_items_qty",
                            "fulfilled_items_qty",
                        )
                    },
                    "evidence_type": min(
                        (Evidence(path["level"]) for path in paths), key=RANK.__getitem__
                    ).value,
                    "identity_path": paths,
                    "participating_ads": sorted(
                        [
                            {"adset_id": adset, "ad_id": ad}
                            for adset, ad in {(t["adset_id"], t["ad_id"]) for t in ts}
                        ],
                        key=digest,
                    ),
                }
                self.spool.put(order_name, row, sorter=canonical([oid, campaign or ""]))
            for c in sorted(self.customers, key=lambda r: r["customer_id"]):
                cid = c["customer_id"]
                selected = bounded(self.customer_orders(order_name, cid))
                ids = {r["order_id"] for r in selected}
                fact_ids = {path["paid_fact_id"] for r in selected for path in r["identity_path"]}
                ts = sorted(
                    (paid[fid] for fid in fact_ids),
                    key=lambda r: (instant(r["occurred_at"]), r["fact_id"]),
                )
                values = [self.commerce[oid] for oid in sorted(ids)]
                row = {
                    **self.base,
                    "row_key": digest([self.policy.store_id, "customer-paid", cid]),
                    "customer_id": cid,
                    "influence_scope": scope.value,
                    "paid_media_influenced": bool(ids),
                    "first_paid_touch_at": ts[0]["occurred_at"] if ts else None,
                    "last_paid_touch_at": ts[-1]["occurred_at"] if ts else None,
                    "paid_touch_count": len(ts),
                    **{
                        name: len({t[field] for t in ts if t[field] is not None})
                        for name, field in (
                            ("campaign_count", "campaign_id"),
                            ("adset_count", "adset_id"),
                            ("ad_count", "ad_id"),
                        )
                    },
                    "first_campaign_id": ts[0]["campaign_id"] if ts else None,
                    "last_campaign_id": ts[-1]["campaign_id"] if ts else None,
                    "influenced_orders": len(ids),
                    **{
                        name: total([o.get(field) for o in values])
                        for name, field in (
                            ("requested_revenue_influenced", "requested_total"),
                            ("fulfilled_revenue_influenced", "fulfilled_total"),
                            ("requested_quantity_influenced", "requested_items_qty"),
                            ("fulfilled_quantity_influenced", "fulfilled_items_qty"),
                        )
                    },
                    "evidence_type": min(
                        (Evidence(r["evidence_type"]) for r in selected), key=RANK.__getitem__
                    ).value
                    if selected
                    else None,
                    "identity_path": [path for r in selected for path in r["identity_path"]],
                }
                self.spool.put(customer_name, row)
            tables = {
                "analytics_paid_touchpoints": self.spool.rows("paid"),
                "analytics_customer_timeline": self.spool.rows("timeline"),
                "analytics_order_paid_influence": self.spool.rows(order_name),
                "analytics_customer_paid_influence": self.spool.rows(customer_name),
            }
            hashes = {
                n: common_hashes[n] if n in common_hashes else rows.content_hash()
                for n, rows in tables.items()
            }
            content = digest(hashes)
            receipt = {
                "layer_version": "influence-stream-v2",
                **self.base,
                "source_snapshot_hash": source_hash,
                "report_from": self.policy.report_from,
                "report_to": self.policy.report_to,
                "influence_scope": scope.value,
                "unresolved_facts": self.selected - self.resolved,
                "content_sha256": content,
                "status": "completed_offline",
            }
            receipt["publication_id"] = digest(receipt)
            result[scope.value] = {"tables": tables, "receipt": receipt}
        self.spool.db.commit()
        return result

    def customer_orders(self, name: str, cid: str) -> Iterator[Row]:
        for (data,) in self.spool.db.execute(
            "SELECT data FROM rows WHERE name=? AND customer=? ORDER BY json_extract(sorter,'$[0]'),json_extract(sorter,'$[1]'),row_key",
            (name, cid),
        ):
            yield json.loads(data)


class JourneyLookup:
    def __init__(self, spool: Spool):
        self.spool = spool

    def get(self, cid: str) -> Row:
        db = self.spool.db
        counts = db.execute(
            """SELECT COUNT(*), COUNT(DISTINCT CASE WHEN TRIM(json_extract(data,'$.session_id'))<>'' THEN json_extract(data,'$.session_id') END),
          COUNT(DISTINCT CASE WHEN json_extract(data,'$.event_name')='product_view' AND json_extract(data,'$.product_id')<>'' THEN json_extract(data,'$.product_id') END),
          COALESCE(SUM(json_extract(data,'$.event_name')='add_to_cart'),0),COALESCE(SUM(json_extract(data,'$.event_name')='checkout_started'),0)
          FROM rows WHERE name='timeline' AND customer=? AND json_extract(data,'$.record_type')='FACT'""",
            (cid,),
        ).fetchone()

        def edge(name: str, reverse: bool, facts: bool = False) -> Row:
            direction = "DESC" if reverse else "ASC"
            predicate = " AND json_extract(data,'$.record_type')='FACT'" if facts else ""
            ordering = "fact" if name == "paid" else "row_key"
            # Paid rows have customer only through their explicit resolution paths.
            if name == "paid":
                found = db.execute(
                    f"SELECT p.data FROM rows p JOIN rows t ON t.name='timeline' AND t.fact=p.fact AND t.customer=? AND json_extract(t.data,'$.record_type')='FACT' WHERE p.name='paid' ORDER BY p.at {direction},p.fact {direction} LIMIT 1",
                    (cid,),
                ).fetchone()
            else:
                found = db.execute(
                    f"SELECT data FROM rows WHERE name=? AND customer=? {predicate} ORDER BY at {direction},{ordering} {direction} LIMIT 1",
                    (name, cid),
                ).fetchone()
            return json.loads(found[0]) if found else {}

        first, last = edge("paid", False), edge("paid", True)
        return {
            "first_touch_at": edge("timeline", False, True).get("occurred_at"),
            "first_paid_touch_at": first.get("occurred_at"),
            "last_paid_touch_at": last.get("occurred_at"),
            "first_campaign_id": first.get("campaign_id"),
            "last_campaign_id": last.get("campaign_id"),
            "total_events": counts[0],
            "total_sessions": counts[1],
            "total_products_viewed": counts[2],
            "total_cart_events": counts[3],
            "total_checkout_events": counts[4],
            "timeline_start": edge("timeline", False).get("occurred_at"),
            "timeline_end": edge("timeline", True).get("occurred_at"),
        }
