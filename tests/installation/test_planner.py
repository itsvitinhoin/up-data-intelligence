from dataclasses import replace
from datetime import timedelta

import pytest

from src.admin.contracts import AdminError, parse_request
from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.installation.adoption import prefix
from src.installation.model import Limits, local_days
from src.installation.planner import Planner
from src.installation.progress import summarize
from src.utils.data import digest
from tests.admin.test_onboarding import body

START = "2026-09-01T03:00:00+00:00"
END = "2026-10-01T03:00:00+00:00"
NOW = "2026-10-02T03:00:00+00:00"


def config(**kwargs):
    return StoreConfig(
        store_id="synthetic-mx",
        timezone="America/Sao_Paulo",
        currency="BRL",
        history_from=START,
        operation_b2b=True,
        policy_version="1.0.0",
        qualifying_order_statuses=("RESERVED", "CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED"),
        upzero_enabled=True,
        upzero_connection_id="synthetic-mx-upzero",
        **kwargs,
    )


def graph(days=30, **kwargs):
    end = (instant(START) + timedelta(days=days)).isoformat()
    return Planner().calculate(
        config(),
        end,
        NOW,
        operation={
            "operation_id": "synthetic-onboarding",
            "status": "INSTALLING",
            "store_id": "synthetic-mx",
        },
        **kwargs,
    )


def cp(c, resource, filters, status="complete", mode="incremental", run="synthetic-run"):
    key = digest([c.store_id, c.upzero_connection_id, resource, filters, mode])
    checkpoint = {
        "row_key": key,
        "plan_key": key,
        "store_id": c.store_id,
        "connection_id": c.upzero_connection_id,
        "resource": resource,
        "filters": filters,
        "mode": mode,
        "status": status,
        "run_id": run,
        "pending_raw_id": None,
        "position": {"cursor": "SYNTHETIC-OPAQUE-CURSOR"},
        "updated_at": NOW,
    }
    report = {
        "row_key": run,
        "run_id": run,
        "store_id": c.store_id,
        "source": "upzero",
        "resource": resource,
        "mode": mode,
        "plan_key": key,
        "status": "completed" if status == "complete" else "running",
        "finished_at": NOW if status == "complete" else None,
        "core_records_processed": 344000,
        "core_pages_processed": 344,
        "core_records_failed": 0,
    }
    return checkpoint, report


def test_new_graph_deterministic_days_dependencies_milestones():
    c, p, rows = graph()
    assert graph() == (c, p, rows)
    assert len([r for r in rows if r["required"]]) == 62
    assert [r["filters"]["report_to"] for r in rows if r["unit_kind"] == "PUBLISH_ANALYTICS"] == [
        "2026-09-02",
        "2026-09-09",
        "2026-09-16",
        "2026-09-23",
        "2026-09-30",
        "2026-10-01",
    ]
    assert summarize(rows)["progress"]["total"] == 62
    assert not c.sync_enabled and c.analytics_enabled and c.status == "DRAFT"
    assert all(set(r["dependencies"]) <= {x["work_unit_id"] for x in rows} for r in rows)
    for r in rows:
        if r["checkpoint_plan_key"]:
            assert r["checkpoint_plan_key"] == digest(
                [c.store_id, c.upzero_connection_id, r["resource"], r["filters"], r["mode"]]
            )


def test_mx_legacy_344k_adoption_no_reset_replay_or_duplicate_facts():
    c = config()
    checkpoints, runs = [], []
    for i in range(4):
        a, b = cp(
            c,
            "customers",
            {"after_id": str(i), "limit": 200},
            "recovered",
            run=f"synthetic-recovered-{i}",
        )
        checkpoints.append(a)
        runs.append(b)
    for resource, filters in [
        ("customers", {"limit": 200}),
        ("orders", {"start_date": "2026-09-01", "end_date": "2026-09-30", "limit": 200}),
    ]:
        a, b = cp(
            c,
            resource,
            filters,
            mode="reconcile" if resource == "orders" else "incremental",
            run="synthetic-" + resource,
        )
        checkpoints.append(a)
        runs.append(b)
    a, b = cp(
        c,
        "analytics_facts",
        {"from": START, "to": END, "limit": 1000},
        "running",
        run="synthetic-large-facts",
    )
    checkpoints.append(a)
    runs.append(b)
    _, plan, rows = Planner().calculate(c, END, NOW, adopt=True, checkpoints=checkpoints, runs=runs)
    legacy = [r for r in rows if r["unit_kind"] == "LEGACY_RESUME"]
    assert (
        len(legacy) == 1
        and legacy[0]["run_id"] == b["run_id"]
        and legacy[0]["checkpoint_plan_key"] == a["plan_key"]
    )
    assert legacy[0]["records_processed"] == 344000 and legacy[0]["pages_processed"] == 344
    assert legacy[0]["filters"] == a["filters"] and legacy[0]["mode"] == a["mode"]
    assert not any(r["unit_kind"] in {"SYNC_WINDOW", "SYNC_SNAPSHOT"} for r in rows)
    assert all(r["mode"] != "replay" for r in rows)
    assert checkpoints[-1]["position"] == {"cursor": "SYNTHETIC-OPAQUE-CURSOR"}
    assert plan["status"] == "RUNNING"


