from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.bigquery.repository import Repository
from src.config.settings import Settings
from src.utils.data import timestamp


def instant(value: str) -> datetime:
    if len(value) == 10:
        value += "T00:00:00+00:00"
    return datetime.fromisoformat(timestamp(value))


def filters_for(resource: str, start: datetime, end: datetime, timezone: str) -> dict[str, Any]:
    if start >= end:
        raise ValueError("empty_window")
    if resource == "analytics_facts":
        return {"from": start.isoformat(), "to": end.isoformat(), "limit": 1000}
    zone = ZoneInfo(timezone) if resource == "orders" else UTC
    return {
        "start_date": start.astimezone(zone).date().isoformat(),
        "end_date": (end - timedelta(microseconds=1)).astimezone(zone).date().isoformat(),
        "limit": 200,
    }


def windows(
    resource: str, start: str, end: str, timezone: str, days: int = 1
) -> list[dict[str, Any]]:
    a, b = instant(start), instant(end)
    if a >= b or days < 1:
        raise ValueError("invalid_window")
    result = []
    while a < b:
        nxt = min(a + timedelta(days=days), b)
        result.append(filters_for(resource, a, nxt, timezone))
        a = nxt
    return result


def incremental(
    repo: Repository, cfg: Settings, resource: str, at: str
) -> tuple[dict[str, Any], int | None]:
    checkpoints = [
        r
        for r in repo.read("sync_checkpoints", cfg.store_id)
        if r["resource"] == resource and r["mode"] == "incremental" and r["status"] == "complete"
    ]
    last = max(checkpoints, key=lambda r: r["updated_at"], default=None)
    end = instant(at)
    if resource == "customers":
        return {"limit": 200}, int(last["high_id"]) if last and last.get("high_id") else None
    lookback = (
        timedelta(hours=cfg.facts_lookback_hours)
        if resource == "analytics_facts"
        else timedelta(days=cfg.orders_lookback_days)
    )
    start = (
        max(instant(cfg.initial_from), instant(last["completed_to"]) - lookback)
        if last
        else instant(cfg.initial_from)
    )
    return filters_for(resource, start, end, cfg.timezone), None


def open_order_windows(repo: Repository, cfg: Settings) -> list[dict[str, Any]]:
    # Only the approved LIST endpoint. Query each known open order's creation date.
    orders = repo.find(
        "orders", cfg.store_id, "order_status", ["RESERVED", "CONFIRMED", "PROCESSING", "INVOICED"]
    )
    dates = sorted(
        {
            instant(r["created_at"]).astimezone(ZoneInfo(cfg.timezone)).date().isoformat()
            for r in orders
            if r.get("created_at")
        }
    )
    return [{"start_date": d, "end_date": d, "limit": 200} for d in dates]
