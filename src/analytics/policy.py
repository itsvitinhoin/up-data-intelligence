import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.utils.data import digest, timestamp

VERSION = "1.0.0"
ORDER_STATUSES = {"RESERVED", "CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED", "CANCELED"}
FUNNEL_EVENTS = {"product_view", "add_to_cart", "checkout_started", "purchase"}
LTV_DAYS = (30, 60, 90, 180, 365)


@dataclass(frozen=True)
class Policy:
    store_id: str
    timezone: str
    currency: str
    as_of: str
    report_from: str
    report_to: str  # exclusive local DATE
    history_complete: bool
    facts_complete: bool
    purchase_statuses: tuple[str, ...]  # explicit commercial definition; no implicit default

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        instant = datetime.fromisoformat(timestamp(self.as_of))
        start, end = date.fromisoformat(self.report_from), date.fromisoformat(self.report_to)
        if type(self.history_complete) is not bool or type(self.facts_complete) is not bool:
            raise ValueError("coverage_flags_must_be_explicit_booleans")
        if self.report_from != start.isoformat() or self.report_to != end.isoformat():
            raise ValueError("canonical_iso_reporting_dates_required")
        if not self.store_id or not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("explicit_store_and_currency_required")
        if start >= end or end > instant.astimezone(ZoneInfo(self.timezone)).date():
            raise ValueError("only_closed_reporting_days_supported")
        if not self.purchase_statuses or not set(self.purchase_statuses) <= ORDER_STATUSES - {
            "CANCELED"
        }:
            raise ValueError("explicit_non_cancelled_purchase_statuses_required")

    @property
    def key(self) -> str:
        return digest(
            {
                "analytics_version": VERSION,
                "store_id": self.store_id,
                "timezone": self.timezone,
                "currency": self.currency,
                "purchase_statuses": sorted(set(self.purchase_statuses)),
            }
        )

    def local_date(self, value: str) -> str:
        return (
            datetime.fromisoformat(timestamp(value))
            .astimezone(ZoneInfo(self.timezone))
            .date()
            .isoformat()
        )
