"""Installation is operational evidence, not a claim of complete customer history."""

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal, ReadError, integer
from src.dashboard.installation_queries import build_installation
from src.dashboard.queries import build
from src.dashboard.repository import Reader
from src.dashboard.service import resolve_publication

ResourceState = Literal["PENDING", "RUNNING", "PARTIAL", "COMPLETE", "BLOCKED"]
InstallationState = Literal["INSTALLING", "PARTIAL", "READY", "BLOCKED", "OUTCOME_UNKNOWN"]


def stamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError
        return at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError):
        raise ReadError(503, "installation_metadata_invalid") from None


def safe_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ReadError(503, "installation_metadata_invalid")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,199}", value):
        raise ReadError(503, "installation_metadata_invalid")
    return value


def flag(value: Any) -> bool | None:
    if value is not None and type(value) is not bool:
        raise ReadError(503, "installation_metadata_invalid")
    return value


def count(value: Any) -> int | None:
    result = integer(value)
    if result is not None and (result < 0 or result > 2**53 - 1):
        raise ReadError(503, "installation_metadata_invalid")
    return result


@dataclass(frozen=True)
class InstallationProgress:
    kind: Literal["RECORDS", "TIME_COVERAGE", "CHUNKS", "UNKNOWN"]
    percent: float | None = None
    processed: int | None = None
    total: int | None = None
    eta_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"RECORDS", "TIME_COVERAGE", "CHUNKS", "UNKNOWN"}:
            raise ValueError("invalid_progress")
        for value in (self.processed, self.total, self.eta_seconds):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("invalid_progress")
        if self.percent is not None and (
            type(self.percent) not in {int, float}
            or not math.isfinite(self.percent)
            or self.processed is None
            or self.total is None
            or self.total <= 0
            or self.processed > self.total
            or self.percent != self.processed / self.total * 100
        ):
            raise ValueError("progress_denominator_required")


@dataclass(frozen=True)
class InstallationCoverage:
    # Local DATE interval, exclusive upper boundary, compatible with Read API.
    from_day: str
    to: str
    reason: str
    resources: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "from": self.from_day,
            "to": self.to,
            "reason": self.reason,
            "resources": list(self.resources),
        }


@dataclass(frozen=True)
class InstallationResource:
    source: str
    connection_id: str | None
    resource: str
    state: ResourceState
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    mode: str | None = None
    records_read: int | None = None
    records_processed: int | None = None
    records_failed: int | None = None
    pending_raw: bool | None = None
    coverage_from: str | None = None
    coverage_to: str | None = None
    updated_at: str | None = None
    last_success_at: str | None = None
    last_error_code: str | None = None


@dataclass(frozen=True)
class InstallationSource:
    source: str
    connection_id: str | None
    configured: bool
    active: bool | None
    state: ResourceState
    last_success_at: str | None
    last_error_code: str | None


def resource_state(row: dict[str, Any]) -> ResourceState:
    checkpoint = row.get("checkpoint_status")
    # Recovered is terminal; the historical run may still say failed/errors.
    if count(row.get("blocked_count")):
        return "BLOCKED"
    if count(row.get("pending_count")) or count(row.get("pending_raw_count")):
        return "RUNNING"
    if checkpoint in {"complete", "recovered"} and row.get("pending_raw") is False:
        return "COMPLETE"
    return "PENDING"


def checkpoint_window(row: dict[str, Any], timezone: str) -> tuple[str | None, str | None]:
    if resource_state(row) != "COMPLETE":
        return None, None
    filters = row.get("filters")
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except ValueError:
            return None, None
    if not isinstance(filters, dict):
        return None, None
    try:
        if filters.get("from") and filters.get("to"):
            start, end = stamp(filters["from"]), stamp(filters["to"])
        elif filters.get("start_date") and filters.get("end_date"):
            zone = ZoneInfo(timezone) if row["resource"] == "orders" else UTC
            start = stamp(datetime.combine(date.fromisoformat(filters["start_date"]), time(), zone))
            end = stamp(
                datetime.combine(
                    date.fromisoformat(filters["end_date"]) + timedelta(days=1), time(), zone
                )
            )
        else:
            return None, None  # ID pagination/customers snapshot has no dated coverage.
        return (start, end) if start and end and start < end else (None, None)
    except (ValueError, KeyError, ReadError):
        return None, None


