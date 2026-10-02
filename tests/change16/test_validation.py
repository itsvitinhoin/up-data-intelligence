"""Offline semantic parity with frozen legacy SQL, plus BigQuery shape guards.

SQLite evaluates both queries over identical synthetic tables. Small adapters
provide COUNTIF/ANY_VALUE/IF/SAFE_DIVIDE and remove time travel for local testing;
this is not a BigQuery dry-run or certification of its NUMERIC implementation.
"""

import json
import re
import sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.bigquery.catalog import TABLES
from src.intelligence.live.materialize import build
from src.intelligence.live.schema import PUBLICATION, SCHEMAS
from src.intelligence.live.validation import sql, validate
from src.utils.data import canonical
from tests.change16.test_stack import fixture16

PROJECT = "synthetic-dev"
REFERENCE = Path("tests/fixtures/change16/validation_correlated_reference.sql").read_text()
CTES = {
    "performance",
    "lifetime_orders",
    "influenced_order_counts",
    "distinct_influenced_orders",
    "influenced_finance",
    "customer_profile",
    "meta_insights",
    "meta_spend",
}


class CountIf:
    def __init__(self):
        self.count = 0

    def step(self, value):
        self.count += int(bool(value))

    def finalize(self):
        return self.count


class AnyValue:
    def __init__(self):
        self.value = None

    def step(self, value):
        if self.value is None and value is not None:
            self.value = value

    def finalize(self):
        return self.value


@pytest.fixture
def case():
    policy, snapshot, args = fixture16("synthetic-brand")
    artifact = build(policy, snapshot, **args)
    p = artifact["publication"]
    return SimpleNamespace(
        policy=policy,
        tables=deepcopy(artifact["tables"]),
        meta=deepcopy(args["meta_insights"]),
        touchpoint_count=None,
        params={
            "store": policy.store_id,
            "policy": policy.policy_hash,
            "generation": p["generation"],
            "account": p["meta_account_id"],
            "configuration": p["meta_configuration_hash"],
            "snapshot": p["source_snapshot_at"],
            "from": policy.report_from,
            "to": policy.report_to,
        },
    )


def summary(case):
    return case.tables["analytics_performance_summary"][0]


def orders(case):
    return case.tables["analytics_customer_orders_summary"]


def evaluate(case, query):
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.create_aggregate("COUNTIF", 1, CountIf)
        db.create_aggregate("ANY_VALUE", 1, AnyValue)
        db.create_function("IF", 3, lambda condition, yes, no: yes if condition else no)
        db.create_function(
            "SAFE_DIVIDE",
            2,
            lambda x, y: None if x is None or y is None or y == 0 else x / y,
        )
        specs = {k: v for k, v in SCHEMAS.items() if k != PUBLICATION}
        specs["meta_live_insights_daily"] = TABLES["meta_live_insights_daily"]
        for name, spec in specs.items():
            table = f"`{PROJECT}.{spec.dataset}.{name}`"
            fields = ",".join(
                f"`{field}` {'NUMERIC' if typ == 'NUMERIC' else 'INTEGER' if typ in {'INT64', 'BOOL'} else 'TEXT'}"
                for field, typ in spec.fields.items()
            )
            db.execute(f"CREATE TABLE {table} ({fields})")
            if name == "analytics_paid_touchpoints" and case.touchpoint_count is not None:
                db.execute(
                    f"WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq WHERE n<@n) "
                    f"INSERT INTO {table}(row_key,store_id,policy_hash,generation) "
                    "SELECT CAST(n AS TEXT),@store,@policy,@generation FROM seq",
                    {**case.params, "n": case.touchpoint_count},
                )
                continue
            rows = case.meta if name == "meta_live_insights_daily" else case.tables[name]
            for row in rows:
                row = json.loads(canonical(row))
                values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in row.values()]
                db.execute(
                    f"INSERT INTO {table} ({','.join('`' + k + '`' for k in row)}) "
                    f"VALUES ({','.join('?' for _ in row)})",
                    values,
                )
        query = query.replace("FOR SYSTEM_TIME AS OF @snapshot", "")
        rows = [dict(row) for row in db.execute(query, case.params)]
        assert len(rows) == len({r["invariant"] for r in rows}) == len(SCHEMAS) - 1 + 7
        assert all(type(r["failures"]) is int and r["failures"] >= 0 for r in rows)
        return {r["invariant"]: r["failures"] for r in rows}


