"""Non-secret registry configuration and explicit operational windows."""

import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.analytics.config import AnalyticsPolicy
from src.analytics.policy import ORDER_STATUSES, HistoryCoverage
from src.domain.models import SafeError
from src.utils.data import digest, timestamp

STATUSES = frozenset("DRAFT READY ACTIVE PAUSED ERROR DISABLED".split())
PIPELINES = ("upzero", "meta", "analytics", "intelligence")
JOBS = {name: f"up-{name}-worker" for name in PIPELINES}
# Explicit initial supported currencies; not a claim that every 3-letter string is ISO currency.
CURRENCIES = frozenset(
    "BRL USD EUR GBP CAD AUD MXN ARS CLP COP PEN JPY CNY CHF UYU PYG BOB NZD".split()
)
REGISTRY = "store_runtime_config"
REGISTRY_FIELDS = {
    "row_key": "STRING",
    "store_id": "STRING",
    "status": "STRING",
    "revision": "INT64",
    **dict.fromkeys(
        "store_name store_slug timezone currency policy_version upzero_connection_id meta_connection_id meta_account_id meta_api_version upzero_store_identifier".split(),
        "STRING",
    ),
    **dict.fromkeys(
        "operation_b2b operation_b2c history_complete facts_complete upzero_enabled meta_enabled analytics_enabled intelligence_enabled sync_enabled".split(),
        "BOOL",
    ),
    **dict.fromkeys(
        "history_from facts_coverage_from facts_coverage_to purchase_order_id_effective_at created_at updated_at".split(),
        "TIMESTAMP",
    ),
    "qualifying_order_statuses": "JSON",
    "history_coverage": "JSON",
}


@dataclass(frozen=True)
class Window:
    report_from: str
    report_to: str
    as_of: str
    source_snapshot_at: str
    calculated_at: str

    def __post_init__(self) -> None:
        a, b = date.fromisoformat(self.report_from), date.fromisoformat(self.report_to)
        if a >= b or (a.isoformat(), b.isoformat()) != (self.report_from, self.report_to):
            raise SafeError("invalid_operational_window")
        at, snapshot, calculated = map(
            instant, (self.as_of, self.source_snapshot_at, self.calculated_at)
        )
        if not at <= snapshot <= calculated:
            raise SafeError("invalid_operational_cutoffs")

    @classmethod
    def previous_closed_day(cls, timezone: str, at: str) -> "Window":
        current = instant(at)
        zone = ZoneInfo(timezone)
        end = current.astimezone(zone).date()
        cutoff = datetime.combine(end, time(), zone).astimezone(UTC).isoformat()
        return cls(
            (end - timedelta(days=1)).isoformat(),
            end.isoformat(),
            cutoff,
            timestamp(at),
            timestamp(at),
        )


def instant(value: str) -> datetime:
    return datetime.fromisoformat(timestamp(value))


