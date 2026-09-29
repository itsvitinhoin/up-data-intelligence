"""BigQuery request construction; never creates a client or discovers credentials."""

import re
import time
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

from src.analytics.engine import Row


@dataclass(frozen=True)
class CloudConfig:
    project: str
    location: str
    maximum_bytes_billed: int
    timeout_seconds: float
    use_query_cache: bool
    maximum_rows: int = 100000

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", self.project):
            raise ValueError("invalid_project")
        if (
            not self.location
            or self.maximum_bytes_billed <= 0
            or self.timeout_seconds <= 0
            or self.maximum_rows <= 0
        ):
            raise ValueError("explicit_cloud_limits_required")


class Transport:
    def __init__(self, client: Any, config: CloudConfig):
        self.client = client
        self.config = config
        self.bytes_processed: int | None = 0
        self.duration_ms = 0
        self.rows_read = 0

    def query(
        self,
        sql: str,
        parameters: list[Any],
        *,
        session: str | None = None,
        create_session: bool = False,
        job_id: str | None = None,
    ) -> tuple[list[Row], str | None]:
        cfg = bigquery.QueryJobConfig(
            query_parameters=parameters,
            use_legacy_sql=False,
            use_query_cache=self.config.use_query_cache,
            maximum_bytes_billed=self.config.maximum_bytes_billed,
            create_session=create_session,
        )
        if session:
            cfg.connection_properties = [
                bigquery.ConnectionProperty(key="session_id", value=session)
            ]
        started = time.monotonic()
        job = self.client.query(
            sql,
            job_config=cfg,
            location=self.config.location,
            project=self.config.project,
            job_id=job_id,
            job_retry=None,
            timeout=self.config.timeout_seconds,
        )
        # No retry of an ambiguous transaction. The writer reconciles its durable receipt.
        rows: list[Row] = []
        for row in job.result(timeout=self.config.timeout_seconds):
            if len(rows) >= self.config.maximum_rows:
                raise ValueError("analytics_unit_too_large_partition_required")
            rows.append(dict(row.items()))
        measured = job.total_bytes_processed
        self.bytes_processed = (
            self.bytes_processed + int(measured)
            if self.bytes_processed is not None and measured is not None
            else None
        )
        self.duration_ms += int((time.monotonic() - started) * 1000)
        self.rows_read += len(rows)
        info = getattr(job, "session_info", None)
        return rows, getattr(info, "session_id", None)


def scalar(name: str, typ: str, value: Any) -> Any:
    return bigquery.ScalarQueryParameter(name, typ, value)


def array(name: str, values: list[str]) -> Any:
    return bigquery.ArrayQueryParameter(name, "STRING", values)