def parity(case):
    before = evaluate(case, REFERENCE)
    after = evaluate(case, sql(PROJECT))
    assert after == before
    return after


def no_failures(case):
    result = parity(case)
    assert not any(result.values()), result
    return result


def clone_with_new_key(row):
    return {**deepcopy(row), "row_key": "synthetic-extra-" + row["row_key"]}


def zero_influence(case):
    for row in orders(case):
        row["paid_media_influenced"] = None
    case.tables["analytics_customer_paid_influence"] = []
    case.tables["analytics_order_paid_influence"] = []
    case.tables["analytics_campaign_customer_performance"] = []
    case.tables["analytics_campaign_order_performance"] = []
    summary(case).update(
        influenced_customers=0,
        influenced_orders=0,
        requested_revenue_influenced="0",
        fulfilled_revenue_influenced="0",
        influence_complete=False,
        history_complete=False,
        new_customers_influenced=None,
        cac_new_customer=None,
        roas_requested=None,
        roas_fulfilled=None,
    )


def test_valid_publication_with_partial_history_matches_all_legacy_invariants(case):
    assert summary(case)["history_complete"] is False
    no_failures(case)


@pytest.mark.parametrize("name", [n for n in SCHEMAS if n != PUBLICATION])
def test_duplicate_row_key_is_still_detected_for_every_model(case, name):
    assert case.tables[name]
    case.tables[name].append(deepcopy(case.tables[name][0]))
    assert parity(case)[name + ":duplicate_key"] == 1


@pytest.mark.parametrize(
    "missing", ["absent", "foreign_store", "foreign_policy", "foreign_generation", "null_id"]
)
def test_timeline_foreign_customer_isolated_and_null_id_preserved(case, missing):
    row = case.tables["analytics_customer_timeline"][0]
    if missing == "null_id":
        row["customer_id"] = None
    else:
        matches = [
            p
            for p in case.tables["analytics_customer_360_profile"]
            if p["customer_id"] == row["customer_id"]
        ]
        assert matches
        case.tables["analytics_customer_360_profile"] = [
            p for p in case.tables["analytics_customer_360_profile"] if p not in matches
        ]
        if missing != "absent":
            field, value = {
                "foreign_store": ("store_id", "synthetic-other"),
                "foreign_policy": ("policy_hash", "synthetic-other"),
                "foreign_generation": ("generation", 99),
            }[missing]
            case.tables["analytics_customer_360_profile"].append({**matches[0], field: value})
    assert parity(case)["timeline:foreign_customer"] >= 1


@pytest.mark.parametrize(
    "name,rule",
    [
        ("analytics_campaign_order_performance", "campaign:duplicate_order"),
        ("analytics_order_paid_influence", "influence:duplicate_order_campaign"),
    ],
)
def test_duplicate_order_campaign_grain_detected_even_with_unique_row_keys(case, name, rule):
    case.tables[name].append(clone_with_new_key(case.tables[name][0]))
    failures = parity(case)
    assert failures[rule] == 1
    assert failures[name + ":duplicate_key"] == 0
    assert failures["summary:distinct_order_finance"] == 0


def test_duplicate_meta_campaign_day_configuration_detected(case):
    case.meta.append(clone_with_new_key(case.meta[0]))
    assert parity(case)["meta:duplicate_campaign_day_config"] == 1


def test_meta_spend_mismatch_detected(case):
    summary(case)["meta_spend"] = "999"
    assert parity(case)["summary:meta_spend"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_id", "synthetic-other"),
        ("account_id", "synthetic-other"),
        ("configuration_hash", "synthetic-other"),
        ("date_start", "2026-08-31"),
        ("date_start", "2026-09-28"),
    ],
)
def test_foreign_meta_and_outside_window_do_not_change_authorized_spend(case, field, value):
    case.meta.append({**clone_with_new_key(case.meta[0]), field: value, "spend": "999"})
    no_failures(case)


def test_meta_null_spend_is_not_zero(case):
    case.meta[0]["spend"] = None
    summary(case).update(
        meta_spend=None, influence_complete=False, roas_requested=None, roas_fulfilled=None
    )
    no_failures(case)
    summary(case)["meta_spend"] = "0"
    assert parity(case)["summary:meta_spend"] == 1


