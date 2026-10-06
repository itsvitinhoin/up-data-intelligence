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


def test_order_quantity_read_is_exact_scoped_and_snapshot_pinned():
    q = build(
        "up-data-intelligence-dev",
        "order_quantity_summary",
        store="synthetic'",
        from_day="2026-09-01",
        to_day="2026-09-03",
        as_of="2026-09-03T03:00:00Z",
        timezone="America/Sao_Paulo",
        snapshot_at="2026-09-03T08:00:00Z",
    )
    assert "synthetic'" not in q.sql
    for guard in (
        "store_id=@store",
        "source_system='upzero'",
        "FOR SYSTEM_TIME AS OF @snapshot_at",
        "created_at<@as_of",
        "DATE(created_at,@timezone)>=@from",
        "DATE(created_at,@timezone)<@to",
        "COUNT(DISTINCT order_id)",
        "requested_items_qty IS NULL",
        "fulfilled_items_qty IS NULL",
    ):
        assert guard in q.sql
    assert "COUNTIF(payment_status='paid') paid_orders" in q.sql
    assert "paid_total" not in q.sql


def test_global_roas_uses_all_upzero_commerce_and_keeps_influence_separate():
    from copy import deepcopy
    from unittest.mock import patch

    from tests.change16.test_stack import service

    svc, reader, principal, grant = service()
    svc.catalog_enabled = True
    reader.override["intelligence_meta_period_evidence"] = [
        {
            "duplicate_grains": 0,
            "action_types": [],
            "action_rows_unavailable": 0,
            "link_clicks": 1,
            "reach_campaign_day_sum": 2,
            "landing_page_views": "1",
        }
    ]
    original = deepcopy(reader.artifact)
    with (
        patch.object(
            svc,
            "_daily",
            return_value=[
                {
                    "event_date": "2026-09-01",
                    "sessions": 10,
                    "add_to_cart": 4,
                    "checkout_started": 2,
                }
            ],
        ),
        patch.object(
            svc,
            "_overview_data",
            return_value={
                "requested_revenue": "200.01",
                "revenue_paid": None,
                "orders_requested": 4,
                "orders_paid": 2,
                "leads_generated": 10,
                "leads_approved": 5,
                "lead_qualification_rate": "50",
                "approved_conversion_rate": None,
                "purchase_frequency_observed": "2",
                "recurring_buyers_observed": 2,
                "average_requested_ticket": "50.0025",
            },
        ),
    ):
        r = svc.intelligence(principal, grant, "performance")
        data = r["data"]
        assert data["commercial_requested_revenue"] == "200.01"
        assert data["commercial_paid_revenue"] is None and data["commercial_roas_paid"] is None
        assert data["commercial_orders_paid"] == 2
        from decimal import Decimal

        assert Decimal(data["commercial_roas_requested"]) == Decimal("200.01") / Decimal(
            data["meta_spend"]
        )
        assert data["commercial_roas_requested"] != data["roas_requested"]
        assert data["media_platforms"] == ["META"]
        assert Decimal(data["registration_cost"]) == Decimal(data["meta_spend"]) / 10
        for row in reader.artifact["tables"]["analytics_performance_summary"]:
            if row["influence_scope"] == "LIFETIME":
                assert data["roas_requested"] == row["roas_requested"]
        assert original["tables"] == reader.artifact["tables"]
        reader.artifact["publication"]["meta_complete"] = False
        data = svc.intelligence(principal, grant, "performance")["data"]
        assert data["available_media_spend"] is None
        assert data["commercial_roas_requested"] is None
        assert data["registration_cost"] is None
        assert data["media_platforms"] == []
