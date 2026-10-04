"""Explicit DEV health execution, with no source client or secret access."""

import argparse
import os
from uuid import uuid4

from src.analytics.cloud.transport import CloudConfig, Transport, scalar
from src.control_plane.model import StoreConfig
from src.domain.models import SafeError
from src.observability.logging import configure, event, execution_id
from src.quality.data_health import DataHealth
from src.utils.data import now


def main() -> int:
    parser = argparse.ArgumentParser(description="Durable evidence only; quality_results writer")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--store-id")
    scope.add_argument("--all-stores", action="store_true")
    parser.add_argument("--confirm-store")
    parser.add_argument("--max-stores", type=int, default=10)
    parser.add_argument("--maximum-bytes-billed", type=int, default=1073741824)
    parser.add_argument("--maximum-total-bytes-billed", type=int, default=137438953472)
    args = parser.parse_args()
    configure()
    execution_id.set(os.environ.get("CLOUD_RUN_EXECUTION"))
    try:
        if (
            not args.live
            or args.project != "up-data-intelligence-dev"
            or args.confirm_project != args.project
            or args.location != "southamerica-east1"
            or not 1 <= args.max_stores <= 10
            or not 0 < args.maximum_bytes_billed <= 1073741824
            or not args.maximum_bytes_billed <= args.maximum_total_bytes_billed <= 137438953472
            or (args.store_id and args.confirm_store != args.store_id)
            or (args.all_stores and args.confirm_store)
        ):
            raise SafeError("data_health_dev_confirmation_required")
        from google.cloud import bigquery

        transport = Transport(
            bigquery.Client(project=args.project, location=args.location),
            CloudConfig(
                args.project,
                args.location,
                args.maximum_bytes_billed,
                300,
                False,
                maximum_total_bytes_billed=args.maximum_total_bytes_billed,
            ),
        )
        where = "store_id=@store" if args.store_id else "status='ACTIVE'"
        at = now()
        rows, _ = transport.query(
            f"SELECT * FROM `{args.project}.up_ops.store_runtime_config` FOR SYSTEM_TIME AS OF @snapshot WHERE {where} ORDER BY store_id LIMIT @limit",
            [
                scalar("store", "STRING", args.store_id),
                scalar("limit", "INT64", args.max_stores + 1),
                scalar("snapshot", "TIMESTAMP", at),
            ],
        )
        if len(rows) > args.max_stores or len({r["store_id"] for r in rows}) != len(rows):
            raise SafeError("health_store_inventory_invalid")
        if args.store_id and len(rows) != 1:
            raise SafeError("health_store_not_registered")
        checker, audit_id = DataHealth(transport), "data-health-" + uuid4().hex
        failed = 0
        for row in rows:
            config = StoreConfig.from_row(row)
            cutoff, findings = checker.check(config, at)
            checker.persist([f.row(config.store_id, cutoff.as_of, audit_id, at) for f in findings])
            for finding in findings:
                event(
                    "data_health_result",
                    store_id=config.store_id,
                    run_id=audit_id,
                    resource="data_health",
                    as_of=cutoff.as_of,
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    failed_count=finding.failed_count,
                    checked_count=finding.checked_count,
                )
                if finding.severity in {"alert", "error"}:
                    failed += finding.failed_count
        event("data_health_finished", run_id=audit_id, failed_count=failed, checked_count=len(rows))
        return int(failed > 0)
    except Exception as exc:
        event(
            "data_health_failed",
            code=exc.code if isinstance(exc, SafeError) else "health_read_failed",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