@pytest.mark.parametrize("pending", [None, "synthetic-pending-raw"])
def test_pending_resume_and_recovered_requires_freshness(pending):
    c = config()
    a, b = cp(c, "analytics_facts", {"from": START, "to": END, "limit": 1000}, "running")
    a["pending_raw_id"] = pending
    old, report = cp(c, "customers", {"limit": 200}, "recovered", run="synthetic-old")
    _, _, rows = Planner().calculate(
        c, END, NOW, adopt=True, checkpoints=[a, old], runs=[b, report]
    )
    assert len([r for r in rows if r["unit_kind"] == "LEGACY_RESUME"]) == 1
    assert len([r for r in rows if r["unit_kind"] == "SYNC_SNAPSHOT"]) == 1
    assert not any(
        r["resource"] == "analytics_facts" and r["unit_kind"] == "SYNC_WINDOW" for r in rows
    )


def test_needs_review_blocked_no_replay():
    a, b = cp(config(), "customers", {"limit": 200}, "needs_review")
    _, p, r = graph(checkpoints=[a], runs=[b])
    assert p["status"] == "BLOCKED" and not r


def test_contiguous_prefix_never_min_max():
    def t(n):
        return (instant(START) + timedelta(days=n)).isoformat()

    ranges = [(t(0), t(1)), (t(1), t(2)), (t(3), t(4))]
    assert prefix(START, END, ranges) == t(2)
    assert prefix(START, END, ranges + [(t(2), t(3))]) == t(4)


@pytest.mark.parametrize(
    "start,end,hours",
    [
        ("2026-03-08T05:00:00Z", "2026-03-09T04:00:00Z", 23),
        ("2026-11-01T04:00:00Z", "2026-11-02T05:00:00Z", 25),
    ],
)
def test_dst_local_days(start, end, hours):
    days = local_days(start, end, "America/New_York")
    assert (
        len(days) == 1
        and (instant(days[0][1]) - instant(days[0][0])).total_seconds() == hours * 3600
    )


def test_explicit_b2b_policy_no_implicit_backend_defaults():
    data = body()
    assert parse_request(data).config.policy_version == "1.0.0"
    assert "RESERVED" in parse_request(data).config.qualifying_order_statuses
    for statuses in [None, [], ["CANCELED"], ["RESERVED", "RESERVED"], ["NOT_A_STATUS"]]:
        data["store"]["qualifying_order_statuses"] = statuses
        with pytest.raises(AdminError):
            parse_request(data)
    del data["store"]["qualifying_order_statuses"]
    with pytest.raises(AdminError):
        parse_request(data)


@pytest.mark.parametrize("n,percent", [(0, 0), (3, 30), (10, 100)])
def test_logical_progress_exact_not_slice_count(n, percent):
    _, _, rows = graph(4)
    assert len([r for r in rows if r["required"]]) == 10
    for r in [r for r in rows if r["required"]][:n]:
        r.update(status="COMPLETE", attempt_count=30)
    result = summarize(rows)
    assert result["progress"]["total"] == 10 and result["progress"]["percent"] == percent
    assert summarize([])["progress"]["percent"] is None


def test_eta_comparable_min_samples_median_not_mean():
    _, _, rows = graph(5)
    facts = [r for r in rows if r["resource"] == "analytics_facts"]
    for i, seconds in enumerate([10, 11, 10000]):
        facts[i].update(status="COMPLETE", duration_seconds=seconds, finished_at=NOW)
    assert summarize(facts)["progress"]["eta_seconds"] == 22
    facts[2]["status"] = "PENDING"
    assert summarize(facts)["progress"]["eta_seconds"] is None


def test_meta_graph_global_token_not_in_filters():
    c = replace(
        config(),
        meta_enabled=True,
        meta_connection_id="synthetic-meta",
        meta_account_id="123",
        meta_api_version="v25.0",
    )
    _, _, rows = Planner().calculate(c, END, NOW, adopt=True)
    assert {r["resource"] for r in rows if r["unit_kind"] == "META_CATALOG"} == {
        "accounts",
        "campaigns",
        "adsets",
        "ads",
    }
    assert len([r for r in rows if r["unit_kind"] == "META_INSIGHTS"]) == 30
    assert not any("secret" in str(r["filters"]) or "token" in str(r["filters"]) for r in rows)
    with pytest.raises(SafeError):
        Limits(global_parallel_store_limit=100)


