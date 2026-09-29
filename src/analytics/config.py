"""Explicit per-store materialization policy; contains no credential or implicit defaults."""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from src.analytics.policy import HistoryCoverage, Policy
from src.utils.data import timestamp


@dataclass(frozen=True)
class AnalyticsPolicy:
    store_id: str
    policy_version: str
    reporting_timezone: str
    currency: str | None
    qualifying_order_statuses: tuple[str, ...]
    history_complete: bool
    facts_complete: bool
    as_of: str
    report_from: str
    report_to: str
    history_from: str
    history_coverage: HistoryCoverage | None = None
    allow_unknown_currency_local: bool = False

    def __post_init__(self) -> None:
        self.reference()
        if datetime.fromisoformat(timestamp(self.history_from)) >= datetime.fromisoformat(
            timestamp(self.as_of)
        ):
            raise ValueError("invalid_history_interval")
        if (
            self.history_complete
            and self.history_coverage
            and datetime.fromisoformat(timestamp(self.history_from))
            > datetime.fromisoformat(timestamp(self.history_coverage.origin_at))
        ):
            raise ValueError("history_coverage_unknown")

    def reference(self) -> Policy:
        return Policy(
            self.store_id,
            self.reporting_timezone,
            self.currency,
            self.as_of,
            self.report_from,
            self.report_to,
            self.history_complete,
            self.facts_complete,
            tuple(self.qualifying_order_statuses),
            policy_version=self.policy_version,
            history_coverage=self.history_coverage,
            allow_unknown_currency_local=self.allow_unknown_currency_local,
        )

    @property
    def policy_hash(self) -> str:
        return self.reference().key

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalyticsPolicy":
        if not data:
            raise ValueError("policy_missing")
        supplied = dict(data)
        if supplied.get("history_coverage") is not None:
            supplied["history_coverage"] = HistoryCoverage(**supplied["history_coverage"])
        supplied["qualifying_order_statuses"] = tuple(supplied.get("qualifying_order_statuses", ()))
        try:
            return cls(**supplied)
        except TypeError:
            raise ValueError("policy_missing") from None
