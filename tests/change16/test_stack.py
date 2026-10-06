"""Synthetic-only #16 end-to-end materialization, transport and publication guards."""

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from src.analytics.config import AnalyticsPolicy
from src.bigquery.catalog import META_TABLE_NAMES
from src.bigquery.repository import SQLiteRepository
from src.connectors.meta.client import MetaConnector
from src.connectors.meta.live import MetaAccountLister, MetaFoundationLiveConnector
from src.connectors.upzero.catalog_schema import TABLE_NAMES as CATALOG_TABLE_NAMES
from src.dashboard.contracts import Grant, Principal, ReadError
from src.dashboard.intelligence import IntelligenceDashboardService
from src.domain.models import SafeError
from src.ingestion.meta_live import MetaLiveEngine
from src.intelligence.live.materialize import build
from src.intelligence.live.publication import Writer, commit_sql
from src.intelligence.live.schema import META_ACTIVE, PUBLICATION, SCHEMAS
from src.security.lease import local_lease
from tests.dashboard.test_read_api import FakeReader
from tests.intelligence.test_customer_intelligence import make
from tests.performance.test_performance import fixture14


def fixture16(store="mx-fashion"):
    p, snapshot, meta = fixture14(complete=False, store=store)
    _, customer, _ = make(store=store)
    snapshot["items"] = customer["items"]
    snapshot["orders"][0]["version_id"] = "ov1"
    policy = AnalyticsPolicy(
        p.store_id,
        p.policy_version,
        p.timezone,
        p.currency,
        p.purchase_statuses,
        p.history_complete,
        p.facts_complete,
        p.as_of,
        p.report_from,
        p.report_to,
        "2026-09-01T00:00:00Z",
    )
    base = {
        "store_id": store,
        "policy_hash": policy.policy_hash,
        "publication_id": "a" * 64,
        "generation": 4,
        "as_of": p.as_of,
        "report_from": p.report_from,
        "report_to": p.report_to,
    }
    args = {
        "account": meta["accounts"][0],
        "meta_insights": meta["meta_insights"],
        "meta_campaigns": meta["meta_campaigns"],
        "coverage": meta["coverage"],
        "calculated_at": meta["calculated_at"],
        "source_snapshot_at": meta["calculated_at"],
        "base_publication": base,
        "generation": 1,
    }
    return policy, snapshot, args


def artifact():
    p, s, a = fixture16()
    return build(p, s, **a)


def live(account, handler, **kwargs):
    return MetaFoundationLiveConnector(
        account,
        project="synthetic-dev",
        live=True,
        confirm_store=account.store_id,
        confirm_account=account.account_id,
        token="SYNTHETIC_TOKEN_SENTINEL",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        **kwargs,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"live": False},
        {"project": "synthetic-prod"},
        {"confirm_store": "foreign"},
        {"confirm_account": "999"},
    ],
)
def test_live_requires_all_confirmations(bad):
    _, _, a = fixture16()
    kw = dict(
        project="synthetic-dev",
        live=True,
        confirm_store=a["account"].store_id,
        confirm_account=a["account"].account_id,
        token="synthetic",
    )
    kw.update(bad)
    with pytest.raises(SafeError):
        MetaFoundationLiveConnector(a["account"], **kw)
    with pytest.raises(SafeError, match="meta_live_disabled"):
        MetaConnector(a["account"], token="synthetic", transport=None)


def test_cursor_sanitization_no_next_url_and_bounded_retry():
    _, _, a = fixture16()
    calls = []

    def handler(req):
        calls.append(req)
        assert (
            req.method == "GET"
            and req.url.host == "graph.facebook.com"
            and req.url.scheme == "https"
        )
        assert (
            "access_token" not in req.url.params
            and req.headers["Authorization"] == "Bearer SYNTHETIC_TOKEN_SENTINEL"
        )
        if len(calls) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"error": {"access_token": "SYNTHETIC_TOKEN_SENTINEL"}},
            )
        if req.url.params.get("after") is None:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "100", "account_id": "001", "name": "Synthetic"}],
                    "paging": {
                        "next": "https://evil.invalid/?access_token=SYNTHETIC_TOKEN_SENTINEL",
                        "cursors": {"after": "synthetic-next"},
                    },
                },
            )
        return httpx.Response(
            200, json={"data": [{"id": "101", "account_id": "001", "name": "Synthetic2"}]}
        )

    c = live(a["account"], handler, page_limit=7)
    pages = list(c.pages("campaigns", None))
    c.close()
    assert len(pages) == 2 and len(calls) == 3 and calls[-1].url.params["after"] == "synthetic-next"
    assert all(req.url.params["limit"] == "7" for req in calls)
    assert "SYNTHETIC_TOKEN_SENTINEL" not in json.dumps([p.payload for p in pages])
    assert pages[0].payload["http_attempts"][0]["status"] == 429


