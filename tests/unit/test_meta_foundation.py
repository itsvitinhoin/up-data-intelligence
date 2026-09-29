"""All names, identifiers, metrics and tokens in this module are synthetic."""

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src.attribution.contracts import LastPaidTouchPolicy, reporting_date
from src.attribution.meta import resolve_facts
from src.bigquery.catalog import META_TABLE_NAMES, TABLES
from src.bigquery.repository import SQLiteRepository, merge_sql
from src.connectors.meta.client import MetaConnector
from src.connectors.meta.config import (
    Account,
    Insights,
    configuration_key,
    meta_id,
    validate_accounts,
)
from src.domain.models import SafeError
from src.ingestion.meta import MetaEngine
from src.normalization.meta import normalize
from src.security.lease import local_lease
from src.utils.data import canonical

ACCOUNT = Account(
    "synthetic-store", "000101", "synthetic-meta", "v23.0", "America/Sao_Paulo", "BRL"
)
INSIGHTS = Insights("2026-01-01", "2026-01-02", "impression", ("7d_click",), "purchase")
TOKEN = "SYNTHETIC_TEST_ONLY_NOT_A_CREDENTIAL"


def source(resource, account=ACCOUNT):
    common = {"account_id": account.account_id, "name": "Synthetic entity"}
    if resource == "accounts":
        return {
            **common,
            "id": "act_" + account.account_id,
            "currency": account.currency,
            "timezone_name": account.timezone,
            "account_status": 1,
        }
    if resource == "campaigns":
        return {**common, "id": "000201", "objective": "OUTCOME_SALES"}
    if resource == "adsets":
        return {**common, "id": "000301", "campaign_id": "000201"}
    if resource == "ads":
        return {**common, "id": "000401", "campaign_id": "000201", "adset_id": "000301"}
    return {
        "account_id": account.account_id,
        "campaign_id": "000201",
        "adset_id": "000301",
        "ad_id": "000401",
        "date_start": "2026-01-01",
        "date_stop": "2026-01-01",
        "account_currency": "BRL",
        "spend": "123.450000001",
        "impressions": "1000",
        "reach": "900",
        "frequency": "1.111",
        "clicks": "10",
        "inline_link_clicks": "8",
        "cpm": "123.45",
        "cpc": "12.345",
        "ctr": "1",
        "actions": [
            {"action_type": "purchase", "value": "2"},
            {"action_type": "omni_purchase", "value": "2"},
            {"action_type": "landing_page_view", "value": "7"},
        ],
        "action_values": [{"action_type": "purchase", "value": "250.12"}],
    }


def response_for(request, account=ACCOUNT):
    resource = request.url.path.rsplit("/", 1)[-1]
    if resource.startswith("act_"):
        return httpx.Response(200, json=source("accounts", account))
    return httpx.Response(200, json={"data": [source(resource, account)]})


@pytest.fixture
def setup(tmp_path):
    repo = SQLiteRepository(str(tmp_path / "state.db"))
    clients = []

    def make(handler=response_for, account=ACCOUNT, accounts=None, repository=None, **kwargs):
        connector = MetaConnector(
            account,
            token=TOKEN,
            transport=httpx.MockTransport(handler),
            sleep=lambda _: None,
            **kwargs,
        )
        clients.append(connector)
        return MetaEngine(
            repository or repo,
            connector,
            accounts=accounts or (account,),
            lease=lambda: local_lease(str(tmp_path / (account.store_id + ".lock"))),
        )

    yield repo, make
    for client in clients:
        client.close()