@dataclass(frozen=True)
class StoreConfig:
    store_id: str
    status: str = "DRAFT"
    revision: int = 1
    store_name: str | None = None
    store_slug: str | None = None
    operation_b2b: bool = False
    operation_b2c: bool = False
    timezone: str | None = None
    currency: str | None = None
    policy_version: str | None = None
    history_from: str | None = None
    history_complete: bool = False
    facts_complete: bool = False
    facts_coverage_from: str | None = None
    facts_coverage_to: str | None = None
    qualifying_order_statuses: tuple[str, ...] = ()
    history_coverage: dict[str, Any] | None = None
    upzero_enabled: bool = False
    meta_enabled: bool = False
    analytics_enabled: bool = False
    intelligence_enabled: bool = False
    upzero_connection_id: str | None = None
    upzero_store_identifier: str | None = None
    purchase_order_id_effective_at: str | None = None
    meta_connection_id: str | None = None
    meta_account_id: str | None = None
    meta_api_version: str | None = None
    sync_enabled: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{0,99}", self.store_id)
            or self.status not in STATUSES
            or type(self.revision) is not int
            or not 1 <= self.revision < 2**63
        ):
            raise SafeError("invalid_store_registry_identity")
        for f in fields(self):
            if REGISTRY_FIELDS[f.name] == "BOOL" and type(getattr(self, f.name)) is not bool:
                raise SafeError("registry_boolean_required")
            if (
                REGISTRY_FIELDS[f.name] == "STRING"
                and getattr(self, f.name) is not None
                and (
                    not isinstance(getattr(self, f.name), str) or not getattr(self, f.name).strip()
                )
            ):
                raise SafeError("invalid_registry_string")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except (ValueError, KeyError):
                raise SafeError("invalid_store_timezone") from None
        if self.currency is not None and self.currency not in CURRENCIES:
            raise SafeError("unsupported_store_currency")
        for f in fields(self):
            if REGISTRY_FIELDS[f.name] == "TIMESTAMP" and getattr(self, f.name) is not None:
                instant(getattr(self, f.name))
        if len(set(self.qualifying_order_statuses)) != len(
            self.qualifying_order_statuses
        ) or not set(self.qualifying_order_statuses) <= ORDER_STATUSES - {"CANCELED"}:
            raise SafeError("invalid_commercial_policy")
        if self.meta_account_id is not None and not re.fullmatch(r"[0-9]+", self.meta_account_id):
            raise SafeError("invalid_meta_account")
        if self.meta_api_version is not None and not re.fullmatch(
            r"v[0-9]+\.0", self.meta_api_version
        ):
            raise SafeError("invalid_meta_api_version")

    def ready(self) -> None:
        if not (
            self.timezone
            and self.currency
            and self.history_from
            and (self.operation_b2b or self.operation_b2c)
        ):
            raise SafeError("store_configuration_incomplete")
        if self.upzero_enabled and not self.upzero_connection_id:
            raise SafeError("upzero_connection_required")
        if self.meta_enabled and not all(
            (self.meta_connection_id, self.meta_account_id, self.meta_api_version)
        ):
            raise SafeError("meta_binding_required")
        if self.analytics_enabled or self.intelligence_enabled:
            if not self.operation_b2b:
                raise SafeError("b2b_analytics_contract_required")
            if (
                not self.upzero_enabled
                or not self.policy_version
                or not self.qualifying_order_statuses
            ):
                raise SafeError("analytics_policy_and_b2b_sources_required")
        if self.intelligence_enabled and not (self.meta_enabled and self.analytics_enabled):
            raise SafeError("intelligence_dependencies_disabled")
        if self.facts_complete and not (
            self.facts_coverage_from
            and self.facts_coverage_to
            and instant(self.facts_coverage_from) < instant(self.facts_coverage_to)
        ):
            raise SafeError("explicit_facts_coverage_required")
        if self.history_complete:
            if not self.history_coverage:
                raise SafeError("history_coverage_required")
            proof = HistoryCoverage(**self.history_coverage)
            proof.validate(self.store_id, proof.verified_through)

    def eligible(self, pipeline: str) -> bool:
        if pipeline not in PIPELINES:
            raise SafeError("invalid_pipeline")
        return (
            self.status == "ACTIVE"
            and self.sync_enabled
            and getattr(self, pipeline + "_enabled") is True
        )

    def policy(self, window: Window) -> AnalyticsPolicy:
        """Build the current B2B contract; B2C capability does not extend its scope."""
        self.ready()
        if not self.operation_b2b or not self.policy_version or not self.qualifying_order_statuses:
            raise SafeError("analytics_policy_required")
        zone = ZoneInfo(self.timezone or "")
        observed_from = self.history_from or ""
        if self.facts_complete:
            start = datetime.combine(
                date.fromisoformat(window.report_from), time(), zone
            ).astimezone(UTC)
            end = datetime.combine(date.fromisoformat(window.report_to), time(), zone).astimezone(
                UTC
            )
            if (
                instant(self.facts_coverage_from or "") > start
                or instant(self.facts_coverage_to or "") < end
            ):
                raise SafeError("facts_window_not_certified")
            # A certified historical extension can precede the original onboarding
            # request. Read its observed orders on subsequent full refreshes too.
            # This is a source-read bound, never lifetime proof or a Registry edit.
            if not self.history_complete:
                if instant(self.facts_coverage_from or "") < instant(observed_from):
                    observed_from = self.facts_coverage_from or ""
        return AnalyticsPolicy(
            self.store_id,
            self.policy_version,
            self.timezone or "",
            self.currency,
            self.qualifying_order_statuses,
            self.history_complete,
            self.facts_complete,
            window.as_of,
            window.report_from,
            window.report_to,
            observed_from,
            HistoryCoverage(**self.history_coverage) if self.history_coverage else None,
        )

    def row(self) -> dict[str, Any]:
        return {"row_key": digest([self.store_id, REGISTRY]), **asdict(self)}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "StoreConfig":
        values = {k: v for k, v in row.items() if k != "row_key"}
        for k in ("qualifying_order_statuses", "history_coverage"):
            if isinstance(values.get(k), str):
                values[k] = json.loads(values[k])
        values["qualifying_order_statuses"] = tuple(values.get("qualifying_order_statuses") or ())
        for k, typ in REGISTRY_FIELDS.items():
            if typ == "TIMESTAMP" and isinstance(values.get(k), datetime):
                values[k] = values[k].isoformat()
        return cls(**values)
