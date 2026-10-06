"""Synthetic installed stores; history cannot mutate the healthy initial graph."""

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.analytics.cloud.reader import BigQueryAnalyticsReader, SourceGeneration
from src.control_plane.model import Window, instant
from src.domain.models import SafeError
from src.installation.enrichment import EnrichmentPrepare
from src.installation.extension_repository import ExtensionLedger, ExtensionSql
from src.installation.extension_runtime import ExtensionOrchestrator, ExtensionWorker
from src.installation.extensions import ExtensionPlanner, missing, validate_extension
from src.installation.model import Limits
from tests.installation.fakes import MemoryLedger
from tests.installation.test_persistence import Transport
from tests.installation.test_planner import NOW, config, cp
from tests.installation.test_runtime import Gateway


def installed():
    c = config(
        status="ACTIVE",
        sync_enabled=True,
        analytics_enabled=True,
        revision=11,
        history_complete=False,
        facts_complete=True,
        facts_coverage_from="2026-09-01T03:00:00Z",
        facts_coverage_to="2026-10-01T03:00:00Z",
    )
    source = dict(
        row_key="synthetic-source",
        store_id=c.store_id,
        connection_id=c.upzero_connection_id,
        source_system="upzero",
        secret_resource_name="projects/synthetic-dev/secrets/synthetic/versions/1",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    pub = dict(
        store_id=c.store_id,
        policy_hash="a" * 64,
        publication_id="b" * 64,
        generation=4,
        report_from="2026-09-01",
        report_to="2026-10-01",
        as_of="2026-10-01T03:00:00Z",
        history_complete=False,
    )
    checkpoints, runs = [], []
    for resource, filters in [
        ("orders", {"start_date": "2026-09-01", "end_date": "2026-09-30", "limit": 200}),
        (
            "analytics_facts",
            {"from": "2026-09-01T03:00:00Z", "to": "2026-10-01T03:00:00Z", "limit": 1000},
        ),
    ]:
        a, b = cp(c, resource, filters, run=resource + "-run")
        checkpoints.append(a)
        runs.append(b)
    return c, source, pub, checkpoints, runs


def test_certified_ad_purchase_definition_has_distinct_id_and_preserves_initial_graph():
    from src.connectors.meta.config import Account, Insights

    c, _, publication, _, _ = installed()
    c = replace(
        c,
        meta_enabled=True,
        meta_connection_id="synthetic-meta",
        meta_account_id="000101",
        meta_api_version="v26.0",
    )
    source = dict(
        store_id=c.store_id,
        connection_id=c.meta_connection_id,
        source_system="meta",
        status="active",
        secret_resource_name=None,
        row_key="source",
        updated_at=NOW,
    )
    account = Account(
        c.store_id,
        c.meta_account_id,
        c.meta_connection_id,
        c.meta_api_version,
        c.timezone,
        c.currency,
    )
    report = Insights("2026-09-01", "2026-09-01", "impression", ("7d_click",), None)

    def calculate(spec):
        return ExtensionPlanner().calculate(
            c,
            source,
            "META_CREATIVE_COVERAGE",
            "2026-09-01",
            "2026-09-02",
            NOW,
            requested_by_hash="c" * 64,
            checkpoints=[],
            runs=[],
            publication=publication,
            account=account,
            reporting=spec,
        )

    observed, observed_units = calculate(report)
    certified, certified_units = calculate(
        replace(report, purchase_action_type="offsite_conversion.fb_pixel_purchase")
    )
    repeated, repeated_units = calculate(
        replace(report, purchase_action_type="offsite_conversion.fb_pixel_purchase")
    )
    assert certified["plan_id"] != observed["plan_id"]
    assert certified == repeated and certified_units == repeated_units
    assert len(certified_units) == 1 and certified_units[0]["resource"] == "creative_insights"
    assert (
        certified_units[0]["filters"]["purchase_action_type"]
        == "offsite_conversion.fb_pixel_purchase"
    )
    assert observed_units[0]["filters"]["purchase_action_type"] is None
    assert c.history_complete is False


def plan(purpose="HISTORY_EXTENSION", start="2026-08-30", end="2026-09-01", **kwargs):
    c, s, p, checkpoints, runs = installed()
    return ExtensionPlanner(kwargs.pop("limits", Limits())).calculate(
        c,
        s,
        purpose,
        start,
        end,
        NOW,
        requested_by_hash="c" * 64,
        checkpoints=checkpoints,
        runs=runs,
        publication=p,
        **kwargs,
    )


def test_missing_intervals_do_not_cross_gaps_or_min_max():
    assert missing(
        "2026-01-01T00:00Z",
        "2026-01-05T00:00Z",
        [("2026-01-01T00:00Z", "2026-01-02T00:00Z"), ("2026-01-04T00:00Z", "2026-01-05T00:00Z")],
    ) == [("2026-01-02T00:00:00+00:00", "2026-01-04T00:00:00+00:00")]
    with pytest.raises(SafeError):
        missing(
            "2026-01-01T00:00Z", "2026-01-02T00:00Z", [("2026-01-02T00:00Z", "2026-01-01T00:00Z")]
        )


def test_history_is_deterministic_and_only_missing_days_and_final_publication():
    p, u = plan()
    assert plan() == (p, u)
    assert len(u) == 5
    assert [r["resource"] for r in u] == [
        "orders",
        "orders",
        "analytics_facts",
        "analytics_facts",
        "publication",
    ]
    assert all(r["mode"] == "backfill" for r in u)
    assert u[-1]["filters"]["report_from"] == "2026-08-30"
    assert u[-1]["filters"]["report_to"] == "2026-10-01"
    assert set(u[-1]["dependencies"]) == {r["work_unit_id"] for r in u[:-1]}
    assert p["onboarding_operation_id"] is None
    assert p["adopted_coverage"]["extension"]["purpose"] == "HISTORY_EXTENSION"
    assert all(r["store_id"] == "synthetic-mx" for r in u)
    assert all(r["unit_kind"] not in {"VERIFY_SOURCE", "LEGACY_RESUME"} for r in u)


def test_disjoint_old_history_does_not_replace_current_publication():
    _, rows = plan(start="2026-01-01", end="2026-01-03")
    assert len(rows) == 4 and not any(r["unit_kind"] == "PUBLISH_ANALYTICS" for r in rows)


def test_certified_history_extension_is_read_again_by_recurring_full_refresh():
    c, *_ = installed()
    before = deepcopy(c.row())
    extended = replace(c, facts_coverage_from="2026-08-30T03:00:00Z")
    window = Window("2026-08-30", "2026-10-01", "2026-10-01T03:00:00Z", NOW, NOW)
    policy = extended.policy(window)
    assert instant(policy.history_from) == instant("2026-08-30T03:00:00Z")
    assert not policy.history_complete
    assert extended.history_from == c.history_from
    assert c.row() == before
    assert policy.policy_hash == c.policy(replace(window, report_from="2026-09-01")).policy_hash

    old_order = dict(store_id=c.store_id, source_system="upzero", created_at="2026-08-31T12:00:00Z")

    class Source:
        class Config:
            project = "synthetic-project"

        config = Config()

        def query(self, sql, parameters):
            values = {p.name: p.value for p in parameters}
            assert "created_at>=@history_from" in sql
            assert "2026-08-30" not in sql
            return (
                [old_order]
                if instant(old_order["created_at"]) >= instant(values["history_from"])
                else []
            ), None

    assert BigQueryAnalyticsReader(Source(), policy).read(
        "orders", SourceGeneration(NOW, "a" * 64, True), full_refresh=True
    ) == [old_order]


def test_history_request_without_complete_coverage_does_not_expand_source_read_bound():
    c, *_ = installed()
    window = Window("2026-08-30", "2026-10-01", "2026-10-01T03:00:00Z", NOW, NOW)
    with pytest.raises(SafeError, match="facts_window_not_certified"):
        c.policy(window)
    intent = replace(c, facts_complete=False, facts_coverage_from="2026-08-30T03:00:00Z")
    assert intent.policy(window).history_from == c.history_from
    assert not intent.policy(window).history_complete


def test_already_covered_period_has_no_new_work():
    p, u = plan(start="2026-09-01", end="2026-09-03")
    assert p["status"] == "COMPLETE" and u == []


def test_catalog_one_logical_snapshot_no_primary_replan_or_history_flag_change():
    c, source, p, checkpoints, runs = installed()
    before = deepcopy(c.row())
    plan, rows = ExtensionPlanner().calculate(
        c,
        source,
        "CATALOG_SNAPSHOT",
        "2026-09-30",
        "2026-10-01",
        NOW,
        requested_by_hash="c" * 64,
        checkpoints=checkpoints,
        runs=runs,
        publication=p,
    )
    assert len(rows) == 1 and rows[0]["resource"] == "catalog" and rows[0]["mode"] == "incremental"
    assert rows[0]["filters"] == {"catalog_as_of": p["as_of"]}
    assert c.row() == before and c.status == "ACTIVE" and c.sync_enabled and not c.history_complete
    validate_extension(plan, c, source)
    # Own canonical coverage increments do not invalidate the stable source contract.
    validate_extension(plan, replace(c, revision=12, facts_coverage_to="2026-10-02T03:00Z"), source)
    with pytest.raises(SafeError):
        validate_extension(
            plan,
            c,
            {
                **source,
                "secret_resource_name": "projects/synthetic-dev/secrets/synthetic/versions/2",
            },
        )


@pytest.mark.parametrize(
    "issue", ["future", "empty", "draft", "foreign", "disabled", "wrong-publication", "too-large"]
)
def test_invalid_or_unsafe_request_fails_closed(issue):
    c, s, p, checkpoints, runs = installed()
    start, end = "2026-08-30", "2026-09-01"
    limits = Limits()
    if issue == "future":
        end = "2027-01-01"
    if issue == "empty":
        end = start
    if issue == "draft":
        c = replace(c, status="DRAFT", sync_enabled=False)
    if issue == "foreign":
        s["store_id"] = "foreign"
    if issue == "disabled":
        s["status"] = "disabled"
    if issue == "wrong-publication":
        p["store_id"] = "foreign"
    if issue == "too-large":
        limits = Limits(max_units=1)
    with pytest.raises(SafeError):
        ExtensionPlanner(limits).calculate(
            c,
            s,
            "HISTORY_EXTENSION",
            start,
            end,
            NOW,
            requested_by_hash="c" * 64,
            checkpoints=checkpoints,
            runs=runs,
            publication=p,
        )


def test_pending_checkpoint_not_bypassed_by_new_history_work():
    c, s, p, cps, runs = installed()
    cps[0]["status"] = "running"
    runs[0]["status"] = "running"
    with pytest.raises(SafeError, match="requires_reconciliation"):
        ExtensionPlanner().calculate(
            c,
            s,
            "HISTORY_EXTENSION",
            "2026-08-30",
            "2026-09-01",
            NOW,
            requested_by_hash="c" * 64,
            checkpoints=cps,
            runs=runs,
            publication=p,
        )


def test_extension_reuses_worker_claim_and_refresh_without_registry_lifecycle_change():
    c, s, _, _, _ = installed()
    p, u = plan(purpose="CATALOG_SNAPSHOT", start="2026-09-30", end="2026-10-01")
    ledger = MemoryLedger(c, p, u)
    gateway = Gateway()
    before = c.row()
    o = ExtensionOrchestrator(
        ledger,
        gateway,
        lambda _: nullcontext(),
        lambda p, rows: (False, True),
        source=lambda p: s,
        clock=lambda: NOW,
        limits=Limits(max_dispatches=1),
    )
    assert o.dispatch() == 1
    r = ledger.units()[0]
    w = ExtensionWorker(
        ledger,
        lambda c, r, limits: {"complete": True, "records_processed": 100, "pages_processed": 2},
        lambda _: nullcontext(),
        source=lambda p: s,
        clock=lambda: NOW,
    )
    w.execute(
        c.store_id, r["work_unit_id"], r["reservation_revision"], r["dispatch_token"], r["pipeline"]
    )
    o.refresh(ledger.plans()[0])
    assert ledger.plans()[0]["status"] == "COMPLETE"
    assert ledger.c.row() == before
    assert ledger.units()[0]["records_processed"] == 100
    assert len(gateway.posts) == 1


def test_extension_reservation_sql_is_scoped_cas_and_cross_ledger_capacity():
    c, s, _, _, _ = installed()
    p, units = plan(purpose="CATALOG_SNAPSHOT", start="2026-09-30", end="2026-10-01")
    transport = Transport()
    ledger = ExtensionLedger(transport)
    ledger.plans = lambda store=None: [p]
    ledger.guard = lambda plan: (c, s)
    row = ledger.reserve(units[0], "synthetic-token", NOW, Limits(max_dispatches=1))
    sql, params, options = transport.calls[-1]
    assert "installation_extension_work_units" in sql and "installation_work_units" in sql
    assert (
        "revision=@config_revision AND status=@config_status AND sync_enabled=@config_sync" in sql
    )
    assert "updated_at IS NOT DISTINCT FROM @source_updated" in sql
    assert (
        sql.count("MERGE") == 1 and "MERGE `synthetic-dev.up_ops.store_runtime_config`" not in sql
    )
    assert c.store_id not in sql and "synthetic-token" not in sql
    assert "COUNT(DISTINCT store_id)" in sql and "ARRAY_LENGTH" in sql
    assert row["reservation_revision"] == 2
    assert options["job_id"].startswith("installation_")
    with pytest.raises(SafeError, match="registry_mutation_forbidden"):
        ledger.update_plan(p, c, status="COMPLETE")
    with pytest.raises(SafeError, match="activation_forbidden"):
        ledger.activate(p, c, NOW)


def test_completed_extension_history_cannot_starve_next_graph_or_reblock_after_rotation():
    c, source, *_ = installed()
    p, rows = plan(purpose="CATALOG_SNAPSHOT", start="2026-09-30", end="2026-10-01")
    ledger = MemoryLedger(c, p, rows)
    # Older completed graphs precede today's snapshot by priority/time.
    for i in range(15):
        key = f"completed-{i}"
        ledger.p[key] = dict(p, plan_id=key, status="COMPLETE", created_at="2026-09-01T00:00Z")
    o = ExtensionOrchestrator(
        ledger,
        Gateway(),
        lambda _: nullcontext(),
        lambda p, u: (True, False),
        source=lambda p: source,
        clock=lambda: NOW,
        limits=Limits(max_stores=1, max_dispatches=1),
    )
    assert len(o.dispatch_plans()) == 1
    assert o.dispatch() == 1
    assert all(ledger.p[f"completed-{i}"]["status"] == "COMPLETE" for i in range(15))
    assert ledger.c == c


def test_enrichment_inventory_is_bounded_fair_and_blocks_only_the_affected_store():
    c, *_ = installed()
    transport = Mock()
    transport.query.return_value = ([{"store_id": "blocked-brand"}, {"store_id": c.store_id}], None)
    ledger = SimpleNamespace(
        transport=transport,
        sql=ExtensionSql(Transport()),
        plans=lambda store: [{"status": "BLOCKED"}] if store == "blocked-brand" else [],
        config=lambda store: c,
    )
    service = SimpleNamespace(
        ledger=ledger, publication=lambda config: installed()[2], prepare=Mock()
    )
    assert EnrichmentPrepare(service, Limits(max_stores=2))() == 1
    sql, parameters = transport.query.call_args.args
    assert "LIMIT @limit" in sql and "NULLS FIRST" in sql
    assert "MAX(p.completed_at)" in sql and "installation_extension_plans" in sql
    assert {p.name: p.value for p in parameters}["limit"] == 2
    assert service.prepare.call_count == 1
    assert service.prepare.call_args.args[0] == {"store_id": c.store_id}
    assert service.prepare.call_args.args[2] == "2026-09-30"
    assert service.prepare.call_args.args[4] == "CATALOG_SNAPSHOT"


def test_images_extension_is_distinct_and_never_replaces_completed_catalog_graph():
    original, units = plan(purpose="CATALOG_SNAPSHOT", start="2026-09-30", end="2026-10-01")
    images, image_units = plan(purpose="CATALOG_IMAGES", start="2026-09-30", end="2026-10-01")
    assert images["plan_id"] != original["plan_id"]
    assert len(image_units) == 1 and image_units[0]["resource"] == "catalog_images"
    assert image_units[0]["unit_kind"] == "SYNC_SNAPSHOT"
    assert image_units[0]["filters"] == units[0]["filters"]
    assert original["status"] == "RUNNING" and units[0]["resource"] == "catalog"
    assert plan(purpose="CATALOG_IMAGES", start="2026-09-30", end="2026-10-01")[0] == images


def test_enrichment_images_only_after_completed_catalog_and_feature_gate():
    c, *_ = installed()
    p, _ = plan(purpose="CATALOG_SNAPSHOT", start="2026-09-30", end="2026-10-01")
    p["status"] = "COMPLETE"
    transport = Mock()
    transport.query.return_value = ([{"store_id": c.store_id}], None)
    service = SimpleNamespace(
        ledger=SimpleNamespace(
            transport=transport,
            sql=ExtensionSql(Transport()),
            plans=lambda store: [p],
            config=lambda store: c,
        ),
        publication=lambda config: installed()[2],
        prepare=Mock(),
    )
    assert EnrichmentPrepare(service, Limits(max_stores=1))() == 0
    assert service.prepare.call_count == 0
    assert EnrichmentPrepare(service, Limits(max_stores=1), images_enabled=True)() == 1
    assert service.prepare.call_args.args[4] == "CATALOG_IMAGES"
    p["status"] = "PARTIAL"
    service.prepare.reset_mock()
    assert EnrichmentPrepare(service, Limits(max_stores=1), images_enabled=True)() == 0
    service.prepare.assert_not_called()


def meta_installed():
    from src.connectors.meta.config import Account, Insights

    c, _, publication, _, _ = installed()
    c = replace(
        c,
        meta_enabled=True,
        meta_connection_id="synthetic-meta",
        meta_account_id="000101",
        meta_api_version="v26.0",
    )
    source = dict(
        store_id=c.store_id,
        connection_id=c.meta_connection_id,
        source_system="meta",
        status="active",
        secret_resource_name=None,
        row_key="source",
        updated_at=NOW,
    )
    account = Account(
        c.store_id,
        c.meta_account_id,
        c.meta_connection_id,
        c.meta_api_version,
        c.timezone,
        c.currency,
    )
    report = Insights(
        "2026-09-01",
        "2026-09-30",
        "impression",
        ("7d_click",),
        "offsite_conversion.fb_pixel_purchase",
    )
    return c, source, publication, account, report


def test_period_extension_is_deterministic_four_levels_and_no_daily_alias():
    c, source, pub, account, report = meta_installed()

    def calculate():
        return ExtensionPlanner().calculate(
            c,
            source,
            "META_PERIOD_REPORT",
            "2026-09-01",
            "2026-10-01",
            NOW,
            requested_by_hash="c" * 64,
            checkpoints=[],
            runs=[],
            publication=pub,
            account=account,
            reporting=report,
        )

    p, rows = calculate()
    assert calculate() == (p, rows)
    assert len(rows) == 4
    assert {r["filters"]["level"] for r in rows} == {"account", "campaign", "adset", "ad"}
    assert all(
        r["resource"] == "period_insights" and r["filters"]["time_increment"] == "all_days"
        for r in rows
    )
    assert c.history_complete is False and c.sync_enabled is True


def test_period_extension_includes_monthly_unique_account_windows_without_duplicate():
    c, source, pub, account, report = meta_installed()
    pub = {**pub, "report_to": "2026-10-05", "as_of": "2026-10-05T03:00:00Z"}
    p, rows = ExtensionPlanner().calculate(
        c,
        source,
        "META_PERIOD_REPORT",
        "2026-09-01",
        "2026-10-05",
        "2026-10-06T03:00:00Z",
        requested_by_hash="c" * 64,
        checkpoints=[],
        runs=[],
        publication=pub,
        account=account,
        reporting=report,
    )
    assert len(rows) == 6
    assert len({r["work_unit_id"] for r in rows}) == 6
    assert [(r["filters"]["since"], r["filters"]["until"]) for r in rows[4:]] == [
        ("2026-09-01", "2026-09-30"),
        ("2026-10-01", "2026-10-04"),
    ]
    assert all(r["filters"]["level"] == "account" for r in rows[4:])


@pytest.mark.parametrize("resource", ["meta_period_insights", "meta_creative_insights_daily"])
def test_new_reporting_definition_never_bypasses_pending_raw(resource):
    c, source, pub, account, report = meta_installed()
    pending = dict(
        store_id=c.store_id,
        connection_id=c.meta_connection_id,
        resource=resource,
        status="running",
        pending_raw_id="synthetic-pending",
        filters={
            "account": account.snapshot(),
            "insights": {
                "since": "2026-09-01",
                "until": "2026-09-30",
                "purchase_action_type": None,
            },
        },
    )
    purpose = (
        "META_PERIOD_REPORT" if resource == "meta_period_insights" else "META_CREATIVE_COVERAGE"
    )
    with pytest.raises(SafeError, match="extension_pending_checkpoint_requires_reconciliation"):
        ExtensionPlanner().calculate(
            c,
            source,
            purpose,
            "2026-09-01",
            "2026-10-01",
            NOW,
            requested_by_hash="c" * 64,
            checkpoints=[pending],
            runs=[],
            publication=pub,
            account=account,
            reporting=report,
        )


def test_completed_old_ad_definition_can_coexist_with_certified_purchase_definition():
    c, source, pub, account, report = meta_installed()
    old = dict(
        store_id=c.store_id,
        connection_id=c.meta_connection_id,
        resource="meta_creative_insights_daily",
        status="complete",
        pending_raw_id=None,
        filters={
            "account": account.snapshot(),
            "insights": {
                "since": "2026-09-01",
                "until": "2026-09-30",
                "purchase_action_type": None,
            },
        },
    )
    p, rows = ExtensionPlanner().calculate(
        c,
        source,
        "META_CREATIVE_COVERAGE",
        "2026-09-01",
        "2026-09-02",
        NOW,
        requested_by_hash="c" * 64,
        checkpoints=[old],
        runs=[],
        publication=pub,
        account=account,
        reporting=report,
    )
    assert (
        len(rows) == 1 and rows[0]["filters"]["purchase_action_type"] == report.purchase_action_type
    )
    assert (
        old["status"] == "complete" and old["filters"]["insights"]["purchase_action_type"] is None
    )
