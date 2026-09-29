"""Local synthetic runner. No cloud adapter, credentials, or production source reader."""

import argparse
import json
from pathlib import Path

from src.analytics.materialization import SQLiteAnalyticsSink, run
from src.analytics.parity import load_fixture
from src.observability.logging import configure


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--previous-fixture", type=Path)
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--full-refresh", action="store_true")
    args = parser.parse_args()
    configure()
    policy, snapshot = load_fixture(args.fixture)
    previous = load_fixture(args.previous_fixture)[1] if args.previous_fixture else None
    sink = SQLiteAnalyticsSink(args.sqlite)
    try:
        print(
            json.dumps(
                run(policy, snapshot, sink, previous=previous, full_refresh=args.full_refresh)
            )
        )
    finally:
        sink.close()


if __name__ == "__main__":
    main()
