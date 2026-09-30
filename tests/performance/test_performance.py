"""Synthetic-only performance contracts; no IO, API or production data."""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.analytics.policy import HistoryCoverage
from src.connectors.meta.config import Account, Insights
from src.domain.models import SafeError
from src.influence.engine import InfluenceScope
from src.normalization.meta import normalize_foundation
from src.performance.engine import MediaCoverage, build, divide
from src.performance.schema import generate
from tests.influence.test_influence import fixture


def fixture14(*, complete=True, store="synthetic"):
    p, snapshot = fixture()
    p = replace(p, store_id=store)
    if complete:
        p = replace(
            p,
            history_complete=True,
            history_coverage=HistoryCoverage(
                store,
                "2020-01-01T00:00:00Z",
                p.as_of,
                "synthetic-history-proof",
                "synthetic-test",
                True,
                True,
            ),
        )
    at = snapshot.pop("calculated_at")
    snapshot.pop("paid_evidence")
    for rows in snapshot.values():
        for row in rows:
            row["store_id"] = store
    a = Account(store, "001", "synthetic-meta", "v23.0", p.timezone, "BRL")
    config = Insights("2026-09-01", "2026-09-27", "impression", ("7d_click",), None)
    campaign = normalize_foundation(
        "campaigns",
        {"id": "100", "account_id": "001", "name": "Synthetic Campaign"},
        a,
        None,
        observed_at=at,
    )
    media = normalize_foundation(
        "insights",
        {
            "account_id": "001",
            "campaign_id": "100",
            "account_currency": "BRL",
            "date_start": "2026-09-03",
            "date_stop": "2026-09-03",
            "spend": "5",
            "impressions": "1000",
            "clicks": "10",
        },
        a,
        config,
        observed_at=at,
        level="campaign",
    )
    coverage = MediaCoverage(
        store,
        a.account_id,
        p.report_from,
        p.report_to,
        media["configuration_hash"],
        True,
        "synthetic-spend-proof",
    )
    args = {
        "accounts": (a,),
        "meta_insights": [media],
        "meta_campaigns": [campaign],
        "coverage": coverage,
        "calculated_at": at,
    }
    return p, snapshot, args


def result(*, complete=True):
    p, s, a = fixture14(complete=complete)
    return build(p, s, **a)


def table(out, name):
    return out["tables"]["analytics_" + name]


def summary(out):
    return table(out, "performance_summary")[0]


def test_first_purchase_complete_history_and_partial_fulfillment():
    out = result()
    row = table(out, "campaign_order_performance")[0]
    assert row["is_new_customer"] and row["previous_purchase_exists"] is False
    assert (
        row["first_qualified_order_id"] == "o1"
        and row["historical_purchase_count_before_first_purchase"] == 0
    )
    total = summary(out)
    assert total["requested_revenue_influenced"] == "100.00"
    assert total["fulfilled_revenue_influenced"] == "80.00"
    assert total["roas_requested"] == "20.000000000" and total["roas_fulfilled"] == "16.000000000"
    assert total["cac_new_customer"] == "5.000000000" and total["fulfillment_rate"] == "0.800000000"
    daily = table(out, "campaign_performance_daily")[0]
    assert daily["adset_id"] is daily["ad_id"] is None


def test_unknown_history_does_not_assert_new_customer():
    out = result(complete=False)
    assert table(out, "campaign_order_performance")[0]["is_new_customer"] is None
    assert summary(out)["new_customers_influenced"] is None
    assert summary(out)["cac_new_customer"] is None
    assert summary(out)["roas_requested"] == "20.000000000"


def test_old_purchase_before_window_blocks_new_even_without_complete_history():
    p, s, a = fixture14(complete=False)
    s["orders"].append({**s["orders"][0], "order_id": "old", "created_at": "2024-01-01T12:00:00Z"})
    out = build(p, s, **a)
    row = table(out, "campaign_order_performance")[0]
    assert row["is_new_customer"] is False and row["previous_purchase_exists"] is True
    assert row["first_qualified_order_id"] == "old" and row["purchase_number"] == 2
    assert row["historical_purchase_count_before_first_purchase"] == 1
    assert summary(out)["new_customers_influenced"] == 0


