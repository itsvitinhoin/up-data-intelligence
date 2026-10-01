"""Synthetic snapshots, in-process API; network remains globally forbidden."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from src.influence.engine import InfluenceScope
from src.influence.materialization import materialize as inf
from src.intelligence.api import MaterializedAPI, Principal
from src.intelligence.materialization import materialize
from src.intelligence.schema import SCHEMAS, generate
from tests.influence.test_influence import fixture


def make(*, repeat=False, canceled=False, media=True, store="synthetic"):
    p, data = fixture()
    p = replace(p, store_id=store)
    data.pop("paid_evidence")
    at = data.pop("calculated_at")
    for rows in data.values():
        for row in rows:
            row["store_id"] = store
    data["customers"][0].update(
        company_name="Synthetic Company",
        trade_name="Synthetic",
        state="SP",
        city="Synthetic City",
        customer_type="WHOLESALE",
        email="PII_SENTINEL",
        phone="PII_SENTINEL",
        cnpj="PII_SENTINEL",
        cpf="PII_SENTINEL",
    )
    data["customers"].append({**data["customers"][0], "customer_id": "c2", "state": "RJ"})
    data["orders"][0]["version_id"] = "ov1"
    if not media:
        data["events"][0].update(meta_campaign_id=None, meta_adset_id=None, meta_ad_id=None)
    if canceled:
        data["orders"][0]["order_status"] = "CANCELED"
    if repeat:
        data["orders"].append(
            {**data["orders"][0], "order_id": "o2", "created_at": "2026-09-05T12:00:00Z"}
        )
        data["events"].append(
            {
                **data["events"][1],
                "fact_id": "f3",
                "order_id": "o2",
                "occurred_at": "2026-09-05T12:00:00Z",
            }
        )
    items = [
        {
            "store_id": store,
            "source_system": "upzero",
            "order_id": "o1",
            "item_id": "i1",
            "parent_order_version_id": "ov1",
            "present_in_latest_snapshot": True,
            "variant_id": "v1",
            "sku": "synthetic-sku",
            "asset_id": "asset",
            "status": "attended",
            "unit_price": "10.00",
            "original_qty": 10,
            "qty": "8",
        }
    ]
    influences = {
        s.value: inf(p, data, calculated_at=at, influence_scope=s) for s in InfluenceScope
    }
    args = {
        "customers": data["customers"],
        "orders": data["orders"],
        "events": data["events"],
        "identity_links": data["identity_links"],
        "items": items,
        "influence": influences,
        "calculated_at": at,
    }
    return p, args, materialize(p, **args)


def api(artifact):
    return MaterializedAPI([artifact], cursor_key=b"synthetic-test-key-not-a-credential" * 2)


def principal(store="synthetic", role="viewer"):
    return Principal("synthetic-user", role, frozenset({store}))


def profile(a):
    return next(
        r for r in a["tables"]["analytics_customer_360_profile"] if r["customer_id"] == "c1"
    )


def test_profile_repurchase_partial_and_scope_separation():
    _, _, a = make(repeat=True)
    p = profile(a)
    assert p["total_orders"] == 2 and p["purchase_count"] == 2 and p["has_repurchase"]
    assert p["total_requested_revenue"] == "200.00" and p["total_fulfilled_revenue"] == "160.00"
    assert (
        p["paid_media_influenced"]
        and p["acquisition_influenced"]
        and not p["repeat_purchase_influenced"]
    )
    assert not p["history_complete"] and p["ltv_observed"] == "200.00"
    products = a["tables"]["analytics_customer_products_summary"]
    assert products[0]["product_id"] is None and products[0]["fulfilled_revenue"] == "80.00"


def test_no_media_and_canceled_commercial_not_qualifying():
    assert not profile(make(media=False)[2])["paid_media_influenced"]
    a = make(canceled=True)[2]
    p = profile(a)
    assert p["total_orders"] == 1 and p["purchase_count"] == 0 and p["ltv_observed"] == "0"
    assert not p["paid_media_influenced"] and p["first_order_at"] is None
    assert a["tables"]["analytics_customer_orders_summary"][0]["purchase_number"] is None


def test_snapshot_coherence_and_item_versions_fail_closed():
    p, args, _ = make()
    args["orders"][0]["requested_total"] = "999"
    with pytest.raises(ValueError, match="incompatible"):
        materialize(p, **args)
    p, args, _ = make()
    args["items"][0]["parent_order_version_id"] = "wrong"
    with pytest.raises(ValueError, match="snapshot_mismatch"):
        materialize(p, **args)


def test_detail_no_pii_and_no_raw_identity_for_any_role():
    a = make()[2]
    # Even fields accidentally added to a materialized row are not automatically exposed.
    a["tables"]["analytics_customer_timeline"][0]["email"] = "PII_SENTINEL"
    for role in ("viewer", "manager", "admin"):
        status, body = api(a).handle(
            "GET", "/v1/customers/c1", {"store_id": "synthetic"}, principal(role=role)
        )
        assert status == 200 and body["profile"]["customer_id"] == "c1"
        assert body["commercial"]["total_fulfilled_revenue"] == "80.00"
        assert "PII_SENTINEL" not in json.dumps(body)
        assert "identity_path" not in json.dumps(body)
        assert body["products"]["data"][0]["product_id"] is None


def test_list_pagination_filters_and_cursor_binding():
    service = api(make()[2])
    q = {"store_id": "synthetic", "page_size": "1"}
    status, first = service.handle("GET", "/v1/customers", q, principal())
    assert status == 200 and len(first["data"]) == 1
    token = first["pagination"]["cursor"]
    status, second = service.handle(
        "GET", "/v1/customers", {**q, "page": "2", "cursor": token}, principal()
    )
    assert status == 200 and first["data"][0]["customer_id"] != second["data"][0]["customer_id"]
    assert second["pagination"]["cursor"] is None
    assert (
        service.handle(
            "GET", "/v1/customers", {**q, "page": "2", "cursor": token, "state": "SP"}, principal()
        )[0]
        == 400
    )
    assert (
        service.handle(
            "GET", "/v1/customers", {**q, "page": "2", "cursor": token + "x"}, principal()
        )[0]
        == 400
    )
    status, res = service.handle(
        "GET",
        "/v1/customers",
        {
            "store_id": "synthetic",
            "state": "SP",
            "paid_media_influenced": "true",
            "min_requested_revenue": "100",
            "first_purchase_date": "2026-09-03",
        },
        principal(),
    )
    assert status == 200 and [r["customer_id"] for r in res["data"]] == ["c1"]


def test_tenant_auth_missing_and_empty_results():
    a = make()[2]
    b = make(store="other")[2]
    service = MaterializedAPI([a, b], cursor_key=b"test-only-key-material-32-bytes!!")
    assert service.handle("GET", "/v1/customers", {"store_id": "other"}, principal())[0] == 403
    assert service.handle("GET", "/v1/customers", {"store_id": "synthetic"}, None)[0] == 401
    assert service.handle("GET", "/v1/customers", {}, principal())[0] == 400
    assert (
        service.handle("GET", "/v1/customers/missing", {"store_id": "synthetic"}, principal())[0]
        == 404
    )
    status, res = service.handle(
        "GET", "/v1/customers", {"store_id": "synthetic", "state": "not-present"}, principal()
    )
    assert status == 200 and res["data"] == []


def test_timeline_ordered_redacted_and_orders_campaign_filter():
    service = api(make()[2])
    q = {"store_id": "synthetic"}
    status, res = service.handle("GET", "/v1/customers/c1/timeline", q, principal())
    assert status == 200
    assert [r["occurred_at"] for r in res["data"]] == sorted(r["occurred_at"] for r in res["data"])
    assert all("session_id" not in r and "user_id" not in r for r in res["data"])
    status, res = service.handle(
        "GET",
        "/v1/orders/influenced",
        {**q, "campaign_id": "100", "date_from": "2026-09-01", "date_to": "2026-09-04"},
        principal(),
    )
    assert status == 200 and len(res["data"]) == 1 and res["data"][0]["campaigns"] == ["100"]
    assert service.handle("GET", "/v1/campaigns/100/customers", q, principal())[0] == 501


def test_schemas_reproducible_and_materialized_api_rejects_core(tmp_path):
    generate(tmp_path)
    folder = Path("infra/terraform/customer_intelligence_proposed")
    for path in folder.rglob("*.json"):
        assert path.read_text() == (tmp_path / path).read_text()
    active = json.loads(Path("infra/terraform/tables.json").read_text())
    assert set(SCHEMAS) <= set(active)  # CHANGE #16 activates revised INT64 live contracts.
    a = deepcopy(make()[2])
    a["tables"]["analytics_events"] = []
    with pytest.raises(ValueError):
        api(a)


def rebuild(p, args):
    data = {k: args[k] for k in ("customers", "orders", "events", "identity_links")}
    args["influence"] = {
        s.value: inf(p, data, calculated_at=args["calculated_at"], influence_scope=s)
        for s in InfluenceScope
    }
    return materialize(p, **args)


def test_multicampaign_and_repeat_touch_do_not_duplicate_money():
    p, args, _ = make(repeat=True)
    args["events"].append(
        {
            **args["events"][0],
            "fact_id": "repeat-touch",
            "version_id": "repeat-version",
            "occurred_at": "2026-09-04T12:00:00Z",
            "meta_campaign_id": "101",
        }
    )
    a = rebuild(p, args)
    assert profile(a)["repeat_purchase_influenced"]
    assert profile(a)["total_requested_revenue"] == "200.00"
    rows = a["tables"]["analytics_customer_orders_summary"]
    assert len(rows) == 2 and rows[1]["campaign_count"] == 2
    service = api(a)
    status, result = service.handle(
        "GET",
        "/v1/orders/influenced",
        {"store_id": "synthetic", "influence_scope": "REPEAT_PURCHASE"},
        principal(),
    )
    assert status == 200 and len(result["data"]) == 1
    row = result["data"][0]
    assert row["campaigns"] == ["101"] and row["campaign_count"] == 1
    assert row["first_campaign_id"] == row["last_campaign_id"] == "101"
    assert row["requested_total"] == "100.00"


def test_nested_pagination_and_generation_role_binding():
    p, args, a = make(repeat=True)
    service = api(a)
    q = {"store_id": "synthetic", "page_size": "1"}
    _, first = service.handle("GET", "/v1/customers/c1", q, principal())
    token = first["orders"]["pagination"]["cursor"]
    second_q = {**q, "orders_page": "2", "orders_cursor": token}
    status, second = service.handle("GET", "/v1/customers/c1", second_q, principal())
    assert status == 200
    assert first["orders"]["data"][0]["order_id"] != second["orders"]["data"][0]["order_id"]
    assert second["products"] == first["products"]
    assert service.handle("GET", "/v1/customers/c1", second_q, principal(role="admin"))[0] == 400
    args["calculated_at"] = "2026-09-30T00:00:00Z"
    updated = rebuild(p, args)
    assert api(updated).handle("GET", "/v1/customers/c1", second_q, principal())[0] == 400


@pytest.mark.parametrize(
    "filter",
    [
        {"page_size": "101"},
        {"page": "0"},
        {"page": "2"},
        {"paid_media_influenced": "yes"},
        {"min_requested_revenue": "NaN"},
        {"first_purchase_date": "invalid"},
        {"email": "forbidden"},
    ],
)
def test_invalid_query_is_rejected(filter):
    assert (
        api(make()[2]).handle(
            "GET",
            "/v1/customers",
            {
                "store_id": "synthetic",
                **filter,
            },
            principal(),
        )[0]
        == 400
    )


def test_empty_purchase_dates_and_negative_filters():
    service = api(make()[2])
    status, result = service.handle(
        "GET",
        "/v1/customers",
        {"store_id": "synthetic", "paid_media_influenced": "false", "has_repurchase": "false"},
        principal(),
    )
    assert status == 200 and [r["customer_id"] for r in result["data"]] == ["c2"]
    status, result = service.handle(
        "GET",
        "/v1/customers",
        {
            "store_id": "synthetic",
            "last_purchase_date": "2026-09-03",
            "max_requested_revenue": "100",
        },
        principal(),
    )
    assert status == 200 and [r["customer_id"] for r in result["data"]] == ["c1"]


def test_contract_reproducibility_and_responses(tmp_path):
    from src.intelligence.contract import contract
    from src.intelligence.contract import generate as generate_contract

    generate_contract(tmp_path)
    path = Path("docs/openapi/data-intelligence.openapi.json")
    assert path.read_text() == (tmp_path / path).read_text()
    spec = contract()
    assert len(spec["paths"]) == 5

    def refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                assert node["$ref"].split("/")[-1] in spec["components"]["schemas"]
            for value in node.values():
                refs(value)
        elif isinstance(node, list):
            for value in node:
                refs(value)

    refs(spec)
    service = api(make()[2])
    for path, name in (
        ("/v1/customers", "CustomerListItem"),
        ("/v1/customers/c1/timeline", "TimelineEvent"),
        ("/v1/orders/influenced", "Order"),
    ):
        status, body = service.handle("GET", path, {"store_id": "synthetic"}, principal())
        assert status == 200 and "PII_SENTINEL" not in json.dumps(body)
        assert all(
            set(row) == set(spec["components"]["schemas"][name]["properties"])
            for row in body["data"]
        )


def test_local_publication_idempotence_and_input_unchanged(tmp_path):
    from src.influence.materialization import publish_local

    p, args, a = make()
    before = deepcopy(args)
    again = materialize(p, **args)
    assert args == before and again == a
    path = tmp_path / "synthetic.json"
    assert publish_local(path, a)
    assert not publish_local(path, again)
    assert json.loads(path.read_text()) == a
    assert path.stat().st_mode & 0o777 == 0o600


def test_local_cli_synthetic_only(tmp_path, monkeypatch):
    import sys

    from src.intelligence.offline import main

    _, args, expected = make()
    config = json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    config["store_id"] = "synthetic"
    policy_path, source_path, output = (
        tmp_path / n for n in ("policy.json", "source.json", "out.json")
    )
    policy_path.write_text(json.dumps(config))
    source_path.write_text(
        json.dumps(
            {k: args[k] for k in ("customers", "orders", "items", "events", "identity_links")}
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "offline",
            "--policy",
            str(policy_path),
            "--input",
            str(source_path),
            "--output",
            str(output),
            "--calculated-at",
            args["calculated_at"],
        ],
    )
    main()
    main()
    assert json.loads(output.read_text()) == expected


def test_materializer_tenant_boundary_and_item_observation():
    p, args, expected = make()
    _, other, _ = make(store="other")
    for field in ("customers", "orders", "items", "events", "identity_links"):
        args[field].extend(other[field])
    assert materialize(p, **args) == expected
    args["items"][0]["observed_at"] = "2026-10-01T00:00:00Z"
    with pytest.raises(ValueError, match="observation_after"):
        materialize(p, **args)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("generation", "generation_mismatch"),
        ("policy", "policy_mismatch"),
        ("duplicate", "duplicate_materialized_key"),
    ],
)
def test_api_rejects_mixed_or_duplicate_materialized_rows(mutation, code):
    a = make()[2]
    rows = a["tables"]["analytics_customer_360_profile"]
    if mutation == "duplicate":
        rows.append(deepcopy(rows[0]))
    else:
        rows[0]["policy_hash" if mutation == "policy" else "generation"] = "incompatible"
    with pytest.raises(ValueError, match=code):
        api(a)
