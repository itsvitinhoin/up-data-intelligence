"""Future Analytics job contract. Live execution is intentionally disabled."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from src.analytics.cloud.transport import CloudConfig
from src.analytics.cloud.writer import commit_sql, stage_ddl
from src.analytics.config import AnalyticsPolicy


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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-project")
    parser.add_argument("--confirm-store")
    args = parser.parse_args()
    if args.live:
        parser.error("live_disabled_pending_cloud_validation_and_activation")
    if not args.dry_run:
        parser.error("offline_only_requires_dry_run")
    policy = AnalyticsPolicy.from_dict(json.loads(args.policy.read_text()))
    if args.store != policy.store_id:
        parser.error("policy_store_mismatch")
    policy = replace(policy, report_from=args.date_from, report_to=args.date_to, as_of=args.as_of)
    CloudConfig(args.project, args.location, args.maximum_bytes_billed, args.timeout_seconds, False)
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
