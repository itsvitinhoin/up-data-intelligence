"""Synthetic Graph pages only. Campaign totals are never assigned to ads."""

from contextlib import nullcontext
from dataclasses import replace
from unittest.mock import patch

import httpx
import pytest

from src.bigquery.repository import SQLiteRepository
from src.connectors.meta.live import MetaFoundationLiveConnector
from src.domain.models import SafeError
from src.ingestion.meta_live import MetaCreativeEngine, MetaLiveEngine
from tests.unit.test_meta_foundation import ACCOUNT, INSIGHTS, source


def setup(tmp_path, handler, *, level="ad"):
    repository = SQLiteRepository(str(tmp_path / "creative.sqlite"))
    connector = MetaFoundationLiveConnector(
        ACCOUNT,
        project="synthetic-dev",
        live=True,
        confirm_store=ACCOUNT.store_id,
        confirm_account=ACCOUNT.account_id,
        token="SYNTHETIC_ONLY",
        page_limit=1,
        transport=httpx.MockTransport(handler),
    )
    connector.set_insights_level(level)
    engine = MetaCreativeEngine(repository, connector, accounts=(ACCOUNT,), lease=nullcontext)
    repository.write({"meta_account_bindings": [engine._binding()]})
    return repository, connector, engine


def test_ad_day_distinct_core_and_configuration_no_campaign_mutation(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.params["level"] == "ad"
        assert request.url.params["time_increment"] == "1"
        return httpx.Response(200, json={"data": [source("insights")]})

    repo, connector, engine = setup(tmp_path, handler)
    try:
        report = engine.advance("insights", INSIGHTS, page_budget=1)
        assert report["complete"] is True
        row = repo.read("meta_creative_insights_daily", ACCOUNT.store_id)[0]
        assert row["level"] == "ad" and row["ad_id"] == "000401"
        assert row["spend"] == "123.450000001"
        assert row["meta_reported_purchases"] == "2"
        assert repo.read("meta_live_insights_daily", ACCOUNT.store_id) == []
        assert len(requests) == 1
        cp = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
        assert cp["resource"] == "meta_creative_insights_daily"
        assert cp["filters"]["insights"]["level"] == "ad"
        assert cp["pending_raw_id"] is None
        campaign = MetaLiveEngine(repo, connector, accounts=(ACCOUNT,), lease=nullcontext)
        assert engine._configuration(INSIGHTS) != campaign._configuration(INSIGHTS)
        engine.run("insights", INSIGHTS)
        assert len(requests) == 1  # Exhausted snapshot reuse, no implicit refresh.
    finally:
        connector.close()


def test_boundaries_yield_same_checkpoint_without_refetching_pending_raw(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params.get("after"):
            row = {**source("insights"), "ad_id": "000402"}
            return httpx.Response(200, json={"data": [row]})
        return httpx.Response(
            200,
            json={
                "data": [source("insights")],
                "paging": {
                    "next": "https://graph.facebook.com/ignored",
                    "cursors": {"after": "next"},
                },
            },
        )

    repo, connector, engine = setup(tmp_path, handler)
    write = repo.write

    def fail_core(rows):
        if "meta_creative_insights_daily" in rows:
            raise SafeError("synthetic_core_failure")
        write(rows)

    try:
        with patch.object(repo, "write", side_effect=fail_core):
            with pytest.raises(SafeError):
                engine.advance("insights", INSIGHTS, page_budget=1)
        cp = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
        assert cp["pending_raw_id"] is not None
        first = engine.advance("insights", INSIGHTS, page_budget=1)
        assert first["yielded"] and not first["complete"]
        assert len(requests) == 1
        assert repo.read("sync_checkpoints", ACCOUNT.store_id)[0]["pending_raw_id"] is None
        second = engine.advance("insights", INSIGHTS, page_budget=1)
        assert second["complete"] and second["run_id"] == first["run_id"] == cp["run_id"]
        assert second["source_records_read"] == second["core_records_processed"] == 2
        assert len(repo.read("meta_creative_insights_daily", ACCOUNT.store_id)) == 2
        assert not repo.read("meta_live_insights_daily", ACCOUNT.store_id)
    finally:
        connector.close()


@pytest.mark.parametrize("bad", ["campaign", "adset"])
def test_wrong_connector_level_rejected_before_any_durable_write(tmp_path, bad):
    repo, connector, engine = setup(tmp_path, lambda _: pytest.fail("no source IO"), level=bad)
    try:
        with pytest.raises(SafeError, match="meta_level_mismatch"):
            engine.advance("insights", INSIGHTS)
        assert not repo.read("sync_runs", ACCOUNT.store_id)
        assert not repo.read("sync_checkpoints", ACCOUNT.store_id)
    finally:
        connector.close()


def test_missing_purchase_definition_preserves_null(tmp_path):
    repo, connector, engine = setup(
        tmp_path, lambda _: httpx.Response(200, json={"data": [source("insights")]})
    )
    try:
        engine.run("insights", replace(INSIGHTS, purchase_action_type=None))
        row = repo.read("meta_creative_insights_daily", ACCOUNT.store_id)[0]
        assert row["meta_reported_purchases"] is None
        assert row["meta_reported_purchase_value"] is None
    finally:
        connector.close()


def test_unsupported_resources_and_breakdowns_fail_before_source_or_ledger(tmp_path):
    repo, connector, engine = setup(tmp_path, lambda _: pytest.fail("no source IO"))
    try:
        for resource, report in [
            ("ads", None),
            ("insights", replace(INSIGHTS, breakdowns=("age",))),
        ]:
            with pytest.raises(SafeError, match="invalid_meta_creative_configuration"):
                engine.run(resource, report)
        assert not repo.read("sync_runs", ACCOUNT.store_id)
    finally:
        connector.close()


def test_creative_replay_rejects_other_resources_before_ledger(tmp_path):
    repo, connector, engine = setup(tmp_path, lambda _: pytest.fail("no source IO"))
    try:
        with pytest.raises(SafeError, match="invalid_meta_creative_configuration"):
            engine.replay("ads", "synthetic-original")
        assert not repo.read("sync_runs", ACCOUNT.store_id)
    finally:
        connector.close()
