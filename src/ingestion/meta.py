"""Source-specific adapter over existing Page/Batch/Repository/metrics/lease contracts.

No CLI, scheduler, credentials provider or live connector is registered here.
Caller supplies the existing store lease factory (same lock namespace as UP Zero).
"""

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, NoReturn

from src.bigquery.repository import Repository
from src.connectors.meta.client import MetaConnector
from src.connectors.meta.config import CORE, Account, Insights, validate_accounts
from src.domain.models import SafeError
from src.ingestion import metrics
from src.normalization.meta import transform
from src.observability.logging import event
from src.security.sanitization import POLICY_VERSION
from src.utils.data import digest, now


class MetaEngine:
    core_names = CORE
    auto_binding = True
    connector_version = "meta-offline-1.0.0"

    def _transform(self, raw: dict[str, Any]) -> Any:
        return transform(raw, self.repo)

    def _configuration(self, insights: Insights | None) -> dict[str, Any]:
        return {
            "account": self.account.snapshot(),
            "insights": insights.snapshot() if insights else None,
        }

    def __init__(
        self,
        repository: Repository,
        connector: MetaConnector,
        *,
        accounts: tuple[Account, ...],
        lease: Callable[[], AbstractContextManager[None]],
    ):
        validate_accounts(accounts)
        if connector.account not in accounts:
            raise SafeError("meta_account_not_configured")
        self.repo, self.connector, self.account = repository, connector, connector.account
        self.accounts, self.lease = accounts, lease

    def _report(self, resource: str, plan: str, mode: str) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        row: dict[str, Any] = {
            **metrics.empty(),
            "row_key": run_id,
            "run_id": run_id,
            "store_id": self.account.store_id,
            "source": "meta",
            "resource": self.core_names[resource],
            "status": "running",
            "error_summary": None,
            "plan_key": plan,
            "mode": mode,
            "started_at": now(),
            "finished_at": None,
            "retries": 0,
        }
        metrics.aliases(row)
        return row

    def _binding(self) -> dict[str, Any]:
        a = self.account
        return {
            "row_key": digest([a.store_id, "meta", a.account_id]),
            "store_id": a.store_id,
            "account_id": a.account_id,
            "connection_id": a.connection_id,
            "api_version": a.api_version,
            "source_timezone": a.timezone,
            "currency": a.currency,
            "configuration_hash": digest(a.snapshot()),
            "configured_at": now(),
        }

    def run(
        self, resource: str, insights: Insights | None = None, *, refresh: bool = False
    ) -> dict[str, Any]:
        if resource not in CORE or ((resource == "insights") != (insights is not None)):
            raise SafeError("invalid_meta_resource_configuration")
        with self.lease():
            return self._run(resource, insights, refresh)

    def _run(self, resource: str, insights: Insights | None, refresh: bool) -> dict[str, Any]:
        a, table = self.account, "meta_raw_" + resource
        config = self._configuration(insights)
        # Page limit belongs to extraction, not entity/Insights logical identity.
        plan = digest(["meta", resource, config, self.connector.page_limit])
        saved = self.repo.read("sync_checkpoints", a.store_id, [plan])
        cp = saved[0] if saved else {}
        # Never discard an unfinished/pending RAW page to refresh.
        if refresh and cp and cp.get("status") != "complete":
            raise SafeError("meta_resume_before_refresh")
        if cp.get("status") == "complete" and not refresh:
            return self.repo.read("sync_runs", a.store_id, [cp["run_id"]])[0]
        if refresh:
            cp = {}
        oldrun = self.repo.read("sync_runs", a.store_id, [cp["run_id"]]) if cp else []
        run = oldrun[0] if oldrun else self._report(resource, plan, "sync")
        done = cp.get("status") == "extracted"
        cp = {
            "row_key": plan,
            "store_id": a.store_id,
            "resource": self.core_names[resource],
            "connection_id": a.connection_id,
            "plan_key": plan,
            "run_id": run["run_id"],
            "status": "running",
            "pending_raw_id": cp.get("pending_raw_id"),
            "mode": "sync",
            "filters": config,
            "position": cp.get("position") or {},
            "updated_at": now(),
            "completed_to": None,
            "high_id": None,
        }
        run.update(status="running", error_summary=None, finished_at=None)
        self.repo.write(
            {
                "sync_runs": [run],
                "sync_checkpoints": [cp],
                **({"meta_account_bindings": [self._binding()]} if self.auto_binding else {}),
            }
        )
        retry_baseline = self.connector.retries
        event(
            "sync_started",
            run_id=run["run_id"],
            store_id=a.store_id,
            resource=self.core_names[resource],
        )

        def promote(raw: dict[str, Any]) -> bool:
            if raw.get("pagination_error"):
                raise SafeError(raw["pagination_error"])
            batch = self._transform(raw)
            if batch.failed:
                # Fail closed: no partial CORE page or cursor advance on validation failure.
                # RAW and captured metrics remain durable; replay after a fix can recover.
                if batch.rows.get("quality_results"):
                    self.repo.write({"quality_results": batch.rows["quality_results"]})
                failure = dict(run)
                failure["core_records_failed"] += batch.failed
                metrics.aliases(failure)
                # Failure count is diagnostic for this attempt, not committed promotion.
                self.repo.write({"sync_runs": [failure]})
                raise SafeError("meta_page_requires_review")
            metrics.promoted(run, raw, batch)
            finished = raw["next_position"] is None
            cp.update(
                pending_raw_id=None,
                position=raw["next_position"] or {},
                status="extracted" if finished else "running",
                updated_at=now(),
            )
            batch.add("sync_runs", run)
            batch.add("sync_checkpoints", cp)
            self.repo.write(batch.rows)
            return finished

        try:
            if cp["pending_raw_id"]:
                pending = self.repo.read(table, a.store_id, [cp["pending_raw_id"]])
                if not pending:
                    raise SafeError("pending_raw_not_found")
                # Failed validation counters describe latest attempt, avoid recount on retry.
                run["core_records_failed"] = 0
                metrics.aliases(run)
                done = promote(pending[0])
            if not done:
                for page in self.connector.pages(resource, insights, cp["position"]):
                    raw = {
                        "row_key": page.request_id,
                        "raw_record_id": page.request_id,
                        "store_id": a.store_id,
                        "source_system": "meta",
                        "resource": resource,
                        "source_connection_id": a.connection_id,
                        "run_id": run["run_id"],
                        "request_id": page.request_id,
                        "ingested_at": now(),
                        "position": page.position,
                        "next_position": page.next_position,
                        "request_filters": config,
                        "payload": page.payload,
                        "payload_hash": digest(page.payload),
                        "connector_version": self.connector_version,
                        "spec_version": a.api_version,
                        "spec_sha256": None,
                        "sanitization_version": POLICY_VERSION,
                        "bytes_read": page.bytes_read,
                        "pagination_error": page.pagination_error,
                    }
                    # A failed HTTP call has no promotable records. Preserve its RAW
                    # audit, keep the cursor unchanged, and allow the next run to retry it.
                    retry_http = (
                        page.pagination_error
                        in {"meta_request_failed", "meta_retry_deferred", "meta_invalid_response"}
                        and not page.payload["data"]
                    )
                    cp.update(
                        pending_raw_id=None if retry_http else page.request_id, updated_at=now()
                    )
                    metrics.captured(run, raw)
                    self.repo.write({table: [raw], "sync_runs": [run], "sync_checkpoints": [cp]})
                    done = promote(raw)
                    if done:
                        break
            run.update(
                status="completed",
                finished_at=now(),
                retries=run["retries"] + self.connector.retries - retry_baseline,
            )
            cp.update(status="complete", updated_at=now())
            # completed_to stays NULL: source DATE is not a UTC watermark.
            self.repo.write({"sync_runs": [run], "sync_checkpoints": [cp]})
            event(
                "sync_finished",
                run_id=run["run_id"],
                resource=self.core_names[resource],
                status=run["status"],
                source_records_read=run["source_records_read"],
                core_records_processed=run["core_records_processed"],
            )
            return run
        except Exception as exc:
            self._fail(run, exc)

    def _fail(self, run: dict[str, Any], exc: Exception) -> NoReturn:
        code = exc.code if isinstance(exc, SafeError) else "internal_failure"
        if code != "bigquery_write_outcome_unknown":
            persisted = self.repo.read("sync_runs", self.account.store_id, [run["run_id"]])
            state = persisted[0] if persisted else run
            state.update(status="failed", finished_at=now(), error_summary=code)
            self.repo.write({"sync_runs": [state]})
        event("job_failed", run_id=run["run_id"], resource=run["resource"], code=code)
        raise SafeError(code) from None

    def replay(self, resource: str, original_run_id: str) -> dict[str, Any]:
        if resource not in CORE:
            raise SafeError("invalid_meta_resource_configuration")
        with self.lease():
            run = self._report(resource, original_run_id, "replay")
            self.repo.write({"sync_runs": [run]})
            found = False
            try:
                for raw in self.repo.iter_find(
                    "meta_raw_" + resource, self.account.store_id, "run_id", [original_run_id]
                ):
                    if raw["request_filters"]["account"] != self.account.snapshot():
                        raise SafeError("meta_replay_account_configuration_mismatch")
                    found = True
                    if raw.get("pagination_error") and not raw["payload"]["data"]:
                        raise SafeError("meta_raw_contains_failed_request_retry_sync")
                    # Source configuration, observation time and RAW identity preserved.
                    batch = self._transform({**raw, "run_id": run["run_id"]})
                    if batch.failed:
                        failure = dict(run)
                        failure["core_records_failed"] += batch.failed
                        metrics.aliases(failure)
                        self.repo.write({"sync_runs": [failure]})
                        self.repo.write({"quality_results": batch.rows.get("quality_results", [])})
                        raise SafeError("meta_page_requires_review")
                    metrics.promoted(run, raw, batch)
                    batch.add("sync_runs", run)
                    self.repo.write(batch.rows)
                if not found:
                    raise SafeError("replay_run_not_found")
                run.update(status="completed", finished_at=now())
                self.repo.write({"sync_runs": [run]})
                return run
            except Exception as exc:
                self._fail(run, exc)


