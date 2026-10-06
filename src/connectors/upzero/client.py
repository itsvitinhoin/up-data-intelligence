import json
import random
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from src.domain.models import Page, SafeError
from src.observability.logging import event
from src.security.sanitization import sanitize

PATHS = {
    "customers": "/external/v1/customers",
    "orders": "/external/v1/orders",
    "analytics_facts": "/external/v1/analytics/facts",
    "products": "/external/v1/products",
    "variants": "/external/v1/variants",
    "attributes": "/external/v1/attributes",
    "inventory": "/external/v1/inventory/availability",
    "images": "/external/v1/products/{product_id}/images",
}
FILTERS = {
    "customers": {"start_date", "end_date", "limit"},
    "orders": {"start_date", "end_date", "status", "limit"},
    "analytics_facts": {"from", "to", "limit"},
    "products": {"limit", "include_inactive", "catalog_as_of"},
    "variants": {"limit", "catalog_as_of"},
    "attributes": {"catalog_as_of"},
    "inventory": {"variant_id", "variant_ids", "catalog_as_of"},
    "images": {"product_ids", "catalog_as_of"},
}
CURSOR_RESOURCES = frozenset({"analytics_facts", "products", "variants"})


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
        path = PATHS[resource]
        query_params = params
        if resource == "images":
            product = params.get("product_id")
            if not isinstance(product, str) or not product.strip() or len(product) > 200:
                raise SafeError("catalog_image_product_required")
            path = path.replace("{product_id}", quote(product, safe=""))
            query_params = {k: v for k, v in params.items() if k != "product_id"}
        for attempt in range(self.attempts):
            response = None
            try:
                response = self.client.get(
                    path, params=query_params, headers={"X-API-Key": self._key}
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
                            # Catalog/stock decimal literals must never become floats.
                            parse_float=(
                                str if resource in {"products", "variants", "inventory"} else float
                            ),
                        )
                        if resource in {"attributes", "images"}:
                            if not isinstance(data, list):
                                raise ValueError
                            if resource == "images" and any(
                                not isinstance(row, dict) or row.get("product_id") != product
                                for row in data
                            ):
                                raise SafeError("catalog_image_product_mismatch")
                            data = {"data": data}
                        elif resource == "inventory":
                            if not isinstance(data, dict) or not data.get("variant_id"):
                                raise ValueError
                            if str(data["variant_id"]) != str(params.get("variant_id")):
                                raise SafeError("inventory_variant_mismatch")
                            data = {"data": [{**data, "id": data["variant_id"]}]}
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
        if "catalog_as_of" in filters:
            from src.utils.data import timestamp

            try:
                if not isinstance(filters["catalog_as_of"], str):
                    raise ValueError
                timestamp(filters["catalog_as_of"])
            except (ValueError, TypeError):
                raise SafeError("catalog_snapshot_required") from None
        variant_ids = filters.get("variant_ids")
        product_ids = filters.get("product_ids")
        if resource == "images":
            if (
                not isinstance(product_ids, list)
                or len(product_ids) > 10000
                or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in product_ids)
                or len(set(product_ids)) != len(product_ids)
                or product_ids != sorted(product_ids)
                or "catalog_as_of" not in filters
            ):
                raise SafeError("catalog_images_snapshot_invalid")
            if not product_ids:
                return
        if variant_ids is not None:
            if (
                resource != "inventory"
                or "variant_id" in filters
                or (
                    not isinstance(variant_ids, list)
                    or len(variant_ids) > 10000
                    or any(
                        not isinstance(v, str) or not v.strip() or len(v) > 200 for v in variant_ids
                    )
                    or len(set(variant_ids)) != len(variant_ids)
                    or variant_ids != sorted(variant_ids)
                    or "catalog_as_of" not in filters
                )
            ):
                raise SafeError("inventory_snapshot_invalid")
            if not variant_ids:
                return
        elif resource == "inventory" and (
            not isinstance(filters.get("variant_id"), str)
            or not filters["variant_id"].strip()
            or len(filters["variant_id"]) > 200
        ):
            raise SafeError("inventory_variant_required")
        limit = int(filters.get("limit", 1000 if resource == "analytics_facts" else 200))
        if not 1 <= limit <= (1000 if resource == "analytics_facts" else 200):
            raise SafeError("invalid_limit")
        if resource == "analytics_facts" and not all(filters.get(k) for k in ("from", "to")):
            raise SafeError("fixed_window_required")
        pos = position or (
            {"index": 0}
            if variant_ids is not None or product_ids is not None
            else {"page": 1}
            if resource == "orders"
            else {}
        )
        targets = product_ids if resource == "images" else variant_ids
        if targets is not None and (
            set(pos) != {"index"}
            or type(pos["index"]) is not int
            or not 0 <= pos["index"] < len(targets)
        ):
            raise SafeError(
                "catalog_images_position_invalid"
                if resource == "images"
                else "inventory_snapshot_position_invalid"
            )
        seen: set[str] = set()
        for _ in range(self.max_pages):
            token = json.dumps(pos, sort_keys=True)
            if token in seen:
                raise SafeError("cursor_repeated")
            seen.add(token)
            # catalog_as_of identifies a durable logical snapshot/checkpoint. It
            # is internal metadata, never an undocumented provider query filter.
            params = {
                k: v
                for k, v in filters.items()
                if k not in {"catalog_as_of", "variant_ids", "product_ids"}
            }
            if variant_ids is not None:
                params["variant_id"] = variant_ids[pos["index"]]
            elif product_ids is not None:
                params["product_id"] = product_ids[pos["index"]]
            else:
                params.update(pos)
            if resource not in {"attributes", "inventory", "images"}:
                params["limit"] = limit
            payload, size = self._get(resource, params)
            rows = payload["data"]
            error = None
            nxt: dict[str, Any] | None = None
            try:
                if product_ids is not None:
                    if pos["index"] + 1 < len(product_ids):
                        nxt = {"index": pos["index"] + 1}
                elif variant_ids is not None:
                    if len(rows) != 1:
                        error = "inventory_snapshot_response_invalid"
                    elif pos["index"] + 1 < len(variant_ids):
                        nxt = {"index": pos["index"] + 1}
                elif resource == "customers" and rows:
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
                elif resource in CURSOR_RESOURCES and payload.get("next_cursor") is not None:
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
