"""Offline scope review of #19.3B saved plans; never applies or reads credentials.

Passing is a scope check, not IAM approval. Review the emitted table-level grant
inventory before any live apply. Existing product APIs and all schedulers are frozen.
"""

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.terraform_drift_guard import changed_paths, has_unknown, review_drift
from src.analytics.schema import SCHEMAS as ANALYTICS_TABLES
from src.bigquery.catalog import TABLES
from src.connectors.upzero.catalog_schema import TABLE_NAMES

PROJECT = "up-data-intelligence-dev"
REGION = "southamerica-east1"
EXTENSIONS = {"installation_extension_plans", "installation_extension_work_units"}
CREATIVES = {"meta_creative_insights_daily", "meta_creative_insights_daily_versions"}
NEW_TABLES = TABLE_NAMES | EXTENSIONS | CREATIVES | {"integration_operations"}
META_UPDATES = {
    "meta_live_ads",
    "meta_live_ads_versions",
    "meta_live_insights_daily",
    "meta_live_insights_daily_versions",
}
CATALOG_READS = {"catalog_observations"} | {
    "catalog_" + resource + "_versions"
    for resource in ("products", "variants", "attributes", "inventory")
}
WRITER = "projects/" + PROJECT + "/roles/upControlPlaneDataWriter_dev"


def member(name: str) -> str:
    return f"serviceAccount:{name}@{PROJECT}.iam.gserviceaccount.com"


def permissions() -> set[tuple[str, str, str]]:
    rules: set[tuple[str, str, str]] = set()

    def add(principal: str, tables: set[str], write: bool = False) -> None:
        rules.update(
            (table, member(principal), WRITER if write else "roles/bigquery.dataViewer")
            for table in tables
        )

    add(
        "up-product-read-dev",
        CATALOG_READS
        | {
            "meta_account_bindings",
            "meta_live_ads",
            "meta_creative_insights_daily",
            "quality_results",
        },
    )
    add(
        "up-product-admin-dev",
        {
            "installation_plans",
            "installation_work_units",
            "sync_checkpoints",
            "sync_runs",
            "analytics_publications",
            "analytics_store_daily",
            "analytics_funnel_daily",
        },
    )
    add("up-product-admin-dev", EXTENSIONS | {"integration_operations"}, True)
    add("up-install-orchestrator-dev", EXTENSIONS, True)
    add("up-data-health-dev", CATALOG_READS)
    for principal in ("dispatcher", "upzero", "meta", "analytics", "intelligence"):
        add(
            "up-cp-" + principal + "-dev",
            EXTENSIONS
            if principal in {"dispatcher", "intelligence"}
            else {"installation_extension_plans"},
        )
    for principal in ("upzero", "meta", "analytics"):
        add("up-cp-" + principal + "-dev", {"installation_extension_work_units"}, True)
    add("up-cp-upzero-dev", set(TABLE_NAMES), True)
    add("up-cp-meta-dev", CREATIVES, True)
    add("up-cp-analytics-dev", {"store_runtime_config"}, True)
    return rules


def job_change(before: dict, after: dict, image: str) -> None:
    names = (
        {"up-store-dispatcher", "up-data-health"}
        | {
            "up-" + pipeline + "-worker"
            for pipeline in ("upzero", "meta", "analytics", "intelligence")
        }
        | {"up-installation-orchestrator"}
        | {
            "up-installation-" + pipeline + "-worker"
            for pipeline in ("upzero", "meta", "analytics")
        }
    )
    if before.get("name") not in names or after.get("name") != before["name"]:
        raise ValueError("UNAPPROVED_JOB")
    left, right = deepcopy(before), deepcopy(after)
    old = left["template"][0]["template"][0]["containers"]
    new = right["template"][0]["template"][0]["containers"]
    if len(old) != 1 or len(new) != 1 or new[0].get("image") != image:
        raise ValueError("IMMUTABLE_IMAGE_REQUIRED")
    new[0]["image"] = old[0]["image"]
    approved = {"UP_INSTALLATION_EXTENSIONS_ENABLED", "UP_INSTALLATION_ENRICHMENT_ENABLED"}
    for container in (old[0], new[0]):
        env = container.get("env", [])
        if len({e["name"] for e in env}) != len(env):
            raise ValueError("DUPLICATE_JOB_ENV")
        if any(
            e["name"] in approved
            and (
                not set(e) <= {"name", "value", "value_source"}
                or e.get("value") != "1"
                or e.get("value_source")
            )
            for e in env
        ):
            # Terraform provider shapes have an empty value_source list, never a
            # caller-controlled secret binding disguised as an opt-in flag.
            raise ValueError("UNAPPROVED_JOB_ENV")
        container["env"] = sorted(
            (e for e in env if e["name"] not in approved), key=lambda e: e["name"]
        )
    if changed_paths(left, right):
        raise ValueError("JOB_CHANGE_NOT_IMAGE_OR_FEATURE_FLAG")


