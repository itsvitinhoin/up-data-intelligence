import json
from copy import deepcopy

import pytest

from src.connectors.meta.period import PeriodInsights, normalize_period
from src.connectors.meta.purchase_reporting import PurchaseCertificate
from src.dashboard.contracts import ReadError
from src.dashboard.meta_period import MetaPeriodReader
from src.utils.data import digest
from tests.integration.test_meta_period_ingestion import ACCOUNT, REPORT, SOURCE

CERT = PurchaseCertificate(
    ACCOUNT,
    REPORT.action_report_time,
    REPORT.action_attribution_windows,
    REPORT.purchase_action_type,
    "synthetic source proof",
)
START, END = "2026-09-01", "2026-10-01"


def evidence():
    checkpoints, runs, metrics = [], [], []
    for level in ("account", "campaign", "adset", "ad"):
        spec = PeriodInsights(
            REPORT.since,
            REPORT.until,
            REPORT.action_report_time,
            REPORT.action_attribution_windows,
            REPORT.purchase_action_type,
            level=level,
        )
        filters = {"account": ACCOUNT.snapshot(), "insights": spec.snapshot()}
        key = digest(["meta", "insights", filters, 100])
        cp = dict(
            store_id=ACCOUNT.store_id,
            connection_id=ACCOUNT.connection_id,
            resource="meta_period_insights",
            plan_key=key,
            filters=filters,
            status="complete",
            pending_raw_id=None,
            run_id=key,
            mode="sync",
            updated_at="2026-10-01T03:06:00Z",
        )
        run = dict(
            store_id=ACCOUNT.store_id,
            source="meta",
            resource="meta_period_insights",
            plan_key=key,
            run_id=key,
            status="completed",
            core_records_failed=0,
            core_records_processed=1,
            mode="sync",
            started_at="2026-10-01T03:00:00Z",
            finished_at="2026-10-01T03:06:00Z",
        )
        checkpoints.append({"value": json.dumps(cp)})
        runs.append({"value": json.dumps(run)})
        ids = {"campaign_id": "200", "adset_id": "300", "ad_id": "400"}
        selected = {"account": 0, "campaign": 1, "adset": 2, "ad": 3}[level]
        source = {**SOURCE, **{k: v for k, v in list(ids.items())[:selected]}}
        row = normalize_period(source, ACCOUNT, spec, "2026-10-01T03:05:00Z")
        for entity in ("campaign", "adset", "ad"):
            row[entity] = dict(matches=1, name="Synthetic", status="ACTIVE")
        metrics.append(row)
    return dict(
        bindings=[
            dict(
                store_id=ACCOUNT.store_id,
                account_id=ACCOUNT.account_id,
                connection_id=ACCOUNT.connection_id,
                api_version=ACCOUNT.api_version,
                source_timezone=ACCOUNT.timezone,
                currency=ACCOUNT.currency,
            )
        ],
        checkpoints=checkpoints,
        runs=runs,
        metrics=metrics,
        daily=[],
    )


def read(e):
    return MetaPeriodReader.project_rows(e, ACCOUNT, CERT, START, END)


def test_period_platform_values_are_decimal_and_never_commercial_attribution():
    result = read(evidence())
    summary = result["summary"]
    assert summary["spend"] == "30.10" and summary["meta_reported_purchase_value"] == "100.10"
    assert summary["reach"] == 800 and summary["frequency"] == "1.25"
    assert summary["cpa"] == "15.05"
    assert result["basis"] == "official_meta_all_days"
    assert len(result["campaigns"]) == len(result["adsets"]) == len(result["ads"]) == 1
    assert not any("requested" in k or "fulfilled" in k or "attributed" in k for k in summary)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_store",
        "wrong_account",
        "binding_duplicate",
        "checkpoint_duplicate",
        "run_foreign",
        "run_failed",
        "pending_raw",
        "nonterminal",
        "window",
        "duplicate_grain",
        "float_money",
        "missing_level",
        "catalog_duplicate",
    ],
)
def test_period_evidence_is_fail_closed(mutation):
    e = evidence()
    if mutation == "wrong_store":
        e["metrics"][0]["store_id"] = "foreign"
    elif mutation == "wrong_account":
        e["bindings"][0]["account_id"] = "999"
    elif mutation == "binding_duplicate":
        e["bindings"].append(deepcopy(e["bindings"][0]))
    elif mutation == "checkpoint_duplicate":
        e["checkpoints"].append(deepcopy(e["checkpoints"][0]))
    elif mutation in {"run_foreign", "run_failed"}:
        r = json.loads(e["runs"][0]["value"])
        r["store_id" if mutation == "run_foreign" else "core_records_failed"] = (
            "foreign" if mutation == "run_foreign" else 1
        )
        e["runs"][0]["value"] = json.dumps(r)
    elif mutation in {"pending_raw", "nonterminal"}:
        cp = json.loads(e["checkpoints"][0]["value"])
        cp["pending_raw_id" if mutation == "pending_raw" else "status"] = "pending"
        e["checkpoints"][0]["value"] = json.dumps(cp)
    elif mutation == "window":
        e["metrics"][0]["date_start"] = "2026-09-02"
    elif mutation == "duplicate_grain":
        e["metrics"].append(deepcopy(e["metrics"][0]))
    elif mutation == "float_money":
        e["metrics"][0]["spend"] = 30.1
    elif mutation == "missing_level":
        e["checkpoints"].pop()
    elif mutation == "catalog_duplicate":
        e["metrics"][1]["campaign"]["matches"] = 2
    with pytest.raises(ReadError):
        read(e)


