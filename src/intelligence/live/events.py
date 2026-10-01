"""Time-travel event inventory and exhaustive deterministic day/SHA256 partitions."""

import hashlib
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from src.analytics.cloud.transport import Transport, scalar
from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row, instant
from src.bigquery.catalog import TABLES
from src.intelligence.live.spool import primitive
from src.observability.logging import event

FIELDS = "store_id source_system fact_id event_name occurred_at order_id session_id visitor_id user_id product_id product_variant_id meta_campaign_id meta_adset_id meta_ad_id utm_source utm_medium utm_campaign fbclid fbc fbp gclid value quantity version_id observed_at".split()


class EventReader:
    def __init__(self, transport: Transport, policy: AnalyticsPolicy, snapshot_at: str):
        if not set(FIELDS) <= TABLES["analytics_events"].fields.keys():
            raise ValueError("intelligence_source_schema_drift")
        self.transport, self.policy, self.snapshot_at = transport, policy, snapshot_at
        self.chunk_count = self.rows_processed = self.largest_chunk_rows = 0

    def chunks(self, *, anchors: bool = False) -> Iterator[list[Row]]:
        self.chunk_count = self.rows_processed = self.largest_chunk_rows = 0
        p, t = self.policy, self.transport
        before, start = t.bytes_processed, time.monotonic()
        params = [
            scalar("store", "STRING", p.store_id),
            scalar("snapshot_at", "TIMESTAMP", self.snapshot_at),
            scalar("history_from", "TIMESTAMP", p.history_from),
            scalar("as_of", "TIMESTAMP", p.as_of),
            scalar("timezone", "STRING", p.reporting_timezone),
        ]
        base = f"FROM `{t.config.project}.up_core.analytics_events` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND source_system='upzero' AND occurred_at>=@history_from AND occurred_at<@as_of"
        if anchors:
            base += " AND (order_id IS NOT NULL OR event_name='register_approved')"
        counts = "COUNT(*) AS n,COUNT(DISTINCT fact_id) AS distinct_n,COUNTIF(fact_id IS NULL OR TRIM(fact_id)='') AS invalid_n"
        global_rows, _ = t.query(
            "/* intelligence_event_inventory_total */ SELECT " + counts + " " + base, params
        )
        if (
            len(global_rows) != 1
            or global_rows[0]["n"] != global_rows[0]["distinct_n"]
            or global_rows[0]["invalid_n"]
        ):
            raise ValueError("duplicate_or_invalid_fact_key")
        inventory, _ = t.query(
            "/* intelligence_event_inventory */ SELECT CAST(DATE(occurred_at,@timezone) AS STRING) AS day,"
            + counts
            + " "
            + base
            + " GROUP BY day ORDER BY day",
            params,
        )
        total = int(global_rows[0]["n"])
        if (
            sum(int(r["n"]) for r in inventory) != total
            or len({r["day"] for r in inventory}) != len(inventory)
            or any(r["n"] != r["distinct_n"] or r["invalid_n"] for r in inventory)
        ):
            raise ValueError("intelligence_event_inventory_incomplete")
        event(
            "intelligence_event_inventory",
            store_id=p.store_id,
            policy_hash=p.policy_hash,
            rows_processed=total,
        )
        hashed = "LOWER(TO_HEX(SHA256(fact_id)))"
        processed = 0
        for day_info in inventory:
            day = day_info["day"]
            date.fromisoformat(day)
            day_base = (
                base
                + " AND occurred_at>=TIMESTAMP(@day,@timezone) AND occurred_at<TIMESTAMP(DATE_ADD(@day,INTERVAL 1 DAY),@timezone)"
            )
            day_params = params + [scalar("day", "DATE", day)]

            def leaves(
                prefix: str,
                count: int,
                query_base: str = day_base,
                query_params: list[Any] = day_params,
                expected_day: str = day,
            ) -> Iterator[list[Row]]:
                scoped = query_base + f" AND STARTS_WITH({hashed},@prefix)"
                parameters = query_params + [scalar("prefix", "STRING", prefix)]
                if count <= t.config.maximum_rows:
                    try:
                        rows, _ = t.query(
                            "/* intelligence_event_leaf */ SELECT "
                            + ",".join(FIELDS)
                            + " "
                            + scoped
                            + f" ORDER BY {hashed},fact_id",
                            parameters,
                        )
                    except ValueError as exc:
                        if str(exc) not in {
                            "analytics_unit_payload_too_large_partition_required",
                            "analytics_unit_too_large_partition_required",
                        }:
                            raise
                    else:
                        if len(rows) != count:
                            raise ValueError("intelligence_event_chunk_incomplete")
                        seen = set()
                        for r in rows:
                            r = primitive(r)
                            fid = r.get("fact_id")
                            if not isinstance(fid, str) or not fid.strip() or fid in seen:
                                raise ValueError("duplicate_or_invalid_fact_key")
                            seen.add(fid)
                            if (
                                r.get("store_id") != p.store_id
                                or r.get("source_system") != "upzero"
                                or not hashlib.sha256(fid.encode()).hexdigest().startswith(prefix)
                                or p.reference().local_date(r["occurred_at"]) != expected_day
                                or not instant(p.history_from)
                                <= instant(r["occurred_at"])
                                < instant(p.as_of)
                            ):
                                raise ValueError("intelligence_event_partition_mismatch")
                            if anchors and not (
                                r.get("order_id") is not None
                                or r.get("event_name") == "register_approved"
                            ):
                                raise ValueError("intelligence_anchor_partition_mismatch")
                        normalized = [primitive(r) for r in rows]
                        normalized.sort(
                            key=lambda r: (
                                hashlib.sha256(r["fact_id"].encode()).hexdigest(),
                                r["fact_id"],
                            )
                        )
                        self.chunk_count += 1
                        self.rows_processed += len(rows)
                        self.largest_chunk_rows = max(self.largest_chunk_rows, len(rows))
                        event(
                            "intelligence_event_chunk",
                            store_id=p.store_id,
                            policy_hash=p.policy_hash,
                            chunk_count=self.chunk_count,
                            rows_processed=self.rows_processed,
                            largest_chunk_rows=self.largest_chunk_rows,
                        )
                        yield normalized
                        return
                if len(prefix) >= 64:
                    raise ValueError("intelligence_unsplittable_event_transport")
                children, _ = t.query(
                    f"/* intelligence_event_split */ SELECT SUBSTR({hashed},1,@depth) AS prefix,COUNT(*) AS n "
                    + scoped
                    + " GROUP BY prefix ORDER BY prefix",
                    parameters + [scalar("depth", "INT64", len(prefix) + 1)],
                )
                if sum(int(c["n"]) for c in children) != count or len(
                    {c["prefix"] for c in children}
                ) != len(children):
                    raise ValueError("intelligence_event_split_incomplete")
                for child in sorted(children, key=lambda c: c["prefix"]):
                    key = child["prefix"]
                    if (
                        len(key) != len(prefix) + 1
                        or not key.startswith(prefix)
                        or any(c not in "0123456789abcdef" for c in key)
                        or int(child["n"]) <= 0
                    ):
                        raise ValueError("intelligence_event_split_invalid")
                    yield from leaves(key, int(child["n"]))

            day_read = 0
            for rows in leaves("", int(day_info["n"])):
                day_read += len(rows)
                yield rows
            if day_read != int(day_info["n"]):
                raise ValueError("intelligence_event_day_incomplete")
            processed += day_read
        if processed != total:
            raise ValueError("intelligence_event_inventory_incomplete")
        event(
            "intelligence_event_stream_finished",
            store_id=p.store_id,
            policy_hash=p.policy_hash,
            chunk_count=self.chunk_count,
            rows_processed=processed,
            largest_chunk_rows=self.largest_chunk_rows,
            duration_ms=int((time.monotonic() - start) * 1000),
            bytes_processed=t.bytes_processed - before
            if before is not None and t.bytes_processed is not None
            else None,
        )
