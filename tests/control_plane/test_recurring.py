"""Synthetic cumulative-window, contiguous source evidence and lease/CAS acceptance."""

from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from src.connectors.meta.config import Account, Insights
from src.control_plane.model import Window
from src.control_plane.recurring import (
    cumulative,
    facts_coverage,
    meta_coverage,
    meta_evidence_hash,
    monotonic,
)
from src.control_plane.worker import StoreWorker
from src.domain.models import SafeError
from src.security.lease import cloud_lease
from src.utils.data import digest
from tests.control_plane.test_control_plane import MemoryRegistry, config


def head(c, start="2026-09-01", end="2026-10-03", as_of="2026-10-03T03:00:00Z"):
    w = Window(start, end, as_of, "2026-10-04T04:00:00Z", "2026-10-04T04:00:00Z")
    h = c.policy(w).policy_hash
    return {
        "store_id": c.store_id,
        "policy_hash": h,
        "generation": 3,
        "publication_id": "a" * 64,
        "status": "completed",
        "report_from": None,
        "report_to": None,
        "as_of": as_of,
        "source_watermark": "safe",
        "receipt_store_id": c.store_id,
        "receipt_policy_hash": h,
        "receipt_generation": 3,
        "receipt_id": "a" * 64,
        "receipt_status": "completed",
        "receipt_version": "1.0.0",
        "receipt_watermark": "safe",
        "receipt_as_of": as_of,
        "receipt_from": start,
        "receipt_to": end,
        "snapshot_at": w.source_snapshot_at,
    }


def test_mx_cumulative_and_same_day_never_shrink():
    c = config(
        status="ACTIVE",
        sync_enabled=True,
        analytics_enabled=True,
        upzero_enabled=True,
        upzero_connection_id="synthetic-up",
    )
    d = Window.previous_closed_day(c.timezone, "2026-10-04T07:00:00Z")
    w = cumulative(c, d, [head(c)])
    assert (w.report_from, w.report_to) == ("2026-09-01", "2026-10-04")
    assert not c.history_complete
    repeat = cumulative(c, d, [head(c, end=w.report_to, as_of=w.as_of)])
    assert repeat == w
    with pytest.raises(SafeError, match="regression"):
        monotonic(w, d)
    with pytest.raises(SafeError, match="regression"):
        cumulative(
            c,
            replace(
                Window.previous_closed_day(c.timezone, "2026-10-03T07:00:00Z"),
                source_snapshot_at="2026-10-04T07:00:00Z",
                calculated_at="2026-10-04T07:00:00Z",
            ),
            [head(c, end=w.report_to, as_of=w.as_of)],
        )


@pytest.mark.parametrize(
    "mutation",
    [None, "missing", "duplicate", "store", "generation", "watermark", "status", "policy", "as_of"],
)
def test_publication_fail_closed(mutation):
    c = config()
    r = head(c)
    rows = [r]
    if mutation == "missing":
        rows = []
    elif mutation == "duplicate":
        rows *= 2
    elif mutation == "store":
        r["receipt_store_id"] = "other"
    elif mutation == "generation":
        r["receipt_generation"] = 2
    elif mutation == "watermark":
        r["receipt_watermark"] = "different"
    elif mutation == "status":
        r["receipt_status"] = "initialized"
    elif mutation == "policy":
        r["receipt_policy_hash"] = "b" * 64
    elif mutation == "as_of":
        r["receipt_as_of"] = "2026-10-02T03:00:00Z"
    if mutation is None:
        assert (
            cumulative(
                c, Window.previous_closed_day(c.timezone, "2026-10-04T07:00:00Z"), rows
            ).report_from
            == "2026-09-01"
        )
    else:
        with pytest.raises(SafeError, match="recurring_publication_required"):
            cumulative(c, Window.previous_closed_day(c.timezone, "2026-10-04T07:00:00Z"), rows)