def test_adoption_keeps_certified_window_and_skips_smaller_publications():
    c = replace(config(), history_from="2026-09-01T00:00:00Z")
    published = {
        "store_id": c.store_id,
        "as_of": "2026-09-28T03:00:00Z",
        "report_from": "2026-09-01",
        "report_to": "2026-09-28",
    }
    configured, plan, rows = Planner().calculate(
        c, END, NOW, adopt=True, certified_publication=published
    )
    assert configured.history_from == c.history_from
    assert plan["adopted_coverage"]["publication"] == published
    pubs = [r for r in rows if r["unit_kind"] == "PUBLISH_ANALYTICS"]
    assert pubs and all(instant(r["filters"]["as_of"]) > instant(published["as_of"]) for r in pubs)
    assert all(r["filters"]["report_from"] == "2026-09-01" for r in pubs)
    assert pubs[-1]["filters"]["facts_complete"] is True
    with pytest.raises(SafeError, match="publication_outside_range"):
        Planner().calculate(
            c, END, NOW, adopt=True, certified_publication={**published, "store_id": "other-store"}
        )


def test_inspection_exposes_completed_coverage_without_mutation():
    from copy import deepcopy

    from src.installation.cli import inspection

    c = config()
    a, b = cp(c, "analytics_facts", {"from": START, "to": END, "limit": 1000})
    payload = {"registry": c.row(), "checkpoints": [a], "runs": [b], "now": NOW}
    original = deepcopy(payload)
    result = inspection(payload, END, adopt=True)
    assert payload == original
    assert result["skipped_completed_windows"]["analytics_facts"] == [(START, END)]
    assert not any(r["resource"] == "analytics_facts" for r in result["new_planned_units"])
    assert result["publication_milestones"]


def test_other_store_checkpoint_never_adopted():
    c = config()
    a, b = cp(c, "analytics_facts", {"from": START, "to": END}, "running")
    a["store_id"] = b["store_id"] = "other-store"
    _, _, rows = graph(checkpoints=[a], runs=[b])
    assert not any(r["unit_kind"] == "LEGACY_RESUME" for r in rows)
    assert len([r for r in rows if r["resource"] == "analytics_facts"]) == 30


def test_committed_mx_fixture_plan_only_without_clients(capsys):
    import json

    from src.installation.cli import main

    assert (
        main(
            [
                "--plan-only",
                "--fixture",
                "tests/installation/fixtures/mx_legacy.json",
                "--store-id",
                "synthetic-mx",
                "--adopt",
                "--target-as-of",
                END,
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert len(output["pending_legacy_units"]) == 1
    assert output["pending_legacy_units"][0]["records_processed"] == 344000
    assert not any(
        r["unit_kind"] == "SYNC_WINDOW" and r["resource"] == "analytics_facts"
        for r in output["new_planned_units"]
    )
    assert output["skipped_completed_windows"]["orders"]
    assert "cursor" not in json.dumps(output) and "secret_resource_name" not in json.dumps(output)


def test_cli_live_guards_before_clients(monkeypatch, capsys):
    from src.installation.cli import main

    def deny(*args):
        raise AssertionError("No SDK client discovery without DEV confirmation")

    monkeypatch.setattr("src.control_plane.cli.clients", deny)
    assert main(["--dispatch", "--store-id", "synthetic-mx"]) == 1
    assert (
        main(
            [
                "--plan-only",
                "--fixture",
                "tests/installation/fixtures/mx_legacy.json",
                "--store-id",
                "other-store",
                "--target-as-of",
                END,
                "--adopt",
            ]
        )
        == 1
    )
    assert capsys.readouterr().out == ""


def test_opt_in_catalog_graph_is_deterministic_and_does_not_rewrite_legacy_plan():
    operation = {
        "operation_id": "synthetic-onboarding",
        "status": "INSTALLING",
        "store_id": "synthetic-mx",
    }
    _, old_plan, old_units = Planner().calculate(config(), END, NOW, operation=operation)
    _, plan, units = Planner(catalog_snapshots=True).calculate(
        config(), END, NOW, operation=operation
    )
    _, same_plan, same_units = Planner(catalog_snapshots=True).calculate(
        config(), END, NOW, operation=operation
    )
    assert plan["plan_id"] == same_plan["plan_id"] != old_plan["plan_id"]
    assert [u["work_unit_id"] for u in units] == [u["work_unit_id"] for u in same_units]
    assert len(units) == len(old_units) + 1
    assert not any(u["resource"] == "catalog" for u in old_units)
    catalog = next(u for u in units if u["resource"] == "catalog")
    verify = next(u for u in units if u["source"] == "upzero" and u["unit_kind"] == "VERIFY_SOURCE")
    assert catalog["dependencies"] == [verify["work_unit_id"]]
    assert catalog["filters"] == {"catalog_as_of": END}
    assert catalog["required"] is True and catalog["checkpoint_plan_key"] is None
    assert catalog["unit_kind"] == "SYNC_SNAPSHOT"
