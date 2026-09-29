"""Manual first DEV Analytics publication with strict opt-in and policy guards."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from src.analytics.cloud.initial import LOCATION, PROJECT, STORE, run_initial, validate_policy
from src.analytics.cloud.transport import CloudConfig, Transport
from src.analytics.cloud.writer import commit_sql, stage_ddl
from src.analytics.config import AnalyticsPolicy
from src.observability.logging import configure, event


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--maximum-bytes-billed", required=True, type=int)
    parser.add_argument("--timeout-seconds", type=float, default=300)
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Offline SQL preparation only; no BigQuery dry-run"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-backfill-complete", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-project")
    parser.add_argument("--confirm-store")
    args = parser.parse_args()
    if args.live == args.dry_run:
        parser.error("choose_exactly_one_live_or_offline_dry_run")
    if args.live and (
        args.project != PROJECT
        or args.confirm_project != PROJECT
        or args.store != STORE
        or args.confirm_store != STORE
        or args.location != LOCATION
        or not args.full_refresh
        or not args.confirm_backfill_complete
    ):
        parser.error(
            "initial_live_requires_approved_environment_full_refresh_and_backfill_confirmation"
        )
    policy = AnalyticsPolicy.from_dict(json.loads(args.policy.read_text()))
    if args.store != policy.store_id:
        parser.error("policy_store_mismatch")
    if args.live:
        validate_policy(policy)
        if (args.date_from, args.date_to, args.as_of) != (
            policy.report_from,
            policy.report_to,
            policy.as_of,
        ):
            parser.error("initial_live_window_mismatch")
    else:
        policy = replace(
            policy, report_from=args.date_from, report_to=args.date_to, as_of=args.as_of
        )
    config = CloudConfig(
        args.project, args.location, args.maximum_bytes_billed, args.timeout_seconds, False
    )
    if args.live:
        # Credential discovery occurs only after every guard and policy validation.
        from google.cloud import bigquery

        configure()
        client = None
        try:
            client = bigquery.Client(project=args.project, location=args.location)
            receipt = run_initial(
                Transport(client, config),
                policy,
                full_refresh=args.full_refresh,
                backfill_confirmed=args.confirm_backfill_complete,
            )
            print(
                json.dumps(
                    {"publication_id": receipt["publication_id"], "status": receipt["status"]}
                )
            )
        except Exception as exc:
            safe_codes = {
                "analytics_head_missing",
                "analytics_duplicate_head",
                "analytics_initial_head_inconsistent",
                "analytics_initial_target_not_empty",
                "analytics_initial_generation_already_advanced",
                "analytics_initial_receipt_mismatch",
                "analytics_unit_too_large_partition_required",
                "analytics_staging_row_too_large",
            }
            code = (
                str(exc)
                if isinstance(exc, ValueError) and str(exc) in safe_codes
                else "analytics_initial_failed"
            )
            event("analytics_execution_finished", status="failed", code=code)
            raise SystemExit(1) from None
        finally:
            if client is not None:
                cast(Any, client).close()
        return
    if args.output is None:
        parser.error("offline_preparation_requires_output")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "staging.sql").write_text(stage_ddl() + "\n")
    (args.output / "publication.sql").write_text(commit_sql(args.project) + "\n")
    print(
        json.dumps(
            {
                "mode": "offline_preparation",
                "live_enabled": False,
                "policy_hash": policy.policy_hash,
                "store_id": policy.store_id,
                "full_refresh_requested": args.full_refresh,
            }
        )
    )


if __name__ == "__main__":
    main()
