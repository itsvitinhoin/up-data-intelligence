"""Explicit DEV-only live transport, kept separate from the mock-only connector."""

import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.connectors.meta.config import Account
from src.connectors.meta.enrichment_schema import CREATIVE_FIELDS
from src.connectors.meta.foundation import FOUNDATION_FIELDS, MetaFoundationConnector
from src.domain.models import SafeError


def gate(
    project: str, account: Account, *, live: bool, confirm_store: str, confirm_account: str
) -> None:
    if (
        not live
        or not project.endswith("-dev")
        or confirm_store != account.store_id
        or confirm_account != account.account_id
    ):
        raise SafeError("meta_live_confirmation_required")


class MetaFoundationLiveConnector(MetaFoundationConnector):
    """Inherits bounded retries/cursor reconstruction/sanitization, never paging.next."""

    fields = {
        **FOUNDATION_FIELDS,
        "ads": FOUNDATION_FIELDS["ads"].replace("creative{id}", CREATIVE_FIELDS),
    }

    def __init__(
        self,
        account: Account,
        *,
        project: str,
        live: bool,
        confirm_store: str,
        confirm_account: str,
        token: str,
        page_limit: int = 100,
        attempts: int = 4,
        max_pages: int = 10000,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        gate(
            project,
            account,
            live=live,
            confirm_store=confirm_store,
            confirm_account=confirm_account,
        )
        if (
            not token
            or not 1 <= page_limit <= 1000
            or not 1 <= attempts <= 5
            or not 1 <= max_pages <= 10000
        ):
            raise SafeError("invalid_meta_client_configuration")
        self.account, self._token = account, token
        self.api_version = account.api_version
        self.page_limit, self.attempts, self.max_pages = page_limit, attempts, max_pages
        self.sleep, self.retries = sleep, 0
        self.insights_level = "campaign"
        self.client = httpx.Client(
            transport=transport, trust_env=False, follow_redirects=False, timeout=30
        )

    def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        if (
            not re.fullmatch(
                r"/v[0-9]+\.0/(?:act_[0-9]+(?:/(?:campaigns|adsets|ads|insights))?|me/adaccounts)",
                path,
            )
            or "access_token" in params
        ):
            raise SafeError("meta_unsafe_request")
        return super()._get(path, params)

    def list_accounts(self) -> list[dict[str, str]]:
        rows = []
        after = None
        seen = set()
        for _ in range(self.max_pages):
            self._attempt_responses = []
            self._attempt_bytes = 0
            params = {"fields": self.fields["accounts"], "limit": str(self.page_limit)}
            if after:
                params["after"] = after
            response = self._get(f"/{self.api_version}/me/adaccounts", params)
            body = self._safe_response(response)
            if (
                response.status_code != 200
                or not isinstance(body, dict)
                or not isinstance(body.get("data"), list)
            ):
                raise SafeError("meta_request_failed")
            for row in body["data"]:
                from src.connectors.meta.config import meta_id

                rows.append(
                    {
                        "account_id": meta_id(row.get("account_id")),
                        "currency": row.get("currency"),
                        "timezone": row.get("timezone_name"),
                    }
                )
            paging = body.get("paging") or {}
            if not paging.get("next"):
                return rows
            after = (paging.get("cursors") or {}).get("after")
            if not isinstance(after, str) or not after or after in seen:
                raise SafeError("meta_cursor_loop")
            seen.add(after)
        raise SafeError("meta_page_budget_exceeded")


class MetaAccountLister(MetaFoundationLiveConnector):
    """Account inventory only; no account is guessed or bound by listing."""

    def __init__(
        self,
        *,
        project: str,
        live: bool,
        store: str,
        confirm_store: str,
        api_version: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
    ):
        if (
            not live
            or not project.endswith("-dev")
            or not store
            or store != confirm_store
            or not re.fullmatch(r"v[0-9]+\.0", api_version)
            or not token
        ):
            raise SafeError("meta_live_confirmation_required")
        self.api_version, self._token = api_version, token
        self.page_limit, self.attempts, self.max_pages = 100, 4, 1000
        self.sleep, self.retries = time.sleep, 0
        self.client = httpx.Client(
            transport=transport, trust_env=False, follow_redirects=False, timeout=30
        )


class MetaCreativeLiveConnector(MetaFoundationLiveConnector):
    """Explicit ad/day source for the separate creative contract."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.insights_level = "ad"
