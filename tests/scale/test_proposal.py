from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from scripts.estimate_scale_cost import Scenario, estimate
from src.scale.proposal import (
    Admission,
    Budget,
    Fact,
    ShadowStore,
    Work,
    affected_facts,
    fast_window,
    links,
    quality,
    reconciliation_window,
    safe_job_labels,
)

T = datetime(2026, 9, 1, tzinfo=UTC)


def test_fast_contiguous_and_no_lookback():
    window = fast_window(
        T, T + timedelta(days=3), T + timedelta(days=3, minutes=15), safety_margin=timedelta(0)
    )
    assert window.start == T + timedelta(days=3)
    assert window.end - window.start == timedelta(minutes=15)
    assert fast_window(T, T, T, safety_margin=timedelta(0)) is None
    with pytest.raises(ValueError):
        fast_window(T, T, T, safety_margin=timedelta(seconds=-1))


def test_late_arrival_restatement_and_retry_without_core_duplicates():
    state = ShadowStore()
    first = Work(
        "a",
        "upzero",
        "fast",
        fast_window(T, None, T + timedelta(hours=1), safety_margin=timedelta(0)),
    )
    original = Fact("a", "f", T + timedelta(minutes=10), None)
    late = Fact("a", "late", T + timedelta(minutes=20), "o")
    assert state.run(first, [original], budget=Budget(10000, 10))
    reconcile = Work(
        "a",
        "upzero",
        "reconcile",
        reconciliation_window(T, T + timedelta(hours=2), lookback=timedelta(hours=72)),
    )
    source = [replace(original, order_id="o"), late, replace(late, store="b")]
    for _ in range(2):
        assert state.run(reconcile, source, budget=Budget(10000, 10))
    assert len(state.core) == 2 and state.core[("a", "f")].order_id == "o"
    assert state.completed["a"] == first.window.end


def test_100_stores_caps_lock_failure_and_fair_progress():
    admission = Admission(7, {"upzero": 5, "meta": 2})
    state = ShadowStore()
    window = reconciliation_window(T, T + timedelta(days=1), lookback=timedelta(days=1))
    pending = [
        Work(str(i), "upzero", "reconcile" if i == 0 else "fast", window) for i in range(100)
    ]
    admitted = []
    while pending:
        batch = [w for w in pending if admission.acquire(w)]
        assert 0 < len(batch) <= 5
        for w in batch:
            assert not admission.acquire(replace(w, mode="reconcile"))
            okay = state.run(w, [], budget=Budget(1000, 2), fail=w.store == "0")
            assert okay == (w.store != "0")
            admission.release(w)
            pending.remove(w)
            admitted.append(w.store)
    assert len(set(admitted)) == 100 and len(state.completed) == 99
    assert (
        "0" not in state.completed
    )  # failed work retained by production queue, not marked complete


def test_budget_defers_without_watermark_or_data_drop():
    state = ShadowStore()
    window = reconciliation_window(T, T + timedelta(days=1), lookback=timedelta(days=1))
    work = Work("a", "upzero", "fast", window)
    budget = Budget(99, 1)
    source = [Fact("a", "f", T, None)]
    assert not state.run(work, source, budget=budget)
    assert (
        budget.state == "deferred_budget_alert_required" and not state.completed and not state.core
    )
    assert state.run(work, source, budget=Budget(100, 1))
    assert len(state.core) == 1


def test_affected_links_equal_deep_and_quality_includes_historical_peers():
    facts = [Fact("a", "f1", T, "o1", True), Fact("a", "f2", T, "o2"), Fact("b", "f1", T, "o1")]
    orders = {("a", "o1"), ("a", "o2")}
    before = links(facts, {("a", "o1")})
    selected = affected_facts(facts, "a", set(), {"o2"}, {"f2"})
    before.update(links(selected, orders))
    assert before == links(facts, orders)
    facts.append(replace(facts[0], at=T + timedelta(days=3)))
    assert quality(facts, "a", {"f1"}) == quality([f for f in facts if f.fact_id == "f1"], "a")
    assert quality(facts, "a", {"f1"})["duplicate_facts"] == 1
    assert len(affected_facts(facts, "a", {"f1"}, set(), set())) == 2


def test_labels_are_safe_and_deterministic():
    labels = safe_job_labels("private-store", "quality", "all", "private-run")
    assert "private" not in str(labels)
    assert labels == safe_job_labels("private-store", "quality", "all", "private-run")
    with pytest.raises(ValueError):
        safe_job_labels("a", "email@example.invalid", "all", "r")


def test_estimator_determinism_scaling_and_formula():
    s = Scenario()
    assert estimate(s) == estimate(s)
    assert estimate(s)["observation_multiplier"] == 4
    assert estimate(s, current=True)["observation_multiplier"] == 319
    assert estimate(replace(s, stores=100))["unique_facts_month"] == 35588600
    assert estimate(replace(s, reconcile_frequency_per_day=4))["observation_multiplier"] == 13
    assert (
        estimate(replace(s, facts_payload_bytes=3000))["raw_ingress_gb_month"]
        > estimate(s)["raw_ingress_gb_month"]
    )
    with pytest.raises(ValueError):
        estimate(replace(s, page_limit=1001))


def test_global_cap_across_sources_and_owner_checked():
    window = reconciliation_window(T, T + timedelta(days=1), lookback=timedelta(days=1))
    gate = Admission(2, {"upzero": 2, "meta": 2})
    a, b, c = [
        Work(name, source, "fast", window)
        for name, source in [("a", "upzero"), ("b", "meta"), ("c", "meta")]
    ]
    assert gate.acquire(a) and gate.acquire(b)
    assert not gate.acquire(c)
    with pytest.raises(ValueError, match="owner"):
        gate.release(replace(a, mode="reconcile"))
    gate.release(a)
    assert gate.acquire(c)


def test_page_budget_keeps_work_pending():
    window = reconciliation_window(T, T + timedelta(days=1), lookback=timedelta(days=1))
    state = ShadowStore()
    work = Work("a", "upzero", "fast", window)
    budget = Budget(10000, 0)
    assert not state.run(work, [Fact("a", "f", T, None)], budget=budget)
    assert not state.completed and not state.evidence
    assert budget.state == "deferred_budget_alert_required"


def test_storage_retention_and_prices_absent():
    base = estimate(Scenario())
    doubled = estimate(Scenario(raw_retention_days=730))
    assert (
        abs(doubled["retained_storage_gb"]["raw"] - 2 * base["retained_storage_gb"]["raw"])
        < 0.000002
    )
    assert "price" not in str(base) and "usd" not in str(base).lower()
    assert estimate(Scenario(stores=200))["unique_facts_month"] == 71177200
