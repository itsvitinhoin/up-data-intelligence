"""Injected Cloud Run REST adapter; no discovery or credentials on import."""

import time
from collections.abc import Callable
from typing import Any

import httpx

from src.control_plane.model import JOBS, StoreConfig, Window
from src.domain.models import SafeError


class RunGateway:
    def __init__(
        self,
        client: httpx.Client,
        project: str,
        region: str,
        bucket: str,
        *,
        project_number: str | None = None,
        maximum_bytes_billed: int,
        maximum_total_bytes_billed: int,
        sleep: Callable[[float], None] = time.sleep,
        timeout_seconds: float = 3900,
    ):
        self.client, self.project, self.region, self.bucket = client, project, region, bucket
        self.maximum_bytes_billed, self.maximum_total_bytes_billed = (
            maximum_bytes_billed,
            maximum_total_bytes_billed,
        )
        self.sleep, self.timeout_seconds = sleep, timeout_seconds
        self.prefix = f"projects/{project}/locations/{region}/"
        self.prefixes = {self.prefix}
        if project_number is not None:
            if not project_number.isdigit():
                raise SafeError("invalid_project_number")
            self.prefixes.add(f"projects/{project_number}/locations/{region}/")

    def get(self, name: str, kind: str, job: str | None = None) -> dict[str, Any]:
        tail = f"jobs/{job}/executions/" if kind == "executions" else "operations/"
        valid = any(
            name.startswith(prefix + tail)
            and len(name[len(prefix + tail) :].split("/")) == 1
            and bool(name[len(prefix + tail) :])
            for prefix in self.prefixes
        )
        if not valid:
            raise SafeError("worker_execution_outcome_unknown")
        response = self.client.get("https://run.googleapis.com/v2/" + name)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def run_and_wait(self, pipeline: str, config: StoreConfig, window: Window) -> bool:
        job = JOBS[pipeline]
        args = [
            "--live",
            "--project",
            self.project,
            "--confirm-project",
            self.project,
            "--location",
            self.region,
            "--lease-bucket",
            self.bucket,
            "--pipeline",
            pipeline,
            "--store-id",
            config.store_id,
            "--confirm-store",
            config.store_id,
            "--expected-revision",
            str(config.revision),
            "--report-from",
            window.report_from,
            "--report-to",
            window.report_to,
            "--as-of",
            window.as_of,
            "--source-snapshot-at",
            window.source_snapshot_at,
            "--calculated-at",
            window.calculated_at,
            "--maximum-bytes-billed",
            str(self.maximum_bytes_billed),
            "--maximum-total-bytes-billed",
            str(self.maximum_total_bytes_billed),
        ]
        submitted = False
        try:
            # No POST retries: losing a response does not prove that the execution was not created.
            submitted = True
            response = self.client.post(
                "https://run.googleapis.com/v2/" + self.prefix + f"jobs/{job}:run",
                json={
                    "overrides": {
                        "containerOverrides": [{"name": "worker", "args": args}],
                        "taskCount": 1,
                    }
                },
            )
            if response.status_code in {400, 401, 403, 404}:
                submitted = False
                raise SafeError("worker_launch_rejected")
            response.raise_for_status()
            operation = response.json()
            deadline = time.monotonic() + self.timeout_seconds
            while not operation.get("done"):
                if time.monotonic() >= deadline:
                    raise SafeError("worker_execution_outcome_unknown")
                self.sleep(2)
                operation = self.get(operation["name"], "operations")
            if operation.get("error"):
                # An operation error may still leave a running execution; reconcile manually.
                raise SafeError("worker_execution_outcome_unknown")
            execution = operation.get("response", {})
            name = execution["name"]
            # Validate even the initial completed response before trusting execution metadata.
            execution = self.get(name, "executions", job)
            while not execution.get("completionTime"):
                if time.monotonic() >= deadline:
                    raise SafeError("worker_execution_outcome_unknown")
                self.sleep(2)
                execution = self.get(name, "executions", job)
            return (
                execution.get("succeededCount") == 1
                and not execution.get("failedCount")
                and not execution.get("cancelledCount")
            )
        except SafeError:
            raise
        except Exception:
            raise SafeError(
                "worker_execution_outcome_unknown" if submitted else "worker_launch_rejected"
            ) from None