@pytest.mark.parametrize(
    "resource,table",
    [
        ("accounts", "meta_accounts"),
        ("campaigns", "meta_campaigns"),
        ("adsets", "meta_adsets"),
        ("ads", "meta_ads"),
        ("insights", "meta_insights_daily"),
    ],
)
def test_roundtrip_raw_core_history_replay_and_cached_run(setup, resource, table):
    repo, make = setup
    engine = make()
    cfg = INSIGHTS if resource == "insights" else None
    run = engine.run(resource, cfg)
    assert run["status"] == "completed"
    assert run["source_records_read"] == run["raw_pages_written"] == 1
    assert run["core_records_inserted"] == 1
    assert run["core_records_processed"] == 1
    assert engine.run(resource, cfg)["run_id"] == run["run_id"]
    replay = engine.replay(resource, run["run_id"])
    assert replay["replay_records_read"] == 1
    assert replay["source_records_read"] == replay["raw_pages_written"] == 0
    assert replay["core_records_inserted"] == replay["core_records_updated"] == 0
    assert (
        len(repo.read(table, ACCOUNT.store_id))
        == len(repo.read(table + "_versions", ACCOUNT.store_id))
        == 1
    )
    raw = repo.read("meta_raw_" + resource, ACCOUNT.store_id)[0]
    assert raw["payload"]["data"] == [source(resource)]
    assert raw["request_filters"]["account"]["timezone"] == "America/Sao_Paulo"


@pytest.mark.parametrize("value", [1, True, "", " 001", "1.0", "act_001", None])
def test_invalid_identifiers_not_coerced(value):
    with pytest.raises(SafeError, match="invalid_meta_id"):
        meta_id(value)


def test_ids_leading_zeroes_and_decimals():
    _, row = normalize("insights", source("insights"), ACCOUNT, INSIGHTS)
    assert row["account_id"] == "000101" and row["ad_id"] == "000401"
    assert row["campaign_id"] == "000201" and row["adset_id"] == "000301"
    assert Decimal(row["spend"]) == Decimal("123.450000001")
    assert row["meta_reported_purchases"] == "2"  # not purchase + omni_purchase = 4
    assert row["meta_reported_purchase_value"] == "250.12"
    assert row["landing_page_views"] == "7"
    assert row["actions"] == source("insights")["actions"]
    assert not any(k.startswith("first_party") for k in row)


def test_purchase_mapping_requires_explicit_choice():
    _, row = normalize(
        "insights", source("insights"), ACCOUNT, replace(INSIGHTS, purchase_action_type=None)
    )
    assert row["meta_reported_purchases"] is None
    assert row["meta_reported_purchase_value"] is None


def test_pagination_uses_cursor_and_fixed_route_not_next_url(setup):
    repo, make = setup
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "graph.facebook.com"
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert "access_token" not in request.url.params
        assert request.url.params["limit"] == "7"
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [],
                    "paging": {
                        "next": "https://untrusted.invalid/?access_token=" + TOKEN,
                        "cursors": {"after": "synthetic-cursor"},
                    },
                },
            )
        assert request.url.params["after"] == "synthetic-cursor"
        return httpx.Response(200, json={"data": [source("ads")]})

    run = make(handler, page_limit=7).run("ads")
    assert len(calls) == run["raw_pages_written"] == 2
    assert run["source_records_read"] == 1
    assert len(repo.read("meta_ads", ACCOUNT.store_id)) == 1


def test_tokens_scrubbed_from_raw_and_logs(setup, caplog):
    repo, make = setup

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [source("ads") | {"name": "accidental " + TOKEN}],
                "access_token": TOKEN,
                "extra_url": "https://example.invalid/?access_token=" + TOKEN,
            },
        )

    with caplog.at_level("INFO"):
        make(handler).run("ads")
    for table in ["meta_raw_ads", "meta_ads", "sync_runs", "sync_checkpoints"]:
        assert TOKEN not in canonical(repo.read(table, ACCOUNT.store_id))
    assert TOKEN not in caplog.text


def test_http_retry_is_safe_and_does_not_duplicate(setup):
    repo, make = setup
    attempts = []

    def handler(request):
        attempts.append(1)
        return (
            httpx.Response(429, headers={"Retry-After": "0"})
            if len(attempts) == 1
            else response_for(request)
        )

    run = make(handler).run("ads")
    assert run["retries"] == 1 and len(attempts) == 2
    assert run["source_records_read"] == run["core_records_inserted"] == 1
    assert len(repo.read("meta_raw_ads", ACCOUNT.store_id)) == 1