def test_summary_influenced_customer_count_cannot_exceed_order_count(case):
    summary(case)["influenced_customers"] = summary(case)["influenced_orders"] + 1
    assert parity(case)["summary:dedupe_revenue_null_roas"] == 1


@pytest.mark.parametrize("field", ["new_customers_influenced", "cac_new_customer"])
def test_partial_history_prohibits_known_new_customer_or_cac(case, field):
    summary(case).update(history_complete=False)
    summary(case)[field] = 1
    assert parity(case)["summary:dedupe_revenue_null_roas"] == 1


@pytest.mark.parametrize("field", ["roas_requested", "roas_fulfilled"])
def test_incomplete_influence_prohibits_known_roas(case, field):
    summary(case).update(influence_complete=False, roas_requested=None, roas_fulfilled=None)
    summary(case)[field] = "0"
    assert parity(case)["summary:dedupe_revenue_null_roas"] == 1


def test_summary_order_count_must_equal_distinct_lifetime_true_orders(case):
    summary(case)["influenced_orders"] += 1
    assert parity(case)["summary:dedupe_revenue_null_roas"] == 1


@pytest.mark.parametrize("field", ["requested_revenue_influenced", "fulfilled_revenue_influenced"])
def test_distinct_order_finance_mismatch_detected(case, field):
    summary(case)[field] = "999"
    assert parity(case)["summary:distinct_order_finance"] == 1


def test_campaign_participation_and_duplicate_order_rows_do_not_double_store_revenue(case):
    # A second participating campaign is a different campaign/order grain. Its
    # own revenue is never added to the store aggregate; order summary is deduped.
    for name in ("analytics_campaign_order_performance", "analytics_order_paid_influence"):
        row = clone_with_new_key(case.tables[name][0])
        row["campaign_id"] = "synthetic-second-campaign"
        case.tables[name].append(row)
    lifetime = next(r for r in orders(case) if r["influence_scope"] == "LIFETIME")
    orders(case).append(clone_with_new_key(lifetime))
    no_failures(case)
    summary(case)["requested_revenue_influenced"] = "200"
    assert parity(case)["summary:distinct_order_finance"] == 1


@pytest.mark.parametrize(
    "field,summary_field",
    [
        ("requested_total", "requested_revenue_influenced"),
        ("fulfilled_total", "fulfilled_revenue_influenced"),
    ],
)
def test_null_order_total_propagates_independently_and_never_becomes_zero(
    case, field, summary_field
):
    for row in orders(case):
        if row["influence_scope"] == "LIFETIME":
            row[field] = None
    summary(case).update(influence_complete=False, roas_requested=None, roas_fulfilled=None)
    summary(case)[summary_field] = None
    no_failures(case)
    summary(case)[summary_field] = "0"
    assert parity(case)["summary:distinct_order_finance"] == 1


@pytest.mark.parametrize(
    "roas,failures",
    [
        ("20.000000000", 0),
        ("20.0000000001", 0),
        ("20.000000010", 1),
        ("21", 1),
    ],
)
def test_complete_influence_roas_uses_existing_tolerance(case, roas, failures):
    summary(case).update(influence_complete=True, roas_requested=roas)
    assert parity(case)["summary:distinct_order_finance"] == failures


@pytest.mark.parametrize("touchpoint_count", [None, 163175])
def test_zero_influenced_orders_with_observed_touchpoints_is_valid(case, touchpoint_count):
    zero_influence(case)
    case.touchpoint_count = touchpoint_count
    no_failures(case)
    assert summary(case)["roas_requested"] is summary(case)["roas_fulfilled"] is None


def test_no_orders_or_meta_rows_have_singleton_zero_aggregates(case):
    zero_influence(case)
    case.tables["analytics_customer_orders_summary"] = []
    case.meta = []
    summary(case)["meta_spend"] = "0"
    no_failures(case)


@pytest.mark.parametrize("field", ["history_complete", "influence_complete"])
def test_unknown_completeness_is_not_reinterpreted_as_false(case, field):
    summary(case)[field] = None
    no_failures(case)


