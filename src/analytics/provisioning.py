"""Promote exactly the eight reviewed schemas to Terraform, never runtime ingestion."""

import json
from pathlib import Path
from typing import Any

from src.analytics.schema import SCHEMAS

ACTIVE_ANALYTICS_TABLES = frozenset(SCHEMAS) | {"analytics_publications"}


def promote_tables(root: Path = Path(".")) -> dict[str, Any]:
    proposed = root / "infra/terraform/analytics_proposed"
    active = root / "infra/terraform/schemas"
    manifest = json.loads((proposed / "tables.json").read_text())
    if set(manifest) != set(SCHEMAS):
        raise ValueError("unexpected_analytics_proposal")
    manifest["analytics_publications"] = {
        "dataset": "up_analytics",
        "partition": None,
        "cluster": ["store_id", "policy_hash", "record_kind"],
    }
    payloads = {}
    for name, spec in manifest.items():
        body = (proposed / "schemas" / f"{name}.json").read_bytes()
        fields = json.loads(body)
        names = [f["name"] for f in fields]
        if (
            spec["dataset"] != "up_analytics"
            or len(names) != len(set(names))
            or any(f["mode"] not in {"NULLABLE", "REQUIRED"} for f in fields)
            or any(
                f["type"] not in {"STRING", "TIMESTAMP", "DATE", "BOOL", "INT64", "NUMERIC", "JSON"}
                for f in fields
            )
            or not set(spec["cluster"]) <= set(names)
            or (spec["partition"] is not None and spec["partition"] not in names)
        ):
            raise ValueError("invalid_analytics_schema")
        if name in SCHEMAS:
            expected = SCHEMAS[name]
            if (
                {f["name"]: f["type"] for f in fields} != expected.fields
                or spec["partition"] != expected.partition
                or spec["cluster"] != list(expected.cluster)
            ):
                raise ValueError("analytics_proposal_schema_drift")
        payloads[name] = body
    active.mkdir(parents=True, exist_ok=True)
    for name, body in payloads.items():
        (active / f"{name}.json").write_bytes(body)
    return dict(manifest)
