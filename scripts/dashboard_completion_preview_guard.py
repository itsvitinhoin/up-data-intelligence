"""Offline Stage 2 guard: two private DEV APIs and narrowly scoped invokers/probe.

No apply or credential read. Outputs only resource counts and safe grant metadata.
Does not approve separate Vercel preview federation changes implicitly.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.dashboard_completion_plan_guard import PROJECT, REGION, member
from scripts.terraform_drift_guard import review_drift

PREFIX = f"{REGION}-docker.pkg.dev/{PROJECT}/up-data-intelligence/product-api@sha256:"


def check(plan: dict[str, Any], image: str, subject_sha256: str, meta_reference: str) -> dict:
    if not re.fullmatch(re.escape(PREFIX) + "[a-f0-9]{64}", image):
        raise ValueError("IMMUTABLE_IMAGE_REQUIRED")
    if not re.fullmatch("[a-f0-9]{64}", subject_sha256) or not re.fullmatch(
        re.escape(f"projects/{PROJECT}/secrets/up-intelligence-meta-global-token/versions/")
        + "[1-9][0-9]*",
        meta_reference,
    ):
        raise ValueError("PINNED_EXISTING_CONFIGURATION_REQUIRED")
    found: set[str] = set()
    for resource in plan.get("resource_changes", []):
        c = resource["change"]
        if c["actions"] in (["read"], ["no-op"]):
            continue
        if c["actions"] != ["create"]:
            raise ValueError("STAGE2_ADDITIVE_ONLY")
        a, kind = c["after"], resource["type"]
        if a.get("project") != PROJECT:
            raise ValueError("DEV_ONLY")
        if kind == "google_cloud_run_v2_service":
            service = {
                "up-read-api-data-preview": "read",
                "up-admin-api-data-preview": "admin",
            }.get(a.get("name"))
            if (
                service is None
                or a.get("location") != REGION
                or a.get("deletion_protection") is not True
                or a.get("invoker_iam_disabled") is not False
                or a.get("ingress") != "INGRESS_TRAFFIC_ALL"
            ):
                raise ValueError("PRIVATE_PREVIEW_REQUIRED")
            if a.get("traffic") and any(
                t.get("type") != "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST" or t.get("percent") != 100
                for t in a["traffic"]
            ):
                raise ValueError("PREVIEW_TRAFFIC_INVALID")
            if len(a["template"]) != 1:
                raise ValueError("PREVIEW_TEMPLATE_INVALID")
            t = a["template"][0]
            if (
                t.get("service_account")
                != member("up-product-" + service + "-dev").removeprefix("serviceAccount:")
                or t.get("timeout") != "120s"
                or t.get("max_instance_request_concurrency") != 8
                or t.get("scaling") != [{"min_instance_count": 0, "max_instance_count": 3}]
                or t.get("volumes")
                or t.get("vpc_access")
            ):
                raise ValueError("PREVIEW_CAPACITY_OR_IDENTITY_INVALID")
            if len(t["containers"]) != 1:
                raise ValueError("PREVIEW_CONTAINER_INVALID")
            container = t["containers"][0]
            if (
                container.get("image") != image
                or container.get("command") != ["gunicorn"]
                or container.get("args")
                != [
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
                    "src.product_auth.runtime:" + service + "_app()",
                ]
                or container.get("ports") != [{"container_port": 8080, "name": "http1"}]
                or container.get("volume_mounts")
            ):
                raise ValueError("PREVIEW_COMMAND_INVALID")
            limits = container.get("resources", [])
            if (
                len(limits) != 1
                or limits[0].get("limits") != {"cpu": "1", "memory": "1Gi"}
                or limits[0].get("cpu_idle") is False
            ):
                raise ValueError("PREVIEW_RESOURCES_INVALID")
            env = container.get("env", [])
            values = {r["name"]: r.get("value") for r in env}
            if len(values) != len(env) or any(r.get("value_source") for r in env):
                raise ValueError("PREVIEW_ENV_INVALID")
            expected = {"UP_PRODUCT_PROJECT": PROJECT, "UP_PRODUCT_LOCATION": REGION}
            if service == "read":
                expected.update(UP_PRODUCT_CATALOG_ENABLED="1", UP_PRODUCT_CREATIVES_ENABLED="1")
            else:
                key = values.get("UP_PRODUCT_SUBJECT_KEY", "")
                if (
                    not re.fullmatch("[a-f0-9]{64}", key)
                    or hashlib.sha256(key.encode()).hexdigest() != subject_sha256
                ):
                    raise ValueError("EXISTING_SUBJECT_KEY_REQUIRED")
                expected.update(
                    UP_INSTALLATION_EXTENSIONS_ENABLED="1",
                    UP_PRODUCT_PROJECT_NUMBER="876521886531",
                    UP_PRODUCT_LEASE_BUCKET=PROJECT + "-876521886531-leases",
                    UP_PRODUCT_SUBJECT_KEY=key,
                    UP_META_SECRET_REFERENCE=meta_reference,
                )
            if values != expected:
                raise ValueError("PREVIEW_ENV_INVALID")
            identity = "service:" + service
        elif kind == "google_cloud_run_v2_service_iam_member":
            service = {
                "up-read-api-data-preview": "read",
                "up-admin-api-data-preview": "admin",
            }.get(a.get("name"))
            if (
                service is None
                or a.get("location") != REGION
                or a.get("role") != "roles/run.invoker"
                or a.get("member") != member("up-product-vercel-dev")
                or a.get("condition")
            ):
                raise ValueError("PREVIEW_INVOKER_INVALID")
            identity = "invoker:" + service
        elif kind == "google_secret_manager_secret_iam_member":
            if (
                a.get("secret_id") != "up-intelligence-meta-global-token"
                or a.get("role") != "roles/secretmanager.secretAccessor"
                or a.get("member") != member("up-product-admin-dev")
                or a.get("condition")
            ):
                raise ValueError("GLOBAL_META_PROBE_GRANT_INVALID")
            identity = "meta-probe"
        else:
            raise ValueError("UNAPPROVED_STAGE2_RESOURCE")
        if identity in found:
            raise ValueError("DUPLICATE_STAGE2_RESOURCE")
        found.add(identity)
    if found != {"service:read", "service:admin", "invoker:read", "invoker:admin", "meta-probe"}:
        raise ValueError("EXACT_PREVIEW_STAGE_REQUIRED")
    return {
        "creates": 5,
        "updates": 0,
        "deletes": 0,
        "services": ["up-read-api-data-preview", "up-admin-api-data-preview"],
        "admin_meta_probe": "scoped existing global secret only",
        **review_drift(plan.get("resource_drift", [])),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--subject-sha256", required=True)
    parser.add_argument("--meta-reference", required=True)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                check(
                    json.loads(args.plan_json.read_text()),
                    args.image,
                    args.subject_sha256,
                    args.meta_reference,
                )
            )
        )
    except (KeyError, TypeError, ValueError):
        raise SystemExit("DASHBOARD_PREVIEW_PLAN_REJECTED") from None