def test_period_null_purchase_evidence_and_reach_preserved():
    e = evidence()
    e["metrics"][0]["meta_reported_purchases"] = None
    e["metrics"][0]["meta_reported_purchase_value"] = None
    e["metrics"][0]["reach"] = None
    r = read(e)["summary"]
    assert r["cpa"] is None and r["roas"] is None and r["reach"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "backfill"),
        ("core_records_processed", 2),
        ("finished_at", None),
        ("started_at", "2026-10-02T00:00:00Z"),
    ],
)
def test_period_completed_run_contract_is_required(field, value):
    e = evidence()
    r = json.loads(e["runs"][0]["value"])
    r[field] = value
    e["runs"][0]["value"] = json.dumps(r)
    with pytest.raises(ReadError):
        read(e)


def test_period_inflight_new_observation_is_not_certified_by_old_run():
    e = evidence()
    e["metrics"][0]["observed_at"] = "2026-10-02T00:00:00Z"
    with pytest.raises(ReadError, match="meta_period_refresh_incomplete"):
        read(e)


def test_period_negative_platform_money_rejected():
    e = evidence()
    e["metrics"][0]["spend"] = "-0.01"
    with pytest.raises(ReadError, match="meta_period_metrics_invalid"):
        read(e)


def daily_evidence():
    from src.connectors.meta.config import Insights

    e = evidence()
    report = Insights(
        START,
        "2026-09-30",
        CERT.action_report_time,
        CERT.attribution_windows,
        CERT.purchase_action_type,
    )
    key = digest(["daily", START])
    cp = dict(
        store_id=ACCOUNT.store_id,
        connection_id=ACCOUNT.connection_id,
        resource="meta_creative_insights_daily",
        filters={"account": ACCOUNT.snapshot(), "insights": report.snapshot()},
        plan_key=key,
        run_id=key,
        status="complete",
        pending_raw_id=None,
    )
    run = dict(
        store_id=ACCOUNT.store_id,
        source="meta",
        resource=cp["resource"],
        plan_key=key,
        run_id=key,
        status="completed",
        core_records_failed=0,
    )
    e["checkpoints"].append({"value": json.dumps(cp)})
    e["runs"].append({"value": json.dumps(run)})
    e["daily"] = [
        dict(
            date=START,
            spend="0.30",
            meta_reported_purchases="2",
            meta_reported_purchase_value="1.00",
            row_count=2,
            identities=2,
            grains=2,
            invalid=0,
        )
    ]
    return e


def test_daily_series_uses_selected_family_and_backend_decimal_roas():
    r = read(daily_evidence())
    assert r["series"][0]["roas"] == "3.333333333333333333333333333"
    assert r["series"][0]["meta_reported_purchase_value"] == "1.00"


def test_daily_duplicate_cannot_compensate_aggregates():
    e = daily_evidence()
    e["daily"][0]["identities"] = 1
    with pytest.raises(ReadError, match="meta_period_daily_invalid"):
        read(e)


def test_daily_missing_coverage_keeps_series_unavailable_not_zero():
    assert read(evidence())["series"] is None


def test_period_read_is_one_parameterized_publication_snapshot_query():
    class Reader:
        def __init__(self):
            self.calls = []

        def query(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return [evidence()]

    reader = Reader()
    result = MetaPeriodReader(
        "synthetic-project",
        reader,
        ACCOUNT.store_id,
        "safe-request",
        "2026-10-02T00:00:00Z",
        (CERT,),
    ).read(START, END)
    assert result["summary"]["reach"] is not None
    assert len(reader.calls) == 1
    query, context = reader.calls[0]
    assert query.name == "meta_period"
    assert context["store_id"] == ACCOUNT.store_id
    assert query.parameters["store"] == ("STRING", ACCOUNT.store_id)
    assert query.parameters["from"] == ("DATE", START)
    assert query.parameters["to"] == ("DATE", END)
    assert query.parameters["action"] == ("STRING", CERT.purchase_action_type)
    assert START not in query.sql and END not in query.sql
    assert CERT.purchase_action_type not in query.sql
    assert "AS i FOR SYSTEM_TIME AS OF @read_at" in query.sql
    assert "AS b FOR SYSTEM_TIME AS OF @read_at" in query.sql
    assert "FOR SYSTEM_TIME AS OF @read_at i" not in query.sql
    assert "SUM(reach)" not in query.sql and "SUM(frequency)" not in query.sql
