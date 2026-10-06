"""A future plan cannot enable cron, widen IAM, alter source identity or capacity."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.dashboard_completion_plan_guard import PROJECT, check, member

IMAGE = (
    f"southamerica-east1-docker.pkg.dev/{PROJECT}/up-data-intelligence/foundation@sha256:"
    + "a" * 64
)


def plan(resource_type, before, after, actions=None):
    return {
        "resource_changes": [
            {
                "type": resource_type,
                "address": resource_type + ".synthetic",
                "change": {"actions": actions or ["create"], "before": before, "after": after},
            }
        ]
    }


def job():
    return {
        "project": PROJECT,
        "name": "up-installation-upzero-worker",
        "location": "southamerica-east1",
        "template": [
            {
                "parallelism": 1,
                "template": [
                    {
                        "timeout": "900s",
                        "service_account": member("up-cp-upzero-dev"),
                        "containers": [
                            {
                                "image": IMAGE.replace("a" * 64, "b" * 64),
                                "args": ["--help"],
                                "resources": [{"limits": {"cpu": "2", "memory": "4Gi"}}],
                                "env": [
                                    {
                                        "name": "UP_META_SECRET_REFERENCE",
                                        "value": "synthetic-pinned-reference",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_scoped_table_iam_and_only_image_feature_job_changes_are_admitted():
    iam = {
        "project": PROJECT,
        "table_id": "catalog_inventory_versions",
        "dataset_id": "up_core",
        "role": "roles/bigquery.dataViewer",
        "member": member("up-product-read-dev"),
    }
    assert check(plan("google_bigquery_table_iam_member", None, iam), IMAGE)["create"] == 1
    before, after = job(), job()
    container = after["template"][0]["template"][0]["containers"][0]
    container["image"] = IMAGE
    container["env"].append(
        {"name": "UP_INSTALLATION_EXTENSIONS_ENABLED", "value": "1", "value_source": []}
    )
    assert check(plan("google_cloud_run_v2_job", before, after, ["update"]), IMAGE)["update"] == 1


@pytest.mark.parametrize(
    "change", ["timeout", "memory", "args", "identity", "secret", "extra-env", "duplicate-env"]
)
def test_job_unsafe_changes_are_rejected(change):
    before, after = job(), job()
    template = after["template"][0]["template"][0]
    container = template["containers"][0]
    container["image"] = IMAGE
    if change == "timeout":
        template["timeout"] = "3600s"
    if change == "memory":
        container["resources"][0]["limits"]["memory"] = "8Gi"
    if change == "args":
        container["args"] = ["--dispatch", "--all-stores"]
    if change == "identity":
        template["service_account"] = member("unapproved")
    if change == "secret":
        container["env"][0]["value"] = "new-reference"
    if change == "extra-env":
        container["env"].append({"name": "BYPASS_AUTH", "value": "1"})
    if change == "duplicate-env":
        container["env"].append(deepcopy(container["env"][0]))
    with pytest.raises(ValueError):
        check(plan("google_cloud_run_v2_job", before, after, ["update"]), IMAGE)


@pytest.mark.parametrize("change", ["writer", "customer-table", "principal", "dataset", "project"])
def test_read_iam_cannot_be_widened(change):
    iam = {
        "project": PROJECT,
        "table_id": "catalog_inventory_versions",
        "dataset_id": "up_core",
        "role": "roles/bigquery.dataViewer",
        "member": member("up-product-read-dev"),
    }
    if change == "writer":
        iam["role"] = "roles/bigquery.dataEditor"
    if change == "customer-table":
        iam["table_id"] = "customers"
    if change == "principal":
        iam["member"] = "allUsers"
    if change == "dataset":
        iam["dataset_id"] = "up_ops"
    if change == "project":
        iam["project"] = "unapproved-prod"
    with pytest.raises(ValueError):
        check(plan("google_bigquery_table_iam_member", None, iam), IMAGE)


@pytest.mark.parametrize(
    "kind",
    [
        "google_cloud_scheduler_job",
        "google_project_iam_member",
        "google_secret_manager_secret",
        "google_cloud_run_v2_service",
    ],
)
def test_unreviewed_scheduler_project_iam_secret_and_product_services_are_rejected(kind):
    with pytest.raises(ValueError):
        check(plan(kind, None, {"project": PROJECT}), IMAGE)


def test_destroy_or_replacement_is_rejected():
    for actions in (["delete"], ["delete", "create"]):
        with pytest.raises(ValueError, match="DESTRUCTIVE_PLAN"):
            check(plan("google_cloud_run_v2_job", job(), job(), actions), IMAGE)


def test_automatic_enrichment_and_preview_capacity_default_fail_closed():
    text = Path("infra/terraform/dashboard_completion.tf").read_text()
    assert text.count("default     = false") + text.count("default  = false") == 6
    image_flag = text.split('variable "dashboard_completion_product_images" {', 1)[1].split("}", 1)[
        0
    ]
    assert "default     = false" in image_flag
    assert "min_instance_count = 0" in text
    assert "invoker_iam_disabled = false" in text
    assert "google_project_iam_member" not in text
    assert "google_cloud_scheduler_job" not in text


def test_provider_integer_alias_remains_additive_only():
    name = "meta_live_insights_daily"
    fields = json.loads(Path("infra/terraform/schemas/" + name + ".json").read_text())
    added = {
        "frequency",
        "actions",
        "action_values",
        "purchase_action_type",
        "purchases",
        "purchase_value",
    }
    old = [
        dict(f, type="INTEGER" if f["type"] == "INT64" else f["type"])
        for f in fields
        if f["name"] not in added
    ]
    before = dict(
        project=PROJECT,
        table_id=name,
        dataset_id="up_core",
        deletion_protection=True,
        schema=json.dumps(old),
    )
    after = dict(before, schema=json.dumps(fields))
    p = plan("google_bigquery_table", before, after, ["update"])
    p["resource_changes"][0]["address"] = 'google_bigquery_table.tables["' + name + '"]'
    assert check(p, IMAGE)["update"] == 1
    for mutation in ("required", "type", "removed"):
        bad = deepcopy(p)
        previous = json.loads(bad["resource_changes"][0]["change"]["before"]["schema"])
        if mutation == "required":
            previous[2]["mode"] = "REQUIRED"
        if mutation == "type":
            previous[2]["type"] = "FLOAT64"
        if mutation == "removed":
            previous.append(dict(name="protected_field", type="STRING", mode="NULLABLE"))
        bad["resource_changes"][0]["change"]["before"]["schema"] = json.dumps(previous)
        with pytest.raises(ValueError, match="NON_ADDITIVE_SCHEMA"):
            check(bad, IMAGE)


def test_existing_production_federation_etag_only_is_not_access_change():
    before = dict(
        etag="old", member="synthetic-current-subject", role="roles/iam.workloadIdentityUser"
    )
    drift = dict(
        type="google_service_account_iam_member",
        address='google_service_account_iam_member.product_vercel_federation["production"]',
        change=dict(actions=["update"], before=before, after=dict(before, etag="new")),
    )
    assert check(dict(resource_drift=[drift]), IMAGE)["benign_drift"] == 1
    for mutation in ("member", "role", "address"):
        bad = deepcopy(drift)
        if mutation == "address":
            bad["address"] = "google_service_account_iam_member.unreviewed"
        else:
            bad["change"]["after"][mutation] = "unreviewed"
        with pytest.raises(ValueError, match="EXISTING_INFRASTRUCTURE_DRIFT"):
            check(dict(resource_drift=[bad]), IMAGE)


@pytest.mark.parametrize(
    "table", ["analytics_publications", "analytics_store_daily", "analytics_funnel_daily"]
)
def test_admin_analytics_read_grants_resolve_the_analytics_catalog(table):
    a = dict(
        project=PROJECT,
        table_id=table,
        dataset_id="up_analytics",
        role="roles/bigquery.dataViewer",
        member=member("up-product-admin-dev"),
    )
    assert check(plan("google_bigquery_table_iam_member", None, a), IMAGE)["create"] == 1
    a["dataset_id"] = "up_core"
    with pytest.raises(ValueError, match="UNAPPROVED_TABLE_IAM"):
        check(plan("google_bigquery_table_iam_member", None, a), IMAGE)


@pytest.mark.parametrize(
    "job_name,flag",
    [
        ("up-installation-upzero-worker", "UP_INSTALLATION_PRODUCT_IMAGES_ENABLED"),
        ("up-installation-orchestrator", "UP_INSTALLATION_PRODUCT_IMAGES_ENABLED"),
        ("up-installation-orchestrator", "UP_META_VERIFIED_PURCHASES_ENABLED"),
    ],
)
def test_new_source_flags_are_scoped_to_installation_jobs(job_name, flag):
    before, after = job(), job()
    before["name"] = after["name"] = job_name
    container = after["template"][0]["template"][0]["containers"][0]
    container["image"] = IMAGE
    container["env"].append(dict(name=flag, value="1", value_source=[]))
    assert check(plan("google_cloud_run_v2_job", before, after, ["update"]), IMAGE)["update"] == 1
    after["name"] = before["name"] = "up-meta-worker"
    with pytest.raises(ValueError):
        check(plan("google_cloud_run_v2_job", before, after, ["update"]), IMAGE)