def extract_foundation_offline(
    connector: MetaConnector,
    resource: str,
    insights: Insights | None = None,
    *,
    observed_at: str,
    max_records: int = 100000,
) -> dict[str, Any]:
    """Bounded, memory-only extraction: sanitized RAW pages before proposed projection.

    No repository, cloud client, checkpoint or persistence. Nothing returned on failure.
    The existing MetaEngine remains the separate durable offline reference.
    """
    from src.connectors.meta.foundation import MetaFoundationConnector
    from src.normalization.meta import normalize_foundation
    from src.quality.meta import validate_foundation

    if not isinstance(connector, MetaFoundationConnector) or max_records < 1:
        raise SafeError("meta_foundation_mock_connector_required")
    raw: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for page in connector.pages(resource, insights):
        if page.pagination_error:
            raise SafeError(page.pagination_error)
        raw.append(
            {
                "store_id": connector.account.store_id,
                "account_id": connector.account.account_id,
                "observed_at": observed_at,
                "position": page.position,
                "next_position": page.next_position,
                "payload": page.payload,
                "resource": resource,
                "configuration": {
                    "account": connector.account.snapshot(),
                    "insights": (
                        {**insights.snapshot(), "level": connector.insights_level}
                        if insights
                        else None
                    ),
                },
            }
        )
        if len(rows) + len(page.payload["data"]) > max_records:
            raise SafeError("meta_offline_record_budget_exceeded")
        rows.extend(
            normalize_foundation(
                resource,
                source,
                connector.account,
                insights,
                observed_at=observed_at,
                level=connector.insights_level,
            )
            for source in page.payload["data"]
        )
    validate_foundation(resource, rows, connector.account)
    return {"raw_pages": raw, "table": CORE[resource], "rows": rows, "status": "completed_offline"}
