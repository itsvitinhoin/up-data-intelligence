"""Local synthetic memory benchmark. No client, credential discovery, or cloud IO.

Run each mode in a fresh process so ru_maxrss measurements do not contaminate it.
The spool mode measures transport-sized batches + reduction, not BigQuery latency.
"""

import argparse
import json
import platform
import resource
import sys
import time
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from src.analytics.cloud.facts import FactSpool
from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row, funnel_rows
from src.analytics.serialization import encode_tables
from src.utils.data import digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("reference", "spool"), required=True)
    parser.add_argument("--facts", type=int, default=355886)
    parser.add_argument("--days", type=int, choices=(1, 27), default=27)
    parser.add_argument("--chunk-rows", type=int, default=25000)
    args = parser.parse_args()
    policy = AnalyticsPolicy.from_dict(
        json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    ).reference()
    policy = replace(
        policy,
        store_id="synthetic-benchmark",
        report_to=(date(2026, 9, 1) + timedelta(days=args.days)).isoformat(),
    )
    names = ("product_view", "add_to_cart", "checkout_started", "purchase")
    start = datetime.fromisoformat("2026-09-01T04:00:00+00:00")

    def row(i: int) -> Row:
        return {
            "store_id": policy.store_id,
            "source_system": "upzero",
            "fact_id": f"synthetic-fact-{i:032d}",
            "session_id": f"synthetic-session-{i // 4:032d}",
            "event_name": names[i % 4],
            "occurred_at": (start + timedelta(days=i % args.days, seconds=i % 3600)).isoformat(),
        }

    began = time.monotonic()
    storage = 0
    if args.mode == "reference":
        # Benchmark only: direct funnel reference, not the bounded build entrypoint.
        facts = [row(i) for i in range(args.facts)]
        result = funnel_rows(policy, facts)
    else:
        result = []
        with TemporaryDirectory(prefix="analytics-benchmark-") as directory:
            path = Path(directory) / "facts.sqlite"
            spool = FactSpool(path, policy)
            try:
                for d in range(args.days):
                    day = (date(2026, 9, 1) + timedelta(days=d)).isoformat()
                    chunk = []
                    count = 0
                    for i in range(d, args.facts, args.days):
                        chunk.append(row(i))
                        count += 1
                        if len(chunk) == args.chunk_rows:
                            spool.add(day, chunk)
                            chunk = []
                    if chunk:
                        spool.add(day, chunk)
                    del chunk
                    result.append(spool.finish_day(day, count))
                storage = path.stat().st_size
                assert spool.rows == args.facts
            finally:
                spool.close()
    encoded = encode_tables({"analytics_funnel_daily": result})
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = int(raw_rss if sys.platform == "darwin" else raw_rss * 1024)
    print(
        json.dumps(
            {
                "mode": args.mode,
                "synthetic_facts": args.facts,
                "days": args.days,
                "transport_batch_rows": args.chunk_rows if args.mode == "spool" else None,
                "peak_rss_bytes": rss,
                "spool_bytes": storage,
                "rss_plus_spool_bytes_conservative": rss + storage,
                "elapsed_seconds": round(time.monotonic() - began, 3),
                "result_sha256": digest(encoded),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "cloud_executed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
