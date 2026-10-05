import hashlib
from copy import deepcopy

import pytest

from scripts.dashboard_completion_plan_guard import PROJECT, REGION, member
from scripts.dashboard_completion_preview_guard import PREFIX, check

IMAGE = PREFIX + "a" * 64

SUBJECT = "a" * 64  # synthetic, never a live key
SHA = hashlib.sha256(SUBJECT.encode()).hexdigest()
META = f"projects/{PROJECT}/secrets/up-intelligence-meta-global-token/versions/1"


def service(role):
    env = dict(UP_PRODUCT_PROJECT=PROJECT, UP_PRODUCT_LOCATION=REGION)
    if role == "read":
        env.update(UP_PRODUCT_CATALOG_ENABLED="1", UP_PRODUCT_CREATIVES_ENABLED="1")
    else:
        env.update(
            UP_INSTALLATION_EXTENSIONS_ENABLED="1",
            UP_PRODUCT_PROJECT_NUMBER="876521886531",
            UP_PRODUCT_LEASE_BUCKET=PROJECT + "-876521886531-leases",
            UP_PRODUCT_SUBJECT_KEY=SUBJECT,
            UP_META_SECRET_REFERENCE=META,
        )
    return dict(
        project=PROJECT,
        location=REGION,
        name="up-" + role + "-api-data-preview",
        deletion_protection=True,
        ingress="INGRESS_TRAFFIC_ALL",
        invoker_iam_disabled=False,
        template=[
            dict(
                service_account=member("up-product-" + role + "-dev").removeprefix(
                    "serviceAccount:"
                ),
                timeout="120s",
                max_instance_request_concurrency=8,
                scaling=[dict(min_instance_count=0, max_instance_count=3)],
                containers=[
                    dict(
                        image=IMAGE,
                        command=["gunicorn"],
                        args=[
                            "--bind",
                            "0.0.0.0:8080",
                            "--workers",
                            "1",
                            "--threads",
                            "8",
                            "--timeout",
                            "120",
                            "--access-logfile",
                            "/dev/null",
                            "src.product_auth.runtime:" + role + "_app()",
                        ],
                        ports=[dict(container_port=8080, name="http1")],
                        resources=[dict(limits=dict(cpu="1", memory="1Gi"))],
                        env=[dict(name=k, value=v) for k, v in env.items()],
                    )
                ],
            )
        ],
    )


def plan():
    rows = []

    def add(kind, after):
        rows.append(dict(type=kind, change=dict(actions=["create"], before=None, after=after)))

    for role in ("read", "admin"):
        add("google_cloud_run_v2_service", service(role))
        add(
            "google_cloud_run_v2_service_iam_member",
            dict(
                project=PROJECT,
                location=REGION,
                name="up-" + role + "-api-data-preview",
                role="roles/run.invoker",
                member=member("up-product-vercel-dev"),
            ),
        )
    add(
        "google_secret_manager_secret_iam_member",
        dict(
            project=PROJECT,
            secret_id="up-intelligence-meta-global-token",
            role="roles/secretmanager.secretAccessor",
            member=member("up-product-admin-dev"),
        ),
    )
    return dict(resource_changes=rows)


def test_private_preview_exact_stage_does_not_print_subject_or_pin():
    result = check(plan(), IMAGE, SHA, META)
    assert result["creates"] == 5 and result["updates"] == 0
    assert SUBJECT not in str(result) and META not in str(result)


@pytest.mark.parametrize(
    "change",
    [
        "public",
        "prod-service",
        "min-instances",
        "capacity",
        "image",
        "secret-pin",
        "subject",
        "env",
        "sa",
        "command",
        "project",
        "secret-admin",
        "invoker",
        "scheduler",
        "destroy",
        "missing",
        "duplicate",
    ],
)
def test_preview_rejects_every_unapproved_resource_or_service_expansion(change):
    p = plan()
    first = p["resource_changes"][0]["change"]["after"]
    t = first["template"][0]
    c = t["containers"][0]
    admin = p["resource_changes"][2]["change"]["after"]["template"][0]["containers"][0]
    if change == "public":
        first["invoker_iam_disabled"] = True
    if change == "prod-service":
        first["name"] = "up-read-api"
    if change == "min-instances":
        t["scaling"][0]["min_instance_count"] = 1
    if change == "capacity":
        t["max_instance_request_concurrency"] = 80
    if change == "image":
        c["image"] = IMAGE.replace("product-api@", "other@")
    if change == "secret-pin":
        next(e for e in admin["env"] if e["name"] == "UP_META_SECRET_REFERENCE")["value"] = (
            META.replace("/1", "/latest")
        )
    if change == "subject":
        next(e for e in admin["env"] if e["name"] == "UP_PRODUCT_SUBJECT_KEY")["value"] = "b" * 64
    if change == "env":
        c["env"].append(dict(name="BYPASS_AUTH", value="1"))
    if change == "sa":
        t["service_account"] = member("unapproved").removeprefix("serviceAccount:")
    if change == "command":
        c["command"] = ["python"]
    if change == "project":
        first["project"] = "unapproved-prod"
    if change == "secret-admin":
        p["resource_changes"][4]["change"]["after"]["role"] = "roles/secretmanager.admin"
    if change == "invoker":
        p["resource_changes"][1]["change"]["after"]["member"] = "allUsers"
    if change == "scheduler":
        p["resource_changes"].append(
            dict(
                type="google_cloud_scheduler_job",
                change=dict(actions=["create"], after=dict(project=PROJECT)),
            )
        )
    if change == "destroy":
        p["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
    if change == "missing":
        p["resource_changes"].pop()
    if change == "duplicate":
        p["resource_changes"].append(deepcopy(p["resource_changes"][0]))
    with pytest.raises(ValueError):
        check(p, IMAGE, SHA, META)


def test_image_host_regex_is_literal():
    with pytest.raises(ValueError):
        check(plan(), IMAGE.replace("pkg.dev", "pkgXdev"), SHA, META)


def test_worker_image_without_http_dependencies_is_rejected():
    p = plan()
    foundation = IMAGE.replace("product-api@", "foundation@")
    for row in p["resource_changes"]:
        if row["type"] == "google_cloud_run_v2_service":
            row["change"]["after"]["template"][0]["containers"][0]["image"] = foundation
    with pytest.raises(ValueError, match="IMMUTABLE_IMAGE_REQUIRED"):
        check(p, foundation, SHA, META)
