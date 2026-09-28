"""Versioned, durable stage counters. Counts are source entries, not HTTP attempts.

RAW counters commit with the envelope; CORE counters commit with normalized rows.
Legacy fields are explicit aliases, not additional independent accumulators.
"""

from collections.abc import Iterable
from typing import Any

from src.domain.models import Batch
from src.utils.data import canonical

VERSION = 2
COUNTERS = (
    "source_records_read",
    "source_bytes_read",
    "raw_pages_written",
    "raw_payload_bytes",
    "core_records_processed",
    "core_records_inserted",
    "core_records_updated",
    "core_records_failed",
    "core_pages_processed",
    "replay_records_read",
)


def empty() -> dict[str, int]:
    return {"metrics_version": VERSION, **dict.fromkeys(COUNTERS, 0)}


def aliases(run: dict[str, Any]) -> None:
    run.update(
        records_read=run["source_records_read"],
        records_written=run["core_records_inserted"],
        records_updated=run["core_records_updated"],
        records_failed=run["core_records_failed"],
        pages=run["raw_pages_written"],
        bytes=run["source_bytes_read"],
    )


def captured(run: dict[str, Any], raw: dict[str, Any]) -> None:
    run["source_records_read"] += len(raw["payload"]["data"])
    run["source_bytes_read"] += raw["bytes_read"]
    run["raw_pages_written"] += 1
    run["raw_payload_bytes"] += len(canonical(raw["payload"]).encode("utf-8"))
    aliases(run)


def promoted(run: dict[str, Any], raw: dict[str, Any], batch: Batch) -> None:
    count = len(raw["payload"]["data"])
    run["core_records_processed"] += count
    run["core_records_inserted"] += batch.written
    run["core_records_updated"] += batch.updated
    run["core_records_failed"] += batch.failed
    run["core_pages_processed"] += 1
    if run["mode"] == "replay":
        run["replay_records_read"] += count
    aliases(run)


def upgrade(run: dict[str, Any], raw_rows: Iterable[dict[str, Any]]) -> None:
    """Resume legacy ingestion: restore captured counts, never recount on v2 retry.

    Only called when metrics_version is absent/old. Legacy CORE counters were already
    transactional; retain them. RAW rows must be streamed for this same store/run.
    """
    if run.get("metrics_version") == VERSION:
        return
    legacy = {
        "core_records_processed": run["records_read"],
        "core_records_inserted": run["records_written"],
        "core_records_updated": run["records_updated"],
        "core_records_failed": run["records_failed"],
        "core_pages_processed": run["pages"],
    }
    run.update(empty())
    run.update(legacy)
    for raw in raw_rows:
        captured(run, raw)
    aliases(run)
