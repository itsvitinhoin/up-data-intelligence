import json
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from src.utils.data import timestamp


@dataclass(frozen=True)
class Settings:
    store_id: str
    store_name: str
    store_slug: str
    timezone: str
    connection_id: str
    initial_from: str
    secret_resource_name: str = ""
    upzero_store_identifier: str | None = None
    environment: str = "dev"
    project_id: str = ""
    location: str = ""
    lease_bucket: str = ""
    state_path: str = ".local/pilot.sqlite"
    purchase_order_id_effective_at: str | None = None
    facts_lookback_hours: int = 72
    orders_lookback_days: int = 30
    stale_after_minutes: int = 60
    max_pages: int = 10000
    page_limit: int | None = None

    def __post_init__(self) -> None:
        if not all((self.store_id, self.connection_id, self.store_slug)):
            raise ValueError("missing_registry_identity")
        if self.environment not in {"dev", "staging", "prod"}:
            raise ValueError("invalid_environment")
        if self.page_limit is not None and not 1 <= self.page_limit <= 1000:
            raise ValueError("invalid_page_limit")
        ZoneInfo(self.timezone)
        timestamp(self.initial_from)
        if self.purchase_order_id_effective_at:
            timestamp(self.purchase_order_id_effective_at)
        if (
            min(
                self.facts_lookback_hours,
                self.orders_lookback_days,
                self.stale_after_minutes,
                self.max_pages,
            )
            <= 0
        ):
            raise ValueError("invalid_limits")

    @classmethod
    def load(cls, path: str) -> "Settings":
        return cls(**json.loads(Path(path).read_text()))
