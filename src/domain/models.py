from dataclasses import dataclass, field
from typing import Any

RESOURCES = {"customers", "orders", "analytics_facts"}


class SafeError(Exception):
    def __init__(self, code: str, status: int | None = None):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass
class Page:
    payload: dict[str, Any]
    position: dict[str, Any]
    next_position: dict[str, Any] | None
    bytes_read: int
    request_id: str
    pagination_error: str | None = None


@dataclass
class Batch:
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    written: int = 0
    updated: int = 0
    failed: int = 0

    def add(self, table: str, row: dict[str, Any]) -> None:
        self.rows.setdefault(table, []).append(row)