def meta_days(days=(1, 2, 3, 4)):
    a = Account("synthetic-brand", "100", "synthetic-meta", "v24.0", "America/Sao_Paulo", "BRL")
    cps = []
    runs = []
    for d in days:
        spec = Insights(f"2026-09-{d:02}", f"2026-09-{d:02}", "impression", ("7d_click",), None)
        f = {"account": a.snapshot(), "insights": {**spec.snapshot(), "level": "campaign"}}
        key = digest(["meta", "insights", f, 100])
        rid = f"synthetic-run-{d}"
        cps.append(
            {
                "store_id": a.store_id,
                "connection_id": a.connection_id,
                "resource": "meta_live_insights_daily",
                "plan_key": key,
                "run_id": rid,
                "filters": f,
                "status": "complete",
                "pending_raw_id": None,
            }
        )
        runs.append(
            {
                "store_id": a.store_id,
                "source": "meta",
                "resource": "meta_live_insights_daily",
                "plan_key": key,
                "run_id": rid,
                "status": "completed",
                "core_records_failed": 0,
            }
        )
    return a, cps, runs


def test_meta_daily_union_gap_extra_and_deterministic_hash():
    a, cp, runs = meta_days()
    report = Insights("2026-09-01", "2026-09-04", "impression", ("7d_click",), None)
    good = meta_coverage(a, report, cp, runs)
    assert len(good) == 4
    assert meta_evidence_hash(good) == meta_evidence_hash(list(reversed(good)))
    with pytest.raises(SafeError, match="meta_complete_checkpoint_required"):
        meta_coverage(a, report, [r for r in cp if not r["run_id"].endswith("-3")], runs)
    a, extra, er = meta_days((5,))
    assert meta_coverage(a, report, cp + extra, runs + er) == good


@pytest.mark.parametrize(
    "field,value",
    [
        ("pending_raw_id", "synthetic-raw"),
        ("status", "running"),
        ("connection_id", "other"),
        ("store_id", "other"),
    ],
)
def test_meta_uncertified_or_other_store_cannot_prove_coverage(field, value):
    a, cp, runs = meta_days()
    cp[2][field] = value
    with pytest.raises(SafeError, match="meta_complete_checkpoint_required"):
        meta_coverage(
            a, Insights("2026-09-01", "2026-09-04", "impression", ("7d_click",), None), cp, runs
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("core_records_failed", 1),
        ("source", "upzero"),
        ("store_id", "other"),
        ("plan_key", "other"),
    ],
)
def test_meta_run_certification(field, value):
    a, cp, runs = meta_days()
    runs[2][field] = value
    with pytest.raises(SafeError, match="meta_complete_checkpoint_required"):
        meta_coverage(
            a, Insights("2026-09-01", "2026-09-04", "impression", ("7d_click",), None), cp, runs
        )


def upzero_evidence(c, target):
    cps = []
    runs = []
    for resource, f in [
        ("customers", {"limit": 200}),
        ("orders", {"start_date": "2026-08-31", "end_date": "2026-10-03"}),
        ("analytics_facts", {"from": c.history_from, "to": target}),
    ]:
        key = digest([c.store_id, c.upzero_connection_id, resource, f, "incremental"])
        rid = "synthetic-" + resource
        cps.append(
            {
                "store_id": c.store_id,
                "connection_id": c.upzero_connection_id,
                "resource": resource,
                "filters": f,
                "mode": "incremental",
                "plan_key": key,
                "run_id": rid,
                "status": "complete",
                "pending_raw_id": None,
            }
        )
        runs.append(
            {
                "store_id": c.store_id,
                "source": "upzero",
                "mode": "incremental",
                "resource": resource,
                "plan_key": key,
                "run_id": rid,
                "status": "completed",
                "core_records_failed": 0,
                "finished_at": target,
            }
        )
    return cps, runs


def test_recurring_registry_coverage_success_failure_and_same_day():
    c = config(
        status="ACTIVE", sync_enabled=True, upzero_enabled=True, upzero_connection_id="synthetic-up"
    )
    target = "2026-10-04T03:00:00Z"
    cp, r = upzero_evidence(c, target)
    updated = facts_coverage(c, cp, r, target, target)
    assert updated.revision == c.revision + 1 and updated.facts_complete
    assert updated.status == "ACTIVE" and updated.sync_enabled and not updated.history_complete
    assert facts_coverage(updated, cp, r, target, target) == updated
    r[-1]["status"] = "failed"
    with pytest.raises(SafeError, match="not_certified"):
        facts_coverage(updated, cp, r, target, target)
    assert updated.facts_coverage_to == target.replace("Z", "+00:00")


