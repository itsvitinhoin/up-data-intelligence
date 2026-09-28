"""Read-only DEV audit. Outputs only counts, sizes, UUIDs and cursor fingerprints.

Run from repository root with approved BigQuery read access. Never logs payloads,
query results, token contents or exception messages. Does not call Engine.run/replay.
"""

import hashlib
import json
from typing import Any

from google.cloud import bigquery

from src.bigquery.repository import decode_row
from src.config.settings import Settings
from src.ingestion.engine import Engine
from src.ingestion.metrics import COUNTERS
from src.utils.data import canonical

PROJECT = "up-data-intelligence-dev"
STORE = "mx-fashion"
RUN = "affd46d5-3371-448c-aa2b-0afb7e7625db"
SQL = """SELECT TO_JSON_STRING(r) raw_body, TO_JSON_STRING(s) run_body,
 TO_JSON_STRING(c) checkpoint_body
FROM `up-data-intelligence-dev.up_raw.upzero_analytics_facts` r
JOIN `up-data-intelligence-dev.up_ops.sync_runs` s
 ON s.store_id=r.store_id AND s.run_id=r.run_id
LEFT JOIN `up-data-intelligence-dev.up_ops.sync_checkpoints` c
 ON c.store_id=r.store_id AND c.run_id=r.run_id
WHERE r.store_id=@store AND r.run_id=@run"""


class EmptyCore:
    """Reconstruct the audited zero-CORE scenario; never persist anything."""

    def read(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
        return []

    def write(self, *_: Any, **__: Any) -> None:
        raise RuntimeError("audit_is_read_only")


def fingerprint(value: Any) -> dict[str, Any]:
    return {
        "present": value is not None,
        "length": len(value) if isinstance(value, str) else None,
        "sha256": hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else None,
    }


def audit(raw: dict[str, Any], oldrun: dict[str, Any], cp: dict[str, Any]) -> dict[str, Any]:
    # Only transform in memory. EmptyCore is intentional, matching supplied audit;
    # this is an estimate, not an assertion about today's CORE state.
    engine = object.__new__(Engine)
    engine.repo = EmptyCore()  # type: ignore[assignment]
    engine.cfg = Settings(
        STORE, "MX Fashion", STORE, "America/Sao_Paulo", "mx-fashion-upzero", "2026-09-01T00:00:00Z"
    )
    batch = engine.transform(raw)
    run = {k: v for k, v in oldrun.items() if k not in (*COUNTERS, "metrics_version")}
    run.update(status="running", finished_at=None, error_summary=None)
    run["records_read"] += len(raw["payload"]["data"])
    run["records_written"] += batch.written
    run["records_updated"] += batch.updated
    run["records_failed"] += batch.failed
    run["pages"] += 1
    run["bytes"] += raw["bytes_read"]
    checkpoint = {
        **cp,
        "pending_raw_id": None,
        "position": raw["next_position"] or {},
        "updated_at": raw["ingested_at"],
        "status": "extracted" if raw["next_position"] is None else "running",
    }
    batch.add("sync_runs", run)
    batch.add("sync_checkpoints", checkpoint)
    records = [
        canonical({"target_table": table, "record": row})
        for table, rows in batch.rows.items()
        for row in {r["row_key"]: r for r in rows}.values()
    ]
    size = len(canonical(records).encode())
    filters = raw["request_filters"] or {}
    return {
        "run_id": raw["run_id"],
        "raw_record_id": raw["raw_record_id"],
        "request_id": raw["request_id"],
        "fact_count": len(raw["payload"]["data"]),
        "response_bytes": raw["bytes_read"],
        "canonical_sanitized_payload_bytes": len(canonical(raw["payload"]).encode()),
        "cursor": fingerprint((raw["position"] or {}).get("cursor")),
        "next_cursor": fingerprint((raw["next_position"] or {}).get("cursor")),
        "window": {k: filters.get(k) for k in ("from", "to", "limit")},
        "checkpoint_status": cp.get("status"),
        "checkpoint_points_to_raw": cp.get("pending_raw_id") == raw["raw_record_id"],
        "checkpoint_completed_to": cp.get("completed_to"),
        "reconstructed_core_batch_rows": {k: len(v) for k, v in batch.rows.items()},
        "reconstructed_old_guard_bytes": size,
        "exceeds_old_8000000_guard": size > 8_000_000,
        "caveat": "Reconstructed with empty CORE; transient timestamps differ from original. Not exact historical request size.",
    }


def main() -> int:
    try:
        client = bigquery.Client(project=PROJECT, location="southamerica-east1")
        config = bigquery.QueryJobConfig(
            maximum_bytes_billed=1_000_000_000,
            query_parameters=[
                bigquery.ScalarQueryParameter("store", "STRING", STORE),
                bigquery.ScalarQueryParameter("run", "STRING", RUN),
            ],
        )
        found = False
        for row in client.query(SQL, job_config=config).result(timeout=60):
            found = True
            if row.checkpoint_body == "null":
                print(json.dumps({"status": "checkpoint_not_found"}))
                return 1
            print(
                json.dumps(
                    audit(
                        decode_row(row.raw_body, "upzero_analytics_facts"),
                        decode_row(row.run_body, "sync_runs"),
                        decode_row(row.checkpoint_body, "sync_checkpoints"),
                    )
                )
            )
        if not found:
            print(json.dumps({"status": "raw_not_found_for_run"}))
            return 1
        return 0
    except Exception as exc:
        print(json.dumps({"status": "audit_failed", "error_class": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