@pytest.mark.parametrize("unknown", [False, True])
def test_raw_before_core_mid_write_failure_and_checkpoint_resume(setup, unknown):
    repo, make = setup
    writes = []
    actual_write = repo.write
    fail = [True]

    def write(tables):
        writes.append(tuple(tables))
        if "meta_ads" in tables and fail[0]:
            fail[0] = False
            assert len(repo.read("meta_raw_ads", ACCOUNT.store_id)) == 1
            assert repo.read("sync_checkpoints", ACCOUNT.store_id)[0]["pending_raw_id"]
            if unknown:
                actual_write(tables)
                raise SafeError("bigquery_write_outcome_unknown")
            raise SafeError("synthetic_persistence_failure")
        actual_write(tables)

    repo.write = write
    engine = make()
    with pytest.raises(SafeError):
        engine.run("ads")
    cp = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
    assert cp["status"] != "complete"

    def no_api(_):
        raise AssertionError("resume must use existing RAW / committed checkpoint")

    report = make(no_api).run("ads")
    assert report["core_records_inserted"] == report["source_records_read"] == 1
    assert len(repo.read("meta_raw_ads", ACCOUNT.store_id)) == 1
    assert len(repo.read("meta_ads", ACCOUNT.store_id)) == 1
    assert repo.read("sync_checkpoints", ACCOUNT.store_id)[0]["status"] == "complete"


@pytest.mark.parametrize(
    "paging", [{"next": "https://example.invalid"}, {"next": "x", "cursors": {"after": "same"}}]
)
def test_invalid_pagination_is_durable_and_never_advances(setup, paging):
    repo, make = setup

    def handler(request):
        return httpx.Response(200, json={"data": [source("ads")], "paging": paging})

    engine = make(handler, max_pages=1)
    with pytest.raises(SafeError):
        engine.run("ads")
    assert repo.read("meta_raw_ads", ACCOUNT.store_id)[0]["pagination_error"]
    assert not repo.read("meta_ads", ACCOUNT.store_id)
    cp = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
    assert cp["pending_raw_id"] and cp["position"] == {}


def test_overlapping_windows_and_refresh_update_not_duplicate(setup):
    repo, make = setup
    engine = make()
    first = engine.run("insights", INSIGHTS)
    engine.run("insights", replace(INSIGHTS, until="2026-01-03"))
    assert len(repo.read("meta_insights_daily", ACCOUNT.store_id)) == 1

    def changed(request):
        return httpx.Response(200, json={"data": [source("insights") | {"spend": "125.01"}]})

    updated = make(changed).run("insights", INSIGHTS, refresh=True)
    assert updated["core_records_updated"] == 1
    assert len(repo.read("meta_insights_daily_versions", ACCOUNT.store_id)) == 2
    engine.replay("insights", first["run_id"])
    assert repo.read("meta_insights_daily", ACCOUNT.store_id)[0]["spend"] == "125.01"


def test_entity_history_keeps_original_and_latest(setup):
    repo, make = setup
    first = make().run("campaigns")

    def changed(request):
        return httpx.Response(
            200, json={"data": [source("campaigns") | {"name": "Synthetic renamed"}]}
        )

    assert make(changed).run("campaigns", refresh=True)["core_records_updated"] == 1
    make().replay("campaigns", first["run_id"])
    assert repo.read("meta_campaigns", ACCOUNT.store_id)[0]["name"] == "Synthetic renamed"
    assert len(repo.read("meta_campaigns_versions", ACCOUNT.store_id)) == 2


def test_insight_configuration_and_breakdown_identity():
    base = source("insights")
    key, _ = normalize("insights", base, ACCOUNT, INSIGHTS)
    other, _ = normalize(
        "insights", base, ACCOUNT, replace(INSIGHTS, action_report_time="conversion")
    )
    assert key != other
    cfg = replace(INSIGHTS, breakdowns=("country",))
    a, _ = normalize("insights", base | {"country": "BR"}, ACCOUNT, cfg)
    b, _ = normalize("insights", base | {"country": "US"}, ACCOUNT, cfg)
    assert len({key, a, b}) == 3
    assert configuration_key(ACCOUNT, INSIGHTS) == configuration_key(
        ACCOUNT, replace(INSIGHTS, until="2026-01-03")
    )


