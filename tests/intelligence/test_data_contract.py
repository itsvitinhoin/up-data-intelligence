"""Executable product contract, synthetic data only; no runtime/cloud changes."""

import json
from pathlib import Path

import pytest

from src.influence.engine import build
from src.intelligence.data_contract import (
    CONTRACT_VERSION,
    EVENT_GROUPS,
    IDENTITY_FIELDS,
    commercial,
    identity,
    segmentation,
    timeline,
)
from tests.influence.test_influence import fixture
from tests.intelligence.test_customer_intelligence import api, make, principal, profile, rebuild


def metrics(orders, **extra):
    return commercial(
        orders,
        store_id="synthetic",
        customer_id="c1",
        qualifying_statuses=frozenset({"CONFIRMED"}),
        as_of="2026-09-28T03:00:00Z",
        **extra,
    )


def event(key="e1", when="2026-09-02T12:00:00Z", **extra):
    return {
        "event_key": key,
        "store_id": "synthetic",
        "customer_id": "c1",
        "event_type": "page_view",
        "occurred_at": when,
        "evidence_type": "CUSTOMER_JOURNEY",
        "evidence_refs": ["synthetic-proof-v1"],
        **extra,
    }


def ordered(events):
    return timeline(events, store_id="synthetic", customer_id="c1", as_of="2026-09-28T03:00:00Z")


def test_declarative_catalog_and_reference_match():
    c = json.loads(Path("config/contracts/customer-intelligence.v1.json").read_text())
    assert c["contract_version"] == CONTRACT_VERSION
    assert c["entity_key"] == ["store_id", "customer_id"]
    assert c["identity_fields"] == IDENTITY_FIELDS
    assert c["event_groups"] == {k: list(v) for k, v in EVENT_GROUPS.items()}
    assert "revenue" not in c["commercial"]
    assert c["health"]["health_score"] is c["health"]["health_status"] is None
    assert len(c["api"]["paths"]) == 5
    assert c["segments"]["AT_RISK"]["rule"] is None


def test_valid_identity_is_scoped_and_allowlisted():
    row = {
        "store_id": "synthetic",
        "customer_id": "c1",
        "email": "private-synthetic",
        "cnpj": "private-synthetic",
    }
    assert identity(row, store_id="synthetic")["customer_id"] == "c1"
    assert "private-synthetic" not in json.dumps(identity(row, store_id="synthetic"))
    with pytest.raises(ValueError):
        identity({**row, "customer_id": ""}, store_id="synthetic")
    with pytest.raises(ValueError):
        identity(row, store_id="other")


def test_unlinked_customer_is_not_invented_from_names_or_user_id():
    p, data = fixture()
    data["events"][0].update(session_id=None, visitor_id=None, user_id="c1", company_name="same")
    out = build(p, **data)
    assert not out["analytics_customer_paid_influence"][0]["paid_media_influenced"]
    assert not any(r.get("fact_id") == "f1" for r in out["analytics_customer_timeline"])


def test_shared_identity_does_not_merge_customers():
    p, data = fixture()
    data["customers"].append({**data["customers"][0], "customer_id": "c2"})
    data["orders"].append({**data["orders"][0], "customer_id": "c2", "order_id": "o2"})
    data["events"].append({**data["events"][1], "fact_id": "f3", "order_id": "o2"})
    out = build(p, **data)
    assert len(out["analytics_customer_paid_influence"]) == 2
    assert not any(r["paid_media_influenced"] for r in out["analytics_customer_paid_influence"])


def test_b2b_example_rates_and_gaps():
    _, args, _ = make()
    args["orders"][0].update(
        requested_total="10000",
        fulfilled_total="8500",
        requested_items_qty=100,
        fulfilled_items_qty=80,
    )
    m = metrics(args["orders"])
    assert m["fulfillment_rate"] == "0.850000000"
    assert m["quantity_fulfillment_rate"] == "0.800000000"
    assert m["revenue_gap"] == "1500" and m["quantity_gap"] == "20"
    assert "revenue" not in m


