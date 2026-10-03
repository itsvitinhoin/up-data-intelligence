"""GET-only mock HTTP; no credentials or live source clients."""

from contextlib import nullcontext
from datetime import timedelta

import httpx
import pytest

from src.connectors.meta.client import MetaConnector
from src.control_plane.model import instant
from src.domain.models import SafeError
from src.installation.model import Limits
from src.installation.planner import Planner
from src.installation.worker import Worker
from tests.installation.fakes import MemoryLedger
from tests.installation.test_planner import END, NOW, config
from tests.unit.test_meta_foundation import ACCOUNT, TOKEN


def connector(status, calls):
    def handle(request):
        calls.append(request.method)
        if status == "network":
            raise httpx.ReadTimeout("synthetic transport failure")
        return httpx.Response(status, json={"error": {"message": "synthetic error"}})

    return MetaConnector(
        ACCOUNT,
        token=TOKEN,
        transport=httpx.MockTransport(handle),
        attempts=3,
        sleep=lambda seconds: None,
    )


@pytest.mark.parametrize("status", [429, 500, 503, "network"])
def test_transient_get_exhaustion_is_deferred_and_audit_preserved(status):
    calls = []
    client = connector(status, calls)
    try:
        pages = client.pages("ads", None)
        page = next(pages)
        assert page.pagination_error == "meta_retry_deferred"
        assert page.payload["data"] == []
        assert len(page.payload["http_attempts"]) == (0 if status == "network" else 3)
        with pytest.raises(SafeError, match="^meta_retry_deferred$"):
            next(pages)
        assert calls == ["GET"] * 3 and client.retries == 2
    finally:
        client.close()


@pytest.mark.parametrize("status", [400, 401, 403])
def test_definitive_http_error_does_not_retry(status):
    calls = []
    client = connector(status, calls)
    try:
        pages = client.pages("ads", None)
        assert next(pages).pagination_error == "meta_request_failed"
        with pytest.raises(SafeError, match="^meta_request_failed$"):
            next(pages)
        assert calls == ["GET"] and client.retries == 0
    finally:
        client.close()


@pytest.mark.parametrize("status", [429, 500, 503, "network"])
def test_connector_worker_defers_then_blocks_third_failure(status):
    c, plan, units = Planner().calculate(
        config(
            meta_enabled=True,
            meta_connection_id=ACCOUNT.connection_id,
            meta_account_id=ACCOUNT.account_id,
            meta_api_version=ACCOUNT.api_version,
        ),
        END,
        NOW,
        adopt=True,
    )
    ledger = MemoryLedger(c, plan, units)
    original = next(r for r in ledger.units() if r["unit_kind"] == "META_CATALOG")
    for dependency in original["dependencies"]:
        ledger.u[dependency]["status"] = "COMPLETE"
    # Healthy slices have already happened; these are not failures.
    ledger.u[original["work_unit_id"]]["attempt_count"] = 12
    clock = [NOW]
    calls = []

    def action(*args):
        client = connector(status, calls)
        try:
            list(client.pages("ads", None))
        finally:
            client.close()

    worker = Worker(ledger, action, lambda key: nullcontext(), clock=lambda: clock[0])
    for failure in range(1, 4):
        row = ledger.reserve(
            ledger.u[original["work_unit_id"]], "synthetic-dispatch", clock[0], Limits()
        )
        with pytest.raises(SafeError, match="^meta_retry_deferred$"):
            worker.execute(
                row["store_id"],
                row["work_unit_id"],
                row["reservation_revision"],
                row["dispatch_token"],
                row["pipeline"],
            )
        saved = ledger.u[row["work_unit_id"]]
        assert saved["failure_count"] == failure
        assert saved["attempt_count"] == 12 + failure
        assert saved["status"] == ("BLOCKED" if failure == 3 else "DEFERRED")
        if failure < 3:
            assert instant(saved["next_eligible_at"]) > instant(clock[0])
            clock[0] = (instant(saved["next_eligible_at"]) + timedelta(seconds=1)).isoformat()
        else:
            assert saved["last_error_code"] == "work_retry_exhausted"
            assert saved["next_eligible_at"] is None
    assert calls == ["GET"] * 9
