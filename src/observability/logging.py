import json
import logging
from contextvars import ContextVar
from typing import Any

execution_id: ContextVar[str | None] = ContextVar("execution_id", default=None)

# Allowlist, not best-effort regex over exceptions containing arbitrary PII.
SAFE_FIELDS = {
    "chunk_count",
    "rows_processed",
    "pipeline",
    "source_chunks",
    "source_rows_read",
    "source_bytes_processed",
    "chunk_days",
    "largest_chunk_rows",
    "reserved_query_bytes",
    "query_count",
    "snapshot_at",
    "source_generation",
    "publication_id",
    "affected_scope_count",
    "model",
    "policy_hash",
    "report_from",
    "report_to",
    "as_of",
    "rows_read",
    "rows_generated",
    "rows_inserted",
    "rows_updated",
    "rows_failed",
    "rows_deleted",
    "bytes_processed",
    "parent_execution_id",
    "ingestion_status",
    "resource_quality_status",
    "global_quality_status",
    "blocking_for_requested_resource",
    "exit_code",
    "child_runs",
    "metrics_scope",
    "core_records_processed",
    "source_records_read",
    "raw_pages_written",
    "core_records_inserted",
    "core_records_updated",
    "core_records_failed",
    "metrics_version",
    "phase",
    "job_id",
    "request_bytes",
    "request_id",
    "generation",
    "query_duration_ms",
    "row_count",
    "payload_bytes",
    "record_bytes",
    "budget_bytes",
    "chunk_index",
    "raw_record_id",
    "run_id",
    "store_id",
    "resource",
    "status",
    "http_status",
    "attempt",
    "records",
    "pages",
    "code",
    "duration_ms",
    "rule_id",
    "severity",
    "failed_count",
    "checked_count",
}


def configure() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("httpx", "httpcore", "google", "urllib3"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def event(name: str, **fields: Any) -> None:
    if execution_id.get():
        fields["parent_execution_id"] = execution_id.get()
    logging.getLogger("upzero").info(
        json.dumps({"event": name, **{k: v for k, v in fields.items() if k in SAFE_FIELDS}})
    )