def test_repurchase_counts_once_and_scopes_remain_distinct():
    p, s, a = fixture14()
    s["orders"].append({**s["orders"][0], "order_id": "o2", "created_at": "2026-09-05T12:00:00Z"})
    s["events"].append(
        {**s["events"][1], "fact_id": "f3", "order_id": "o2", "occurred_at": "2026-09-05T12:00:00Z"}
    )
    lifetime = build(p, s, **a)
    assert summary(lifetime)["new_customers_influenced"] == 1
    assert summary(lifetime)["influenced_orders"] == 2
    repeat = build(p, s, **a, influence_scope=InfluenceScope.REPEAT_PURCHASE)
    assert summary(repeat)["influenced_orders"] == 0
    s["events"].append(
        {**s["events"][0], "fact_id": "repeat-touch", "occurred_at": "2026-09-04T12:00:00Z"}
    )
    repeat = build(p, s, **a, influence_scope=InfluenceScope.REPEAT_PURCHASE)
    assert (
        summary(repeat)["influenced_orders"] == 1
        and summary(repeat)["new_customers_influenced"] == 0
    )
    assert summary(repeat)["cac_new_customer"] is None


def test_cancelled_never_qualifies_but_spend_remains():
    p, s, a = fixture14()
    s["orders"][0]["order_status"] = "CANCELED"
    out = build(p, s, **a)
    assert summary(out)["influenced_orders"] == 0
    assert summary(out)["meta_spend"] == "5"
    assert summary(out)["roas_requested"] == "0.000000000"
    assert not table(out, "campaign_order_performance")


def test_no_paid_touch_and_equal_conversion_time_are_not_influence():
    p, s, a = fixture14()
    s["events"][0].update(meta_campaign_id=None, meta_adset_id=None, meta_ad_id=None)
    assert summary(build(p, s, **a))["influenced_orders"] == 0
    p, s, a = fixture14()
    s["events"][0]["occurred_at"] = s["orders"][0]["created_at"]
    assert summary(build(p, s, **a))["influenced_orders"] == 0


def test_multiple_campaigns_and_touchpoints_do_not_duplicate_store_totals():
    p, s, a = fixture14()
    s["events"].extend(
        [
            {**s["events"][0], "fact_id": "touch2"},
            {**s["events"][0], "fact_id": "campaign2", "meta_campaign_id": "101"},
        ]
    )
    a["meta_campaigns"].append(
        {**a["meta_campaigns"][0], "row_key": "synthetic-c2", "campaign_id": "101"}
    )
    a["meta_insights"].append(
        {**a["meta_insights"][0], "row_key": "synthetic-i2", "campaign_id": "101"}
    )
    out = build(p, s, **a)
    assert len(table(out, "campaign_order_performance")) == 2
    assert max(r["touch_count"] for r in table(out, "campaign_order_performance")) == 2
    assert summary(out)["influenced_orders"] == 1 and summary(out)["influenced_customers"] == 1
    assert summary(out)["requested_revenue_influenced"] == "100.00"
    assert summary(out)["meta_spend"] == "10" and summary(out)["roas_requested"] == "10.000000000"
    assert (
        sum(
            Decimal(r["requested_revenue_influenced"])
            for r in table(out, "campaign_performance_daily")
        )
        == 200
    )


def test_spend_zero_safe_and_missing_spend_not_zero():
    p, s, a = fixture14()
    a["meta_insights"][0]["spend"] = "0"
    zero = summary(build(p, s, **a))
    assert zero["roas_requested"] is None and zero["cac_new_customer"] == "0.000000000"
    a["coverage"] = replace(a["coverage"], complete=False)
    missing = summary(build(p, s, **a))
    assert missing["meta_spend"] is None and missing["cac_new_customer"] is None
    assert missing["roas_requested"] is None
    assert divide(0, 0) is None and divide(0, 2) == 0 and divide(None, 2) is None
    assert divide(5000, 35) == Decimal("142.857142857")


def test_unknown_facts_or_unmapped_campaign_disable_efficiency():
    p, s, a = fixture14()
    out = build(replace(p, facts_complete=False), s, **a)
    assert summary(out)["roas_requested"] is None
    s["events"][0]["meta_campaign_id"] = "999"
    out = build(p, s, **a)
    assert out["metadata"]["unmapped_influenced_order_campaign_pairs"] == 1
    assert summary(out)["roas_requested"] is None and not summary(out)["influence_complete"]