@pytest.mark.parametrize("status", [301, 401, 403, 500])
def test_http_failure_never_redirects_or_leaks(status):
    _, _, a = fixture16()
    c = live(
        a["account"],
        lambda _: httpx.Response(
            status,
            headers={"Location": "https://evil.invalid"},
            json={"error": {"token": "SYNTHETIC_TOKEN_SENTINEL"}},
        ),
        attempts=1,
    )
    pages = c.pages("campaigns", None)
    p = next(pages)
    assert p.pagination_error and "SYNTHETIC_TOKEN_SENTINEL" not in json.dumps(p.payload)
    with pytest.raises(SafeError):
        next(pages)
    c.close()


def test_listing_never_selects_or_binds_account():
    c = MetaAccountLister(
        project="synthetic-dev",
        live=True,
        store="synthetic",
        confirm_store="synthetic",
        api_version="v23.0",
        token="synthetic",
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "account_id": "001",
                            "currency": "BRL",
                            "timezone_name": "America/Sao_Paulo",
                        },
                        {
                            "account_id": "002",
                            "currency": "BRL",
                            "timezone_name": "America/Sao_Paulo",
                        },
                    ]
                },
            )
        ),
    )
    assert [r["account_id"] for r in c.list_accounts()] == ["001", "002"]
    assert not hasattr(c, "account")
    c.close()


def test_durable_raw_first_binding_replay_and_canonical_projection(tmp_path):
    p, _, a = fixture16()
    repo = SQLiteRepository(str(tmp_path / "synthetic.sqlite"))
    c = live(
        a["account"],
        lambda _: httpx.Response(
            200,
            json={
                "data": [
                    {"id": "100", "account_id": "001", "name": "Synthetic", "status": "ACTIVE"}
                ]
            },
        ),
    )
    engine = MetaLiveEngine(
        repo, c, accounts=(a["account"],), lease=lambda: local_lease(str(tmp_path / "lease"))
    )
    with pytest.raises(SafeError, match="META_ACCOUNT_BINDING_REQUIRED"):
        engine.run("campaigns")
    repo.write({"meta_account_bindings": [engine._binding()]})
    original = repo.write

    def fail_core(batch):
        if "meta_live_campaigns" in batch:
            raise SafeError("synthetic_write_failure")
        original(batch)

    with patch.object(repo, "write", side_effect=fail_core):
        with pytest.raises(SafeError):
            engine.run("campaigns")
    assert len(repo.read("meta_raw_campaigns", p.store_id)) == 1
    cp = repo.read("sync_checkpoints", p.store_id)[0]
    assert cp["pending_raw_id"] and cp["status"] != "complete"
    engine.run("campaigns")
    assert len(repo.read("meta_live_campaigns", p.store_id)) == 1
    assert len(repo.read("meta_live_campaigns_versions", p.store_id)) == 1
    assert not repo.read("meta_campaigns", p.store_id)
    raw = repo.read("meta_raw_campaigns", p.store_id)[0]
    assert raw["connector_version"] == "meta-live-1.0.0"
    engine.replay("campaigns", raw["run_id"])
    assert (
        len(repo.read("meta_live_campaigns", p.store_id))
        == len(repo.read("meta_live_campaigns_versions", p.store_id))
        == 1
    )
    assert repo.read("sync_checkpoints", p.store_id)[0]["status"] == "complete"
    c.close()


