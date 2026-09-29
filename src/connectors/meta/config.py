"""Explicit, non-secret account ownership and reporting configuration."""

import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from src.domain.models import SafeError
from src.utils.data import digest

RESOURCES = ("accounts", "campaigns", "adsets", "ads", "insights")
CORE = {r: "meta_" + ("insights_daily" if r == "insights" else r) for r in RESOURCES}


def meta_id(value: Any) -> str:
    # No integer coercion: leading zeroes belong to the source identifier.
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise SafeError("invalid_meta_id")
    return value


@dataclass(frozen=True)
class Account:
    store_id: str
    account_id: str
    connection_id: str
    api_version: str
    timezone: str
    currency: str

    def __post_init__(self) -> None:
        meta_id(self.account_id)
        if not self.store_id.strip() or not self.connection_id.strip():
            raise SafeError("meta_missing_owner")
        if not re.fullmatch(r"v[0-9]+\.0", self.api_version):
            raise SafeError("meta_api_version_required")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise SafeError("meta_currency_required")
        ZoneInfo(self.timezone)

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


def validate_accounts(accounts: tuple[Account, ...]) -> None:
    # Complete configuration inventory is mandatory, not a per-store subset.
    if len({a.account_id for a in accounts}) != len(accounts):
        raise SafeError("meta_account_requires_single_explicit_owner")


@dataclass(frozen=True)
class Insights:
    since: str
    until: str
    action_report_time: str
    action_attribution_windows: tuple[str, ...]
    purchase_action_type: str | None
    breakdowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            date.fromisoformat(self.since).isoformat() != self.since
            or date.fromisoformat(self.until).isoformat() != self.until
            or date.fromisoformat(self.since) > date.fromisoformat(self.until)
        ):
            raise SafeError("invalid_insights_date")
        if self.action_report_time not in {"impression", "conversion", "mixed"}:
            raise SafeError("meta_report_time_required")
        if not self.action_attribution_windows or any(
            w not in {"1d_click", "7d_click", "28d_click", "1d_view", "7d_view", "28d_view"}
            for w in self.action_attribution_windows
        ):
            raise SafeError("meta_attribution_windows_required")
        # Small reviewed surface; availability/combinations must be checked for pinned API.
        if len(set(self.breakdowns)) != len(self.breakdowns) or not set(self.breakdowns) <= {
            "age",
            "gender",
            "country",
            "publisher_platform",
            "platform_position",
        }:
            raise SafeError("unsupported_meta_breakdown")
        if self.purchase_action_type is not None and not re.fullmatch(
            r"[a-zA-Z0-9_.]+", self.purchase_action_type
        ):
            raise SafeError("invalid_purchase_action_type")

    def definition(self) -> dict[str, Any]:
        # Query window deliberately excluded from logical identity: overlapping refreshes
        # of the same reporting day must update rather than duplicate that day.
        return {
            "level": "ad",
            "time_increment": 1,
            "action_report_time": self.action_report_time,
            "action_attribution_windows": sorted(set(self.action_attribution_windows)),
            "purchase_action_type": self.purchase_action_type,
            "breakdowns": sorted(self.breakdowns),
        }

    def snapshot(self) -> dict[str, Any]:
        return {**self.definition(), "since": self.since, "until": self.until}


def configuration_key(account: Account, insights: Insights) -> str:
    return digest(
        {
            "api_version": account.api_version,
            "timezone": account.timezone,
            "currency": account.currency,
            **insights.definition(),
        }
    )
