"""Offline review of a future saved plan: additions only; explicit operational drift only."""

import json
import sys
from pathlib import Path

from scripts.terraform_drift_guard import review_drift

ALLOWED = {
    "google_service_account.control_plane",
    "google_project_iam_member.control_plane_query",
    "google_project_iam_custom_role.control_plane_writer",
    "google_bigquery_table_iam_member.control_plane",
    "google_storage_bucket_iam_member.control_plane_lease",
    "google_project_iam_member.control_plane_upzero_secret",
    "google_secret_manager_secret_iam_member.control_plane_meta_secret",
    "google_bigquery_table_iam_member.control_plane_admin",
    "google_project_iam_member.control_plane_admin_query",
    "google_bigquery_table_iam_member.control_plane_admin_read",
    "google_storage_bucket_iam_member.control_plane_admin_lease",
    "google_cloud_run_v2_job.control_plane_worker",
    "google_cloud_run_v2_job.control_plane_dispatcher",
    "google_project_iam_custom_role.control_plane_run",
    "google_project_iam_custom_role.control_plane_poll",
    "google_project_iam_member.control_plane_poll",
    "google_cloud_run_v2_job_iam_member.control_plane_run",
    "google_cloud_run_v2_job_iam_member.control_plane_schedule",
    "google_cloud_scheduler_job.control_plane",
}


def check(plan: dict) -> dict:
    adds = 0
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        if change["actions"] in (["no-op"], ["read"]):
            continue
        if change["actions"] != ["create"]:
            raise ValueError("NON_ADDITIVE_TERRAFORM_PLAN")
        base = resource["address"].split("[")[0]
        after = change["after"]
        if base == "google_bigquery_table.tables":
            if (
                resource.get("index") != "store_runtime_config"
                or after.get("dataset_id") != "up_ops"
                or after.get("table_id") != "store_runtime_config"
                or after.get("deletion_protection") is not True
            ):
                raise ValueError("UNAPPROVED_TABLE")
        elif base not in ALLOWED:
            raise ValueError("UNAPPROVED_RESOURCE")
        if resource["type"] == "google_cloud_scheduler_job" and after.get("paused") is not True:
            raise ValueError("SCHEDULER_MUST_REMAIN_PAUSED")
        adds += 1
    drift = review_drift(plan.get("resource_drift", []))
    return {"add": adds, "change": 0, "destroy": 0, **drift}


if __name__ == "__main__":
    try:
        print(json.dumps(check(json.loads(Path(sys.argv[1]).read_text()))))
    except (ValueError, KeyError):
        raise SystemExit("CONTROL_PLANE_PLAN_REJECTED") from None