def test_all_models_int64_scopes_dedupe_partial_and_reorder_idempotence():
    p, s, a = fixture16()
    r = build(p, s, **a)
    assert set(r["tables"]) == set(SCHEMAS)
    assert all(
        set(row) == set(SCHEMAS[n].fields) and type(row["generation"]) is int
        for n, rows in r["tables"].items()
        for row in rows
    )
    flags = r["tables"]["analytics_customer_paid_influence"]
    assert {row["influence_scope"] for row in flags} == {
        "LIFETIME",
        "ACQUISITION",
        "REPEAT_PURCHASE",
    }
    assert len({row["row_key"] for row in flags}) == 3
    summary = r["tables"]["analytics_performance_summary"][0]
    assert (
        summary["requested_revenue_influenced"] == "100.00"
        and summary["fulfilled_revenue_influenced"] == "80.00"
    )
    assert summary["new_customers_influenced"] is None and summary["cac_new_customer"] is None
    assert r["tables"]["analytics_customer_products_summary"][0]["product_id"] is None
    s["events"].reverse()
    assert build(p, s, **a)["publication"]["publication_id"] == r["publication"]["publication_id"]
    assert (
        build(p, s, **{**a, "generation": 2})["publication"]["publication_id"]
        == r["publication"]["publication_id"]
    )


def test_historical_unlinked_purchase_preserved_unknown_not_false():
    p, s, a = fixture16()
    for f in s["events"]:
        f["order_id"] = None
    r = build(p, s, **a)
    assert r["tables"]["analytics_paid_touchpoints"]
    assert not r["tables"]["analytics_order_paid_influence"]
    assert r["tables"]["analytics_customer_360_profile"][0]["paid_media_influenced"] is None
    assert r["tables"]["analytics_performance_summary"][0]["roas_requested"] is None
    assert r["publication"]["influence_complete"] is False


@pytest.mark.parametrize("kind", ["store", "account", "generation", "base", "limit"])
def test_materializer_fail_closed(kind):
    p, s, a = fixture16()
    if kind == "store":
        s["orders"][0]["store_id"] = "foreign"
    if kind == "account":
        a["meta_campaigns"][0]["account_id"] = "999"
    if kind == "generation":
        a["generation"] = "1"
    if kind == "base":
        a["base_publication"]["policy_hash"] = "foreign"
    if kind == "limit":
        s["orders"] *= 100001
    with pytest.raises(ValueError):
        build(p, s, **a)


class StageTransport:
    def __init__(self, fail=None):
        self.config = type("Config", (), {"project": "synthetic-dev"})()
        self.stage = {}
        self.receipts = []
        self.head = 0
        self.calls = []
        self.fail = fail

    def query(self, sql, params, **kwargs):
        self.calls.append((sql, kwargs))
        values = {p.name: p.value for p in params}
        if sql.startswith("SELECT *"):
            return [r for r in self.receipts if r["publication_id"] == values["publication"]], None
        if kwargs.get("create_session"):
            self.stage = {}
            return [], "synthetic-session"
        if sql.startswith("CALL"):
            return [], None
        if sql.startswith("INSERT INTO _SESSION"):
            name = re.search(r"stage_(\w+)", sql)[1]
            if self.fail == name:
                raise ValueError("synthetic_stage_failed")
            self.stage.setdefault(name, []).extend(json.loads(values["rows"]))
            return [], None
        if sql.startswith("BEGIN"):
            if self.fail == "commit":
                raise TimeoutError("synthetic_ambiguous_commit")
            assert self.head == values["expected"]
            self.receipts += deepcopy(self.stage[PUBLICATION])
            self.head = values["generation"]
            if self.fail == "response":
                raise TimeoutError("synthetic_response_lost")
            return [], None
        raise AssertionError("Unexpected offline transport SQL")


