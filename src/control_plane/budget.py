"""Execution-wide ceiling around SDK clients, including legacy repository reads."""

import time
from typing import Any

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.analytics.cloud.transport import CloudConfig
from src.domain.models import SafeError


class ExecutionBudgetExceeded(BadRequest):
    """Definitive LOCAL pre-submission rejection; compatible with AtomicWriter guards."""

    def __init__(self) -> None:
        super().__init__("store_execution_budget_exhausted")  # type: ignore[no-untyped-call]


class BoundedClient:
    def __init__(self, client: Any, config: CloudConfig):
        if config.maximum_total_bytes_billed is None:
            raise SafeError("store_execution_budget_required")
        self.client, self.config = client, config
        self.query_count = 0
        self.reserved_bytes = 0
        self.bytes_processed: int | None = 0
        self.duration_ms = 0
        self.measured: set[str] = set()
        self.mutation_outcome_unknown = False
        self.budget_exhausted = False

    def query(self, sql: str, **kwargs: Any) -> Any:
        from google.cloud import bigquery

        ceiling = self.config.maximum_bytes_billed
        if self.reserved_bytes + ceiling > (self.config.maximum_total_bytes_billed or 0):
            self.budget_exhausted = True
            raise ExecutionBudgetExceeded()
        self.query_count += 1
        self.reserved_bytes += ceiling
        config = kwargs.pop("job_config", None) or bigquery.QueryJobConfig()
        config.maximum_bytes_billed = min(config.maximum_bytes_billed or ceiling, ceiling)
        config.use_legacy_sql = False
        kwargs.update(
            job_config=config,
            project=self.config.project,
            location=self.config.location,
            timeout=self.config.timeout_seconds,
        )
        # Disable SDK job relaunches even for reads: every new billed job must be metered.
        kwargs["job_retry"] = None
        kwargs["retry"] = None
        write_possible = not sql.lstrip().upper().startswith("SELECT ")
        try:
            return MeasuredJob(self.client.query(sql, **kwargs), self, write_possible)
        except Exception as exc:
            self.mutation_outcome_unknown |= write_possible and not isinstance(
                exc, (BadRequest, Forbidden, Unauthorized)
            )
            self.bytes_processed = None
            raise

    def get_job(self, *args: Any, **kwargs: Any) -> Any:
        return MeasuredJob(self.client.get_job(*args, **kwargs), self)


class MeasuredJob:
    def __init__(self, job: Any, client: BoundedClient, write_possible: bool = True):
        self.job, self.client = job, client
        self.write_possible = write_possible

    def __getattr__(self, name: str) -> Any:
        return getattr(self.job, name)

    def result(self, **kwargs: Any) -> Any:
        started = time.monotonic()
        kwargs.setdefault("timeout", self.client.config.timeout_seconds)
        try:
            result = self.job.result(**kwargs)
        except Exception:
            terminal_failure = self.job.state == "DONE" and self.job.error_result is not None
            self.client.mutation_outcome_unknown |= self.write_possible and not terminal_failure
            self.client.bytes_processed = None
            raise
        self.client.duration_ms += int((time.monotonic() - started) * 1000)
        key = self.job.job_id
        if key not in self.client.measured:
            self.client.measured.add(key)
            value = self.job.total_bytes_processed
            self.client.bytes_processed = (
                self.client.bytes_processed + int(value)
                if self.client.bytes_processed is not None and value is not None
                else None
            )
        return result
