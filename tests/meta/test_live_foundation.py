"""CHANGE #13 mocks and synthetic entities only; network globally forbidden."""

from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from src.connectors.meta.foundation import FOUNDATION_FIELDS, MetaFoundationConnector
from src.connectors.meta.foundation_schema import generate
from src.domain.models import SafeError
from src.ingestion.meta import extract_foundation_offline
from src.normalization.meta import normalize_foundation
from src.quality.meta import validate_foundation
from tests.unit.test_meta_foundation import ACCOUNT, INSIGHTS, TOKEN, source

AT = "2026-01-03T00:00:00Z"


def norm(resource="insights", row=None, *, insights=INSIGHTS, level="ad"):
    return normalize_foundation(
        resource,
        source(resource) if row is None else row,
        ACCOUNT,
        insights if resource == "insights" else None,
        observed_at=AT,
        level=level,
    )


@pytest.mark.parametrize("resource", ["accounts", "campaigns", "adsets", "ads"])
def test_valid_entities(resource):
    row = source(resource)
    if resource == "adsets":
        row.update(
            optimization_goal="LINK_CLICKS",
            billing_event="IMPRESSIONS",
            targeting={"geo_locations": {"countries": ["BR"]}},
        )
    if resource == "ads":
        row["creative"] = {"id": "000501"}
    out = norm(resource, row)
    assert out["store_id"] == ACCOUNT.store_id and out["account_id"] == "000101"
    if resource == "adsets":
        assert out["targeting_summary"] == {"fields_present": ["geo_locations"]}
        assert out["optimization_goal"] == "LINK_CLICKS"
    if resource == "ads":
        assert out["creative_id"] == "000501"


@pytest.mark.parametrize("spend", ["0", "100.00"])
def test_exact_spend_and_calculated_rates(spend):
    row = {**source("insights"), "spend": spend, "cpm": "999999"}
    out = norm(row=row)
    assert out["spend"] == spend and out["ctr"] == "1.000000000"
    assert out["cpm"] in {"0.000000000", "100.000000000"}
    assert out["link_clicks"] == 8 and out["landing_page_views"] == "7"
    assert out["source_updated_at"] is None
    assert norm(row={**row, "clicks": "0"})["cpc"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"spend": "-1"},
        {"spend": None},
        {"account_currency": "USD"},
        {"date_start": "2026-02-30"},
        {"date_stop": "2026-01-02"},
        {"ad_id": ""},
        {"ad_id": 401},
        {"account_id": "999"},
        {"impressions": "-1"},
        {"clicks": "1.5"},
        {"actions": [{"action_type": "landing_page_view", "value": "-1"}]},
    ],
)
def test_invalid_insights_blocked(change):
    with pytest.raises((SafeError, ValueError)):
        norm(row={**source("insights"), **change})


def test_duplicate_identical_and_conflicting_blocked():
    out = norm()
    for other in (out, {**out, "spend": "999"}):
        with pytest.raises(SafeError, match="duplicate"):
            validate_foundation("insights", [out, other], ACCOUNT)


def test_multi_day_levels_and_breakdowns_have_distinct_keys():
    day2 = norm(row={**source("insights"), "date_start": "2026-01-02", "date_stop": "2026-01-02"})
    ad = norm()
    data = source("insights")
    data.pop("ad_id")
    adset = norm(row=data, level="adset")
    data.pop("adset_id")
    campaign = norm(row=data, level="campaign")
    config = replace(INSIGHTS, breakdowns=("country",))
    br = norm(row={**source("insights"), "country": "BR"}, insights=config)
    us = norm(row={**source("insights"), "country": "US"}, insights=config)
    assert len({r["row_key"] for r in (day2, ad, adset, campaign, br, us)}) == 6
    validate_foundation("insights", [day2, ad, adset, campaign, br, us], ACCOUNT)
    assert campaign["ad_id"] is None and campaign["adset_id"] is None
    with pytest.raises(SafeError):
        norm(insights=config)
    with pytest.raises(SafeError):
        norm(row={**source("insights"), "country": "BR"})
    with pytest.raises(SafeError):
        norm(level="campaign")


def test_schema_incompatible_and_currency_blocked():
    out = norm()
    for changed in (
        {**out, "unexpected": 1},
        {**out, "spend": 1.2},
        {**out, "currency": "XXX"},
        {**out, "timezone": "UTC"},
    ):
        with pytest.raises(SafeError):
            validate_foundation("insights", [changed], ACCOUNT)
    with pytest.raises(SafeError):
        replace(ACCOUNT, currency="brl")