@pytest.mark.parametrize("fail", ["analytics_customer_timeline", "commit", "response", None])
def test_atomic_publication_failure_recovery_retry(fail):
    t = StageTransport(fail)
    a = artifact()
    w = Writer(t)
    if fail in {"commit", "analytics_customer_timeline"}:
        with pytest.raises((ValueError, SafeError)):
            w.publish(a, 0)
        assert not t.receipts and t.head == 0
        t.fail = None
    p = w.publish(a, 0)
    assert t.head == 1 and len(t.receipts) == 1
    assert w.publish(a, 1) == p and len(t.receipts) == 1
    sql = commit_sql("synthetic-dev")
    assert sql.index(
        "INSERT INTO `synthetic-dev.up_analytics.analytics_intelligence_publications`"
    ) < sql.index("UPDATE `synthetic-dev.up_analytics.analytics_intelligence_publications`")
    assert "BEGIN TRANSACTION" in sql and "COMMIT TRANSACTION" in sql and "@expected" in sql
    assert not re.search(r"DELETE|DROP|TRUNCATE", sql)


class IntelligenceReader(FakeReader):
    def __init__(self, policy, artifact):
        super().__init__(policy)
        self.artifact = artifact

    def query(self, q, **kw):
        if q.name in self.override:
            return super().query(q, **kw)
        if q.name == "intelligence_head":
            self.calls.append(q)
            r = deepcopy(self.artifact["publication"])
            h = {**r, "record_kind": "HEAD", "row_key": "head", "receipt_json": json.dumps(r)}
            return [h]
        if q.name == "intelligence_performance_period":
            self.calls.append(q)
            rows = deepcopy(self.artifact["tables"]["analytics_performance_summary"])
            row = next(r for r in rows if r["influence_scope"] == "LIFETIME")
            return [
                {
                    "store_id": row["store_id"],
                    "policy_hash": row["policy_hash"],
                    "generation": row["generation"],
                    "summary": row,
                    "series": [],
                }
            ]
        if q.name == "intelligence_customer_context":
            self.calls.append(q)
            customer = q.parameters["customer"][1]
            return [
                {
                    "journey": deepcopy(
                        [
                            r
                            for r in self.artifact["tables"]["analytics_customer_journey_summary"]
                            if r["customer_id"] == customer
                        ]
                    ),
                    "marketing": deepcopy(
                        [
                            r
                            for r in self.artifact["tables"]["analytics_customer_paid_influence"]
                            if r["customer_id"] == customer
                        ]
                    ),
                }
            ]
        if q.name.startswith("intelligence_analytics_"):
            self.calls.append(q)
            n = q.name.removeprefix("intelligence_")
            params = {k: v[1] for k, v in q.parameters.items()}
            rows = deepcopy(self.artifact["tables"][n])
            for field, k in [
                ("customer_id", "customer"),
                ("campaign_id", "campaign"),
                ("influence_scope", "influence_scope"),
            ]:
                if params.get(k) is not None:
                    rows = [r for r in rows if r.get(field) == params[k]]
            return [r for r in rows if r["row_key"] > params.get("after", "")][
                : params.get("limit", 101)
            ]
        return super().query(q, **kw)


def service():
    p, s, a = fixture16()
    r = build(p, s, **a)
    reader = IntelligenceReader(p, r)
    grant = Grant("synthetic", p.store_id, "B2B")
    principal = Principal("synthetic-user", "CLIENT_USER", frozenset({grant}))
    svc = IntelligenceDashboardService(
        "up-data-intelligence-dev",
        {p.store_id: p},
        lambda: reader,
        b"synthetic-cursor-signing-key-32-bytes",
    )
    return svc, reader, principal, grant


@pytest.mark.parametrize(
    "resource",
    [
        "performance",
        "customer360",
        "timeline",
        "customerProducts",
        "campaigns",
        "campaign",
        "campaignCustomers",
        "campaignOrders",
        "influencedOrders",
        "influencedCustomers",
    ],
)
def test_read_routes_authorized_generation_and_pii_projection(resource):
    s, r, p, g = service()
    entity = (
        "c1"
        if resource in {"customer360", "timeline", "customerProducts"}
        else "100"
        if resource.startswith("campaign") and resource != "campaigns"
        else None
    )
    out = s.intelligence(p, g, resource, entity=entity)
    assert out["metadata"]["generation"] == 1 and out["metadata"]["analytics_generation"] == 4
    assert out["metadata"]["history_complete"] is False
    payload = json.dumps(out)
    assert all(
        '"' + k + '"' not in payload
        for k in [
            "email",
            "phone",
            "cpf",
            "cnpj",
            "identity_path",
            "session_id",
            "visitor_id",
            "user_id",
            "fbclid",
            "fbc",
            "gclid",
            "access_token",
        ]
    )
    if resource == "performance":
        assert out["data"]["cac_new_customer"] is None
    if resource == "customer360":
        assert out["data"]["health_policy"] == "NOT_DEFINED" and out["data"]["ltv_complete"] is None
    assert not any("up_raw" in q.sql for q in r.calls)


