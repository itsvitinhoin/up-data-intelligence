"""Build a local Customer Intelligence artifact; no listener, cloud client or query."""

import argparse
import json
from pathlib import Path

from src.analytics.config import AnalyticsPolicy
from src.influence.engine import InfluenceScope
from src.influence.materialization import materialize as influence_materialize
from src.influence.materialization import publish_local
from src.intelligence.materialization import materialize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--calculated-at", required=True)
    args = parser.parse_args()
    policy = AnalyticsPolicy.from_dict(json.loads(Path(args.policy).read_text())).reference()
    source = json.loads(Path(args.input).read_text())
    items = source.pop("items")
    influences = {
        s.value: influence_materialize(
            policy, source, calculated_at=args.calculated_at, influence_scope=s
        )
        for s in InfluenceScope
    }
    result = materialize(
        policy,
        customers=source["customers"],
        orders=source["orders"],
        items=items,
        events=source["events"],
        identity_links=source["identity_links"],
        influence=influences,
        calculated_at=args.calculated_at,
    )
    publish_local(Path(args.output), result)


if __name__ == "__main__":
    main()
