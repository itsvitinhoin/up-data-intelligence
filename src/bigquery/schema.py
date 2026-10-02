"""Generate reviewed SQL and Terraform schemas, without connecting to GCP."""

import json
from pathlib import Path
from typing import Any

from src.analytics.provisioning import promote_tables
from src.bigquery.catalog import META_TABLE_NAMES, TABLES
from src.control_plane.model import REGISTRY


def generate() -> None:
    folder = Path("infra/terraform/schemas")
    folder.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    meta_manifest: dict[str, Any] = {}
    for name, spec in TABLES.items():
        required = {"row_key", "store_id"} | ({"status", "revision"} if name == REGISTRY else set())
        if name == "workspace_store_bindings":
            required |= {"tenant_id", "brand_id", "workspace_operation_id", "operation"}
        if name == "onboarding_operations":
            required |= {
                "operation_id",
                "idempotency_key",
                "admin_subject_hash",
                "request_hash",
                "tenant_id",
                "status",
                "current_step",
                "revision",
            }
        fields = [
            {
                "name": k,
                "type": t,
                "mode": "REQUIRED" if k in required else "NULLABLE",
            }
            for k, t in spec.fields.items()
        ]
        (folder / (name + ".json")).write_text(json.dumps(fields, indent=2) + "\n")
        target_manifest = meta_manifest if name in META_TABLE_NAMES else manifest
        if name.startswith("meta_live_"):
            target_manifest = manifest
        target_manifest[name] = {
            "dataset": spec.dataset,
            "partition": spec.partition,
            "cluster": list(spec.cluster),
        }
        sql = "CREATE TABLE IF NOT EXISTS `${project_id}." + spec.dataset + "." + name + "` (\n"
        sql += (
            ",\n".join(
                f"  `{k}` {t}" + (" NOT NULL" if k in required else "")
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
    manifest.update(promote_tables())
    Path("infra/terraform/tables.json").write_text(json.dumps(manifest, indent=2) + "\n")
    from src.intelligence.live.schema import promote

    promote()
    Path("infra/terraform/meta_tables.proposed.json").write_text(
        json.dumps(
            {
                k: v
                for k, v in meta_manifest.items()
                if k not in manifest
                and not k.startswith("meta_raw_")
                and k != "meta_account_bindings"
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    generate()
