"""Synthetic evidence only: no customer data, cloud client or network."""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.analytics.config import AnalyticsPolicy
from src.influence.engine import build
from src.influence.schema import SCHEMAS, generate


def fixture():
    policy = replace(
        AnalyticsPolicy.from_dict(
            json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
        ).reference(),
        store_id="synthetic",
    )
    customer = {"store_id": "synthetic", "source_system": "upzero", "customer_id": "c1"}
    order = {
        **customer,
        "order_id": "o1",
        "created_at": "2026-09-03T12:00:00Z",
        "order_status": "CONFIRMED",
        "requested_total": "100.00",
        "fulfilled_total": "80.00",
        "requested_items_qty": 10,
        "fulfilled_items_qty": 8,
    }
    touch = {
        "store_id": "synthetic",
        "source_system": "upzero",
        "fact_id": "f1",
        "version_id": "fv1",
        "event_id": "evt1",
        "event_name": "product_view",
        "session_id": "s1",
        "visitor_id": "v1",
        "user_id": "u1",
        "occurred_at": "2026-09-02T12:00:00Z",
        "meta_campaign_id": "100",
        "meta_adset_id": "200",
        "meta_ad_id": "300",
    }
    conversion = {
        **touch,
        "fact_id": "f2",
        "version_id": "fv2",
        "event_id": "evt2",
        "event_name": "purchase",
        "order_id": "o1",
        "occurred_at": order["created_at"],
        "meta_campaign_id": None,
        "meta_adset_id": None,
        "meta_ad_id": None,
    }
    return policy, {
        "customers": [customer],
        "orders": [order],
        "events": [touch, conversion],
        "identity_links": [],
        "paid_evidence": [proof(touch)],
        "calculated_at": "2026-09-29T00:00:00Z",
    }


def proof(t):
    return {
        "store_id": t["store_id"],
        "source_system": "upzero",
        "fact_id": t["fact_id"],
        "source_fact_version_id": t["version_id"],
        "account_id": "999",
        "confidence": "deterministic_entity_match",
        "evidence_type": "configured_account_and_exact_source_ids",
        "attribution_eligible": True,
        "issues": [],
        "entity_versions": {"campaign_id": "synthetic-meta-version"},
        **{k: t.get("meta_" + k) for k in ("campaign_id", "adset_id", "ad_id")},
    }


def customer(result):
    return result["analytics_customer_paid_influence"][0]


def test_customer_without_media_or_without_identity():
    p, data = fixture()
    data["paid_evidence"] = []
    data["events"][0].update(meta_campaign_id=None, meta_adset_id=None, meta_ad_id=None)
    out = build(p, **data)
    assert not customer(out)["paid_media_influenced"]
    assert customer(out)["requested_revenue_influenced"] == 0
    assert out["analytics_paid_touchpoints"] == []
    p, data = fixture()
    data["events"].pop()
    out = build(p, **data)
    assert len(out["analytics_paid_touchpoints"]) == 1
    assert not customer(out)["paid_media_influenced"]


def test_direct_order_partial_fulfillment_and_originals_unchanged():
    p, data = fixture()
    before = deepcopy(data)
    out = build(p, **data)
    assert data == before
    row = out["analytics_order_paid_influence"][0]
    assert row["evidence_type"] == "DIRECT" and row["purchase_number"] == 1
    assert row["requested_total"] == Decimal("100")
    assert row["fulfilled_total"] == Decimal("80")
    assert customer(out)["requested_quantity_influenced"] == 10
    assert customer(out)["fulfilled_quantity_influenced"] == 8
    assert customer(out)["paid_media_influenced"]
    for name, rows in out.items():
        assert all(set(r) == set(SCHEMAS[name].fields) for r in rows)


def test_repurchase_without_exclusive_attribution():
    p, data = fixture()
    data["orders"].append(
        {**data["orders"][0], "order_id": "o2", "created_at": "2026-09-04T12:00:00Z"}
    )
    out = build(p, **data)
    assert [r["purchase_number"] for r in out["analytics_order_paid_influence"]] == [1, 2]
    assert [r["evidence_type"] for r in out["analytics_order_paid_influence"]] == [
        "DIRECT",
        "CUSTOMER_JOURNEY",
    ]
    assert customer(out)["influenced_orders"] == 2
    assert customer(out)["paid_touch_count"] == 1
    assert customer(out)["requested_revenue_influenced"] == 200


def test_multiple_campaigns_and_ads_do_not_duplicate_customer_revenue():
    p, data = fixture()
    for i, campaign in [(3, "100"), (4, "101")]:
        t = {
            **data["events"][0],
            "fact_id": f"f{i}",
            "version_id": f"fv{i}",
            "meta_campaign_id": campaign,
            "meta_ad_id": str(300 + i),
        }
        data["events"].append(t)
        data["paid_evidence"].append(proof(t))
    out = build(p, **data)
    rows = out["analytics_order_paid_influence"]
    assert len(rows) == 2 and sum(r["touch_count"] for r in rows) == 3
    assert rows[0]["ad_id"] is None and len(rows[0]["participating_ads"]) == 2
    assert customer(out)["campaign_count"] == 2 and customer(out)["ad_count"] == 3
    assert customer(out)["influenced_orders"] == 1
    assert customer(out)["requested_revenue_influenced"] == 100
    assert sum(r["requested_total"] for r in rows) == 200  # non-additive across campaigns


def test_canceled_order_excluded_and_missing_amount_not_zero():
    p, data = fixture()
    data["orders"][0]["order_status"] = "CANCELED"
    assert not customer(build(p, **data))["paid_media_influenced"]
    p, data = fixture()
    data["orders"][0]["fulfilled_total"] = None
    assert customer(build(p, **data))["fulfilled_revenue_influenced"] is None


