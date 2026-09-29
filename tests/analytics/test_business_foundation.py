"""Synthetic-only business scenarios; no exports or real customer information."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.analytics.engine import build, ratio
from src.analytics.media import (
    AttributedFirstParty,
    AttributionEvidence,
    MeasurementScope,
    PaidMedia,
    media_metrics,
)
from src.analytics.policy import HistoryCoverage, Policy
from src.analytics.quality import AnalyticsQualityError, validate_outputs
from src.analytics.schema import SCHEMAS

POLICY = Policy(
    "synthetic-store",
    "America/Sao_Paulo",
    "BRL",
    "2027-01-01T12:00:00Z",
    "2026-01-01",
    "2026-04-01",
    True,
    True,
    ("CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED"),
    history_coverage=HistoryCoverage(
        "synthetic-store",
        "2020-01-01T00:00:00Z",
        "2029-01-01T00:00:00Z",
        "synthetic-origin-audit",
        "synthetic-reviewer",
        True,
        True,
    ),
)


def customer(cid="c1", **extra):
    return {
        "store_id": POLICY.store_id,
        "source_system": "upzero",
        "customer_id": cid,
        "customer_type": "WHOLESALE",
        **extra,
    }


def order(oid="o1", cid="c1", at="2026-01-01T10:00:00Z", **extra):
    return {
        "store_id": POLICY.store_id,
        "source_system": "upzero",
        "order_id": oid,
        "customer_id": cid,
        "created_at": at,
        "order_status": "CONFIRMED",
        "payment_status": "unpaid",
        "requested_total": "100",
        "fulfilled_total": "80",
        "total": "80",
        "requested_items_qty": 5,
        "fulfilled_items_qty": 4,
        "version_id": "v-" + oid,
        **extra,
    }


def event(fid, name, at, session="s1", **extra):
    return {
        "store_id": POLICY.store_id,
        "source_system": "upzero",
        "fact_id": fid,
        "event_id": "e-" + fid,
        "event_name": name,
        "occurred_at": at,
        "session_id": session,
        **extra,
    }


def run(orders=(), customers=(), items=(), events=(), policy=POLICY):
    return build(
        policy,
        orders=list(orders),
        customers=list(customers),
        items=list(items),
        events=list(events),
    )


def rows(result, table):
    return result["tables"]["analytics_" + table]


def day(result, date="2026-01-01"):
    return next(r for r in rows(result, "store_daily") if r["order_date"] == date)


def test_generated_fulfilled_paid_and_cancelled_have_distinct_semantics():
    output = run(
        [
            order(payment_status="paid"),
            order("cancel", order_status="CANCELED", requested_total="50", fulfilled_total="0"),
        ],
        [customer()],
    )
    daily = day(output)
    assert (
        daily["orders_generated"] == 2
        and daily["orders_paid"] == 1
        and daily["orders_cancelled"] == 1
    )
    assert daily["revenue_generated"] == Decimal("150")
    assert daily["revenue_fulfilled"] == Decimal("80")
    assert daily["revenue_cancelled"] == Decimal("50")
    assert daily["revenue_unfulfilled"] == Decimal("70")  # not called cancelled
    assert (
        daily["revenue_paid"] is daily["payment_date"] is daily["average_order_value_paid"] is None
    )
    assert daily["approval_rate"] == Decimal("0.5")
    assert daily["average_order_value_generated"] == Decimal("75")
    assert daily["items_per_order_generated"] == Decimal(5)
    assert daily["items_per_order_fulfilled"] == Decimal(4)
    assert any(q["rule_id"] == "paid_orders_without_paid_revenue" for q in output["quality"])
    assert rows(output, "customer_metrics")[0]["purchases"] == 1


def test_sequence_new_returning_ltv_and_fractional_interpurchase_days():
    output = run(
        [
            order(),
            order("o2", at="2026-01-31T10:00:00Z"),
            order("o3", at="2026-03-02T22:00:00Z"),
            order("o4", at="2026-03-10T22:00:00Z"),
        ],
        [customer()],
    )
    sequence = rows(output, "customer_purchase_sequence")
    assert [r["purchase_number"] for r in sequence] == [1, 2, 3, 4]
    assert [r["customer_classification"] for r in sequence] == [
        "new_customer",
        "returning_customer",
        "returning_customer",
        "returning_customer",
    ]
    metric = rows(output, "customer_metrics")[0]
    assert metric["days_first_to_second"] == 30
    assert metric["days_second_to_third"] == Decimal("30.5")
    assert metric["days_third_to_fourth"] == 8
    assert metric["ltv_30d"] == 100  # exact day 30 excluded
    assert metric["ltv_60d"] == 200  # third occurs after exact 60d
    assert (
        metric["ltv_90d"]
        == metric["ltv_180d"]
        == metric["ltv_365d"]
        == metric["ltv_lifetime_observed"]
        == 400
    )
    assert metric["ltv_365d_complete"]
    assert day(output)["new_customers"] == 1
    assert day(output, "2026-01-31")["returning_customers"] == 1


def test_unknown_history_does_not_claim_new_acquisition_or_full_retention():
    policy = replace(POLICY, history_complete=False)
    output = run([order(), order("o2", at="2026-02-01T10:00:00Z")], [customer()], policy=policy)
    assert (
        rows(output, "customer_purchase_sequence")[0]["customer_classification"] == "first_observed"
    )
    assert day(output)["new_customers"] is None
    assert day(output, "2026-02-01")["returning_customers"] == 1
    assert not rows(output, "customer_metrics")[0]["ltv_30d_complete"]
    assert all(r["retention_rate"] is None for r in rows(output, "cohorts"))
    assert output["period_metrics"]["customer_repurchase_rate"] is None


def test_immature_ltv_is_not_a_mature_zero():
    policy = replace(POLICY, as_of="2026-01-20T12:00:00Z", report_to="2026-01-20")
    metrics = rows(run([order()], [customer()], policy=policy), "customer_metrics")[0]
    assert metrics["ltv_30d"] is None and not metrics["ltv_30d_complete"]
    assert metrics["ltv_lifetime_observed"] == 100
    assert metrics["second_purchase_at"] is metrics["days_first_to_second"] is None


def test_cohorts_calendar_offsets_dense_zero_months_and_partial_month():
    policy = replace(POLICY, as_of="2026-04-15T12:00:00Z")
    output = run(
        [
            order(at="2026-01-31T23:00:00Z"),
            order("o2", at="2026-03-01T05:00:00Z"),
            order("o3", cid="c2", at="2026-01-02T12:00:00Z"),
        ],
        [customer(), customer("c2")],
        policy=policy,
    )
    cohorts = rows(output, "cohorts")
    assert [r["months_since_first_purchase"] for r in cohorts] == [0, 1, 2, 3]
    assert cohorts[0]["customers_in_cohort"] == 2 and cohorts[0]["retention_rate"] == 1
    assert cohorts[1]["active_customers"] == 0 and cohorts[1]["revenue_generated"] == 0
    assert cohorts[2]["retention_rate"] == Decimal("0.5")
    assert cohorts[3]["retention_rate"] is None and not cohorts[3]["period_complete"]


def test_timezone_changes_order_date_and_cohort_at_month_boundary():
    output = run([order(at="2026-02-01T01:00:00Z")], [customer()])
    sequence = rows(output, "customer_purchase_sequence")[0]
    assert sequence["order_date"] == sequence["first_purchase_date"] == "2026-01-31"
    assert sequence["order_at"] == "2026-02-01T01:00:00+00:00"
    assert rows(output, "cohorts")[0]["cohort_month"] == "2026-01-01"


def test_distribution_five_plus_counts_customers_once_but_sums_repeat_revenue():
    orders = [order(f"o{i}", at=f"2026-01-{i:02}T12:00:00Z") for i in range(1, 7)] + [
        order("single", "c2")
    ]
    distribution = rows(run(orders, [customer(), customer("c2")]), "purchase_distribution")
    assert [r["customers"] for r in distribution] == [2, 1, 1, 1, 1]
    assert distribution[4]["revenue"] == 200 and distribution[4][
        "percentage_of_original_cohort"
    ] == Decimal("0.5")
    assert distribution[0]["revenue"] == 200


def test_missing_customer_still_counts_financials_but_does_not_invent_identity():
    output = run([order(cid=None), order("missing", cid="unknown")], [customer()])
    assert day(output)["revenue_generated"] == 200 and day(output)["orders_without_customer"] == 2
    assert not rows(output, "customer_purchase_sequence")
    assert not rows(output, "customer_metrics")
    assert len([q for q in output["quality"] if q["rule_id"] == "order_without_customer"]) == 2


def test_snapshot_order_customer_resolution_uses_ids_only():
    output = run(
        [order(cid="c2", customer_snapshot={"id": "c1"})], [customer("c2", name="Synthetic Name")]
    )
    assert rows(output, "customer_purchase_sequence")[0]["customer_id"] == "c2"
    assert rows(output, "customer_purchase_sequence")[0]["customer_type"] == "WHOLESALE"


@pytest.mark.parametrize("kind", ["order", "customer", "fact"])
def test_duplicate_input_blocks_instead_of_arbitrary_deduplication(kind):
    args = {"orders": [order()], "customers": [customer()]}
    if kind == "order":
        args["orders"].append(order())
    elif kind == "customer":
        args["customers"].append(customer())
    else:
        args["events"] = [event("f", "purchase", "2026-01-01T10:00:00Z")] * 2
    with pytest.raises(AnalyticsQualityError, match="duplicate"):
        run(**args)


@pytest.mark.parametrize("field", ["requested_total", "fulfilled_total"])
def test_negative_revenue_blocked(field):
    with pytest.raises(AnalyticsQualityError, match="negative_revenue"):
        run([order(**{field: "-0.01"})], [customer()])


def test_missing_value_is_not_summed_as_zero():
    output = run([order(), order("o2", requested_total=None)], [customer()])
    assert day(output)["revenue_generated"] is None
    assert day(output)["average_order_value_generated"] is None
    assert rows(output, "customer_metrics")[0]["ltv_lifetime_observed"] is None


def item(iid="i1", **extra):
    return {
        "store_id": POLICY.store_id,
        "source_system": "upzero",
        "order_id": "o1",
        "item_id": iid,
        "parent_order_version_id": "v-o1",
        "present_in_latest_snapshot": True,
        "asset_id": "asset-1",
        "variant_id": "variant-1",
        "sku": "SYNTHETIC-SKU",
        "original_qty": 5,
        "qty": "3",
        "unit_price": "12.50",
        "status": "active",
        **extra,
    }


def test_products_use_gross_lines_not_artificial_order_or_ad_allocation():
    output = run(
        [order(payment_status="paid")],
        [customer()],
        [item(), item("removed", original_qty=2, qty="2", status="removed")],
    )
    product = rows(output, "products_daily")[0]
    assert product["units_requested"] == 7 and product["units_fulfilled"] == 3
    assert product["revenue_generated"] == Decimal("87.50") and product[
        "revenue_fulfilled"
    ] == Decimal("37.50")
    assert product["average_selling_price"] == Decimal("12.50")
    assert product["cancellation_rate"] == Decimal(2) / 7
    assert product["orders"] == product["customers"] == 1
    assert (
        product["product_id"]
        is product["reference"]
        is product["spend"]
        is product["revenue_paid"]
        is None
    )
    assert product["asset_id"] == "asset-1" and product["sku"] == "SYNTHETIC-SKU"


def test_stale_or_removed_from_snapshot_items_are_excluded_with_warning():
    output = run(
        [order()],
        [customer()],
        [item(parent_order_version_id="old"), item("i2", present_in_latest_snapshot=False)],
    )
    assert not rows(output, "products_daily")
    assert any(q["rule_id"] == "item_order_snapshot_mismatch" for q in output["quality"])


def test_funnel_event_names_session_sets_chronology_and_orphans():
    events = [
        event("f1", "product_view", "2026-01-01T10:00:00Z"),
        event("f2", "add_to_cart", "2026-01-01T10:01:00Z"),
        event("f3", "checkout_started", "2026-01-01T10:02:00Z"),
        event("f4", "purchase", "2026-01-01T10:03:00Z"),
        event("f5", "purchase", "2026-01-01T10:04:00Z"),
        event("f6", "page_view", "2026-01-01T11:00:00Z", session="s2"),
        event("f7", "purchase", "2026-01-01T11:01:00Z", session=None),
        event("f8", "purchase_item", "2026-01-01T11:02:00Z", session=None),
    ]
    output = run(events=events)
    row = rows(output, "funnel_daily")[0]
    assert row["sessions"] == 2 and row["purchase"] == 3 and row["events_without_session"] == 2
    assert row["session_conversion_rate"] == row["session_to_cart_rate"] == Decimal("0.5")
    assert row["cart_to_checkout_rate"] == row["checkout_to_purchase_rate"] == 1
    assert row["cost_per_session"] is None
    assert day(output)["orders_generated"] == 0  # purchase event never becomes an order


def test_checkout_before_cart_is_not_ordered_conversion():
    events = [
        event("a", "checkout_started", "2026-01-01T10:00:00Z"),
        event("b", "add_to_cart", "2026-01-01T11:00:00Z"),
        event("c", "purchase", "2026-01-01T12:00:00Z"),
    ]
    row = rows(run(events=events), "funnel_daily")[0]
    assert row["cart_to_checkout_rate"] == 0 and row["checkout_to_purchase_rate"] is None
    assert row["session_conversion_rate"] == 1


def test_cross_midnight_sessions_use_daily_scope_explicitly():
    events = [
        event("a", "add_to_cart", "2026-01-02T02:59:00Z"),
        event("b", "checkout_started", "2026-01-02T03:01:00Z"),
    ]
    output = rows(run(events=events), "funnel_daily")
    assert output[0]["sessions"] == output[1]["sessions"] == 1
    assert output[1]["cart_to_checkout_rate"] is None


def test_incomplete_facts_do_not_publish_conversion_rates():
    row = rows(
        run(
            events=[event("a", "purchase", "2026-01-01T10:00:00Z")],
            policy=replace(POLICY, facts_complete=False),
        ),
        "funnel_daily",
    )[0]
    assert row["purchase"] == 1 and row["session_conversion_rate"] is None


def test_period_repurchase_retention_denominators_are_not_cohort_averages():
    policy = replace(POLICY, report_from="2026-02-01", report_to="2026-03-01")
    orders = [
        order(at="2026-01-15T10:00:00Z"),
        order("o2", at="2026-02-15T10:00:00Z"),
        order("o3", "c2", at="2026-02-16T10:00:00Z"),
        order("o4", "c3", at="2026-01-20T10:00:00Z"),
    ]
    result = run(orders, [customer(), customer("c2"), customer("c3")], policy=policy)[
        "period_metrics"
    ]
    assert result["purchase_frequency"] == 1
    assert result["customer_repurchase_rate"] == result["customer_retention_rate"] == Decimal("0.5")
    assert result["frequency_denominator"] == result["retention_denominator"] == 2
    assert result["retention_previous_from"] == "2026-01-04"


def test_same_day_repeat_customer_buckets_are_mutually_exclusive():
    output = run([order(), order("o2", at="2026-01-01T12:00:00Z")], [customer()])
    assert day(output)["new_customers"] == 1 and day(output)["returning_customers"] == 0
    assert (
        rows(output, "customer_purchase_sequence")[1]["customer_classification"]
        == "returning_customer"
    )


def test_no_future_purchase_leaks_into_period_repurchase():
    output = run([order(), order("future", at="2026-05-01T10:00:00Z")], [customer()])
    assert output["period_metrics"]["customer_repurchase_rate"] == 0


def test_no_zero_divisions_or_fake_spend_in_empty_store():
    output = run()
    daily = day(output)
    assert daily["revenue_generated"] == 0 and daily["orders_generated"] == 0
    for metric in (
        "new_customer_cac",
        "meta_spend",
        "roas_generated",
        "roas_paid",
        "average_order_value_generated",
        "approval_rate",
    ):
        assert daily[metric] is None
    assert ratio(1, 0) is None and ratio(None, 5) is None
    assert all(v is None for v in media_metrics(None, None).values())


def test_isolation_idempotence_inputs_unchanged_and_stable_daily_keys():
    orders = [order(), order(store_id="foreign", requested_total="99999")]
    original = deepcopy(orders)
    first = run(orders, [customer(), customer(store_id="foreign")])
    assert first == run(orders, [customer(), customer(store_id="foreign")])
    assert orders == original and day(first)["revenue_generated"] == 100
    later = run(
        orders,
        [customer()],
        policy=replace(
            POLICY, as_of="2027-02-01T12:00:00Z", report_from="2026-01-01", report_to="2026-01-02"
        ),
    )
    assert day(first)["row_key"] == day(later)["row_key"]


def test_media_contract_never_uses_reported_purchases_as_cac_denominator():
    scope = MeasurementScope(
        "synthetic", "BRL", "America/Sao_Paulo", "2026-01-01", "2026-02-01", "synthetic-config"
    )
    evidence = AttributionEvidence(
        "LAST_PAID_TOUCH", 3, "synthetic-touch", "0001", "0002", None, None
    )
    media = PaidMedia(scope, Decimal(100), 1000, 10, Decimal(999), Decimal(9999))
    first_party = AttributedFirstParty(scope, evidence, 2, 3, Decimal(300), Decimal(200))
    result = media_metrics(media, first_party)
    assert (
        result["new_customer_cac"] == 50
        and result["roas_generated"] == 3
        and result["roas_paid"] == 2
    )
    assert result["meta_reported_purchases"] == 999
    with pytest.raises(ValueError, match="incompatible"):
        media_metrics(media, replace(first_party, scope=replace(scope, currency="USD")))
    assert media_metrics(replace(media, spend=Decimal(0)), first_party)["roas_generated"] is None
    assert media_metrics(media, None)["new_customer_cac"] is None
    with pytest.raises(TypeError):
        AttributionEvidence()


@pytest.mark.parametrize(
    "rule,table,patch",
    [
        ("negative_revenue", "store_daily", {"revenue_generated": -1}),
        (
            "paid_revenue_greater_than_generated",
            "store_daily",
            {"revenue_generated": 1, "revenue_paid": 2},
        ),
        ("cohort_negative_month", "cohorts", {"months_since_first_purchase": -1}),
        ("funnel_negative_counts", "funnel_daily", {"sessions": -1}),
        ("customer_ltv_negative", "customer_metrics", {"ltv_lifetime_observed": -1}),
    ],
)
def test_quality_rules(rule, table, patch):
    output = run([order()], [customer()])["tables"]
    output["analytics_" + table][0].update(patch)
    assert any(
        r["rule_id"] == rule and r["severity"] == "blocking" for r in validate_outputs(output)
    )


def test_duplicate_grain_detected_even_if_row_key_differs():
    output = run([order()], [customer()])["tables"]
    output["analytics_store_daily"].append(
        output["analytics_store_daily"][0] | {"row_key": "different"}
    )
    assert any(r["rule_id"] == "analytics_duplicate_grain" for r in validate_outputs(output))


def test_invalid_purchase_sequence_checks():
    output = run([order()], [customer()])["tables"]
    sequence = output["analytics_customer_purchase_sequence"][0]
    sequence.update(purchase_number=2, first_purchase_at="2020-01-01T00:00:00Z")
    rules = {r["rule_id"] for r in validate_outputs(output)}
    assert {"purchase_sequence_gap", "invalid_first_purchase"} <= rules


def test_schemas_cover_actual_results_and_are_not_active_terraform():
    import json

    output = run([order()], [customer()], [item()])
    for table, data in output["tables"].items():
        for row in data:
            assert set(row) == set(SCHEMAS[table].fields), table
        saved = json.loads(
            Path(f"infra/terraform/analytics_proposed/schemas/{table}.json").read_text()
        )
        assert {f["name"]: f["type"] for f in saved} == SCHEMAS[table].fields
    active = json.loads(Path("infra/terraform/tables.json").read_text())
    assert not set(active) & set(SCHEMAS)


def test_sql_pruning_no_meta_dependency_and_no_persistent_writes():
    files = [
        Path("sql/analytics") / name
        for name in ("business_reference.sql", "products_reference.sql", "funnel_reference.sql")
    ]
    for path in files:
        sql = path.read_text()
        assert "@store" in sql and "@timezone" in sql and "SAFE_DIVIDE" in sql
        assert "up_core.meta_" not in sql
        assert "DROP " not in sql and "CREATE OR REPLACE" not in sql and "INSERT INTO" not in sql
    assert "created_at >= @history_from" in files[0].read_text()
    assert "order_created_at>=TIMESTAMP(@date_from,@timezone)" in files[1].read_text()
    assert "occurred_at>=TIMESTAMP(@date_from,@timezone)" in files[2].read_text()


def test_numeric_precision_and_json_encoding_are_explicit():
    import json

    from src.analytics.serialization import encode_tables

    value = "12345678901234567890.123456789"
    output = run([order(requested_total=value, fulfilled_total=value)], [customer()])
    assert day(output)["revenue_generated"] == Decimal(value)
    encoded = encode_tables(output["tables"])
    assert encoded["analytics_store_daily"][0]["revenue_generated"] == value
    json.dumps(encoded, allow_nan=False)


def test_policy_snapshot_boundaries_and_unknown_status_fail_closed():
    with pytest.raises(ValueError, match="closed_reporting_days"):
        replace(POLICY, as_of="2026-01-01T12:00:00Z")
    with pytest.raises(AnalyticsQualityError, match="unknown_commerce_status"):
        run([order(order_status="UNREVIEWED_STATUS")], [customer()])
    with pytest.raises(AnalyticsQualityError, match="snapshot_observed_after_as_of"):
        run([order(observed_at="2028-01-01T00:00:00Z")], [customer()])
