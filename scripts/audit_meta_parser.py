"""Read-only aggregate audit. Never print URLs, identifiers, query values or exceptions."""

import argparse
import json
from collections import Counter
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from src.normalization.meta_url import FIELDS, parse_meta_url

BAD = {"invalid_url", "invalid_id", "placeholder", "conflict"}


def categories(value: Any) -> list[str]:
    parsed = parse_meta_url(value)
    status = str(parsed["parse_status"])
    if status == "invalid_url":
        return ["url:invalid_url"]
    if not value:
        return ["parameters:absent"]
    params = parse_qs(
        urlsplit(value).query, keep_blank_values=True, max_num_fields=256, errors="strict"
    )
    reasons = []
    for field in FIELDS:
        if field in params:
            single = "https://example.invalid/?" + urlencode({field: params[field]}, doseq=True)
            field_status = parse_meta_url(single)["parse_status"]
            if field_status in BAD:
                reasons.append(field + ":" + field_status)
    return reasons or ["parameters:" + status]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    parser.add_argument("--store", required=True)
    parser.add_argument("--confirm-store", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live or args.confirm_store != args.store:
        parser.error("explicit_live_and_store_confirmation_required")
    # Reject SQL identifier interpolation; tenant remains a bound parameter.
    import re

    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", args.project):
        parser.error("invalid_project")
    from google.api_core.retry import Retry
    from google.cloud import bigquery

    try:
        client = bigquery.Client(project=args.project, location=args.location)
        config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("store", "STRING", args.store)],
            maximum_bytes_billed=1_000_000_000,
        )
        # Existing sanitized CORE only. No RAW export or mutation.
        rows = client.query(
            f"SELECT parse_status, landing_url FROM `{args.project}.up_core.analytics_events` "
            "WHERE store_id=@store AND parse_status IN ('invalid_url','invalid_id','placeholder','conflict')",
            job_config=config,
            retry=Retry(predicate=lambda _: False),
            timeout=30,
        ).result(timeout=60)
        statuses: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        mismatches = 0
        for row in rows:
            statuses[str(row.parse_status)] += 1
            reasons.update(categories(row.landing_url))
            mismatches += parse_meta_url(row.landing_url)["parse_status"] != row.parse_status
        print(
            json.dumps(
                {
                    "facts": sum(statuses.values()),
                    "stored_status_counts": dict(statuses),
                    "category_counts_nonexclusive": dict(reasons),
                    "status_mismatches": mismatches,
                }
            )
        )
        return 0
    except Exception:
        print(json.dumps({"code": "aggregate_audit_unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
