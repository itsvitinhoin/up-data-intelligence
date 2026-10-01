"""Operator-only, read-only DEV probe. Never use its local grant as HTTP authentication."""

import argparse
import json
import secrets
from pathlib import Path

from google.cloud import bigquery

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal, ReadError
from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.dashboard.service import DashboardService


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Analytics V1 overview probe")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--from", dest="from_day", required=True)
    parser.add_argument("--to", dest="to_day", required=True)
    parser.add_argument("--allow-bq-read", action="store_true", required=True)
    args = parser.parse_args()
    policy = AnalyticsPolicy.from_dict(json.loads(args.policy.read_text()))
    if policy.store_id != args.store_id:
        parser.error("policy_store_mismatch")
    # This diagnostic runs under the operator's GCP IAM. It is not a network auth provider.
    client = bigquery.Client(project=args.project, location=args.location)
    budget = ReadBudget(args.project, args.location)
    service = DashboardService(
        args.project,
        {policy.store_id: policy},
        lambda: BigQueryReadSession(client, budget),
        secrets.token_bytes(32),
    )
    grant = Grant(args.tenant_id, policy.store_id, "B2B")
    principal = Principal("local-dev-read-probe", "ADMIN_UP", frozenset({grant}))
    try:
        response = service.overview(principal, grant, from_day=args.from_day, to_day=args.to_day)
    except ReadError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}))
        return 1
    data, meta = response["data"], response["metadata"]
    print(
        json.dumps(
            {
                "status": "completed",
                "store_id": meta["store_id"],
                "generation": meta["generation"],
                "policy_hash": meta["policy_hash"],
                "report_from": meta["report_from"],
                "report_to": meta["report_to"],
                "days_returned": len(data["series"]),
                "history_complete": meta["history_complete"],
                "facts_complete": meta["facts_complete"],
                "limitations": meta["limitations"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