@pytest.mark.parametrize(
    "changes,rule",
    [
        ({"spend": "-1"}, "negative_spend"),
        ({"ad_id": 123}, "invalid_meta_id"),
        ({"date_stop": "2026-01-02"}, "invalid_insights_date"),
        ({"date_start": "not-a-date"}, "invalid_insights_date"),
        ({"account_id": "999"}, "meta_account_mismatch"),
    ],
)
def test_blocking_quality_keeps_raw_and_checkpoint(setup, changes, rule):
    repo, make = setup

    def handler(request):
        return httpx.Response(200, json={"data": [source("insights") | changes]})

    with pytest.raises(SafeError, match="meta_page_requires_review"):
        make(handler).run("insights", INSIGHTS)
    assert len(repo.read("meta_raw_insights", ACCOUNT.store_id)) == 1
    assert not repo.read("meta_insights_daily", ACCOUNT.store_id)
    assert repo.read("quality_results", ACCOUNT.store_id)[0]["rule_id"] == rule
    report = repo.read("sync_runs", ACCOUNT.store_id)[0]
    assert report["source_records_read"] == 1 and report["core_records_processed"] == 0
    assert report["core_records_failed"] == 1
    assert repo.read("sync_checkpoints", ACCOUNT.store_id)[0]["pending_raw_id"]


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_page_quality(setup, conflicting):
    repo, make = setup

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    source("ads"),
                    source("ads") | ({"name": "conflict"} if conflicting else {}),
                ]
            },
        )

    if conflicting:
        with pytest.raises(SafeError):
            make(handler).run("ads")
        assert not repo.read("meta_ads", ACCOUNT.store_id)
    else:
        make(handler).run("ads")
        assert len(repo.read("meta_ads", ACCOUNT.store_id)) == 1
    assert repo.read("quality_results", ACCOUNT.store_id)[0]["rule_id"] == "duplicate_ads"


def fact(**kwargs):
    return {
        "store_id": ACCOUNT.store_id,
        "fact_id": "synthetic-fact",
        "source_system": "upzero",
        "version_id": "synthetic-version",
        "occurred_at": "2026-01-02T01:00:00Z",
        "meta_ad_id": "000401",
        "meta_adset_id": "000301",
        "meta_campaign_id": "000201",
        **kwargs,
    }


def seed_entities(make, account=ACCOUNT, accounts=None):
    for resource in ("campaigns", "adsets", "ads"):
        make(lambda r: response_for(r, account), account=account, accounts=accounts).run(resource)


def test_fact_three_id_links_and_no_customer_inference(setup):
    repo, make = setup
    seed_entities(make)
    point = resolve_facts([fact(user_id="synthetic-user")], repo, (ACCOUNT,))[0]
    assert point["account_id"] == ACCOUNT.account_id
    assert set(point["entity_versions"]) == {"ad_id", "adset_id", "campaign_id"}
    assert point["confidence"] == "deterministic_entity_match"
    assert point["attribution_eligible"]
    assert "customer_id" not in point


@pytest.mark.parametrize("field", ["ad_id", "adset_id", "campaign_id"])
def test_single_id_relation_supported(setup, field):
    repo, make = setup
    seed_entities(make)
    f = fact(meta_ad_id=None, meta_adset_id=None, meta_campaign_id=None)
    f["meta_" + field] = fact()["meta_" + field]
    point = resolve_facts([f], repo, (ACCOUNT,))[0]
    assert set(point["entity_versions"]) == {field}
    assert point["account_id"] == ACCOUNT.account_id
    assert all(point[k] is None for k in {"ad_id", "adset_id", "campaign_id"} - {field})


def test_missing_ids_names_cookies_do_not_create_relation(setup):
    repo, make = setup
    seed_entities(make)
    point = resolve_facts(
        [
            fact(
                meta_ad_id=None,
                meta_adset_id=None,
                meta_campaign_id=None,
                meta_adset_name="Synthetic entity",
                fbclid="synthetic-click",
            )
        ],
        repo,
        (ACCOUNT,),
    )[0]
    assert point["account_id"] is None and not point["issues"]
    assert not point["attribution_eligible"]