def test_multi_store_inputs_are_isolated_and_replay_stable():
    p, s, a = fixture14()
    expected = build(p, s, **a)
    _, other, b = fixture14(store="other")
    for key in s:
        s[key].extend(other[key])
    a["accounts"] += b["accounts"]
    # Same account cannot be assigned to two stores by inventory.
    with pytest.raises((ValueError, SafeError)):
        build(p, s, **a)
    a["accounts"] = a["accounts"][:1]
    a["meta_insights"] += b["meta_insights"]
    a["meta_campaigns"] += b["meta_campaigns"]
    assert build(p, s, **a) == expected
    assert all(r["store_id"] == p.store_id for rows in expected["tables"].values() for r in rows)


@pytest.mark.parametrize(
    "mutation", ["level", "breakdown", "configuration", "duplicate", "timezone", "coverage"]
)
def test_incompatible_inputs_fail_closed(mutation):
    p, s, a = fixture14()
    if mutation == "level":
        a["meta_insights"][0]["level"] = "ad"
    if mutation == "breakdown":
        a["meta_insights"][0]["breakdown_values"] = {"country": "BR"}
    if mutation == "configuration":
        a["meta_insights"][0]["configuration_hash"] = "wrong"
    if mutation == "duplicate":
        a["meta_insights"] *= 2
    if mutation == "timezone":
        a["accounts"] = (replace(a["accounts"][0], timezone="UTC"),)
    if mutation == "coverage":
        a["coverage"] = replace(a["coverage"], evidence_ref="")
    with pytest.raises((ValueError, SafeError)):
        build(p, s, **a)


def test_source_unchanged_schemas_reproducible_and_all_requested_models(tmp_path):
    p, s, a = fixture14()
    before = deepcopy((s, a))
    out = build(p, s, **a)
    assert (s, a) == before
    assert len(out["tables"]) == 4
    generate(tmp_path)
    for path in Path("infra/terraform/performance_proposed").rglob("*.json"):
        assert path.read_text() == (tmp_path / path).read_text()
        json.loads(path.read_text())
    assert "roas_paid" not in str(out) and "revenue'" not in str(summary(out))


def test_zero_revenue_is_not_missing_revenue():
    p, s, a = fixture14()
    s["orders"][0].update(requested_total="0", fulfilled_total="0")
    row = summary(build(p, s, **a))
    assert row["roas_requested"] == "0.000000000"
    assert row["roas_fulfilled"] == "0.000000000"
    assert row["fulfillment_rate"] is None
    s["orders"][0]["fulfilled_total"] = None
    assert summary(build(p, s, **a))["roas_fulfilled"] is None


def test_old_cancellation_is_not_previous_purchase():
    p, s, a = fixture14()
    s["orders"].append(
        {
            **s["orders"][0],
            "order_id": "old-cancel",
            "created_at": "2024-01-01T12:00:00Z",
            "order_status": "CANCELED",
        }
    )
    row = table(build(p, s, **a), "campaign_order_performance")[0]
    assert row["is_new_customer"] and row["historical_purchase_count_before_first_purchase"] == 0


def test_independent_stores_with_equal_order_ids_do_not_share_keys():
    p, s, a = fixture14()
    other_p, other_s, other_a = fixture14(store="other")
    left, right = build(p, s, **a), build(other_p, other_s, **other_a)
    assert summary(left)["row_key"] != summary(right)["row_key"]
    assert (
        summary(left)["requested_revenue_influenced"]
        == summary(right)["requested_revenue_influenced"]
    )
    assert summary(left)["generation"] != summary(right)["generation"]


def test_daily_metrics_use_conversion_date_and_period_summary_is_distinct():
    p, s, a = fixture14()
    # Media on contact day, conversion next day; coverage attests remaining days have zero spend.
    a["meta_insights"][0].update(date_start="2026-09-02", date_stop="2026-09-02")
    out = build(p, s, **a)
    daily = {r["date"]: r for r in table(out, "campaign_performance_daily")}
    assert daily["2026-09-02"]["influenced_orders"] == 0
    assert daily["2026-09-03"]["influenced_orders"] == 1
    assert daily["2026-09-03"]["spend"] == "0"
    assert daily["2026-09-03"]["roas_requested"] is None
    assert summary(out)["roas_requested"] == "20.000000000"
