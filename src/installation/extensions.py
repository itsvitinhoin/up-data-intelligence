"""Purpose-isolated V2 work for installed stores; initial graph remains immutable.

Pure planning only. No SDK, source IO, Registry write or automatic history request.
The caller must resolve tenant/workspace ownership and hold canonical store leases
before persisting any calculated plan. Dates use exclusive local ends internally.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.connectors.meta.config import Account, Insights
from src.control_plane.model import StoreConfig, instant
from src.control_plane.recurring import meta_coverage
from src.domain.models import SafeError
from src.ingestion.planning import filters_for
from src.installation.adoption import inspect, prefix
from src.installation.model import (
    DEFAULT_LIMITS,
    VERSION,
    Limits,
    Row,
    config_hash,
    local_days,
    unit,
)
from src.utils.data import digest

PURPOSES = frozenset(
    {"CATALOG_SNAPSHOT", "META_CREATIVE_COVERAGE", "HISTORY_EXTENSION", "META_SOURCE_ADDITION"}
)


def admissible(config: StoreConfig) -> None:
    if (
        config.status not in {"ACTIVE", "READY"}
        or config.sync_enabled != (config.status == "ACTIVE")
        or not config.operation_b2b
    ):
        raise SafeError("extension_store_not_admissible")
    config.ready()


def source_identity(config: StoreConfig, source: Row, system: str) -> str:
    if system not in {"upzero", "meta"}:
        raise SafeError("extension_provider_unavailable")
    if (
        source.get("store_id") != config.store_id
        or source.get("connection_id") != getattr(config, system + "_connection_id")
        or source.get("source_system") != system
        or source.get("status") != "active"
    ):
        raise SafeError("extension_source_not_active")
    if system == "meta" and source.get("secret_resource_name") is not None:
        raise SafeError("extension_meta_global_secret_required")
    # Reference metadata only. Never include a secret value or credential digest.
    return digest(
        {
            k: source.get(k)
            for k in (
                "row_key",
                "store_id",
                "connection_id",
                "source_system",
                "secret_resource_name",
                "status",
                "updated_at",
            )
        }
    )


def missing(start: str, end: str, coverage: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Subtract certified intervals. Gaps are retained, never collapsed with MIN/MAX."""
    cursor, stop = instant(start), instant(end)
    gaps = []
    for left, right in sorted((instant(a), instant(b)) for a, b in coverage):
        if left >= right:
            raise SafeError("extension_coverage_invalid")
        if right <= cursor or left >= stop:
            continue
        if left > cursor:
            gaps.append((cursor.isoformat(), min(left, stop).isoformat()))
        cursor = max(cursor, min(right, stop))
        if cursor >= stop:
            break
    if cursor < stop:
        gaps.append((cursor.isoformat(), stop.isoformat()))
    return gaps


