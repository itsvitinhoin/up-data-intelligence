"""Offline saved-plan safety review. No credentials, subprocesses or GCP clients."""

import json
import sys
from pathlib import Path

from scripts.terraform_drift_guard import review_drift
from src.intelligence.live.schema import META_ACTIVE, SCHEMAS

ALLOWED = {
    "google_service_account.change16",
    "google_project_iam_member.change16_jobs",
    "google_bigquery_table_iam_member.change16_meta_write",
    "google_bigquery_table_iam_member.change16_read",
    "google_bigquery_table_iam_member.change16_write",
    "google_bigquery_table_iam_member.change16_dashboard_read",
    "google_secret_manager_secret.change16_meta",
    "google_secret_manager_secret_iam_member.change16_meta",
    "google_storage_bucket_iam_member.change16_lease",
    "google_cloud_run_v2_job.change16",
}


def check(plan: dict) -> dict:
    adds = 0
    for r in plan.get("resource_changes", []):
        actions = r["change"]["actions"]
        if actions in (["no-op"], ["read"]):
            continue
        if actions != ["create"]:
            raise ValueError("NON_ADDITIVE_TERRAFORM_PLAN")
        base = r["address"].split("[")[0]
        if base == "google_bigquery_table.tables":
            if r.get("index") not in META_ACTIVE | set(SCHEMAS):
                raise ValueError("UNAPPROVED_TABLE")
            if r["change"]["after"].get("deletion_protection") is not True:
                raise ValueError("TABLE_PROTECTION_REQUIRED")
        elif base not in ALLOWED:
            raise ValueError("UNAPPROVED_RESOURCE")
        adds += 1
    drift = review_drift(plan.get("resource_drift", []))
    return {"add": adds, "change": 0, "destroy": 0, **drift}


if __name__ == "__main__":
    try:
        print(json.dumps(check(json.loads(Path(sys.argv[1]).read_text()))))
    except (ValueError, KeyError):
        raise SystemExit("CHANGE16_PLAN_REJECTED") from None