def schema_fields(fields: list[dict]) -> list[dict]:
    """BigQuery returns INTEGER for the canonical INT64 spelling, with equal semantics."""
    if len({field["name"] for field in fields}) != len(fields):
        raise ValueError("DUPLICATE_SCHEMA_FIELD")
    return [
        {**field, "type": "INT64" if field.get("type") == "INTEGER" else field.get("type")}
        for field in fields
    ]


def completion_drift(resources: list[dict]) -> dict[str, int]:
    """Only the existing production federation's opaque etag may differ here."""
    ordinary = []
    federation_etags = 0
    for resource in resources:
        change = resource.get("change", {})
        if (
            resource.get("type") == "google_service_account_iam_member"
            and resource.get("address")
            == 'google_service_account_iam_member.product_vercel_federation["production"]'
            and resource.get("mode", "managed") == "managed"
            and change.get("actions") == ["update"]
            and isinstance(change.get("before"), dict)
            and isinstance(change.get("after"), dict)
            and not has_unknown(change.get("after_unknown"))
            and changed_paths(change["before"], change["after"]) == [("etag",)]
        ):
            federation_etags += 1
        else:
            ordinary.append(resource)
    result = review_drift(ordinary)
    result["benign_drift"] += federation_etags
    return result


def check(plan: dict[str, Any], image: str) -> dict[str, Any]:
    if not re.fullmatch(
        re.escape(f"{REGION}-docker.pkg.dev/{PROJECT}/up-data-intelligence/foundation@sha256:")
        + r"[a-f0-9]{64}",
        image,
    ):
        raise ValueError("IMMUTABLE_IMAGE_REQUIRED")
    counts = {"create": 0, "update": 0}
    iam: list[dict[str, str]] = []
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        actions = change["actions"]
        if actions in (["no-op"], ["read"]):
            continue
        if actions not in (["create"], ["update"]):
            raise ValueError("DESTRUCTIVE_PLAN")
        after, before = change["after"], change.get("before")
        kind, base = resource["type"], resource["address"].split("[")[0]
        if after.get("project", PROJECT) != PROJECT:
            raise ValueError("DEV_ONLY")
        if kind == "google_bigquery_table" and base == "google_bigquery_table.tables":
            name = after.get("table_id")
            if after.get("deletion_protection") is not True:
                raise ValueError("TABLE_PROTECTION_REQUIRED")
            expected_schema = (
                json.loads(
                    (
                        Path(__file__).resolve().parents[1]
                        / "infra/terraform/schemas"
                        / f"{name}.json"
                    ).read_text()
                )
                if name in NEW_TABLES | META_UPDATES
                else None
            )
            if (
                expected_schema is None
                or json.loads(after.get("schema", "null")) != expected_schema
            ):
                raise ValueError("UNAPPROVED_SCHEMA")
            if actions == ["create"]:
                if name not in NEW_TABLES or after.get("dataset_id") != (
                    "up_analytics"
                    if name == "analytics_publications"
                    else (TABLES | ANALYTICS_TABLES)[name].dataset
                ):
                    raise ValueError("UNAPPROVED_TABLE")
            else:
                if name not in META_UPDATES or changed_paths(
                    {k: v for k, v in before.items() if k != "schema"},
                    {k: v for k, v in after.items() if k != "schema"},
                ):
                    raise ValueError("UNAPPROVED_TABLE_UPDATE")
                old, new = (
                    schema_fields(json.loads(before["schema"])),
                    schema_fields(json.loads(after["schema"])),
                )
                if not all(field in new for field in old) or any(
                    f.get("mode") != "NULLABLE" for f in new if f not in old
                ):
                    raise ValueError("NON_ADDITIVE_SCHEMA")
        elif kind == "google_bigquery_table_iam_member" and actions == ["create"]:
            name = after.get("table_id")
            if (name, after.get("member"), after.get("role")) not in permissions() or after.get(
                "dataset_id"
            ) != (
                "up_analytics"
                if name == "analytics_publications"
                else (TABLES | ANALYTICS_TABLES)[name].dataset
            ):
                raise ValueError("UNAPPROVED_TABLE_IAM")
            iam.append({k: after[k] for k in ("dataset_id", "table_id", "role", "member")})
        elif kind == "google_cloud_run_v2_job" and actions == ["update"]:
            job_change(before, after, image)
        else:
            # Preview private services/invokers and the Admin global Meta grant
            # are separately reviewed before Stage 2, never admitted implicitly.
            raise ValueError("UNAPPROVED_RESOURCE")
        counts[actions[0]] += 1
    return {
        **counts,
        "delete": 0,
        "iam": sorted(iam, key=lambda r: (r["member"], r["table_id"])),
        **completion_drift(plan.get("resource_drift", [])),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("saved_plan_json", type=Path)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check(json.loads(args.saved_plan_json.read_text()), args.image)))
    except (ValueError, KeyError, TypeError):
        raise SystemExit("DASHBOARD_COMPLETION_PLAN_REJECTED") from None
