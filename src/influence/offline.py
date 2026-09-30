"""Explicit local snapshot input/output. Never discovers credentials or calls APIs."""

import argparse
import json
from pathlib import Path

from src.analytics.config import AnalyticsPolicy
from src.influence.engine import InfluenceScope
from src.influence.materialization import materialize, publish_local


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument(
        "--input", required=True, help="Local coherent snapshot JSON; no live extraction."
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--calculated-at", required=True)
    parser.add_argument(
        "--influence-scope", choices=list(InfluenceScope), default=InfluenceScope.LIFETIME
    )
    args = parser.parse_args()
    policy = AnalyticsPolicy.from_dict(json.loads(Path(args.policy).read_text())).reference()
    snapshot = json.loads(Path(args.input).read_text())
    artifact = materialize(
        policy, snapshot, calculated_at=args.calculated_at, influence_scope=args.influence_scope
    )
    publish_local(Path(args.output), artifact)


if __name__ == "__main__":
    main()