@pytest.mark.parametrize("at", ["2026-09-03T12:00:00Z", "2026-09-03T13:00:00Z"])
def test_touch_must_strictly_precede_order(at):
    p, data = fixture()
    data["events"][0]["occurred_at"] = at
    assert not customer(build(p, **data))["paid_media_influenced"]


def test_user_id_is_not_customer_id_and_needs_explicit_links():
    p, data = fixture()
    t, anchor = data["events"]
    t.update(session_id="other", visitor_id=None, user_id="c1")
    anchor.update(visitor_id=None, user_id="c1")
    assert not customer(build(p, **data))["paid_media_influenced"]
    for event in data["events"]:
        data["identity_links"].append(
            {
                "store_id": "synthetic",
                "source_system": "upzero",
                "link_id": "link-" + event["fact_id"],
                "source_fact_id": event["fact_id"],
                "source_version_id": event["version_id"],
                "confidence_type": "DETERMINISTIC",
                "evidence_type": "observed_cooccurrence",
                "left_namespace": "session_id",
                "left_id": event["session_id"],
                "right_namespace": "user_id",
                "right_id": event["user_id"],
                "occurred_at": event["occurred_at"],
            }
        )
    out = build(p, **data)
    assert out["analytics_order_paid_influence"][0]["evidence_type"] == "SUPPORTED"
    data["identity_links"][0]["source_version_id"] = "stale"
    assert not customer(build(p, **data))["paid_media_influenced"]


def test_shared_identity_is_ambiguous_not_merged():
    p, data = fixture()
    data["customers"].append({**data["customers"][0], "customer_id": "c2"})
    data["orders"].append({**data["orders"][0], "order_id": "o2", "customer_id": "c2"})
    data["events"].append({**data["events"][1], "fact_id": "f3", "order_id": "o2"})
    out = build(p, **data)
    assert all(not r["paid_media_influenced"] for r in out["analytics_customer_paid_influence"])


def test_isolation_replay_stale_paid_evidence_and_no_utm_guess():
    p, data = fixture()
    expected = build(p, **data)
    data["events"].append({**data["events"][0], "store_id": "other"})
    assert build(p, **data) == expected
    data["paid_evidence"][0]["source_fact_version_id"] = "stale"
    data["events"][0].update(
        utm_source="facebook",
        utm_medium="cpc",
        meta_campaign_id=None,
        meta_adset_id=None,
        meta_ad_id=None,
    )
    assert not customer(build(p, **data))["paid_media_influenced"]


def test_schema_generation_is_reproducible_and_not_active(tmp_path):
    generate(tmp_path)
    folder = Path("infra/terraform/paid_influence_proposed")
    for file in folder.rglob("*.json"):
        assert file.read_text() == (tmp_path / file).read_text()
    active = json.loads(Path("infra/terraform/tables.json").read_text())
    assert set(SCHEMAS) <= set(active)  # CHANGE #16 activates revised INT64 live contracts.


def test_duplicate_fact_rejected_and_output_order_deterministic():
    p, data = fixture()
    expected = build(p, **data)
    data["events"].reverse()
    assert build(p, **data) == expected
    data["events"].append(deepcopy(data["events"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        build(p, **data)


def test_visitor_journey_and_future_anchor_cannot_influence_earlier_order():
    p, data = fixture()
    data["events"][0]["session_id"] = "different"
    out = build(p, **data)
    assert out["analytics_order_paid_influence"][0]["evidence_type"] == "CUSTOMER_JOURNEY"
    data["orders"].append(
        {**data["orders"][0], "order_id": "earlier", "created_at": "2026-09-03T10:00:00Z"}
    )
    assert {r["order_id"] for r in build(p, **data)["analytics_order_paid_influence"]} == {"o1"}


def test_cancelled_customer_anchor_still_prevents_shared_identity_claim():
    p, data = fixture()
    data["customers"].append({**data["customers"][0], "customer_id": "c2"})
    data["orders"].append(
        {**data["orders"][0], "order_id": "o2", "customer_id": "c2", "order_status": "CANCELED"}
    )
    data["events"].append({**data["events"][1], "fact_id": "f3", "order_id": "o2"})
    assert not build(p, **data)["analytics_order_paid_influence"]


def test_missing_campaign_is_not_invented_and_names_are_never_identity():
    p, data = fixture()
    data["events"][0]["meta_campaign_id"] = None
    data["paid_evidence"] = [proof(data["events"][0])]
    out = build(p, **data)
    assert out["analytics_order_paid_influence"][0]["campaign_id"] is None
    assert customer(out)["campaign_count"] == 0
    data["events"][0].update(
        session_id=None, visitor_id=None, user_id=None, name="Synthetic", cnpj="synthetic-only"
    )
    data["customers"][0].update(name="Synthetic", cnpj="synthetic-only")
    assert not customer(build(p, **data))["paid_media_influenced"]


def test_offline_cli_writes_exact_numeric_and_does_not_overwrite(tmp_path, monkeypatch):
    from src.influence.offline import main

    _, data = fixture()
    raw_policy = json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    raw_policy["store_id"] = "synthetic"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(raw_policy))
    calculated = data.pop("calculated_at")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(data))
    output = tmp_path / "output.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "offline",
            "--policy",
            str(policy),
            "--input",
            str(snapshot),
            "--output",
            str(output),
            "--calculated-at",
            calculated,
        ],
    )
    main()
    result = json.loads(output.read_text())
    assert result["tables"]["analytics_order_paid_influence"][0]["requested_total"] == "100.00"
    assert output.stat().st_mode & 0o777 == 0o600
    main()  # identical local publication reconciles without rewriting
    assert json.loads(output.read_text()) == result
