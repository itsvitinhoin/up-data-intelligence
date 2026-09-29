"""Generate reviewed SQL and Terraform schemas, without connecting to GCP."""

import json
from pathlib import Path
from typing import Any

from src.bigquery.catalog import META_TABLE_NAMES, TABLES


def generate() -> None:
    folder = Path("infra/terraform/schemas")
    folder.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    meta_manifest: dict[str, Any] = {}
    for name, spec in TABLES.items():
        fields = [
            {
                "name": k,
                "type": t,
                "mode": "REQUIRED" if k in {"row_key", "store_id"} else "NULLABLE",
            }
            for k, t in spec.fields.items()
        ]
        (folder / (name + ".json")).write_text(json.dumps(fields, indent=2) + "\n")
        target_manifest = meta_manifest if name in META_TABLE_NAMES else manifest
        target_manifest[name] = {
            "dataset": spec.dataset,
            "partition": spec.partition,
            "cluster": list(spec.cluster),
        }
        sql = "CREATE TABLE IF NOT EXISTS `${project_id}." + spec.dataset + "." + name + "` (\n"
        sql += (
            ",\n".join(
                f"  `{k}` {t}" + (" NOT NULL" if k in {"row_key", "store_id"} else "")
                for k, t in spec.fields.items()
            )
            + "\n)"
        )
        if spec.partition:
            expression = (
                spec.partition
                if spec.fields[spec.partition] == "DATE"
                else f"DATE({spec.partition})"
            )
            sql += f"\nPARTITION BY {expression}"
        if spec.cluster:
            sql += "\nCLUSTER BY " + ", ".join(spec.cluster)
        path = Path(
            "sql/raw"
            if spec.dataset == "up_raw"
            else "sql/core"
            if spec.dataset == "up_core"
            else "sql/ops"
        )
        path.mkdir(parents=True, exist_ok=True)
        (path / (name + ".sql")).write_text(sql + ";\n")
    Path("infra/terraform/tables.json").write_text(json.dumps(manifest, indent=2) + "\n")
    Path("infra/terraform/meta_tables.proposed.json").write_text(
        json.dumps(meta_manifest, indent=2) + "\n"
    )


if __name__ == "__main__":
    generate()
