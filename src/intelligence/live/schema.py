"""Active additive schemas; legacy reference schemas stay reproducible."""

import json
from pathlib import Path

from src.bigquery.catalog import TABLES, Table
from src.influence.schema import SCHEMAS as INFLUENCE
from src.intelligence.schema import SCHEMAS as CUSTOMER
from src.performance.schema import SCHEMAS as PERFORMANCE

MODELS = {
    **INFLUENCE,
    **CUSTOMER,
    **{
        k: Table(
            "up_analytics",
            v,
            "date" if k.endswith("daily") else "period_start",
            ("store_id", "account_id"),
        )
        for k, v in PERFORMANCE.items()
    },
}
SCHEMAS = {
    name: Table(spec.dataset, {**spec.fields, "generation": "INT64"}, spec.partition, spec.cluster)
    for name, spec in MODELS.items()
}
SCHEMAS["analytics_campaign_performance_daily"] = Table(
    "up_analytics",
    {**SCHEMAS["analytics_campaign_performance_daily"].fields, "campaign_status": "STRING"},
    "date",
    ("store_id", "account_id"),
)
PUBLICATION = "analytics_intelligence_publications"
SCHEMAS[PUBLICATION] = Table(
    "up_analytics",
    {
        **dict.fromkeys(
            "row_key record_kind store_id policy_hash publication_id status source_snapshot_hash meta_configuration_hash meta_account_id base_publication_id".split(),
            "STRING",
        ),
        **dict.fromkeys("generation base_generation".split(), "INT64"),
        **dict.fromkeys("as_of calculated_at source_snapshot_at".split(), "TIMESTAMP"),
        **dict.fromkeys("report_from report_to".split(), "DATE"),
        **dict.fromkeys(
            "history_complete facts_complete meta_complete influence_complete customer_intelligence_complete performance_complete".split(),
            "BOOL",
        ),
        "row_counts": "JSON",
        "limitations": "JSON",
    },
    None,
    ("store_id", "policy_hash", "record_kind"),
)
META_ACTIVE = {
    k
    for k in TABLES
    if k.startswith("meta_raw_") or k.startswith("meta_live_") or k == "meta_account_bindings"
}


def promote(root: Path = Path(".")) -> None:
    folder = root / "infra/terraform"
    manifest = json.loads((folder / "tables.json").read_text())
    for name, spec in {**{k: TABLES[k] for k in sorted(META_ACTIVE)}, **SCHEMAS}.items():
        body = [
            {
                "name": f,
                "type": t,
                "mode": "REQUIRED" if f in {"row_key", "store_id", "generation"} else "NULLABLE",
            }
            for f, t in spec.fields.items()
        ]
        (folder / "schemas" / (name + ".json")).write_text(json.dumps(body, indent=2) + "\n")
        manifest[name] = {
            "dataset": spec.dataset,
            "partition": spec.partition,
            "cluster": list(spec.cluster),
        }
    (folder / "tables.json").write_text(json.dumps(manifest, indent=2) + "\n")