@pytest.mark.parametrize(
    "problem", ["missing", "duplicate", "wrong_receipt", "foreign_base", "foreign_store"]
)
def test_head_receipt_fail_closed(problem):
    s, r, p, g = service()
    s._scope(p, g)
    rows = r.query(type("Q", (), {"name": "intelligence_head"})())
    if problem == "missing":
        rows = []
    if problem == "duplicate":
        rows *= 2
    if problem == "wrong_receipt":
        rows[0]["receipt_json"] = None
    if problem == "foreign_base":
        rows[0]["base_generation"] = 999
    if problem == "foreign_store":
        rows[0]["store_id"] = "foreign"
    r.override["intelligence_head"] = rows
    with pytest.raises(ReadError):
        s.intelligence(p, g, "performance")


def test_authorization_before_queries_customer_isolation_cursor_and_period():
    s, r, p, g = service()
    with pytest.raises(ReadError):
        s.intelligence(p, replace(g, store_id="foreign"), "timeline", entity="c1")
    assert not r.calls
    with pytest.raises(ReadError, match="customer_not_found"):
        s.intelligence(p, g, "timeline", entity="other-customer")
    out = s.intelligence(p, g, "timeline", entity="c1", size="1")
    assert out["pagination"]["has_more"]
    nxt = s.intelligence(
        p, g, "timeline", entity="c1", size="1", cursor=out["pagination"]["cursor"]
    )
    assert nxt["data"] != out["data"]
    with pytest.raises(ReadError):
        s.intelligence(p, g, "timeline", entity="c1", size="2", cursor=out["pagination"]["cursor"])
    with pytest.raises(ReadError):
        s.intelligence(p, g, "timeline", entity="c1", cursor="invalid")
    with pytest.raises(ReadError, match="intelligence_period_not_materialized"):
        s.intelligence(p, g, "timeline", entity="c1", from_day="2026-09-02", to_day="2026-09-28")


def test_terraform_additive_baseline_and_canonical_families():
    root = Path("infra/terraform")
    old = json.loads(Path("tests/fixtures/change16/base_tables.json").read_text())
    active = json.loads((root / "tables.json").read_text())
    assert {k: active[k] for k in old} == old
    assert set(active) - set(old) == META_ACTIVE | set(SCHEMAS) | CATALOG_TABLE_NAMES | {
        "store_runtime_config",
        "workspace_store_bindings",
        "onboarding_operations",
        "installation_plans",
        "installation_work_units",
        "installation_extension_plans",
        "installation_extension_work_units",
        "integration_operations",
        "meta_creative_insights_daily",
        "meta_creative_insights_daily_versions",
        "meta_period_insights",
        "meta_period_insights_versions",
    } and len(set(active) - set(old)) == 41 + len(CATALOG_TABLE_NAMES)
    for name, sha in json.loads(
        Path("tests/fixtures/change16/base_schema_hashes.json").read_text()
    ).items():
        assert hashlib.sha256((root / "schemas" / (name + ".json")).read_bytes()).hexdigest() == sha
    creative = {"meta_creative_insights_daily", "meta_creative_insights_daily_versions"}
    assert not (
        META_TABLE_NAMES
        - META_ACTIVE
        - creative
        - {"meta_period_insights", "meta_period_insights_versions"}
    ) & set(active)
    assert all(active[name]["cluster"] == ["store_id", "account_id", "ad_id"] for name in creative)
    assert all(SCHEMAS[n].fields["generation"] == "INT64" for n in SCHEMAS)
    tf = (root / "change16.tf").read_text()
    assert (
        "google_cloud_scheduler" not in tf
        and "google_secret_manager_secret_version" not in tf
        and "prevent_destroy = true" in tf
    )
    assert re.search(r"scheduler_paused\s*=\s*true", (root / "environments/dev.tfvars").read_text())


