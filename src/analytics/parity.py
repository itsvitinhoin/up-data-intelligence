"""Synthetic parity preparation; cloud validation is a separate, explicit CLI action."""

import argparse
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import build
from src.analytics.materialization import CoreSnapshot
from src.analytics.schema import SCHEMAS
from src.analytics.serialization import encode_tables
from src.analytics.sql_models import compile_model
from src.utils.data import canonical, digest

PROJECT = "up-data-intelligence-dev"
LOCATION = "southamerica-east1"


def load_fixture(path: Path) -> tuple[AnalyticsPolicy, CoreSnapshot]:
    data = json.loads(path.read_text())
    return AnalyticsPolicy.from_dict(data["policy"]), CoreSnapshot(**data["core"])


def structural_check(model: str, sql: str) -> None:
    sql = re.sub(r"--[^\n]*", "", sql).strip()
    if not sql.lstrip().startswith("WITH ") or re.search(
        r"\b(CREATE|DELETE|UPDATE|INSERT|MERGE|DROP|ALTER|CALL|EXPORT)\b|;|up_raw", sql, re.I
    ):
        raise ValueError("analytics_parity_failure")
    for field, typ in SCHEMAS[model].fields.items():
        if not re.search(r"AS " + typ + r"\) AS `" + field + r"`", sql):
            raise ValueError("analytics_parity_failure")


def parameters(
    policy: AnalyticsPolicy, snapshot: CoreSnapshot | None = None
) -> list[dict[str, Any]]:
    values = {
        "store": ("STRING", policy.store_id),
        "timezone": ("STRING", policy.reporting_timezone),
        "currency": ("STRING", policy.currency),
        "policy_hash": ("STRING", policy.policy_hash),
        "history_from": ("TIMESTAMP", policy.history_from),
        "as_of": ("TIMESTAMP", policy.as_of),
        "date_from": ("DATE", policy.report_from),
        "date_to": ("DATE", policy.report_to),
        "history_complete": ("BOOL", str(policy.history_complete).lower()),
        "facts_complete": ("BOOL", str(policy.facts_complete).lower()),
    }
    if snapshot:
        for name, rows in zip(
            ("orders", "customers", "order_items", "analytics_events"),
            (snapshot.orders, snapshot.customers, snapshot.items, snapshot.events),
            strict=True,
        ):
            values["fixture_" + name] = ("STRING", canonical(rows))
    result = [
        {"name": name, "parameterType": {"type": typ}, "parameterValue": {"value": value}}
        for name, (typ, value) in values.items()
    ]
    result.append(
        {
            "name": "purchase_statuses",
            "parameterType": {"type": "ARRAY", "arrayType": {"type": "STRING"}},
            "parameterValue": {
                "arrayValues": [{"value": s} for s in policy.qualifying_order_statuses]
            },
        }
    )
    return result


def normalized(model: str, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        if set(row) != set(SCHEMAS[model].fields):
            raise ValueError("analytics_parity_failure")
        converted = {}
        for field, typ in SCHEMAS[model].fields.items():
            value = row[field]
            if value is not None:
                if typ == "NUMERIC":
                    value = Decimal(str(value))
                elif typ == "INT64":
                    value = int(value)
                elif typ == "TIMESTAMP":
                    value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                elif typ == "DATE":
                    value = str(value)
                elif typ == "BOOL" and isinstance(value, str):
                    if value.lower() not in {"true", "false"}:
                        raise ValueError("analytics_parity_failure")
                    value = value.lower() == "true"
            converted[field] = value
        key = row["row_key"]
        if key in result:
            raise ValueError("analytics_materialization_duplicate_key")
        result[key] = converted
    return result


def compare(model: str, expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> None:
    if normalized(model, expected) != normalized(model, actual):
        raise ValueError("analytics_parity_failure")


def prepare(fixture: Path, output: Path) -> dict[str, Any]:
    policy, snapshot = load_fixture(fixture)
    expected = encode_tables(
        build(
            policy.reference(),
            orders=snapshot.orders,
            customers=snapshot.customers,
            items=snapshot.items,
            events=snapshot.events,
        )["tables"]
    )
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "project": PROJECT,
        "location": LOCATION,
        "policy_hash": policy.policy_hash,
        "fixture_hash": digest(json.loads(fixture.read_text())),
        "bigquery_validated": False,
        "models": {},
    }
    for model in SCHEMAS:
        structural_check(model, compile_model(model, project=PROJECT))
        (output / f"{model}.expected.json").write_text(canonical(expected[model]) + "\n")
        for mode, source in (("dry-run", None), ("parity", snapshot)):
            sql = compile_model(model, project=PROJECT, fixtures=source is not None)
            structural_check(model, sql)
            request = {
                "query": sql,
                "useLegacySql": False,
                "parameterMode": "NAMED",
                "queryParameters": parameters(policy, source),
                "useQueryCache": False,
            }
            (output / f"{model}.{mode}.json").write_text(canonical(request) + "\n")
        manifest["models"][model] = {
            "expected_rows": len(expected[model]),
            "schema": SCHEMAS[model].fields,
        }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "dry-run", "parity"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=tuple(SCHEMAS))
    parser.add_argument("--allow-gcp", action="store_true")
    parser.add_argument("--confirm-project")
    parser.add_argument("--maximum-bytes-billed", type=int, default=1000000000)
    args = parser.parse_args()
    if args.mode != "prepare" and (
        not args.allow_gcp or args.confirm_project != PROJECT or not args.model
    ):
        parser.error("explicit --allow-gcp --confirm-project and --model required")
    prepare(args.fixture, args.output)
    if args.mode == "prepare":
        return
    # Only this explicitly authorized branch imports/constructs a cloud client.
    from google.cloud import bigquery

    request = json.loads((args.output / f"{args.model}.{args.mode}.json").read_text())
    config = bigquery.QueryJobConfig.from_api_repr({"query": request})
    assert isinstance(config, bigquery.QueryJobConfig)
    config.dry_run = args.mode == "dry-run"
    config.maximum_bytes_billed = args.maximum_bytes_billed
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    job = client.query(request["query"], job_config=config, location=LOCATION)
    if args.mode == "parity":
        actual = [dict(row.items()) for row in job.result()]
        expected = json.loads((args.output / f"{args.model}.expected.json").read_text())
        compare(args.model, expected, actual)
    print(
        json.dumps(
            {
                "model": args.model,
                "mode": args.mode,
                "bytes_processed": job.total_bytes_processed,
                "schema": [{"name": f.name, "type": f.field_type} for f in job.schema or []],
                "status": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
