"""Synthetic publication simulation. No cloud/SQL execution is claimed."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from src.analytics.config import AnalyticsPolicy
from src.analytics.materialization import SQLiteAnalyticsSink, run
from src.analytics.parity import compare, load_fixture, prepare, structural_check
from src.analytics.policy import HistoryCoverage
from src.analytics.schema import SCHEMAS
from src.analytics.sql_models import compile_model

FIXTURE = Path("tests/fixtures/analytics_readiness/synthetic.json")


@pytest.fixture
def setup():
    policy, snapshot = load_fixture(FIXTURE)
    sink = SQLiteAnalyticsSink(":memory:")
    yield policy, snapshot, sink
    sink.close()


def all_rows(sink, policy):
    return {m: sink.rows(m, policy.store_id, policy.policy_hash) for m in SCHEMAS}


def test_policy_hash_and_semantic_isolation(setup):
    p, _, _ = setup
    assert replace(p, report_to="2026-03-04").policy_hash == p.policy_hash
    assert replace(p, as_of="2026-04-03T12:00:00Z").policy_hash == p.policy_hash
    for altered in (
        replace(p, reporting_timezone="UTC"),
        replace(p, currency="USD"),
        replace(p, qualifying_order_statuses=("SHIPPED",)),
        replace(p, policy_version="v2"),
    ):
        assert altered.policy_hash != p.policy_hash
    assert AnalyticsPolicy.from_dict(p.to_dict()) == p


def test_coverage_never_inferred(setup):
    p, s, sink = setup
    with pytest.raises(ValueError, match="history_coverage_unknown"):
        replace(p, history_complete=True)
    coverage = HistoryCoverage(
        p.store_id, p.history_from, p.as_of, "synthetic-proof", "synthetic-reviewer", True, True
    )
    assert replace(p, history_complete=True, history_coverage=coverage).history_complete
    for bad in (
        replace(coverage, gaps_checked=False),
        replace(coverage, store_id="other"),
        replace(coverage, verified_through=p.history_from),
    ):
        with pytest.raises(ValueError, match="history_coverage_unknown"):
            replace(p, history_complete=True, history_coverage=bad)
    run(p, s, sink)
    assert all(r["new_customers"] is None for r in all_rows(sink, p)["analytics_store_daily"])


def test_unknown_currency_and_paid_null(setup):
    p, s, sink = setup
    with pytest.raises(ValueError, match="currency_missing"):
        replace(p, currency=None)
    p = replace(p, currency=None, allow_unknown_currency_local=True)
    run(p, s, sink)
    for rows in all_rows(sink, p).values():
        for r in rows:
            assert r["currency"] is None
            for f in (
                "revenue_paid",
                "average_order_value_paid",
                "roas_paid",
                "ltv_paid",
                "new_customer_cac",
            ):
                if f in r:
                    assert r[f] is None


def test_retry_replay_isolation_and_no_core_mutation(setup):
    p, s, sink = setup
    original = deepcopy(s)
    receipt = run(p, s, sink)
    rows = all_rows(sink, p)
    assert run(p, s, sink) == receipt
    assert rows == all_rows(sink, p)
    other = replace(p, store_id="another-synthetic-store")
    run(other, s, sink)
    run(replace(p, qualifying_order_statuses=("SHIPPED",)), s, sink)
    assert rows == all_rows(sink, p)
    assert s == original
    assert len(rows["analytics_products_daily"]) == 4


def test_partial_publication_rollback_and_retry(setup, monkeypatch):
    p, s, sink = setup

    def fail(model):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(sink, "after_model", fail)
    with pytest.raises(RuntimeError):
        run(p, s, sink)
    assert sink.head(p) is None
    assert not any(all_rows(sink, p).values())
    monkeypatch.setattr(sink, "after_model", lambda model: None)
    assert run(p, s, sink)["status"] == "completed"


def test_lost_commit_acknowledgement(setup, monkeypatch):
    p, s, sink = setup
    publish = sink.publish

    def lost(*args, **kwargs):
        publish(*args, **kwargs)
        raise RuntimeError("lost ack")

    monkeypatch.setattr(sink, "publish", lost)
    with pytest.raises(RuntimeError):
        run(p, s, sink)
    assert run(p, s, sink)["status"] == "completed"
    assert sink.head(p)[0] == 1


@pytest.mark.parametrize(
    "change", ["cancel", "amount", "late_order", "late_fact", "customer_change"]
)
def test_incremental_matches_rebuild(setup, change):
    p, s, sink = setup
    run(p, s, sink)
    current = deepcopy(s)
    if change == "cancel":
        current.orders[0]["order_status"] = "CANCELED"
    elif change == "amount":
        current.orders[0]["fulfilled_total"] = "21"
    elif change == "late_order":
        current.orders.append(
            {
                **current.orders[0],
                "order_id": "older-synthetic",
                "created_at": "2026-02-01T12:00:00Z",
            }
        )
    elif change == "late_fact":
        current.events.append(
            {
                **current.events[0],
                "fact_id": "late-synthetic",
                "occurred_at": "2026-02-01T12:00:00Z",
            }
        )
    else:
        current.orders[0]["customer_id"] = "c2"
    run(p, current, sink, previous=s)
    # Reference rebuild includes the same expanded closed-day interval.
    reference = SQLiteAnalyticsSink(":memory:")
    try:
        expanded = replace(p, report_from="2026-02-01") if change.startswith("late_") else p
        run(expanded, current, reference)
        actual = all_rows(sink, p)
        expected = all_rows(reference, expanded)
        for model in SCHEMAS:
            # Unaffected daily zero partitions need not be created by an incremental run.
            keys = {r["row_key"] for r in actual[model]}
            if model in {
                "analytics_store_daily",
                "analytics_products_daily",
                "analytics_funnel_daily",
            }:
                expected[model] = [r for r in expected[model] if r["row_key"] in keys]
            assert actual[model] == expected[model], model
        if change == "late_order":
            customer = next(
                r for r in actual["analytics_customer_metrics"] if r["customer_id"] == "c1"
            )
            assert customer["purchases"] == 3 and customer["first_purchase_date"] == "2026-02-01"
            assert {r["cohort_month"] for r in actual["analytics_cohorts"]} == {
                "2026-02-01",
                "2026-03-01",
            }
    finally:
        reference.close()


def test_guards_for_stale_and_missing_baseline(setup):
    p, s, sink = setup
    run(p, s, sink)
    with pytest.raises(ValueError, match="analytics_model_stale"):
        run(replace(p, as_of="2026-04-01T12:00:00Z"), s, sink)
    with pytest.raises(ValueError, match="analytics_previous_snapshot_required"):
        run(replace(p, as_of="2026-04-03T12:00:00Z"), s, sink)
    with pytest.raises(ValueError, match="policy_missing"):
        run(None, s, sink)


def test_synthetic_sql_python_contract(tmp_path):
    manifest = prepare(FIXTURE, tmp_path)
    assert manifest["bigquery_validated"] is False
    for model in SCHEMAS:
        expected = json.loads((tmp_path / f"{model}.expected.json").read_text())
        golden = json.loads((FIXTURE.parent / "expected" / f"{model}.expected.json").read_text())
        compare(model, golden, expected)
        for fixture in (False, True):
            structural_check(
                model, compile_model(model, project="up-data-intelligence-dev", fixtures=fixture)
            )
        request = json.loads((tmp_path / f"{model}.dry-run.json").read_text())
        assert request["useLegacySql"] is False
        if expected:
            broken = deepcopy(expected)
            broken[0]["store_id"] = "wrong"
            with pytest.raises(ValueError, match="analytics_parity_failure"):
                compare(model, expected, broken)
            with pytest.raises(ValueError, match="analytics_materialization_duplicate_key"):
                compare(model, expected, expected + expected[:1])


def test_cancellation_of_only_purchase_removes_old_history(setup):
    p, s, sink = setup
    run(p, s, sink)
    current = deepcopy(s)
    current.orders[2]["order_status"] = "CANCELED"
    run(p, current, sink, previous=s)
    tables = all_rows(sink, p)
    assert {r["customer_id"] for r in tables["analytics_customer_metrics"]} == {"c1"}
    assert {r["customer_id"] for r in tables["analytics_customer_purchase_sequence"]} == {"c1"}
    assert all(r["customers_in_cohort"] == 1 for r in tables["analytics_cohorts"])


def test_clock_maturity_and_coverage_rebuild(setup):
    p, s, sink = setup
    early = replace(p, as_of="2026-03-15T12:00:00Z")
    run(early, s, sink)
    assert all(r["ltv_30d"] is None for r in all_rows(sink, p)["analytics_customer_metrics"])
    run(p, s, sink, previous=s)
    assert all(r["ltv_30d"] is not None for r in all_rows(sink, p)["analytics_customer_metrics"])
    changed = replace(p, facts_complete=True)
    with pytest.raises(ValueError, match="coverage_changed"):
        run(changed, s, sink, previous=s)
    assert run(changed, s, sink, full_refresh=True)["status"] == "completed"


def test_asof_admits_previously_future_order(setup):
    p, s, sink = setup
    s.orders.append({**s.orders[0], "order_id": "future", "created_at": "2026-04-03T12:00:00Z"})
    run(p, s, sink)
    later = replace(p, as_of="2026-04-05T12:00:00Z")
    run(later, s, sink, previous=s)
    assert (
        next(
            r for r in all_rows(sink, p)["analytics_customer_metrics"] if r["customer_id"] == "c1"
        )["purchases"]
        == 3
    )


def test_atomic_publish_rejects_duplicates_policy_and_race(setup):
    from src.analytics.materialization import calculate, plan_changes

    p, s, sink = setup
    plan = plan_changes(p, s, None, None)
    tables, _, _ = calculate(p, s, plan)
    broken = deepcopy(tables)
    broken["analytics_store_daily"].append(broken["analytics_store_daily"][0])
    with pytest.raises(ValueError, match="analytics_materialization_duplicate_key"):
        sink.publish("synthetic-dup", p, s, plan, broken, 0)
    broken = deepcopy(tables)
    broken["analytics_store_daily"][0]["policy_hash"] = "invalid"
    with pytest.raises(ValueError, match="policy_hash_mismatch"):
        sink.publish("synthetic-hash", p, s, plan, broken, 0)
    assert sink.head(p) is None
    run(p, s, sink)
    with pytest.raises(ValueError, match="analytics_concurrent_publication_retry"):
        sink.publish("synthetic-race", p, s, plan, tables, 0)
