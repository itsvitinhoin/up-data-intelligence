"""Customer campaigns use exact period participation, never client N+1 scans."""

from copy import deepcopy
from unittest.mock import patch

import pytest

from src.dashboard.contracts import ReadError
from src.dashboard.intelligence_queries import campaigns
from tests.change16.test_stack import service


def campaign_rows(reader, customer="c1"):
    rows = deepcopy(reader.artifact["tables"]["analytics_campaign_performance_daily"])
    result = []
    for index, row in enumerate(rows[:2]):
        row.update(customer_id=customer, row_key=str(index + 100), campaign_id=str(index + 100))
        result.append(row)
    return result


def test_customer_campaign_query_is_correlated_parametrized_and_bounded():
    sql = campaigns("up-data-intelligence-dev", customer_scoped=True)
    assert "EXISTS (SELECT 1" in sql
    assert "p.campaign_id=d.campaign_id AND p.customer_id=@customer" in sql
    assert "p.store_id=@store" in sql
    assert "DATE(o.created_at,@timezone)>=@from" in sql
    assert "DATE(o.created_at,@timezone)<@to" in sql
    assert "FOR SYSTEM_TIME AS OF @snapshot" in sql
    assert "ORDER BY d.campaign_id LIMIT @limit" in sql
    assert "@customer customer_id" in sql
    assert "@customer" not in campaigns("up-data-intelligence-dev")


def test_customer_campaign_single_collection_query_and_scope_validation():
    svc, reader, principal, grant = service()
    original = reader.query
    rows = campaign_rows(reader)

    def query(q, **kw):
        if q.name == "intelligence_analytics_campaign_performance_daily":
            reader.calls.append(q)
            assert q.parameters["customer"] == ("STRING", "c1")
            assert q.parameters["store"] == ("STRING", grant.store_id)
            return rows
        return original(q, **kw)

    with patch.object(reader, "query", side_effect=query):
        result = svc.intelligence(principal, grant, "customerCampaigns", entity="c1")
    assert len(result["data"]) == len(rows)
    assert (
        sum(q.name == "intelligence_analytics_campaign_performance_daily" for q in reader.calls)
        == 1
    )
    assert "customer_id" not in result["data"][0]
    assert result["metadata"]["history_complete"] is False

    # Even a reader violating the correlated projection cannot escape isolation.
    rows[0]["customer_id"] = "other-customer"
    with (
        patch.object(reader, "query", side_effect=query),
        pytest.raises(ReadError, match="intelligence_scope_mismatch"),
    ):
        svc.intelligence(principal, grant, "customerCampaigns", entity="c1")


def test_customer_campaigns_reject_missing_customer_before_campaign_query():
    svc, reader, principal, grant = service()
    with pytest.raises(ReadError, match="customer_not_found"):
        svc.intelligence(principal, grant, "customerCampaigns", entity="foreign-customer")
    assert not any(
        q.name == "intelligence_analytics_campaign_performance_daily" for q in reader.calls
    )