class ExtensionPlanner:
    def __init__(self, limits: Limits = DEFAULT_LIMITS):
        self.limits = limits

    def calculate(
        self,
        config: StoreConfig,
        source: Row,
        purpose: str,
        start_day: str,
        end_day: str,
        at: str,
        *,
        requested_by_hash: str,
        checkpoints: list[Row],
        runs: list[Row],
        publication: Row,
        account: Account | None = None,
        reporting: Insights | None = None,
    ) -> tuple[Row, list[Row]]:
        admissible(config)
        if (
            purpose not in PURPOSES
            or not isinstance(requested_by_hash, str)
            or len(requested_by_hash) != 64
            or any(c not in "0123456789abcdef" for c in requested_by_hash)
        ):
            raise SafeError("extension_request_invalid")
        try:
            start, end = date.fromisoformat(start_day), date.fromisoformat(end_day)
            zone = ZoneInfo(config.timezone or "")
            cutoff = instant(at).astimezone(zone).date()
            if start >= end or end > cutoff or (end - start).days > 3660:
                raise ValueError("range")
            left = datetime.combine(start, time(), zone).astimezone(UTC).isoformat()
            right = datetime.combine(end, time(), zone).astimezone(UTC).isoformat()
        except (ValueError, TypeError):
            raise SafeError("extension_closed_range_required") from None
        if (
            publication.get("store_id") != config.store_id
            or publication.get("history_complete") is not config.history_complete
            or not publication.get("policy_hash")
            or not publication.get("publication_id")
            or type(publication.get("generation")) is not int
            or publication["generation"] < 1
        ):
            raise SafeError("extension_certified_publication_required")
        if end_day > str(publication.get("report_to")):
            raise SafeError("extension_outside_certified_cutoff")
        system = (
            "upzero"
            if purpose == "CATALOG_SNAPSHOT"
            else "meta"
            if purpose in {"META_CREATIVE_COVERAGE", "META_SOURCE_ADDITION"}
            else source.get("source_system")
        )
        if system not in {"upzero", "meta"}:
            raise SafeError("extension_provider_unavailable")
        fingerprint = source_identity(config, source, system)
        identity = digest(
            [
                config.store_id,
                system,
                source["connection_id"],
                purpose,
                left,
                right,
                config_hash(config),
                fingerprint,
                publication["policy_hash"],
                "extension.v1",
            ]
        )
        plan: Row = dict(
            row_key=identity,
            plan_id=identity,
            onboarding_operation_id=None,
            store_id=config.store_id,
            status="RUNNING",
            revision=1,
            planner_version=VERSION,
            registry_revision=config.revision,
            config_hash=config_hash(config),
            requested_from=left,
            target_as_of=right,
            created_at=at,
            updated_at=at,
            completed_at=None,
            error_code=None,
            priority=10,
            adopted_coverage={
                "extension": {
                    "version": "1.0.0",
                    "purpose": purpose,
                    "source": system,
                    "connection_id": source["connection_id"],
                    "source_metadata_hash": fingerprint,
                    "requested_by_hash": requested_by_hash,
                    "publication": publication,
                },
                "orders": [],
                "analytics_facts": [],
            },
        )
        units: list[Row] = []
        if purpose == "CATALOG_SNAPSHOT":
            if end_day != str(publication["report_to"]) or start != end - timedelta(days=1):
                raise SafeError("catalog_current_cutoff_required")
            units.append(
                unit(
                    plan,
                    "upzero",
                    source["connection_id"],
                    "catalog",
                    "SYNC_SNAPSHOT",
                    {"catalog_as_of": publication["as_of"]},
                    [],
                    0,
                    mode="incremental",
                )
            )
        elif system == "upzero":
            evidence = inspect(config, checkpoints, runs, publication["as_of"])
            if evidence["pending"]:
                raise SafeError("extension_pending_checkpoint_requires_reconciliation")
            plan["adopted_coverage"].update(evidence["coverage"])
            for resource in ("orders", "analytics_facts"):
                gaps = missing(left, right, evidence["coverage"][resource])
                for a, b in gaps:
                    # Provider Orders is local-day based, Facts is precise timestamps.
                    windows = (
                        local_days(a, b, config.timezone or "")
                        if resource == "orders"
                        else [(a, b)]
                    )
                    for wa, wb in windows:
                        if resource == "analytics_facts":
                            # At most one local day of Facts per logical unit.
                            pieces = []
                            cursor = instant(wa)
                            stop = instant(wb)
                            while cursor < stop:
                                boundary = min(cursor + timedelta(days=1), stop)
                                pieces.append((cursor.isoformat(), boundary.isoformat()))
                                cursor = boundary
                        else:
                            pieces = [(wa, wb)]
                        for pa, pb in pieces:
                            filters = filters_for(
                                resource, instant(pa), instant(pb), config.timezone or ""
                            )
                            row = unit(
                                plan,
                                "upzero",
                                source["connection_id"],
                                resource,
                                "SYNC_WINDOW",
                                filters,
                                [],
                                len(units),
                                mode="backfill",
                            )
                            row["checkpoint_plan_key"] = digest(
                                [
                                    config.store_id,
                                    source["connection_id"],
                                    resource,
                                    filters,
                                    "backfill",
                                ]
                            )
                            units.append(row)
            # Publication is only planned when both resources become contiguous with
            # the currently certified range. A disjoint old range remains CORE-only.
            publish_start = min(start_day, str(publication["report_from"]))
            pub_left = (
                datetime.combine(date.fromisoformat(publish_start), time(), zone)
                .astimezone(UTC)
                .isoformat()
            )
            pub_right = publication["as_of"]
            complete = True
            for resource in ("orders", "analytics_facts"):
                intervals = evidence["coverage"][resource] + [(left, right)]
                complete &= instant(prefix(pub_left, pub_right, intervals)) == instant(pub_right)
            if complete and publish_start < str(publication["report_from"]):
                units.append(
                    unit(
                        plan,
                        "analytics",
                        "analytics:" + config.store_id,
                        "publication",
                        "PUBLISH_ANALYTICS",
                        {
                            "report_from": publish_start,
                            "report_to": publication["report_to"],
                            "as_of": publication["as_of"],
                            "facts_complete": True,
                        },
                        [r["work_unit_id"] for r in units],
                        len(units),
                    )
                )
        else:
            if (
                account is None
                or reporting is None
                or account.store_id != config.store_id
                or account.connection_id != source["connection_id"]
                or reporting.breakdowns
            ):
                raise SafeError("extension_meta_definition_required")
            if purpose == "META_SOURCE_ADDITION":
                # Addition admits a previously absent connection. Existing source
                # evidence must be reconciled instead of silently reinstalling it.
                if any(
                    r.get("store_id") == config.store_id
                    and r.get("connection_id") == source["connection_id"]
                    for r in checkpoints + runs
                ):
                    raise SafeError("extension_source_addition_evidence_exists")
                previous: list[str] = []
                for resource_name in ("accounts", "campaigns", "adsets", "ads"):
                    row = unit(
                        plan,
                        "meta",
                        source["connection_id"],
                        resource_name,
                        "META_CATALOG",
                        {},
                        previous,
                        len(units),
                        mode="sync",
                    )
                    units.append(row)
                    previous = [row["work_unit_id"]]
                day = start
                while day < end:
                    report = Insights(
                        day.isoformat(),
                        day.isoformat(),
                        reporting.action_report_time,
                        reporting.action_attribution_windows,
                        reporting.purchase_action_type,
                    )
                    for resource_name in ("insights", "creative_insights"):
                        units.append(
                            unit(
                                plan,
                                "meta",
                                source["connection_id"],
                                resource_name,
                                "META_INSIGHTS",
                                report.snapshot(),
                                previous,
                                len(units),
                                mode="sync",
                            )
                        )
                    day += timedelta(days=1)
                if len(units) > self.limits.max_units:
                    raise SafeError("installation_plan_too_large")
                return plan, units
            level, resource = (
                ("ad", "meta_creative_insights_daily")
                if purpose == "META_CREATIVE_COVERAGE"
                else ("campaign", "meta_live_insights_daily")
            )
            day = start
            while day < end:
                report = Insights(
                    day.isoformat(),
                    day.isoformat(),
                    reporting.action_report_time,
                    reporting.action_attribution_windows,
                    reporting.purchase_action_type,
                )
                try:
                    meta_coverage(
                        account, report, checkpoints, runs, level=level, resource=resource
                    )
                except SafeError as exc:
                    # Missing coverage may create work, existing nonterminal evidence
                    # must never be bypassed with a new checkpoint or definition.
                    for cp in checkpoints:
                        spec = (cp.get("filters") or {}).get("insights") or {}
                        if (
                            cp.get("store_id") == config.store_id
                            and cp.get("connection_id") == source["connection_id"]
                            and cp.get("resource") == resource
                            and spec.get("since", "") <= day.isoformat() <= spec.get("until", "")
                        ):
                            raise SafeError(
                                "extension_pending_checkpoint_requires_reconciliation"
                            ) from None
                    if exc.code != "meta_complete_checkpoint_required":
                        raise
                    units.append(
                        unit(
                            plan,
                            "meta",
                            source["connection_id"],
                            "creative_insights" if level == "ad" else "insights",
                            "META_INSIGHTS",
                            report.snapshot(),
                            [],
                            len(units),
                            mode="sync",
                        )
                    )
                day += timedelta(days=1)
        if len(units) > self.limits.max_units:
            raise SafeError("installation_plan_too_large")
        if not units:
            plan.update(status="COMPLETE", completed_at=at)
        return plan, units


def validate_extension(plan: Row, config: StoreConfig, source: Row) -> None:
    admissible(config)
    contract = plan.get("adopted_coverage", {}).get("extension", {})
    if (
        contract.get("version") != "1.0.0"
        or contract.get("purpose") not in PURPOSES
        or plan.get("store_id") != config.store_id
        or plan.get("planner_version") != VERSION
        or plan.get("config_hash") != config_hash(config)
        or source_identity(config, source, contract.get("source", ""))
        != contract.get("source_metadata_hash")
    ):
        raise SafeError("extension_configuration_changed")
