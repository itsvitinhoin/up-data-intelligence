"""Future attribution contract. No default window or algorithm is implemented."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.utils.data import timestamp


@dataclass(frozen=True)
class LastPaidTouchPolicy:
    window: timedelta
    policy_version: str
    revenue_basis: str

    def __post_init__(self) -> None:
        if self.window.total_seconds() <= 0 or not self.policy_version:
            raise ValueError("explicit_positive_attribution_window_required")
        if self.revenue_basis not in {"requested", "fulfilled", "current", "paid"}:
            raise ValueError("explicit_revenue_basis_required")


def reporting_date(occurred_at: str, account_timezone: str) -> str:
    """Explicit comparison date; never rewrite the original UTC event timestamp."""
    return (
        datetime.fromisoformat(timestamp(occurred_at))
        .astimezone(ZoneInfo(account_timezone))
        .date()
        .isoformat()
    )
