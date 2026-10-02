"""Execution-wide ceiling around SDK clients, including legacy repository reads."""

import time
from threading import Lock
from typing import Any

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.analytics.cloud.transport import CloudConfig
from src.bigquery.query_budget import QueryBudget, QueryBudgetExceeded, Reservation
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
        self.query_budget = QueryBudget(config.maximum_total_bytes_billed)
        self.bytes_processed: int | None = 0
        self.duration_ms = 0
        self.measured: set[str] = set()
        self.mutation_outcome_unknown = False
        self.budget_exhausted = False

    @property
    def reserved_bytes(self) -> int:
        """Compatibility alias for current accounted execution cost."""
        return self.query_budget.accounted_bytes

    @reserved_bytes.setter
    def reserved_bytes(self, value: int) -> None:
        try:
            self.query_budget.import_accounted(value)
        except QueryBudgetExceeded as exc:
            self.budget_exhausted = True
            raise ExecutionBudgetExceeded() from exc

    @property
    def settled_billed_bytes(self) -> int:
        return self.query_budget.settled_billed_bytes

    @property
    def unresolved_reserved_bytes(self) -> int:
        return self.query_budget.unresolved_reserved_bytes

    @property
    def budget_accounted_bytes(self) -> int:
        return self.query_budget.accounted_bytes

    def query(self, sql: str, **kwargs: Any) -> Any:
        from google.cloud import bigquery

        ceiling = self.config.maximum_bytes_billed
        try:
            reservation = self.query_budget.reserve(ceiling)
        except QueryBudgetExceeded as exc:
            self.budget_exhausted = True
            raise ExecutionBudgetExceeded() from exc
        self.query_count += 1
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
            return MeasuredJob(self.client.query(sql, **kwargs), self, write_possible, reservation)
        except Exception as exc:
            self.mutation_outcome_unknown |= write_possible and not isinstance(
                exc, (BadRequest, Forbidden, Unauthorized)
            )
            self.bytes_processed = None
            raise

    def get_job(self, *args: Any, **kwargs: Any) -> Any:
        return MeasuredJob(self.client.get_job(*args, **kwargs), self)


class MeasuredJob:
    def __init__(
        self,
        job: Any,
        client: BoundedClient,
        write_possible: bool = True,
        reservation: Reservation | None = None,
    ):
        self.job, self.client = job, client
        self.write_possible = write_possible
        self.reservation = reservation
        self._accounting_finished = False
        self._budget_invalid = False
        self._result_lock = Lock()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.job, name)

    def result(self, **kwargs: Any) -> Any:
        # Serialize repeated results so the owned reservation is finalized only once.
        with self._result_lock:
            return self._result(**kwargs)

    def _result(self, **kwargs: Any) -> Any:
        if self._budget_invalid:
            raise ExecutionBudgetExceeded()
        started = time.monotonic()
        kwargs.setdefault("timeout", self.client.config.timeout_seconds)
        try:
            result = self.job.result(**kwargs)
        except Exception:
            # Failure retains worst-case cost for the rest of this execution, even
            # if a later reconciliation result succeeds.
            self._accounting_finished = True
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
        if self.reservation is not None and not self._accounting_finished:
            self._accounting_finished = True
            try:
                self.client.query_budget.settle(
                    self.reservation, getattr(self.job, "total_bytes_billed", None)
                )
            except QueryBudgetExceeded as exc:
                self._budget_invalid = True
                self.client.budget_exhausted = True
                raise ExecutionBudgetExceeded() from exc
        return result
