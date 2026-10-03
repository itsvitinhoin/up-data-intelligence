"""GET-only, mock-transport-only connector. No live API capability in this phase."""

import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from src.connectors.meta.config import RESOURCES, Account, Insights
from src.domain.models import Page, SafeError
from src.observability.logging import event
from src.security.sanitization import REDACTED, sanitize
from src.utils.data import canonical

FIELDS = {
    "accounts": "id,account_id,name,account_status,currency,timezone_name",
    "campaigns": "id,account_id,name,status,effective_status,objective,created_time,updated_time",
    "adsets": "id,account_id,campaign_id,name,status,effective_status,created_time,updated_time",
    "ads": "id,account_id,campaign_id,adset_id,name,status,effective_status,created_time,updated_time",
    "insights": "account_id,campaign_id,adset_id,ad_id,date_start,date_stop,account_currency,spend,impressions,reach,frequency,clicks,inline_link_clicks,cpm,cpc,ctr,actions,action_values",
}


class MetaConnector:
    fields = FIELDS
    insights_level = "ad"

    def __init__(
        self,
        account: Account,
        *,
        token: str,
        transport: httpx.MockTransport,
        page_limit: int = 100,
        attempts: int = 4,
        max_pages: int = 10000,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not isinstance(transport, httpx.MockTransport):
            raise SafeError("meta_live_disabled")
        if not token or page_limit < 1 or attempts < 1 or max_pages < 1:
            raise SafeError("invalid_meta_client_configuration")
        self.account, self._token = account, token
        self.page_limit, self.attempts, self.max_pages = page_limit, attempts, max_pages
        self.sleep, self.retries = sleep, 0
        self.client = httpx.Client(
            transport=transport, trust_env=False, follow_redirects=False, timeout=30
        )

    def close(self) -> None:
        self.client.close()

    def pages(
        self,
        resource: str,
        insights: Insights | None,
        position: dict[str, Any] | None = None,
        *,
        cooperative: bool = False,
    ) -> Iterator[Page]:
        if resource not in RESOURCES or (resource == "insights" and insights is None):
            raise SafeError("invalid_meta_resource_configuration")
        params: dict[str, str] = {"fields": self.fields[resource], "limit": str(self.page_limit)}
        if insights and resource == "insights":
            params.update(
                level=self.insights_level,
                time_increment="1",
                time_range=canonical({"since": insights.since, "until": insights.until}),
                action_report_time=insights.action_report_time,
                action_attribution_windows=canonical(
                    sorted(set(insights.action_attribution_windows))
                ),
                breakdowns=",".join(sorted(insights.breakdowns)),
            )
        path = f"/{self.account.api_version}/act_{self.account.account_id}"
        if resource != "accounts":
            path += "/" + resource
        current = dict(position or {})
        seen: set[str] = set()
        for page_number in range(self.max_pages):
            cursor = current.get("after")
            if cursor is not None:
                if not isinstance(cursor, str) or not cursor or cursor in seen:
                    raise SafeError("meta_cursor_loop")
                seen.add(cursor)
            query = params | ({"after": cursor} if cursor else {})
            self._attempt_responses: list[dict[str, Any]] = []
            self._attempt_bytes = 0
            safe: Any = None
            error = None
            data: list[Any] = []
            next_position = None
            try:
                response = self._get(path, query)
                safe = self._safe_response(response)
                if response.status_code != 200:
                    error = "meta_request_failed"
                elif not isinstance(safe, dict) or "error" in safe:
                    error = "meta_invalid_response"
                else:
                    candidate = [safe] if resource == "accounts" else safe.get("data")
                    if not isinstance(candidate, list):
                        raise ValueError
                    data = candidate
                    paging = safe.get("paging") or {}
                    after = (paging.get("cursors") or {}).get("after")
                    has_next = bool(paging.get("next")) and resource != "accounts"
                    if has_next:
                        if not isinstance(after, str) or not after or REDACTED in after:
                            error = "meta_cursor_missing_or_redacted"
                        elif after in seen:
                            error = "meta_cursor_loop"
                        elif page_number + 1 == self.max_pages and not cooperative:
                            error = "meta_page_budget_exceeded"
                        else:
                            next_position = {"after": after}
            except SafeError as exc:
                error = exc.code
            except (ValueError, TypeError, AttributeError):
                error = "meta_invalid_response"
            # Authentication is scrubbed before ANY persistence. Failed HTTP attempts
            # are retained in the same audit envelope; never followed as URLs.
            yield Page(
                {"response": safe, "data": data, "http_attempts": self._attempt_responses},
                current,
                next_position,
                self._attempt_bytes,
                str(uuid.uuid4()),
                error,
            )
            if error:
                raise SafeError(error)
            if next_position is None:
                return
            current = next_position

    def _safe_response(self, response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError:
            body = {"non_json_body": response.text}
        return sanitize(body, (self._token,))

    def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        for attempt in range(self.attempts):
            response = None
            try:
                response = self.client.get(
                    "https://graph.facebook.com" + path,
                    params=params,
                    headers={"Authorization": "Bearer " + self._token},
                )
            except httpx.TransportError:
                pass
            if response is not None:
                self._attempt_bytes += len(response.content)
                self._attempt_responses.append(
                    {"status": response.status_code, "response": self._safe_response(response)}
                )
                if response.status_code == 200:
                    return response
            retryable = (
                response is None or response.status_code == 429 or 500 <= response.status_code < 600
            )
            if not retryable:
                if response is not None:
                    return response
            if attempt + 1 == self.attempts:
                # Only GET is retried here. Even an uncertain transport result is
                # safe to defer; this does not authorize repeating ambiguous POSTs.
                raise SafeError("meta_retry_deferred")
            delay = float(2**attempt)
            if response is not None and response.headers.get("Retry-After"):
                try:
                    delay = max(delay, float(response.headers["Retry-After"]))
                except ValueError:
                    raise SafeError("meta_retry_deferred") from None
            if not 0 <= delay <= 300:
                raise SafeError("meta_retry_deferred")
            self.retries += 1
            event("meta_retry", attempt=attempt + 1)
            self.sleep(delay)
        raise SafeError("meta_retry_deferred")
