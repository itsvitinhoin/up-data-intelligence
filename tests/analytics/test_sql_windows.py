"""Structural regression checks, not a claim of executing GoogleSQL."""

import re
from pathlib import Path

import pytest

from src.analytics.schema import SCHEMAS
from src.analytics.sql_models import ROOT, compile_model


def parenthesized(sql: str, offset: int) -> str:
    depth = 0
    for index in range(offset, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return sql[offset + 1 : index]
    raise AssertionError("unbalanced SQL")


def assert_numbering_without_frame(sql: str) -> None:
    sql = re.sub(r"--[^\n]*", "", sql)
    definitions = {
        m.group(1).lower(): parenthesized(sql, m.end() - 1)
        for m in re.finditer(r"\b([a-z_]\w*)\s+AS\s*\(", sql, re.I)
    }

    def inspect(spec: str, seen: frozenset[str] = frozenset()) -> None:
        assert not re.search(r"\b(ROWS|RANGE)\b", spec, re.I), "ROW_NUMBER inherits frame"
        first = re.match(r"\s*([a-z_]\w*)", spec, re.I)
        if first and first.group(1).upper() not in {"PARTITION", "ORDER"}:
            name = first.group(1).lower()
            assert name in definitions and name not in seen, "unresolved/cyclic window"
            inspect(definitions[name], seen | {name})

    for match in re.finditer(r"\bROW_NUMBER\s*\(\s*\)\s+OVER\s*", sql, re.I):
        tail = sql[match.end() :]
        spec = parenthesized(sql, match.end()) if tail.startswith("(") else tail.split()[0]
        inspect(spec)


@pytest.mark.parametrize("model", SCHEMAS)
@pytest.mark.parametrize("fixtures", [False, True])
def test_all_compiled_models_have_safe_numbering_windows(model, fixtures):
    sql = compile_model(model, project="up-data-intelligence-dev", fixtures=fixtures)
    assert_numbering_without_frame(sql)
    if model != "analytics_funnel_daily":
        assert "ROW_NUMBER() OVER purchase_order AS purchase_number" in sql
        for field in ("created_at", "order_date"):
            assert f"FIRST_VALUE({field}) OVER purchase_first" in sql
        assert re.search(
            r"purchase_order AS \(PARTITION BY resolved_customer_id ORDER BY created_at, order_id\)",
            sql,
        )
        assert re.search(
            r"purchase_first AS \(PARTITION BY resolved_customer_id ORDER BY created_at, order_id\s+ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\)",
            sql,
        )
    if not fixtures:
        assert (ROOT / "sql/analytics/models" / f"{model}.sql").read_text() == sql


def test_reference_numbering_has_no_frame():
    assert_numbering_without_frame(Path("sql/analytics/business_reference.sql").read_text())


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ROW_NUMBER() OVER (ORDER BY x ROWS UNBOUNDED PRECEDING)",
        "SELECT ROW_NUMBER() OVER w WINDOW w AS (ORDER BY x RANGE UNBOUNDED PRECEDING)",
        "SELECT ROW_NUMBER() OVER child WINDOW base AS (ORDER BY x ROWS UNBOUNDED PRECEDING), child AS (base)",
        "SELECT ROW_NUMBER() OVER (base ORDER BY x) WINDOW base AS (ROWS UNBOUNDED PRECEDING)",
    ],
)
def test_guard_rejects_direct_and_inherited_frames(sql):
    with pytest.raises(AssertionError, match="inherits frame"):
        assert_numbering_without_frame(sql)
