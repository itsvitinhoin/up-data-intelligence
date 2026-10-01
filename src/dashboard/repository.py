"""Bounded BigQuery read transport; the caller supplies a client and permissions."""

import re
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

from src.dashboard.contracts import ReadError
from src.dashboard.queries import Query
from src.observability.logging import event


@dataclass(frozen=True)
class ReadBudget:
    project: str
    location: str
    maximum_bytes_billed: int = 1_073_741_824
    maximum_total_bytes_billed: int = 8_589_934_592
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", self.project)
            or not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", self.location)
            or self.maximum_bytes_billed <= 0
            or self.maximum_total_bytes_billed < self.maximum_bytes_billed
            or self.timeout_seconds <= 0
        ):
            raise ValueError("invalid_dashboard_read_budget")


class Reader(Protocol):
    def query(
        self, query: Query, *, request_id: str, store_id: str, generation: int | None
    ) -> list[dict[str, Any]]: ...


class BigQueryReadSession:
    def __init__(self, client: Any, budget: ReadBudget):
        self.client = client
        self.budget = budget
        self.reserved_bytes = 0

    def query(
        self, query: Query, *, request_id: str, store_id: str, generation: int | None
    ) -> list[dict[str, Any]]:
        ceiling = self.budget.maximum_bytes_billed
        if self.reserved_bytes + ceiling > self.budget.maximum_total_bytes_billed:
            raise ReadError(503, "query_budget_exceeded")
        self.reserved_bytes += ceiling  # Failed/unknown jobs retain their reservation.
        parameters = [
            bigquery.ScalarQueryParameter(key, kind, cast(Any, value))
            for key, (kind, value) in query.parameters.items()
        ]
        config = bigquery.QueryJobConfig(
            query_parameters=parameters,
            use_legacy_sql=False,
            use_query_cache=False,
            maximum_bytes_billed=ceiling,
        )
        start = time.monotonic()
        try:
            job = self.client.query(
                query.sql,
                job_config=config,
                project=self.budget.project,
                location=self.budget.location,
                job_retry=None,
                timeout=self.budget.timeout_seconds,
            )
            rows = [dict(row.items()) for row in job.result(timeout=self.budget.timeout_seconds)]
        except BadRequest as exc:
            code = (
                "query_budget_exceeded"
                if "maximum bytes billed" in str(exc).lower()
                else "bigquery_read_failed"
            )
            event(
                "dashboard_query_finished",
                request_id=request_id,
                store_id=store_id,
                resource=query.name,
                generation=generation,
                status=code,
            )
            raise ReadError(503, code) from None
        except Exception:
            event(
                "dashboard_query_finished",
                request_id=request_id,
                store_id=store_id,
                resource=query.name,
                generation=generation,
                status="failed",
            )
            raise ReadError(503, "bigquery_read_failed") from None
        event(
            "dashboard_query_finished",
            request_id=request_id,
            store_id=store_id,
            resource=query.name,
            generation=generation,
            query_duration_ms=int((time.monotonic() - start) * 1000),
            bytes_processed=getattr(job, "total_bytes_processed", None),
            row_count=len(rows),
            status="completed",
        )
        return rows
