"""Only resolver-consumed identity evidence; bounded fixed-snapshot day/hash chunks."""

import hashlib
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from src.analytics.cloud.transport import Transport, scalar
from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row, instant
from src.bigquery.catalog import TABLES
from src.influence.identity import resolver_evidence
from src.intelligence.live.spool import primitive
from src.observability.logging import event

FIELDS = "store_id source_system link_id source_fact_id source_version_id left_namespace left_id right_namespace right_id confidence_type evidence_type occurred_at observed_at".split()

# Exactly the two relationship types the current resolver consumes. No general identity graph.
EVIDENCE_PREDICATE = """confidence_type='DETERMINISTIC' AND (
 (evidence_type='observed_cooccurrence' AND left_namespace='session_id' AND right_namespace='user_id') OR
 (evidence_type='observed_registration_customer' AND left_namespace='fact_id' AND right_namespace='customer_id')
)"""


class EvidenceReader:
    def __init__(self, transport: Transport, policy: AnalyticsPolicy, snapshot_at: str):
        if not set(FIELDS) <= TABLES["identity_links"].fields.keys():
            raise ValueError("intelligence_source_schema_drift")
        self.transport, self.policy, self.snapshot_at = transport, policy, snapshot_at
        self.chunk_count = self.rows_processed = self.largest_chunk_rows = 0

    def chunks(self) -> Iterator[list[Row]]:
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
        base = f"FROM `{t.config.project}.up_core.identity_links` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND source_system='upzero' AND occurred_at IS NOT NULL AND occurred_at>=@history_from AND occurred_at<@as_of AND source_version_id IS NOT NULL AND {EVIDENCE_PREDICATE}"
        # Inventory deliberately precedes source_fact_id IS NOT NULL: relevant broken
        # references must fail, rather than silently disappear under an eligibility filter.
        counts = "COUNT(*) AS n,COUNT(DISTINCT link_id) AS distinct_n,COUNTIF(link_id IS NULL OR TRIM(link_id)='') AS invalid_n,COUNTIF(source_fact_id IS NULL OR TRIM(source_fact_id)='') AS invalid_source_n"
        global_rows, _ = t.query(
            "/* intelligence_evidence_inventory_total */ SELECT " + counts + " " + base, params
        )
        if (
            len(global_rows) != 1
            or global_rows[0]["n"] != global_rows[0]["distinct_n"]
            or global_rows[0]["invalid_n"]
            or global_rows[0]["invalid_source_n"]
        ):
            raise ValueError("duplicate_or_invalid_identity_evidence")
        base += " AND source_fact_id IS NOT NULL"
        inventory, _ = t.query(
            "/* intelligence_evidence_inventory */ SELECT CAST(DATE(occurred_at,@timezone) AS STRING) AS day,"
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
            or any(
                r["n"] != r["distinct_n"] or r["invalid_n"] or r["invalid_source_n"]
                for r in inventory
            )
        ):
            raise ValueError("intelligence_evidence_inventory_incomplete")
        event(
            "intelligence_evidence_inventory",
            store_id=p.store_id,
            policy_hash=p.policy_hash,
            rows_processed=total,
        )
        hashed = "LOWER(TO_HEX(SHA256(link_id)))"
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
                            "/* intelligence_evidence_leaf */ SELECT "
                            + ",".join(FIELDS)
                            + " "
                            + scoped
                            + f" ORDER BY {hashed},link_id",
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
                            raise ValueError("intelligence_evidence_chunk_incomplete")
                        seen = set()
                        for r in rows:
                            r = primitive(r)
                            fid = r.get("link_id")
                            if not isinstance(fid, str) or not fid.strip() or fid in seen:
                                raise ValueError("duplicate_or_invalid_identity_evidence")
                            if (
                                not isinstance(r.get("source_fact_id"), str)
                                or not r["source_fact_id"].strip()
                                or r.get("source_version_id") is None
                            ):
                                raise ValueError("duplicate_or_invalid_identity_evidence")
                            seen.add(fid)
                            if (
                                r.get("store_id") != p.store_id
                                or r.get("source_system") != "upzero"
                                or not resolver_evidence(r)
                                or not hashlib.sha256(fid.encode()).hexdigest().startswith(prefix)
                                or p.reference().local_date(r["occurred_at"]) != expected_day
                                or not instant(p.history_from)
                                <= instant(r["occurred_at"])
                                < instant(p.as_of)
                            ):
                                raise ValueError("intelligence_evidence_partition_mismatch")
                        normalized = [primitive(r) for r in rows]
                        normalized.sort(
                            key=lambda r: (
                                hashlib.sha256(r["link_id"].encode()).hexdigest(),
                                r["link_id"],
                            )
                        )
                        self.chunk_count += 1
                        self.rows_processed += len(rows)
                        self.largest_chunk_rows = max(self.largest_chunk_rows, len(rows))
                        event(
                            "intelligence_evidence_chunk",
                            store_id=p.store_id,
                            policy_hash=p.policy_hash,
                            chunk_count=self.chunk_count,
                            rows_processed=self.rows_processed,
                            largest_chunk_rows=self.largest_chunk_rows,
                        )
                        yield normalized
                        return
                if len(prefix) >= 64:
                    raise ValueError("intelligence_unsplittable_evidence_transport")
                children, _ = t.query(
                    f"/* intelligence_evidence_split */ SELECT SUBSTR({hashed},1,@depth) AS prefix,COUNT(*) AS n "
                    + scoped
                    + " GROUP BY prefix ORDER BY prefix",
                    parameters + [scalar("depth", "INT64", len(prefix) + 1)],
                )
                if sum(int(c["n"]) for c in children) != count or len(
                    {c["prefix"] for c in children}
                ) != len(children):
                    raise ValueError("intelligence_evidence_split_incomplete")
                for child in sorted(children, key=lambda c: c["prefix"]):
                    key = child["prefix"]
                    if (
                        len(key) != len(prefix) + 1
                        or not key.startswith(prefix)
                        or any(c not in "0123456789abcdef" for c in key)
                        or int(child["n"]) <= 0
                    ):
                        raise ValueError("intelligence_evidence_split_invalid")
                    yield from leaves(key, int(child["n"]))

            day_read = 0
            for rows in leaves("", int(day_info["n"])):
                day_read += len(rows)
                yield rows
            if day_read != int(day_info["n"]):
                raise ValueError("intelligence_evidence_day_incomplete")
            processed += day_read
        if processed != total:
            raise ValueError("intelligence_evidence_inventory_incomplete")
        event(
            "intelligence_evidence_stream_finished",
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