def test_unmapped_campaign_still_counts_proven_store_orders_once():
    p, s, a = fixture16()
    s["events"][0]["meta_campaign_id"] = "999"
    out = build(p, s, **a)
    summary = out["tables"]["analytics_performance_summary"][0]
    assert summary["influenced_orders"] == 1 and summary["influenced_customers"] == 1
    assert summary["requested_revenue_influenced"] == "100.00"
    assert summary["influence_complete"] is False and summary["roas_requested"] is None
    assert out["tables"]["analytics_campaign_order_performance"] == []


def test_publication_sequence_survives_head_rollback_and_retry():
    t = StageTransport()
    w = Writer(t)
    a = artifact()
    w.publish(a, 0)
    # Simulates an operator's guarded HEAD rollback; receipts/generations remain immutable.
    t.head = 0
    p, s, args = fixture16()
    args.update(generation=2, calculated_at="2026-09-30T00:00:00Z")
    next_artifact = build(p, s, **args)
    saved = w.publish(next_artifact, 0)
    assert saved["generation"] == 2 and len(t.receipts) == 2
    assert w.publish(next_artifact, 2) == saved and len(t.receipts) == 2


def test_saved_plan_guard_rejects_destroy_updates_and_unapproved_creates():
    from scripts.change16_plan_guard import check

    for action in [["delete"], ["delete", "create"], ["update"]]:
        with pytest.raises(ValueError):
            check(
                {
                    "resource_changes": [
                        {
                            "address": 'google_bigquery_table.tables["orders"]',
                            "change": {"actions": action},
                        }
                    ]
                }
            )
    with pytest.raises(ValueError):
        check(
            {
                "resource_changes": [
                    {
                        "address": "google_cloud_scheduler_job.unsafe",
                        "change": {"actions": ["create"]},
                    }
                ]
            }
        )
    assert (
        check(
            {
                "resource_changes": [
                    {
                        "address": 'google_bigquery_table.tables["analytics_customer_timeline"]',
                        "index": "analytics_customer_timeline",
                        "change": {"actions": ["create"], "after": {"deletion_protection": True}},
                    }
                ]
            }
        )["add"]
        == 1
    )


def test_campaign_aggregate_sql_parameterized_without_alias_regression():
    from src.dashboard.intelligence_queries import campaigns

    q = campaigns("synthetic-dev")
    assert "@store" in q and "@policy" in q and "@generation" in q and "@campaign" in q
    assert "COUNT(DISTINCT customer_id)" in q and "COUNT(DISTINCT order_id)" in q
    assert not re.search(r"FOR SYSTEM_TIME AS OF @snapshot [a-z]+\b", q)
    assert "CAST(d.clicks AS NUMERIC)" in q and "SUM(d.influenced_customers)" not in q


def test_bigquery_json_foundation_rows_keep_money_and_decode_declared_json_only():
    from decimal import Decimal

    from src.intelligence.live.runtime import foundation_row

    row = {
        "spend": Decimal("15.120000000"),
        "reporting_configuration": '{"level":"campaign"}',
        "breakdown_values": "{}",
        "campaign_name": '{"literal":"name"}',
        "version_id": "synthetic-version",
    }
    decoded = foundation_row("insights_daily", row)
    assert decoded["spend"] == "15.120000000"
    assert decoded["reporting_configuration"] == {"level": "campaign"}
    assert decoded["breakdown_values"] == {}
    assert decoded["campaign_name"] == row["campaign_name"]
    assert "version_id" not in decoded
    assert row["reporting_configuration"].startswith("{")


def test_spend_invariant_uses_authorized_account_configuration_and_window():
    from src.intelligence.live.validation import sql

    q = sql("synthetic-dev")
    assert "summary:meta_spend" in q
    assert "s.meta_spend IS DISTINCT FROM" in q
    assert "SUM(spend)" in q
    assert "COUNTIF(spend IS NULL)>0,NULL" in q
    assert "account_id=@account AND configuration_hash=@configuration" in q
    assert "date_start>=@from AND date_start<@to" in q


