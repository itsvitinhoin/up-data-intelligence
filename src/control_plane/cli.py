"""Explicit DEV CLI gates, before SDK/ADC/Secret Manager discovery."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.analytics.cloud.transport import CloudConfig, Transport
from src.control_plane.budget import BoundedClient
from src.control_plane.model import PIPELINES, Window
from src.control_plane.preflight import Prerequisites
from src.control_plane.registry import Admin, StoreAdmin
from src.control_plane.repository import BigQueryRegistry
from src.domain.models import SafeError
from src.observability.logging import configure, event, execution_id
from src.security.lease import cloud_lease


def common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    parser.add_argument("--lease-bucket", required=True)
    parser.add_argument("--maximum-bytes-billed", type=int, default=1073741824)
    parser.add_argument("--maximum-total-bytes-billed", type=int, default=137438953472)


def gated(args: Any) -> None:
    if (
        not args.live
        or args.project != "up-data-intelligence-dev"
        or args.confirm_project != args.project
        or args.location != "southamerica-east1"
        or not args.lease_bucket
    ):
        raise SafeError("control_plane_dev_confirmation_required")
    if hasattr(args, "store_id") and (not args.store_id or args.confirm_store != args.store_id):
        raise SafeError("store_confirmation_required")


def clients(args: Any) -> tuple[Transport, BoundedClient]:
    config = CloudConfig(
        args.project,
        args.location,
        args.maximum_bytes_billed,
        300,
        False,
        maximum_total_bytes_billed=args.maximum_total_bytes_billed,
    )
    from google.cloud import bigquery

    client = BoundedClient(bigquery.Client(project=args.project, location=args.location), config)
    return Transport(client, config), client


def worker_main() -> int:
    parser = argparse.ArgumentParser(
        description="Shared DEV worker; exactly one store, no pilot policy file"
    )
    common(parser)
    parser.add_argument("--pipeline", choices=PIPELINES, required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--confirm-store", required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--page-limit", type=int, default=1000)
    for key in ("report-from", "report-to", "as-of", "source-snapshot-at", "calculated-at"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    configure()
    execution_id.set(os.environ.get("CLOUD_RUN_EXECUTION"))
    try:
        gated(args)
        window = Window(
            args.report_from,
            args.report_to,
            args.as_of,
            args.source_snapshot_at,
            args.calculated_at,
        )
        transport, client = clients(args)
        from src.control_plane.worker import Actions, StoreWorker

        pre = Prerequisites(transport)
        action = Actions(
            transport,
            pre,
            lease_bucket=args.lease_bucket,
            meta_secret_reference=os.environ.get("UP_META_SECRET_REFERENCE"),
            page_limit=args.page_limit,
        )
        worker = StoreWorker(
            BigQueryRegistry(transport),
            pre.check,
            lambda store: cloud_lease(args.lease_bucket, store),
            action,
            lambda: {
                "query_count": client.query_count,
                "reserved_query_bytes": client.reserved_bytes,
                "bytes_processed": client.bytes_processed,
                "query_duration_ms": client.duration_ms,
            },
        )
        worker.execute(args.store_id, args.expected_revision, args.pipeline, window)
        return 0
    except Exception as exc:
        event(
            "job_failed",
            store_id=args.store_id,
            pipeline=args.pipeline,
            code=exc.code if isinstance(exc, SafeError) else "control_plane_worker_failed",
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Internal ADMIN_UP DEV registry CLI; never runs Terraform"
    )
    common(parser)
    parser.add_argument(
        "command",
        choices=(
            "register-store",
            "update-store",
            "validate-store",
            "activate-store",
            "pause-store",
            "read-store",
        ),
    )
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--confirm-store", required=True)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    configure()
    try:
        gated(args)
        payload = json.loads(args.request.read_text()) if args.request else {}
        StoreAdmin.editable(payload)
        if (
            args.command == "register-store"
            and payload.get("store_id", args.store_id) != args.store_id
        ):
            raise SafeError("store_confirmation_required")
        transport, _ = clients(args)
        service = StoreAdmin(
            BigQueryRegistry(transport),
            lambda store: cloud_lease(args.lease_bucket, store),
            Prerequisites(transport).configuration,
        )
        # Trusted internal operator CLI, authenticated by ADC/IAM; not a public role field.
        admin = Admin("adc-internal-operator", "ADMIN_UP")
        if args.command == "register-store":
            result = service.register(admin, {**payload, "store_id": args.store_id})
        elif args.command == "read-store":
            result = service.read(admin, args.store_id)
        else:
            result = service.change(admin, args.store_id, args.command, payload)
        print(json.dumps(asdict(result)))
        return 0
    except Exception as exc:
        event(
            "job_failed",
            store_id=args.store_id,
            resource="registry",
            code=exc.code if isinstance(exc, SafeError) else "store_registry_operation_failed",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