def test_mock_pagination_raw_before_projection_no_token_persistence():
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [source("insights")],
                    "access_token": TOKEN,
                    "paging": {
                        "next": "https://untrusted.example/?access_token=" + TOKEN,
                        "cursors": {"after": "cursor-2"},
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {**source("insights"), "date_start": "2026-01-02", "date_stop": "2026-01-02"}
                ]
            },
        )

    connector = MetaFoundationConnector(ACCOUNT, token=TOKEN, transport=httpx.MockTransport(handle))
    try:
        out = extract_foundation_offline(connector, "insights", INSIGHTS, observed_at=AT)
        assert len(out["raw_pages"]) == len(out["rows"]) == 2
        assert TOKEN not in str(out)
        assert requests[1].url.params["after"] == "cursor-2"
        assert all(r.url.host == "graph.facebook.com" for r in requests)
    finally:
        connector.close()


def test_connector_level_and_fields_prepared_but_live_blocked():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"data": []})

    c = MetaFoundationConnector(ACCOUNT, token=TOKEN, transport=httpx.MockTransport(handle))
    try:
        c.set_insights_level("campaign")
        extract_foundation_offline(c, "insights", INSIGHTS, observed_at=AT)
        assert calls[0].url.params["level"] == "campaign"
        assert (
            "targeting" in FOUNDATION_FIELDS["adsets"]
            and "creative{id}" in FOUNDATION_FIELDS["ads"]
        )
        with pytest.raises(SafeError):
            c.set_insights_level("account")
    finally:
        c.close()
    with pytest.raises(SafeError, match="live_disabled"):
        MetaFoundationConnector(ACCOUNT, token=TOKEN, transport=None)


def test_duplicate_across_pages_and_budget_fail_closed():
    def handle(request):
        return httpx.Response(200, json={"data": [source("insights"), source("insights")]})

    c = MetaFoundationConnector(ACCOUNT, token=TOKEN, transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(SafeError, match="duplicate"):
            extract_foundation_offline(c, "insights", INSIGHTS, observed_at=AT)
        with pytest.raises(SafeError, match="budget"):
            extract_foundation_offline(c, "insights", INSIGHTS, observed_at=AT, max_records=1)
    finally:
        c.close()


def test_schema_proposal_reproducible_and_existing_schemas_untouched(tmp_path):
    generate(tmp_path)
    root = Path("infra/terraform/meta_live_proposed")
    for path in root.rglob("*.json"):
        assert path.read_text() == (tmp_path / path).read_text()


def test_exact_campaign_adset_ad_ids_connect_to_influence_without_coercion():
    from src.influence.engine import build
    from tests.influence.test_influence import fixture

    p, data = fixture()
    account = replace(ACCOUNT, store_id=p.store_id)
    normalized = {}
    for resource in ("campaigns", "adsets", "ads"):
        normalized[resource] = normalize_foundation(
            resource, source(resource), account, None, observed_at=AT
        )
    data["events"][0].update(
        meta_campaign_id=normalized["campaigns"]["campaign_id"],
        meta_adset_id=normalized["adsets"]["adset_id"],
        meta_ad_id=normalized["ads"]["ad_id"],
    )
    result = build(p, **data)
    touch = result["analytics_paid_touchpoints"][0]
    assert (
        touch["campaign_id"] == "000201"
        and touch["adset_id"] == "000301"
        and touch["ad_id"] == "000401"
    )
    assert result["analytics_customer_paid_influence"][0]["paid_media_influenced"]


def test_same_insight_on_two_pages_cannot_publish_twice():
    def handle(request):
        body = {"data": [source("insights")]}
        if "after" not in request.url.params:
            body["paging"] = {"next": "ignored", "cursors": {"after": "next"}}
        return httpx.Response(200, json=body)

    connector = MetaFoundationConnector(ACCOUNT, token=TOKEN, transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(SafeError, match="duplicate"):
            extract_foundation_offline(connector, "insights", INSIGHTS, observed_at=AT)
    finally:
        connector.close()


def test_store_isolation_and_replay_keys():
    original = norm()
    other = normalize_foundation(
        "insights",
        source("insights"),
        replace(ACCOUNT, store_id="other-store"),
        INSIGHTS,
        observed_at=AT,
    )
    assert original["row_key"] != other["row_key"]
    assert norm() == original
    with pytest.raises(SafeError, match="account_mismatch"):
        validate_foundation("insights", [other], ACCOUNT)
    with pytest.raises(SafeError):
        validate_foundation("insights", [{**original, "ad_id": None}], ACCOUNT)