class InstallationReader:
    def __init__(
        self,
        project: str,
        policies: Mapping[str, AnalyticsPolicy],
        reader_factory: Callable[[], Reader],
    ):
        self.project, self.policies, self.reader_factory = project, policies, reader_factory

    def read(self, principal: Principal | None, grant: Grant) -> dict[str, Any]:
        if principal is None:
            raise ReadError(401, "unauthenticated")
        principal.authorize(grant.tenant_id, grant.store_id, grant.operation)
        reader = self.reader_factory()
        request_id = uuid4().hex

        def query(name: str, snapshot: str | None = None) -> list[dict[str, Any]]:
            return reader.query(
                build_installation(self.project, name, grant.store_id, snapshot),
                request_id=request_id,
                store_id=grant.store_id,
                generation=None,
            )

        registries = query("installation_registry")
        if not registries:
            raise ReadError(404, "store_not_configured")
        if len(registries) != 1 or registries[0].get("store_id") != grant.store_id:
            raise ReadError(503, "installation_registry_invalid")
        registry = registries[0]
        if registry.get("operation_b2b") is not True:
            raise ReadError(403, "store_operation_forbidden")
        snapshot = stamp(registry.get("snapshot_at"))
        if snapshot is None:
            raise ReadError(503, "installation_metadata_invalid")
        history, facts = (
            flag(registry.get("history_complete")),
            flag(registry.get("facts_complete")),
        )
        timezone = registry.get("timezone")
        if not isinstance(timezone, str):
            raise ReadError(503, "installation_metadata_invalid")
        try:
            ZoneInfo(timezone)
        except (TypeError, ValueError, KeyError):
            raise ReadError(503, "installation_metadata_invalid") from None
        connections = query("installation_sources", snapshot)
        rows = query("installation_resources", snapshot)
        if len(connections) > 100 or len(rows) > 500:
            raise ReadError(503, "installation_metadata_limit_exceeded")
        keys = [(r.get("source_system"), r.get("connection_id")) for r in connections]
        if len(keys) != len(set(keys)) or len({r.get("connection_id") for r in connections}) != len(
            connections
        ):
            raise ReadError(503, "installation_connections_invalid")
        expected = {
            source: registry.get(f"{source}_connection_id")
            for source in ("upzero", "meta")
            if registry.get(f"{source}_enabled") is True
        }
        selected = [
            c
            for c in connections
            if c["source_system"] not in {"upzero", "meta"}
            or (
                c["source_system"] in expected
                and c["connection_id"] == expected[c["source_system"]]
            )
        ]
        sources: list[InstallationSource] = []
        resources: list[InstallationResource] = []
        for source, connection_id in expected.items():
            if not any(c["source_system"] == source for c in selected):
                sources.append(
                    InstallationSource(
                        source, connection_id, False, None, "PENDING", None, "source_not_configured"
                    )
                )
                if source == "upzero":
                    resources.extend(
                        InstallationResource(source, connection_id, r, "PENDING")
                        for r in ("customers", "orders", "analytics_facts")
                    )
        for connection in selected:
            source, cid = safe_id(connection["source_system"]), safe_id(connection["connection_id"])
            active = (
                True
                if connection.get("status") == "active"
                else False
                if connection.get("status") in {"inactive", "disabled"}
                else None
            )
            pending_source = connection.get("status") == "pending"
            evidence = [
                r for r in rows if r.get("source") == source and r.get("connection_id") == cid
            ]
            names = sorted(
                {safe_id(r["resource"]) for r in evidence}
                | ({"customers", "orders", "analytics_facts"} if source == "upzero" else set())
            )
            for name in names:
                matched = [r for r in evidence if r["resource"] == name]
                if len(matched) > 1:
                    raise ReadError(503, "installation_resources_invalid")
                if not matched:
                    resources.append(
                        InstallationResource(
                            source, cid, name, "PENDING" if active or pending_source else "BLOCKED"
                        )
                    )
                    continue
                r = matched[0]
                state = "PENDING" if pending_source else resource_state(r) if active else "BLOCKED"
                start, end = checkpoint_window(r, timezone)
                modern = r.get("metrics_version") == 2
                resources.append(
                    InstallationResource(
                        source,
                        cid,
                        name,
                        state,
                        safe_id(r["run_id"]) if r.get("run_id") is not None else None,
                        r["run_status"]
                        if r.get("run_status")
                        in {"running", "completed", "completed_with_errors", "failed"}
                        else None,
                        r["mode"]
                        if r.get("mode")
                        in {"backfill", "incremental", "open_orders", "replay", "reconcile"}
                        else None,
                        count(r.get("source_records_read")) if modern else None,
                        count(r.get("core_records_processed")) if modern else None,
                        count(r.get("core_records_failed")) if modern else None,
                        (
                            bool(count(r.get("pending_raw_count")))
                            if r.get("pending_raw_count") is not None
                            else None
                        ),
                        start,
                        end,
                        stamp(r.get("updated_at")),
                        stamp(r.get("last_success_at")),
                        "sync_requires_review" if state == "BLOCKED" else None,
                    )
                )
            own = [r for r in resources if r.connection_id == cid]
            state = (
                "PENDING"
                if pending_source
                else "BLOCKED"
                if not active or any(r.state == "BLOCKED" for r in own)
                else "RUNNING"
                if any(r.state == "RUNNING" for r in own)
                else "COMPLETE"
                if own and all(r.state == "COMPLETE" for r in own)
                else "PARTIAL"
                if any(r.state == "COMPLETE" for r in own)
                else "PENDING"
            )
            successes = [r.last_success_at for r in own if r.last_success_at is not None]
            sources.append(
                InstallationSource(
                    source,
                    cid,
                    True,
                    active,
                    state,
                    max(successes) if successes else None,
                    "source_inactive"
                    if active is False
                    else "source_status_unknown"
                    if active is None and not pending_source
                    else "sync_requires_review"
                    if state == "BLOCKED"
                    else None,
                )
            )
        plans = query("installation_plans", snapshot)
        work = query("installation_units", snapshot) if plans else []
        if (
            len(plans) > 1
            or len(work) > 10000
            or any(p.get("store_id") != grant.store_id for p in plans)
            or any(
                r.get("store_id") != grant.store_id or r.get("plan_id") != plans[0]["plan_id"]
                for r in work
            )
        ):
            raise ReadError(503, "installation_metadata_invalid")
        limitations = ["history_incomplete"] if history is not True else []
        if facts is not True:
            limitations.append("facts_incomplete")
        window = None
        publication = None
        policy = self.policies.get(grant.store_id)
        if plans:
            from src.control_plane.model import StoreConfig
            from src.installation.publication import available

            config = StoreConfig.from_row({k: v for k, v in registry.items() if k != "snapshot_at"})
            try:
                policy, publication = available(
                    reader, self.project, config, work, snapshot, request_id
                )
                if publication:
                    window = InstallationCoverage(
                        publication.report_from,
                        publication.report_to,
                        "analytics_head_receipt_certified",
                        ("overview", "customers", "orders", "retention", "products"),
                    )
            except ReadError:
                limitations.append("publication_invalid")
            if not publication:
                limitations.append("publication_unavailable")
        elif policy is not None:
            head = reader.query(
                build(
                    self.project,
                    "head",
                    store=grant.store_id,
                    policy=policy.policy_hash,
                    snapshot_at=snapshot,
                ),
                request_id=request_id,
                store_id=grant.store_id,
                generation=None,
            )
            if head:
                try:
                    publication = resolve_publication(head, policy)
                    if (
                        timezone != policy.reporting_timezone
                        or registry.get("currency") != policy.currency
                        or registry.get("policy_version") != policy.policy_version
                    ):
                        raise ReadError(503, "publication_registry_mismatch")
                    window = InstallationCoverage(
                        publication.report_from,
                        publication.report_to,
                        "analytics_head_receipt_certified",
                        ("overview", "customers", "orders", "retention", "products"),
                    )
                except ReadError:
                    publication = None
                    limitations.append("publication_invalid")
            else:
                limitations.append("publication_unavailable")
        else:
            limitations.append("publication_policy_unavailable")
        blocked = (
            registry.get("status") not in {"READY", "ACTIVE"} and registry.get("status") != "DRAFT"
        )
        blocked = (
            blocked
            or "publication_invalid" in limitations
            or any(s.state == "BLOCKED" for s in sources)
        )
        all_complete = bool(sources) and all(s.state == "COMPLETE" for s in sources)
        overall: InstallationState = (
            "BLOCKED"
            if blocked
            else "READY"
            if all_complete
            and history is True
            and facts is True
            and window
            and policy
            and policy.history_complete
            and policy.facts_complete
            else "PARTIAL"
            if window
            else "INSTALLING"
        )
        # Counters describe latest checkpoint-linked attempts, never unique lifetime totals.
        counters = [r.records_processed for r in resources]
        processed = (
            sum(c for c in counters if c is not None)
            if counters and all(c is not None for c in counters)
            else None
        )
        progress = InstallationProgress(
            "RECORDS" if processed is not None else "UNKNOWN", processed=processed
        )
        limitations.extend(
            [
                "installation_total_unknown",
                "eta_unknown",
                "latest_attempt_counters_not_unique_history",
            ]
        )
        updates = (
            [stamp(registry.get("updated_at"))]
            + [r.updated_at for r in resources]
            + [stamp(c.get("updated_at")) for c in selected]
        )
        if not any(v is not None for v in updates):
            updates = [snapshot]
            limitations.append("state_update_unknown")
        data = {
            "store_id": grant.store_id,
            "overall_state": overall,
            "updated_at": max(v for v in updates if v is not None),
            "history_complete": history,
            "facts_complete": facts,
            "facts_coverage_from": stamp(registry.get("facts_coverage_from")),
            "facts_coverage_to": stamp(registry.get("facts_coverage_to")),
            "sources": [asdict(s) for s in sources],
            "resources": [asdict(r) for r in resources],
            "available_window": window.payload() if window else None,
            "recommended_preview_window": window.payload() if window else None,
            "progress": asdict(progress),
            "limitations": sorted(set(limitations)),
        }
        if plans:
            from src.installation.model import AMBIGUOUS, PLAN_STATES, WORK_STATES
            from src.installation.progress import summarize

            plan = plans[0]
            if plan.get("status") not in PLAN_STATES or any(
                r.get("status") not in WORK_STATES for r in work
            ):
                raise ReadError(503, "installation_metadata_invalid")
            summary = summarize(work)
            summary["progress"]["eta_seconds"] = (
                round(summary["progress"]["eta_seconds"])
                if summary["progress"]["eta_seconds"] is not None
                else None
            )
            data.update(
                summary,
                installation_plan_id=safe_id(plan["plan_id"]),
                installation_plan_status=plan["status"],
            )
            ready = (
                plan["status"] == "COMPLETE"
                and all(r["status"] == "COMPLETE" for r in work)
                and facts is True
                and window is not None
                and bool(sources)
                and all(s.active is True for s in sources)
                and not any(r.pending_raw or r.state in {"RUNNING", "BLOCKED"} for r in resources)
                and not any(r["status"] in AMBIGUOUS for r in work)
            )
            data["overall_state"] = (
                "OUTCOME_UNKNOWN"
                if plan["status"] == "OUTCOME_UNKNOWN" or summary["work"]["ambiguous"]
                else "BLOCKED"
                if plan["status"] == "BLOCKED"
                or summary["work"]["blocked"]
                or "publication_invalid" in limitations
                else "READY"
                if ready
                else "PARTIAL"
                if window
                else "INSTALLING"
            )
            data["limitations"] = sorted(
                set(limitations)
                - {
                    "installation_total_unknown",
                    "latest_attempt_counters_not_unique_history",
                    "eta_unknown",
                }
            ) + (["eta_unknown"] if summary["progress"]["eta_seconds"] is None else [])
        return {
            "data": data,
            "pagination": None,
            "metadata": {
                "contract_version": "installation.v2" if plans else "installation.v1",
                "store_id": grant.store_id,
                "snapshot_at": snapshot,
                "generation": publication.generation if publication else None,
                "policy_hash": publication.policy_hash if publication else None,
                "reporting_timezone": timezone,
                "currency": registry.get("currency"),
            },
        }
