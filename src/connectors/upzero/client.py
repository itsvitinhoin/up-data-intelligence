import json
import random
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from src.domain.models import Page, SafeError
from src.observability.logging import event
from src.security.sanitization import sanitize

PATHS = {
    "customers": "/external/v1/customers",
    "orders": "/external/v1/orders",
    "analytics_facts": "/external/v1/analytics/facts",
}
FILTERS = {
    "customers": {"start_date", "end_date", "limit"},
    "orders": {"start_date", "end_date", "status", "limit"},
    "analytics_facts": {"from", "to", "limit"},
}


class UpZeroConnector:
    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        *,
        timeout: float = 30,
        attempts: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        max_pages: int = 10000,
    ):
        self._key = api_key
        self.client = httpx.Client(
            base_url="https://api.upzero.com.br",
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
        self.attempts, self.sleep, self.max_pages = attempts, sleep, max_pages
        self.retries = 0

    def close(self) -> None:
        self.client.close()

    def _get(self, resource: str, params: dict[str, Any]) -> tuple[dict[str, Any], int]:
        for attempt in range(self.attempts):
            response = None
            try:
                response = self.client.get(
                    PATHS[resource], params=params, headers={"X-API-Key": self._key}
                )
                status = response.status_code
                event("http_response", resource=resource, http_status=status, attempt=attempt)
                if status == 200:
                    # Disallow ambiguous duplicate object keys before sanitization/persistence.
                    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                        result: dict[str, Any] = {}
                        for k, v in pairs:
                            if k in result:
                                raise ValueError
                            result[k] = v
                        return result

                    try:
                        data = json.loads(
                            response.content,
                            object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                        )
                        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                            raise ValueError
                        return sanitize(data, (self._key,)), len(response.content)
                    except (ValueError, TypeError):
                        raise SafeError("invalid_response") from None
                if status != 429 and status < 500:
                    raise SafeError("http_rejected", status)
            except httpx.TransportError:
                status = 0
            if attempt + 1 == self.attempts:
                raise SafeError("retry_exhausted", status)
            delay = min(60.0, 2.0**attempt + random.random())
            if response is not None and response.headers.get("Retry-After"):
                value = response.headers["Retry-After"]
                try:
                    delay = max(delay, float(value))
                except ValueError:
                    try:
                        delay = max(
                            delay,
                            (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds(),
                        )
                    except (ValueError, TypeError):
                        pass
            # Do not retry sooner than a long server delay; defer whole run instead.
            if delay > 300:
                raise SafeError("retry_after_deferred", status)
            self.retries += 1
            self.sleep(delay)
        raise SafeError("invalid_attempts")

    def pages(
        self, resource: str, filters: dict[str, Any], position: dict[str, Any] | None = None
    ) -> Iterator[Page]:
        if resource not in PATHS or set(filters) - FILTERS[resource]:
            raise SafeError("unsupported_resource_or_filter")
        limit = int(filters.get("limit", 1000 if resource == "analytics_facts" else 200))
        if not 1 <= limit <= (1000 if resource == "analytics_facts" else 200):
            raise SafeError("invalid_limit")
        if resource == "analytics_facts" and not all(filters.get(k) for k in ("from", "to")):
            raise SafeError("fixed_window_required")
        pos = position or ({"page": 1} if resource == "orders" else {})
        seen: set[str] = set()
        for _ in range(self.max_pages):
            token = json.dumps(pos, sort_keys=True)
            if token in seen:
                raise SafeError("cursor_repeated")
            seen.add(token)
            payload, size = self._get(resource, {**filters, "limit": limit, **pos})
            rows = payload["data"]
            error = None
            nxt: dict[str, Any] | None = None
            try:
                if resource == "customers" and rows:
                    ids = [int(r["id"]) for r in rows]
                    if ids != sorted(ids, reverse=True):
                        error = "after_id_no_progress"
                    elif "after_id" in pos and any(i >= int(pos["after_id"]) for i in ids):
                        error = "after_id_no_progress"
                    else:
                        nxt = {"after_id": min(ids)}
                elif resource == "orders":
                    page, total = payload["page"], payload["total_pages"]
                    if (
                        not isinstance(page, int)
                        or not isinstance(total, int)
                        or page != pos["page"]
                        or total < 0
                        or (not rows and page < total)
                        or (bool(rows) and page > total)
                    ):
                        error = "invalid_order_pagination"
                    elif page < total:
                        nxt = {"page": page + 1}
                elif resource == "analytics_facts" and payload.get("next_cursor") is not None:
                    cursor = payload["next_cursor"]
                    if not isinstance(cursor, str) or not cursor:
                        error = "invalid_cursor"
                    elif json.dumps({"cursor": cursor}, sort_keys=True) in seen:
                        error = "cursor_repeated"
                    else:
                        nxt = {"cursor": cursor}
            except (ValueError, TypeError, KeyError):
                error = "invalid_pagination"
            yield Page(payload, pos, nxt, size, str(uuid.uuid4()), error)
            if error:
                raise SafeError(error)
            if nxt is None:
                return
            pos = nxt
        raise SafeError("page_limit_exceeded")