def test_multiple_accounts_isolation_and_ambiguous_link(setup):
    repo, make = setup
    second = replace(ACCOUNT, account_id="000102", connection_id="synthetic-second")
    third = replace(ACCOUNT, store_id="other-store", account_id="000103")
    accounts = (ACCOUNT, second, third)
    for account in accounts:
        seed_entities(make, account, accounts)
    assert len(repo.read("meta_ads", ACCOUNT.store_id)) == 2
    assert len(repo.read("meta_ads", third.store_id)) == 1
    ambiguous = resolve_facts([fact()], repo, accounts)[0]
    assert ambiguous["account_id"] is None and not ambiguous["attribution_eligible"]
    foreign = resolve_facts([fact(store_id="unconfigured-store")], repo, accounts)[0]
    assert foreign["account_id"] is None
    isolated = resolve_facts([fact(store_id=third.store_id)], repo, accounts)[0]
    assert isolated["account_id"] == third.account_id


def test_hierarchy_conflict_never_silently_links(setup):
    repo, make = setup
    seed_entities(make)
    point = resolve_facts([fact(meta_campaign_id="999")], repo, (ACCOUNT,))[0]
    assert point["account_id"] is None and not point["attribution_eligible"]
    assert point["evidence_type"] == "conflicting_meta_hierarchy"


def test_account_ownership_and_replay_account_enforced(setup):
    repo, make = setup
    with pytest.raises(SafeError):
        validate_accounts((ACCOUNT, replace(ACCOUNT, store_id="foreign")))
    report = make().run("ads")
    wrong = replace(ACCOUNT, account_id="000102")
    with pytest.raises(SafeError, match="meta_replay_account_configuration_mismatch"):
        make(account=wrong).replay("ads", report["run_id"])


def test_timezone_and_attribution_no_default_window():
    assert reporting_date("2026-01-02T01:00:00Z", "America/Sao_Paulo") == "2026-01-01"
    assert reporting_date("2026-01-02T01:00:00Z", "UTC") == "2026-01-02"
    with pytest.raises(TypeError):
        LastPaidTouchPolicy()
    with pytest.raises(ValueError):
        LastPaidTouchPolicy(timedelta(0), "synthetic", "paid")
    assert (
        LastPaidTouchPolicy(timedelta(hours=3), "synthetic", "paid").window.total_seconds() == 10800
    )


def test_offline_gate_and_no_deployed_config_changes():
    with pytest.raises(SafeError, match="meta_live_disabled"):
        MetaConnector(ACCOUNT, token=TOKEN, transport=None)
    tfvars = Path("infra/terraform/environments/dev.tfvars").read_text()
    assert "sha256:52732474ca926b7b1e14765cfbe14cab90fc18ae2cdd9a6a01247dd7aeffa9c5" in tfvars
    assert "meta" not in Path("src/jobs/cli.py").read_text().lower()


def test_proposed_schemas_are_separate_and_bq_date_merge_supported():
    active = json.loads(Path("infra/terraform/tables.json").read_text())
    proposed = json.loads(Path("infra/terraform/meta_tables.proposed.json").read_text())
    assert set(proposed) == META_TABLE_NAMES and not set(active) & META_TABLE_NAMES
    assert len(proposed) == 16
    for table in META_TABLE_NAMES:
        schema = json.loads(Path(f"infra/terraform/schemas/{table}.json").read_text())
        assert {c["name"]: c["type"] for c in schema} == TABLES[table].fields
        assert all(
            c["mode"] == "NULLABLE" for c in schema if c["name"] not in {"store_id", "row_key"}
        )
    sql = merge_sql("synthetic-project", "meta_insights_daily")
    assert "AS DATE)" in sql
    assert "PARTITION BY date_start" in Path("sql/core/meta_insights_daily.sql").read_text()


def test_missing_ad_is_warning_not_lost_insights(setup):
    repo, make = setup
    report = make().run("insights", INSIGHTS)
    assert report["status"] == "completed"
    quality = repo.read("quality_results", ACCOUNT.store_id)
    assert quality[0]["rule_id"] == "insights_without_ad" and quality[0]["severity"] == "warning"