def test_timeline_records_expose_stable_opaque_key_without_identity_path():
    s, _, p, g = service()
    first = s.intelligence(p, g, "timeline", entity="c1")
    second = s.intelligence(p, g, "timeline", entity="c1")
    assert first["data"] == second["data"]
    keys = [row["record_key"] for row in first["data"]]
    assert len(keys) == len(set(keys))
    assert all(re.fullmatch("[a-f0-9]{64}", key) for key in keys)
    assert all("identity_path" not in row for row in first["data"])


@pytest.mark.parametrize("counts", [None, {}, {"unexpected_model": 1}])
def test_completed_publication_requires_all_model_receipt_counts(counts):
    s, r, p, g = service()
    s._scope(p, g)
    rows = r.query(type("Q", (), {"name": "intelligence_head"})())
    receipt = json.loads(rows[0]["receipt_json"])
    receipt["row_counts"] = counts
    rows[0]["row_counts"] = counts
    rows[0]["receipt_json"] = json.dumps(receipt)
    r.override["intelligence_head"] = rows
    with pytest.raises(ReadError, match="intelligence_publication_invalid"):
        s.intelligence(p, g, "performance")


@pytest.mark.parametrize(
    "reference",
    [
        "projects/up-data-intelligence-prod/secrets/up-intelligence-meta-global-token/versions/1",
        "projects/up-data-intelligence-dev/secrets/per-customer-token/versions/1",
        "projects/up-data-intelligence-dev/secrets/up-intelligence-meta-global-token/versions/latest",
    ],
)
def test_secret_reference_rejects_cross_project_store_tokens_or_implicit_versions(reference):
    from src.intelligence.live.cli import validated_secret_reference

    with pytest.raises(SafeError, match="global_dev_meta_secret_version_required"):
        validated_secret_reference(reference)
    approved = (
        "projects/up-data-intelligence-dev/secrets/up-intelligence-meta-global-token/versions/1"
    )
    assert validated_secret_reference(approved) == approved


def test_selected_performance_and_campaign_periods_bind_values_and_preserve_nulls():
    s, r, p, g = service()
    out = s.intelligence(p, g, "performance", from_day="2026-09-02", to_day="2026-09-28")
    assert out["data"]["new_customers_influenced"] is None
    assert out["data"]["cac_new_customer"] is None
    assert isinstance(out["data"]["series"], list)
    query = next(q for q in r.calls if q.name == "intelligence_performance_period")
    assert query.parameters["from"] == ("DATE", "2026-09-02")
    assert query.parameters["to"] == ("DATE", "2026-09-28")
    assert "2026-09-02" not in query.sql
    assert "@history_complete AND @influence_complete" in query.sql
    assert "COUNT(DISTINCT order_id)" in query.sql
    s.intelligence(p, g, "campaigns", from_day="2026-09-02", to_day="2026-09-28")
    q = r.calls[-1]
    assert "date>=@from AND date<@to" in q.sql
    assert "DATE(o.created_at,@timezone)>=@from" in q.sql
    assert "identity_path" not in q.sql
    assert "FOR SYSTEM_TIME AS OF @snapshot p" not in q.sql


def test_selected_campaign_participation_period_cursor_and_store_isolation():
    s, r, p, g = service()
    campaigns = s.intelligence(p, g, "campaigns")["data"]
    campaign = campaigns[0]["campaign_id"]
    s.intelligence(
        p, g, "campaignCustomers", entity=campaign, from_day="2026-09-02", to_day="2026-09-28"
    )
    q = r.calls[-1]
    assert q.parameters["campaign"] == ("STRING", campaign)
    assert q.parameters["store"] == ("STRING", g.store_id)
    assert "COUNT(DISTINCT order_id)" in q.sql
    assert "identity_path" not in q.sql
    assert campaign not in q.sql
    with pytest.raises(ReadError, match="interval_outside_publication"):
        s.intelligence(p, g, "performance", from_day="2020-01-01", to_day="2020-01-02")
    r.calls.clear()
    with pytest.raises(ReadError):
        s.intelligence(p, replace(g, store_id="foreign"), "performance")
    assert not r.calls
