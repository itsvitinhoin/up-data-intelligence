"""Explicit internal DEV administrative recovery; no auto-selection or replay."""

import argparse

from src.control_plane.cli import clients, common, gated
from src.control_plane.recovery import CheckpointRecovery, validate_target
from src.control_plane.recovery_repository import BigQueryRecovery
from src.control_plane.registry import Admin
from src.domain.models import SafeError
from src.observability.logging import configure, event
from src.security.lease import cloud_lease


def main() -> int:
    parser = argparse.ArgumentParser(description="ADMIN_UP audited checkpoint recovery in DEV")
    common(parser)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--confirm-store", required=True)
    parser.add_argument("--original-run-id", required=True)
    parser.add_argument("--replay-run-id", required=True)
    args = parser.parse_args()
    configure()
    try:
        gated(args)
        admin = Admin("adc-internal-operator", "ADMIN_UP")
        admin.authorize()
        validate_target(args.store_id, args.original_run_id, args.replay_run_id)
        transport, _ = clients(args)
        CheckpointRecovery(
            BigQueryRecovery(transport), lambda store: cloud_lease(args.lease_bucket, store)
        ).recover(admin, args.store_id, args.original_run_id, args.replay_run_id)
        return 0
    except Exception as exc:
        event(
            "job_failed",
            store_id=args.store_id,
            code=exc.code if isinstance(exc, SafeError) else "checkpoint_recovery_failed",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
