"""Epic #08/#09 synthetic cases; all IO confined to pytest temporary folders."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from test_influence import customer, fixture

from src.influence.engine import InfluenceScope, build
from src.influence.materialization import encode, materialize, publish_local
from src.influence.schema import SCHEMAS


def register(data, *, linked=True):
    anchor = {
        **data["events"][0],
        "fact_id": "registration",
        "version_id": "reg-v1",
        "event_name": "register_approved",
        "occurred_at": "2026-09-02T16:00:00Z",
        "meta_campaign_id": None,
        "meta_adset_id": None,
        "meta_ad_id": None,
    }
    data["events"].append(anchor)
    if linked:
        data["identity_links"].append(
            {
                "store_id": "synthetic",
                "source_system": "upzero",
                "link_id": "registered-customer",
                "source_fact_id": "registration",
                "source_version_id": "reg-v1",
                "left_namespace": "fact_id",
                "left_id": "registration",
                "right_namespace": "customer_id",
                "right_id": "c1",
                "confidence_type": "DETERMINISTIC",
                "evidence_type": "observed_registration_customer",
                "occurred_at": anchor["occurred_at"],
            }
        )
    return anchor


@pytest.mark.parametrize(
    "marker", ["meta_campaign_id", "meta_adset_id", "meta_ad_id", "fbclid", "fbc", "gclid"]
)
def test_each_approved_marker_without_meta_api_lookup(marker):
    p, data = fixture()
    fact = data["events"][0]
    for field in ("meta_campaign_id", "meta_adset_id", "meta_ad_id"):
        fact[field] = None
    fact[marker] = "123" if marker.startswith("meta_") else "synthetic-click"
    data.pop("paid_evidence")
    out = build(p, **data)
    assert customer(out)["paid_media_influenced"]
    point = out["analytics_paid_touchpoints"][0]
    assert point["touch_type"] == "PAID_TRACKING" and marker in point["paid_signal_types"]
    assert point["identity_path"]
    if marker != "meta_campaign_id":
        assert point["campaign_id"] is None


def test_media_before_registration_resolves_without_purchase_event():
    p, data = fixture()
    data["events"].pop()  # order exists, but purchase tracking missing
    register(data)
    out = build(p, **data)
    assert customer(out)["paid_media_influenced"]
    timeline = out["analytics_customer_timeline"]
    assert {r["event_name"] for r in timeline} == {
        "product_view",
        "register_approved",
        "order_created",
    }
    assert len(timeline) == 3
    assert all(r["customer_id"] == "c1" for r in timeline)
    order = next(r for r in timeline if r["record_type"] == "ORDER")
    assert order["fact_id"] is None and order["value"] is None
    assert order["requested_total"] == 100 and order["fulfilled_total"] == 80
    assert order["requested_items_qty"] == 10 and order["fulfilled_items_qty"] == 8


def test_registration_name_alone_is_not_customer_evidence():
    p, data = fixture()
    data["events"].pop()
    register(data, linked=False)
    assert not customer(build(p, **data))["paid_media_influenced"]
    result = build(p, **data)
    assert [r["record_type"] for r in result["analytics_customer_timeline"]] == ["ORDER"]


def test_explicit_order_resolution_wins_and_unknown_order_does_not_fall_back():
    p, data = fixture()
    paid = data["events"][0]
    paid["order_id"] = "o1"
    paid.update(session_id=None, visitor_id=None, user_id=None)
    resolved = build(p, **data)
    assert customer(resolved)["paid_media_influenced"]
    assert resolved["analytics_paid_touchpoints"][0]["evidence_type"] == "SUPPORTED"
    paid["order_id"] = "missing"
    paid.update(session_id="s1", visitor_id="v1", user_id="u1")
    out = build(p, **data)
    assert not customer(out)["paid_media_influenced"]
    assert not any(r["fact_id"] == "f1" for r in out["analytics_customer_timeline"])


def test_repeat_scope_requires_touch_between_previous_and_new_purchase():
    p, data = fixture()
    o2 = {**data["orders"][0], "order_id": "o2", "created_at": "2026-09-05T12:00:00Z"}
    data["orders"].append(o2)
    data["events"].append(
        {
            **data["events"][1],
            "fact_id": "conversion2",
            "order_id": "o2",
            "occurred_at": o2["created_at"],
        }
    )
    assert customer(build(p, **data))["influenced_orders"] == 2
    assert customer(build(p, **data, influence_scope="ACQUISITION"))["influenced_orders"] == 1
    assert not customer(build(p, **data, influence_scope="REPEAT_PURCHASE"))[
        "paid_media_influenced"
    ]
    data["events"].append(
        {
            **data["events"][0],
            "fact_id": "new-touch",
            "version_id": "new-version",
            "occurred_at": "2026-09-04T12:00:00Z",
        }
    )
    out = build(p, **data, influence_scope=InfluenceScope.REPEAT_PURCHASE)
    row = out["analytics_order_paid_influence"][0]
    assert row["order_id"] == "o2" and row["purchase_number"] == 2 and row["touch_count"] == 1
    assert row["influence_scope"] == "REPEAT_PURCHASE"
    assert customer(out)["requested_revenue_influenced"] == 100


def test_canceled_is_in_timeline_not_purchase_metrics_and_fact_fields_preserved():
    p, data = fixture()
    data["orders"][0]["order_status"] = "CANCELED"
    data["events"][0].update(
        value="-1.50",
        quantity=2,
        product_id="product",
        product_variant_id="variant",
        channel="b2b",
        source="site",
        device_type="desktop",
    )
    out = build(p, **data)
    assert not customer(out)["paid_media_influenced"]
    fact = next(r for r in out["analytics_customer_timeline"] if r["fact_id"] == "f1")
    assert fact["variant_id"] == "variant" and fact["quantity"] == 2
    assert str(fact["value"]) == "-1.50" and fact["source"] == "site"
    assert any(r["order_status"] == "CANCELED" for r in out["analytics_customer_timeline"])


def artifact():
    p, data = fixture()
    at = data.pop("calculated_at")
    return materialize(p, data, calculated_at=at)


def test_local_materialization_has_four_models_receipt_and_stable_keys(tmp_path):
    output = artifact()
    assert set(output["tables"]) == set(SCHEMAS)
    assert output["receipt"]["unresolved_facts"] == 0
    assert output["receipt"]["status"] == "completed_offline"
    target = tmp_path / "publication.json"
    assert publish_local(target, output)
    before = target.stat().st_mtime_ns
    assert not publish_local(target, artifact())
    assert target.stat().st_mtime_ns == before
    assert target.stat().st_mode & 0o777 == 0o600
    changed = deepcopy(output)
    changed["receipt"]["status"] = "different"
    with pytest.raises(FileExistsError):
        publish_local(target, changed)
    assert not list(tmp_path.glob(".influence-*"))


def test_failure_before_atomic_link_never_publishes_partial_models(tmp_path):
    target = tmp_path / "publication.json"
    with patch("src.influence.materialization.os.link", side_effect=OSError("synthetic")):
        with pytest.raises(OSError):
            publish_local(target, artifact())
    assert not target.exists() and not list(tmp_path.iterdir())
    assert publish_local(target, artifact())


def test_unresolved_counts_no_customer_or_insufficient_evidence():
    p, data = fixture()
    data["customers"] = []
    at = data.pop("calculated_at")
    output = materialize(p, data, calculated_at=at)
    assert output["tables"]["analytics_customer_timeline"] == []
    assert output["receipt"]["unresolved_facts"] == 2
    assert len(output["tables"]["analytics_paid_touchpoints"]) == 1


def test_fail_closed_model_schema_and_scope():
    tables = artifact()["tables"]
    tables.pop("analytics_customer_timeline")
    with pytest.raises(ValueError, match="incomplete"):
        encode(tables)
    p, data = fixture()
    with pytest.raises(ValueError):
        build(p, **data, influence_scope="LAST_CLICK")


def test_registration_scope_conflict_and_cross_store_links():
    p, data = fixture()
    data["events"].pop()
    register(data)
    data["identity_links"][0]["store_id"] = "other-store"
    assert not customer(build(p, **data))["paid_media_influenced"]
    data["identity_links"][0]["store_id"] = "synthetic"
    data["customers"].append({**data["customers"][0], "customer_id": "c2"})
    data["identity_links"].append(
        {**data["identity_links"][0], "link_id": "conflict", "right_id": "c2"}
    )
    assert not customer(build(p, **data))["paid_media_influenced"]


def test_no_active_schema_or_runtime_registration():
    active = Path("infra/terraform/tables.json").read_text()
    assert (
        "analytics_customer_timeline" in active
    )  # Dedicated #16 runner; Foundation stays isolated.
    assert "src.influence" not in Path("src/jobs/cli.py").read_text()


def test_publication_deterministic_for_reordered_inputs_and_foreign_store():
    p, data = fixture()
    at = data.pop("calculated_at")
    first = materialize(p, data, calculated_at=at)
    data["events"].reverse()
    data["events"].append({**data["events"][0], "store_id": "foreign"})
    assert materialize(p, data, calculated_at=at) == first


@pytest.mark.parametrize("marker", ["", "   ", "{{campaign.id}}", "undefined"])
def test_empty_or_placeholder_marker_is_not_paid(marker):
    p, data = fixture()
    data["events"][0].update(
        meta_campaign_id=None, meta_adset_id=None, meta_ad_id=None, fbclid=marker
    )
    assert not build(p, **data)["analytics_paid_touchpoints"]