@pytest.mark.parametrize("resource", ["accounts", "campaigns", "adsets", "ads", "insights"])
def test_physical_duplicate_audit_is_resource_scoped(resource):
    from src.quality.meta import DUPLICATE_RULES, duplicate_current_rows

    row = {"store_id": ACCOUNT.store_id, "row_key": "synthetic-key"}
    quality = duplicate_current_rows(
        ACCOUNT.store_id, "synthetic-run", resource, [row, row, row | {"store_id": "foreign"}]
    )
    assert len(quality) == 1 and quality[0]["failed_count"] == 1
    assert quality[0]["rule_id"] == DUPLICATE_RULES[resource]
    assert quality[0]["severity"] == "alert"


def test_api_request_insights_configuration_explicit(setup):
    _, make = setup

    def handler(request):
        params = request.url.params
        assert params["level"] == "ad" and params["time_increment"] == "1"
        assert json.loads(params["time_range"]) == {
            "since": INSIGHTS.since,
            "until": INSIGHTS.until,
        }
        assert params["action_report_time"] == "impression"
        assert json.loads(params["action_attribution_windows"]) == ["7d_click"]
        assert "landing_page_views" not in params["fields"].split(",")
        return response_for(request)

    make(handler).run("insights", INSIGHTS)


def test_repeated_next_cursor_is_detected_after_raw_capture(setup):
    repo, make = setup

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [],
                "paging": {"next": "https://example.invalid", "cursors": {"after": "same"}},
            },
        )

    with pytest.raises(SafeError, match="meta_cursor_loop"):
        make(handler).run("ads")
    assert len(repo.read("meta_raw_ads", ACCOUNT.store_id)) == 2
    assert any(
        r["pagination_error"] == "meta_cursor_loop"
        for r in repo.read("meta_raw_ads", ACCOUNT.store_id)
    )


def test_error_http_responses_preserved_scrubbed_before_failure(setup):
    repo, make = setup

    def handler(request):
        return httpx.Response(
            403, json={"error": {"message": "synthetic failure " + TOKEN, "code": 190}}
        )

    with pytest.raises(SafeError, match="meta_request_failed"):
        make(handler).run("ads")
    raw = repo.read("meta_raw_ads", ACCOUNT.store_id)[0]
    assert raw["payload"]["http_attempts"][0]["status"] == 403
    assert raw["payload"]["response"]["error"]["code"] == 190
    assert raw["payload"]["data"] == [] and TOKEN not in canonical(raw)
    assert not repo.read("meta_ads", ACCOUNT.store_id)


def test_raw_includes_transient_http_response_audit(setup):
    repo, make = setup
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"message": "synthetic outage"}})
        return response_for(request)

    make(handler).run("ads")
    attempts = repo.read("meta_raw_ads", ACCOUNT.store_id)[0]["payload"]["http_attempts"]
    assert [a["status"] for a in attempts] == [503, 200]


def test_fact_invalid_id_and_wrong_source_never_link(setup):
    repo, make = setup
    seed_entities(make)
    point = resolve_facts([fact(meta_ad_id=401)], repo, (ACCOUNT,))[0]
    assert point["account_id"] is None and "invalid_meta_id" in point["issues"]
    with pytest.raises(SafeError, match="meta_fact_lookup_scope_invalid"):
        resolve_facts([fact(source_system="foreign")], repo, (ACCOUNT,))


def test_failed_http_can_resume_same_cursor_without_losing_audit(setup):
    repo, make = setup

    def failed(request):
        return httpx.Response(503, json={"error": {"message": "synthetic outage"}})

    with pytest.raises(SafeError):
        make(failed, attempts=1).run("ads")
    cp = repo.read("sync_checkpoints", ACCOUNT.store_id)[0]
    assert cp["position"] == {} and cp["pending_raw_id"] is None
    report = make().run("ads")
    assert report["status"] == "completed"
    assert report["raw_pages_written"] == 2 and report["source_records_read"] == 1
    assert report["core_records_inserted"] == 1