def test_generated_query_has_independent_ctes_and_no_correlated_subquery():
    query = sql(PROJECT)
    assert query.lstrip().startswith("WITH")
    assert set(re.findall(r"\b(\w+) AS \(", query)) == CTES
    assert "FROM performance s CROSS JOIN influenced_order_counts c" in query
    assert "FROM performance s CROSS JOIN influenced_finance v" in query
    assert "FROM performance s CROSS JOIN meta_spend m" in query
    assert "LEFT JOIN customer_profile p ON p.store_id=t.store_id" in query
    assert "AND p.customer_id IS NULL" in query
    assert "FOR SYSTEM_TIME AS OF @snapshot" in query
    assert "COUNT(DISTINCT order_id) influenced_orders FROM lifetime_orders" in query
    assert "ANY_VALUE(requested_total)" in query and "ANY_VALUE(fulfilled_total)" in query
    assert "COUNTIF(requested_total IS NULL)>0,NULL,COALESCE(SUM(requested_total),0)" in query
    assert "COUNTIF(fulfilled_total IS NULL)>0,NULL,COALESCE(SUM(fulfilled_total),0)" in query
    assert ">0.000000001" in query
    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE)\b", query)
    assert not re.search(r"\b(?:NOT )?EXISTS\s*\(", query)

    assert_no_outer_alias_in_nested_select(query)


def assert_no_outer_alias_in_nested_select(query):
    masked = re.sub(r"--[^\n]*|`[^`]*`|'[^']*'", " ", query)
    for opening in re.finditer(r"\(\s*SELECT\b", masked, re.I):
        depth = 1
        for bracket in re.finditer(r"[()]", masked[opening.end() :]):
            depth += 1 if bracket.group() == "(" else -1
            if depth == 0:
                end = opening.end() + bracket.end()
                break
        else:
            raise AssertionError("unbalanced_SQL_subquery")
        # CTEs and duplicate-key subqueries intentionally contain no references
        # to the summary/timeline aliases. Inspect balanced blocks, including
        # nested aggregates, so an outer reference cannot hide behind a FROM.
        assert not re.search(r"\b[st]\.", masked[opening.start() : end])


def test_dialect_guard_rejects_frozen_bigquery_correlated_aggregate_regression():
    with pytest.raises(AssertionError):
        assert_no_outer_alias_in_nested_select(REFERENCE)


def test_validator_response_and_failure_contract_unchanged(case):
    results = [{"invariant": k, "failures": v} for k, v in no_failures(case).items()]
    transport = SimpleNamespace(
        client=object(),
        config=SimpleNamespace(project=PROJECT, location="southamerica-east1"),
        query=Mock(return_value=(results, None)),
    )
    service = Mock()
    service.overview.return_value = {"data": {}}
    service.customers.return_value = {"data": [], "pagination": {"has_more": False}}
    service.intelligence_head = {
        **case.params,
        "meta_account_id": case.params["account"],
        "meta_configuration_hash": case.params["configuration"],
        "source_snapshot_at": case.params["snapshot"],
    }
    with (
        patch("src.intelligence.live.validation.BigQueryReadSession"),
        patch(
            "src.intelligence.live.validation.IntelligenceDashboardService", return_value=service
        ),
    ):
        assert validate(transport, case.policy, tenant="synthetic-tenant") == {
            "status": "completed",
            "generation": 1,
            "invariants_checked": len(results),
        }
        params = {p.name: p.value for p in transport.query.call_args.args[1]}
        assert (
            params["store"] == case.policy.store_id and params["policy"] == case.policy.policy_hash
        )
        assert params["generation"] == 1
        results[0]["failures"] = 1
        with pytest.raises(ValueError, match="^intelligence_invariant_failed$"):
            validate(transport, case.policy, tenant="synthetic-tenant")


def test_one_unknown_order_among_known_orders_propagates_null(case):
    lifetime = next(r for r in orders(case) if r["influence_scope"] == "LIFETIME")
    orders(case).append(
        {
            **clone_with_new_key(lifetime),
            "order_id": "synthetic-unknown-order",
            "requested_total": None,
        }
    )
    summary(case).update(
        influenced_orders=2,
        requested_revenue_influenced=None,
        fulfilled_revenue_influenced="160",
        influence_complete=False,
        roas_requested=None,
        roas_fulfilled=None,
    )
    no_failures(case)
    summary(case)["requested_revenue_influenced"] = "100"
    assert parity(case)["summary:distinct_order_finance"] == 1


@pytest.mark.parametrize("spend,roas", [("0", None), (None, None), ("5", None)])
def test_roas_null_and_undefined_division_keep_existing_three_valued_semantics(case, spend, roas):
    case.meta[0]["spend"] = spend
    summary(case).update(meta_spend=spend, influence_complete=True, roas_requested=roas)
    no_failures(case)
