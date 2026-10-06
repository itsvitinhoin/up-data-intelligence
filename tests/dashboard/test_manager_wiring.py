"""Structural source-read tests; no source credentials or client construction."""

from src.dashboard.intelligence_queries import meta_period_evidence
from src.dashboard.queries import build


def test_meta_extra_is_pinned_to_source_snapshot_account_and_definition():
    sql = meta_period_evidence("up-data-intelligence-dev")
    for guard in (
        "FOR SYSTEM_TIME AS OF @meta_snapshot",
        "store_id=@store",
        "account_id=@account",
        "configuration_hash=@configuration",
        "level='campaign'",
        "date_start>=@from",
        "date_stop<@to",
    ):
        assert guard in sql
    assert "duplicate_grains" in sql and "COUNT(DISTINCT" in sql
    assert "action_type" in sql and "LIMIT 101" in sql
    assert "reach_campaign_day_sum" in sql and "frequency" not in sql
    assert "COUNTIF(link_clicks IS NULL)>0,NULL" in sql


def test_retention_gaps_and_ticket_use_qualifying_sequence_without_paid_inference():
    query = build(
        "up-data-intelligence-dev",
        "customer_period",
        store="synthetic'",
        policy="safe",
        from_day="2026-09-01",
        to_day="2026-10-01",
    )
    assert "synthetic'" not in query.sql
    assert "LAG(order_at)" in query.sql and "PERCENTILE_CONT" in query.sql
    assert "purchase_number>=2" in query.sql
    assert "revenue_fulfilled IS NULL" in query.sql
    assert "paid" not in query.sql


def test_purchase_item_is_its_own_event_not_purchase_alias():
    q = build(
        "up-data-intelligence-dev",
        "funnel_extra",
        store="synthetic'",
        from_day="2026-09-01",
        to_day="2026-10-01",
    )
    assert "event_name='purchase_item'" in q.sql
    assert "COUNT(DISTINCT fact_id)" in q.sql
    assert "synthetic'" not in q.sql
    assert "DATE(occurred_at,@timezone)<@to" in q.sql
