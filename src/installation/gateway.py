"""One POST, bounded GETs. Losing a POST response is never a retry signal."""

import re
from typing import Any

import httpx

from src.domain.models import SafeError
from src.installation.model import DEFAULT_LIMITS, Limits, Row

JOBS = {s: "up-installation-" + s + "-worker" for s in ("upzero", "meta", "analytics")}


class InstallationGateway:
    def __init__(
        self,
        client: httpx.Client,
        project: str,
        region: str,
        bucket: str,
        *,
        project_number: str | None = None,
        maximum_bytes_billed: int = 1073741824,
        maximum_total_bytes_billed: int = 137438953472,
        limits: Limits = DEFAULT_LIMITS,
        extension: bool = False,
    ):
        self.client, self.project, self.region, self.bucket = client, project, region, bucket
        self.extension = extension
        self.prefix = f"projects/{project}/locations/{region}/"
        self.prefixes = {self.prefix}
        if project_number:
            if not project_number.isdigit():
                raise SafeError("invalid_project_number")
            self.prefixes.add(f"projects/{project_number}/locations/{region}/")
        self.bytes, self.total, self.limits = (
            maximum_bytes_billed,
            maximum_total_bytes_billed,
            limits,
        )

    def validate(self, name: str, kind: str, pipeline: str | None = None) -> None:
        tail = (
            "operations/"
            if kind == "operation"
            else f"jobs/{JOBS.get(pipeline or '', '')}/executions/"
        )
        if not any(
            name.startswith(p + tail) and re.fullmatch(r"[A-Za-z0-9_-]+", name[len(p + tail) :])
            for p in self.prefixes
        ):
            raise SafeError("work_dispatch_unknown")

    def submit(self, row: Row) -> str:
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
            "--worker",
            "--store-id",
            row["store_id"],
            "--confirm-store",
            row["store_id"],
            "--work-unit-id",
            row["work_unit_id"],
            "--expected-revision",
            str(row["revision"]),
            "--dispatch-token",
            row["dispatch_token"],
            "--pipeline",
            row["pipeline"],
            "--page-budget",
            str(self.limits.page_budget),
            "--soft-time-budget-seconds",
            str(self.limits.soft_time_budget_seconds),
            "--maximum-bytes-billed",
            str(self.bytes),
            "--maximum-total-bytes-billed",
            str(self.total),
        ]
        if self.extension:
            args.append("--extension")
        try:
            response = self.client.post(
                "https://run.googleapis.com/v2/"
                + self.prefix
                + f"jobs/{JOBS[row['pipeline']]}:run",
                json={
                    "overrides": {
                        "containerOverrides": [{"name": "worker", "args": args}],
                        "taskCount": 1,
                    }
                },
            )
            if response.status_code in {400, 401, 403, 404}:
                raise SafeError("installation_launch_rejected")
            response.raise_for_status()
            name = response.json()["name"]
            self.validate(name, "operation")
            return str(name)
        except SafeError:
            raise
        except Exception:
            raise SafeError("work_dispatch_unknown") from None

    def operation(self, name: str) -> Row:
        self.validate(name, "operation")
        return self._get(name)

    def execution(self, name: str, pipeline: str) -> Row:
        self.validate(name, "execution", pipeline)
        return self._get(name)

    def _get(self, name: str) -> dict[str, Any]:
        try:
            response = self.client.get("https://run.googleapis.com/v2/" + name)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except Exception:
            raise SafeError("work_execution_outcome_unknown") from None