def test_registry_unknown_cas_retains_lease_no_retry():
    c = config(
        status="ACTIVE", sync_enabled=True, upzero_enabled=True, upzero_connection_id="synthetic-up"
    )
    target = "2026-10-04T03:00:00Z"
    cp, r = upzero_evidence(c, target)
    updated = facts_coverage(c, cp, r, target, target)
    registry = MemoryRegistry([c])
    registry.save = Mock(side_effect=SafeError("registry_write_outcome_unknown"))
    with patch("google.cloud.storage.Client") as sdk:
        blob = sdk.return_value.bucket.return_value.blob.return_value
        worker = StoreWorker(
            registry,
            lambda *a: None,
            lambda s: cloud_lease("synthetic-bucket", s),
            lambda *a: updated,
            lambda: {},
        )
        with pytest.raises(SafeError, match="registry_write_outcome_unknown"):
            worker.execute(
                c.store_id, c.revision, "upzero", Window.previous_closed_day(c.timezone, target)
            )
        registry.save.assert_called_once_with(updated, c.revision)
        blob.delete.assert_not_called()
    assert registry.get(c.store_id) == c


@pytest.mark.parametrize(
    "code",
    [
        "registry_write_outcome_unknown",
        "work_execution_outcome_unknown",
        "work_dispatch_unknown",
        "source_verification_outcome_unknown",
    ],
)
def test_cloud_lease_preserved_for_ambiguous_activation_or_launch(code):
    blob = Mock()
    with patch("google.cloud.storage.Client") as client:
        client.return_value.bucket.return_value.blob.return_value = blob
        with pytest.raises(SafeError, match=code):
            with cloud_lease("synthetic-bucket", "synthetic-store"):
                raise SafeError(code)
    blob.delete.assert_not_called()


@pytest.mark.parametrize("problem", [None, "pending_raw", "source", "publication", "unit", "plan"])
def test_final_activation_uses_real_evidence_guards(problem):
    from src.control_plane.preflight import Prerequisites

    c = config(
        status="READY",
        sync_enabled=False,
        upzero_enabled=True,
        analytics_enabled=True,
        upzero_connection_id="synthetic-up",
        facts_complete=True,
        facts_coverage_from="2026-09-01T00:00:00Z",
        facts_coverage_to="2026-10-03T03:00:00Z",
    )
    cp, runs = upzero_evidence(c, c.facts_coverage_to)
    tables = {
        "up_ops.sync_checkpoints": cp,
        "up_ops.sync_runs": runs,
        "up_ops.installation_plans": [{"plan_id": "synthetic-plan", "status": "COMPLETE"}],
        "up_ops.installation_work_units": [{"plan_id": "synthetic-plan", "status": "COMPLETE"}],
        "up_core.source_connections": [
            {"source_system": "upzero", "connection_id": c.upzero_connection_id, "status": "active"}
        ],
    }
    pre = Prerequisites(Mock())
    pre.configuration = Mock()
    pre.rows = lambda store, table, *args, **kwargs: tables[table]
    pre.publication = lambda c, w: [] if problem == "publication" else [head(c)]
    if problem == "pending_raw":
        cp[0]["pending_raw_id"] = "synthetic-raw"
    if problem == "source":
        tables["up_core.source_connections"][0]["status"] = "pending"
    if problem == "unit":
        tables["up_ops.installation_work_units"][0]["status"] = "PENDING"
    if problem == "plan":
        tables["up_ops.installation_plans"][0]["status"] = "PARTIAL"
    with patch("src.utils.data.now", return_value="2026-10-04T07:00:00Z"):
        if problem:
            with pytest.raises(SafeError):
                pre.activation(c)
        else:
            pre.activation(c)
