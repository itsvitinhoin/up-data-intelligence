"""Bounded jobs.insert requests; one atomic durable transaction per logical write.

Large writes stage fragments in private session TEMP tables. Only the final MERGE
script touches durable tables, including checkpoints. No persistent staging schema.
"""

import json
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from google.api_core.exceptions import (
    BadRequest,
    Conflict,
    DeadlineExceeded,
    Forbidden,
    InternalServerError,
    NotFound,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
    Unauthorized,
)
from google.cloud import bigquery
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from src.domain.models import SafeError
from src.observability.logging import event

REQUEST_BYTES = 8_000_000  # Below the 10 MB jobs.insert request quota, including JSON escaping.
MAX_RECORD_BYTES = 64_000_000  # Headroom below BigQuery's approximate 100 MB row limit.
TRANSIENT = (
    Conflict,
    DeadlineExceeded,
    InternalServerError,
    ServiceUnavailable,
    TooManyRequests,
    RetryError,
    RequestsConnectionError,
    RequestsTimeout,
    TimeoutError,
)

CREATE_STAGE = (
    "CREATE TEMP TABLE write_fragments (row_index INT64, part_index INT64, fragment STRING);"
)
STAGE = """MERGE _SESSION.write_fragments T
USING (SELECT CAST(JSON_VALUE(p, '$.row') AS INT64) row_index,
 CAST(JSON_VALUE(p, '$.part') AS INT64) part_index,
 JSON_VALUE(p, '$.text') fragment FROM UNNEST(@parts) p) S
ON T.row_index=S.row_index AND T.part_index=S.part_index
WHEN NOT MATCHED THEN INSERT (row_index, part_index, fragment)
VALUES (S.row_index, S.part_index, S.fragment);"""
ASSEMBLE = """CREATE TEMP TABLE write_records AS
SELECT row_index, STRING_AGG(fragment, '' ORDER BY part_index) item
FROM _SESSION.write_fragments GROUP BY row_index;"""


def config_for(
    values: Sequence[str] = (), *, parameter: str = "records", session: str | None = None
) -> bigquery.QueryJobConfig:
    cfg = bigquery.QueryJobConfig()
    if values:
        cfg.query_parameters = [bigquery.ArrayQueryParameter(parameter, "STRING", values)]
    if session:
        cfg.connection_properties = [bigquery.ConnectionProperty("session_id", session)]
    return cfg


def request_bytes(sql: str, config: bigquery.QueryJobConfig) -> int:
    # SDK serializes this config into a jobs.insert envelope. Reserve 64 KiB for
    # jobReference, session ID, user-agent/client fields and serialization changes.
    body = {"configuration": config.to_api_repr()}
    body["configuration"]["query"]["query"] = sql
    return len(json.dumps(body, ensure_ascii=True).encode("utf-8")) + 65_536


def fragment_batches(records: Sequence[str], budget: int) -> Iterator[list[str]]:
    # Unicode/codepoint slices reconstruct the exact JSON string; no truncation.
    # Size every parameter as it will be represented on the wire (double escaping).
    width = max(1, (budget - 65_536) // 32)
    overhead = request_bytes(STAGE, config_for([""], parameter="parts", session="s" * 512))
    batch: list[str] = []
    size = overhead
    for row_index, record in enumerate(records):
        for part_index, start in enumerate(range(0, len(record), width)):
            part = json.dumps(
                {"row": row_index, "part": part_index, "text": record[start : start + width]},
                ensure_ascii=False,
            )
            added = len(json.dumps({"value": part}, ensure_ascii=True).encode()) + 2
            if batch and size + added > budget:
                yield batch
                batch, size = [], overhead
            if size + added > budget:
                raise SafeError("bigquery_fragment_exceeds_request_budget")
            batch.append(part)
            size += added
    if batch:
        yield batch


class AtomicWriter:
    def __init__(
        self,
        client: Any,
        location: str,
        *,
        budget: int = REQUEST_BYTES,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not 100_000 <= budget <= REQUEST_BYTES:
            raise SafeError("invalid_bigquery_request_budget")
        self.client, self.location, self.budget, self.sleep = client, location, budget, sleep

    def execute(self, sql: str, config: bigquery.QueryJobConfig, phase: str) -> Any:
        size = request_bytes(sql, config)
        if size > self.budget:
            raise SafeError("bigquery_request_budget_exceeded")
        job_id = "upwrite_" + uuid.uuid4().hex
        event("bigquery_write_job", phase=phase, job_id=job_id, request_bytes=size)
        job = None
        for attempt in range(3):
            try:
                if job is None:
                    job = self.client.query(
                        sql,
                        job_config=config,
                        job_id=job_id,
                        location=self.location,
                        job_retry=None,
                    )
                job.result(job_retry=None)
                return job
            except TRANSIENT:
                # Reattach to the SAME ID, never create a second job on ambiguity.
                try:
                    job = self.client.get_job(job_id, location=self.location)
                except NotFound:
                    job = None
                except Exception:
                    pass
                if job is not None and job.state == "DONE":
                    if job.error_result:
                        raise SafeError("bigquery_write_failed") from None
                    return job
                if attempt < 2:
                    self.sleep(2**attempt)
            except Exception as exc:
                # Known terminal job failures have no committed transaction.
                if job is not None and job.state == "DONE":
                    if job.error_result:
                        raise SafeError("bigquery_write_failed") from None
                    return job
                # Submission validation/permission rejection is definitive, unlike
                # a response lost after submission or result retrieval.
                if job is None and isinstance(exc, (BadRequest, Forbidden, Unauthorized)):
                    raise SafeError("bigquery_write_failed") from None
                break
        event("bigquery_write_unresolved", phase=phase, job_id=job_id)
        raise SafeError("bigquery_write_outcome_unknown")

    def write(self, records: Sequence[str], direct_sql: str, staged_sql: str) -> None:
        for record in records:
            if len(record.encode()) > MAX_RECORD_BYTES:
                event("bigquery_record_rejected", record_bytes=len(record.encode()))
                raise SafeError("bigquery_record_exceeds_safe_row_limit")
        config = config_for(records)
        if request_bytes(direct_sql, config) <= self.budget:
            self.execute(direct_sql, config, "direct_commit")
            return
        # Release the large API-parameter representation before building chunks.
        del config
        event("bigquery_write_staged", records=len(records), budget_bytes=self.budget)
        create = config_for()
        create.create_session = True
        job = self.execute(CREATE_STAGE, create, "stage_create")
        session = job.session_info.session_id if job.session_info else None
        if not isinstance(session, str) or not session:
            raise SafeError("bigquery_session_missing")
        unresolved = False
        try:
            for index, parts in enumerate(fragment_batches(records, self.budget)):
                self.execute(
                    STAGE, config_for(parts, parameter="parts", session=session), "stage_chunk"
                )
                event("bigquery_chunk_staged", chunk_index=index, records=len(parts))
            self.execute(ASSEMBLE, config_for(session=session), "stage_assemble")
            self.execute(staged_sql, config_for(session=session), "staged_commit")
        except SafeError as exc:
            unresolved = exc.code == "bigquery_write_outcome_unknown"
            raise
        finally:
            # Never abort an unresolved commit. Keep the store lease for inspection.
            # Otherwise cleanup failure must not turn a committed write into failure.
            if not unresolved:
                try:
                    self.execute(
                        "CALL BQ.ABORT_SESSION();", config_for(session=session), "stage_cleanup"
                    )
                except Exception:
                    event("bigquery_session_cleanup_deferred")
