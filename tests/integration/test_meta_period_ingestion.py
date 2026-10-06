"""Synthetic all-days source proves unique period reach without daily summation."""

from contextlib import nullcontext
from copy import deepcopy

import httpx
import pytest

from src.bigquery.repository import SQLiteRepository
from src.connectors.meta.config import Account, Insights
from src.connectors.meta.period import (
    MetaPeriodEngine,
    MetaPeriodLiveConnector,
    PeriodInsights,
    normalize_period,
)
from src.domain.models import SafeError
from src.utils.data import digest

ACCOUNT = Account("synthetic", "100", "meta-synthetic", "v26.0", "America/Sao_Paulo", "BRL")
REPORT = PeriodInsights(
    "2026-09-01", "2026-09-30", "impression", ("7d_click",), "offsite_conversion.fb_pixel_purchase"
)
SOURCE = dict(
    account_id="100",
    account_currency="BRL",
    date_start="2026-09-01",
    date_stop="2026-09-30",
    spend="30.10",
    impressions="1000",
    reach="800",
    frequency="1.25",
    clicks="20",
    inline_link_clicks="15",
    actions=[
        dict(action_type="offsite_conversion.fb_pixel_purchase", value="2"),
        dict(action_type="purchase", value="2"),
    ],
    action_values=[
        dict(action_type="offsite_conversion.fb_pixel_purchase", value="100.10"),
        dict(action_type="purchase", value="100.10"),
    ],
)


def test_period_reach_and_exact_family_do_not_sum_overlaps():
    row = normalize_period(SOURCE, ACCOUNT, REPORT, "2026-10-01T03:00:00Z")
    assert row["reach"] == 800 and row["frequency"] == "1.25"
    assert row["meta_reported_purchases"] == "2" and row["meta_reported_purchase_value"] == "100.10"
    assert row["spend"] == "30.10"
    assert row["ctr"] == "2" and row["cpc"] == "1.505"
    assert REPORT.definition()["time_increment"] == "all_days"
    assert digest(REPORT.definition()) != digest(
        Insights(
            "2026-09-01", "2026-09-30", "impression", ("7d_click",), REPORT.purchase_action_type
        ).definition()
    )
    other = PeriodInsights(
        "2026-09-02", "2026-09-30", "impression", ("7d_click",), REPORT.purchase_action_type
    )
    assert digest(other.definition()) != digest(REPORT.definition())


@pytest.mark.parametrize(
    "mutation",
    [
        dict(account_id="200"),
        dict(account_currency="USD"),
        dict(date_start="2026-09-02"),
        dict(date_stop="2026-09-29"),
        dict(campaign_id="200"),
        dict(spend="-1"),
        dict(reach="-1"),
    ],
)
def test_period_scope_and_window_fail_closed(mutation):
    with pytest.raises((SafeError, ValueError)):
        normalize_period({**SOURCE, **mutation}, ACCOUNT, REPORT, "2026-10-01T03:00:00Z")


def test_absent_purchase_evidence_is_not_zero():
    row = normalize_period(
        {**SOURCE, "actions": [], "action_values": None}, ACCOUNT, REPORT, "2026-10-01T03:00:00Z"
    )
    assert row["meta_reported_purchases"] is None and row["meta_reported_purchase_value"] is None


def test_period_durable_checkpoint_resumes_and_same_window_is_idempotent(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert (
            request.url.params["time_increment"] == "all_days"
            and request.url.params["level"] == "account"
        )
        assert "access_token" not in request.url.params
        return httpx.Response(200, json={"data": [SOURCE]})

    repo = SQLiteRepository(str(tmp_path / "period.sqlite"))
    repo.write(
        {
            "meta_account_bindings": [
                dict(
                    row_key="binding",
                    store_id=ACCOUNT.store_id,
                    account_id=ACCOUNT.account_id,
                    connection_id=ACCOUNT.connection_id,
                    api_version=ACCOUNT.api_version,
                    source_timezone=ACCOUNT.timezone,
                    currency=ACCOUNT.currency,
                    configuration_hash=digest(ACCOUNT.snapshot()),
                    configured_at="2026-10-01T03:00:00Z",
                )
            ]
        }
    )
    connector = MetaPeriodLiveConnector(
        ACCOUNT,
        project="synthetic-dev",
        live=True,
        confirm_store=ACCOUNT.store_id,
        confirm_account=ACCOUNT.account_id,
        token="synthetic",
        level="account",
        transport=httpx.MockTransport(handler),
    )
    engine = MetaPeriodEngine(
        repo, connector, accounts=(ACCOUNT,), lease=lambda: nullcontext(), level="account"
    )
    result = engine.advance("insights", REPORT, page_budget=1)
    assert result["complete"] and result["core_records_failed"] == 0
    cp = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
    assert (
        cp["resource"] == "meta_period_insights"
        and cp["pending_raw_id"] is None
        and cp["status"] == "complete"
    )
    row = repo.read("meta_period_insights", ACCOUNT.store_id)[0]
    assert row["reach"] == 800 and row["meta_reported_purchases"] == "2"
    before = deepcopy(cp)
    again = engine.advance("insights", REPORT, page_budget=1)
    assert again["run_id"] == result["run_id"] and len(requests) == 1
    assert repo.read("sync_checkpoints", ACCOUNT.store_id)[0] == before
    assert len(repo.read("meta_period_insights_versions", ACCOUNT.store_id)) == 1
