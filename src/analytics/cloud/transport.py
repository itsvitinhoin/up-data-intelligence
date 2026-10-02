"""BigQuery request construction; never creates a client or discovers credentials."""

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

from src.analytics.engine import Row
from src.bigquery.query_budget import QueryBudget, QueryBudgetExceeded


@dataclass(frozen=True)
class CloudConfig:
    project: str
    location: str
    maximum_bytes_billed: int
    timeout_seconds: float
    use_query_cache: bool
    maximum_rows: int = 100000
    maximum_payload_bytes: int = 32 * 1024 * 1024
    maximum_total_bytes_billed: int | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", self.project):
            raise ValueError("invalid_project")
        if (
            not self.location
            or self.maximum_bytes_billed <= 0
            or self.timeout_seconds <= 0
            or self.maximum_rows <= 0
            or self.maximum_payload_bytes <= 0
            or (
                self.maximum_total_bytes_billed is not None and self.maximum_total_bytes_billed <= 0
            )
        ):
            raise ValueError("explicit_cloud_limits_required")


class Transport:
    def __init__(self, client: Any, config: CloudConfig):
        self.client = client
        self.config = config
        self.bytes_processed: int | None = 0
        self.duration_ms = 0
        self.rows_read = 0
        self.query_budget = QueryBudget(config.maximum_total_bytes_billed)
        self.query_count = 0

    @property
    def reserved_query_bytes(self) -> int:
        """Compatibility alias for settled billing plus unresolved reservations."""
        return self.query_budget.accounted_bytes

    @reserved_query_bytes.setter
    def reserved_query_bytes(self, value: int) -> None:
        try:
            self.query_budget.import_accounted(value)
        except QueryBudgetExceeded as exc:
            raise ValueError("analytics_execution_query_budget_exhausted") from exc

    @property
    def settled_billed_bytes(self) -> int:
        return self.query_budget.settled_billed_bytes

    @property
    def unresolved_reserved_bytes(self) -> int:
        return self.query_budget.unresolved_reserved_bytes

    @property
    def budget_accounted_bytes(self) -> int:
        return self.query_budget.accounted_bytes

    def query(
        self,
        sql: str,
        parameters: list[Any],
        *,
        session: str | None = None,
        create_session: bool = False,
        job_id: str | None = None,
    ) -> tuple[list[Row], str | None]:
        ceiling = self.config.maximum_bytes_billed
        try:
            reservation = self.query_budget.reserve(ceiling)
        except QueryBudgetExceeded as exc:
            raise ValueError("analytics_execution_query_budget_exhausted") from exc
        self.query_count += 1
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
        try:
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
            result = job.result(timeout=self.config.timeout_seconds)
        except Exception:
            # Submission/result failures do not establish zero processed bytes.
            self.bytes_processed = None
            raise
        measured = job.total_bytes_processed
        self.bytes_processed = (
            self.bytes_processed + int(measured)
            if self.bytes_processed is not None and measured is not None
            else None
        )
        try:
            self.query_budget.settle(reservation, getattr(job, "total_bytes_billed", None))
        except QueryBudgetExceeded as exc:
            raise ValueError("analytics_execution_query_budget_exhausted") from exc
        self.duration_ms += int((time.monotonic() - started) * 1000)
        rows: list[Row] = []
        payload_bytes = 0
        for row in result:
            if len(rows) >= self.config.maximum_rows:
                raise ValueError("analytics_unit_too_large_partition_required")
            record = dict(row.items())
            payload_bytes += len(
                json.dumps(record, default=str, ensure_ascii=False, separators=(",", ":")).encode()
            )
            if payload_bytes > self.config.maximum_payload_bytes:
                raise ValueError("analytics_unit_payload_too_large_partition_required")
            rows.append(record)
        self.rows_read += len(rows)
        info = getattr(job, "session_info", None)
        return rows, getattr(info, "session_id", None)


def scalar(name: str, typ: str, value: Any) -> Any:
    return bigquery.ScalarQueryParameter(name, typ, value)


def array(name: str, values: list[str]) -> Any:
    return bigquery.ArrayQueryParameter(name, "STRING", values)