def test_canceled_orders_remain_commercial_but_not_purchases():
    _, args, _ = make(canceled=True)
    m = metrics(args["orders"])
    assert m["orders_count"] == 1 and m["purchase_count"] == 0
    assert m["requested_revenue"] == "100.00"
    assert m["first_order_at"] is not None
    assert not segmentation(purchase_count=0, paid_acquired=False)["NEW_CUSTOMER"]


def test_repurchase_and_segments_do_not_invent_thresholds():
    _, args, _ = make(repeat=True)
    m = metrics(args["orders"])
    seg = segmentation(purchase_count=m["purchase_count"], paid_acquired=True)
    assert seg["REPEAT_CUSTOMER"] and not seg["NEW_CUSTOMER"] and seg["PAID_ACQUIRED"]
    assert all(seg[k] is None for k in ("ACTIVE_CUSTOMER", "HIGH_VALUE_CUSTOMER", "AT_RISK"))
    assert segmentation(purchase_count=1, paid_acquired=None)["NEW_CUSTOMER"]


@pytest.mark.parametrize(
    "requested,fulfilled,rate,gap",
    [("0", "0", None, "0"), ("10", None, None, None), ("10", "12", "1.200000000", "-2")],
)
def test_unknown_zero_and_overfulfillment(requested, fulfilled, rate, gap):
    _, args, _ = make()
    args["orders"][0].update(requested_total=requested, fulfilled_total=fulfilled)
    m = metrics(args["orders"])
    assert m["fulfillment_rate"] == rate and m["revenue_gap"] == gap


def test_no_orders_unknown_recency_and_duplicate_rejection():
    m = metrics([])
    assert m["orders_count"] == 0 and m["first_order_at"] is None and m["fulfillment_rate"] is None
    _, args, _ = make()
    with pytest.raises(ValueError, match="duplicate"):
        metrics(args["orders"] * 2)
    with pytest.raises(ValueError, match="mixed"):
        metrics([{**args["orders"][0], "store_id": "other"}])


def test_media_presence_and_multicampaign_no_commercial_duplication():
    assert profile(make()[2])["paid_media_influenced"]
    assert not profile(make(media=False)[2])["paid_media_influenced"]
    p, args, _ = make()
    args["events"].append(
        {**args["events"][0], "fact_id": "second-campaign", "meta_campaign_id": "101"}
    )
    a = rebuild(p, args)
    assert a["tables"]["analytics_customer_orders_summary"][0]["campaign_count"] == 2
    assert metrics(args["orders"])["requested_revenue"] == "100.00"


def test_timeline_late_arrival_sorted_by_event_time_and_stable_key():
    newer = event("new", "2026-09-03T00:00:00Z")
    late = event("late", "2026-09-01T00:00:00Z")
    assert [e["event_key"] for e in ordered([newer, late])] == ["late", "new"]
    assert ordered([newer, late]) == ordered([late, newer])
    assert ordered([event(when="2026-09-28T03:00:00Z")]) == []


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_type": None},
        {"evidence_refs": []},
        {"evidence_type": "FUZZY"},
        {"customer_id": None},
        {"store_id": "other"},
    ],
)
def test_timeline_without_proof_or_identity_rejected(change):
    with pytest.raises(ValueError):
        ordered([event(**change)])


def test_timeline_projection_and_api_security():
    row = ordered([event(email="private-synthetic", phone="private-synthetic")])[0]
    assert "private-synthetic" not in json.dumps(row)
    service = api(make()[2])
    assert service.handle("GET", "/v1/customers", {"store_id": "other"}, principal())[0] == 403
    status, body = service.handle("GET", "/v1/customers/c1", {"store_id": "synthetic"}, principal())
    assert status == 200 and "PII_SENTINEL" not in json.dumps(body)
