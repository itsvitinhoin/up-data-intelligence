"""Separate CHANGE #13 proposal; never registers or replaces active CORE schemas."""

import json
from pathlib import Path


def fields(names: str, typ: str) -> dict[str, str]:
    return dict.fromkeys(names.split(), typ)


BASE = fields("row_key store_id account_id api_version contract_version", "STRING") | fields(
    "observed_at source_updated_at", "TIMESTAMP"
)
SCHEMAS = {
    "meta_accounts": BASE
    | fields("meta_account_id account_name currency timezone status", "STRING")
    | fields("created_time updated_time", "TIMESTAMP"),
    "meta_campaigns": BASE
    | fields("campaign_id campaign_name objective status effective_status", "STRING")
    | fields("created_time updated_time", "TIMESTAMP"),
    "meta_adsets": BASE
    | fields(
        "adset_id campaign_id adset_name optimization_goal billing_event status effective_status",
        "STRING",
    )
    | {"targeting_summary": "JSON"},
    "meta_ads": BASE
    | fields("ad_id adset_id campaign_id ad_name creative_id status effective_status", "STRING"),
    "meta_insights_daily": BASE
    | fields("level campaign_id adset_id ad_id currency timezone configuration_hash", "STRING")
    | fields("date_start date_stop", "DATE")
    | fields("impressions reach clicks link_clicks", "INT64")
    | fields("landing_page_views spend cpm cpc ctr", "NUMERIC")
    | fields("breakdown_values reporting_configuration", "JSON"),
}


def generate(root: Path = Path(".")) -> None:
    directory = root / "infra/terraform/meta_live_proposed"
    (directory / "schemas").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, schema in SCHEMAS.items():
        (directory / "schemas" / f"{name}.json").write_text(
            json.dumps(
                [
                    {
                        "name": field,
                        "type": typ,
                        "mode": "REQUIRED"
                        if field in {"row_key", "store_id", "account_id"}
                        else "NULLABLE",
                    }
                    for field, typ in schema.items()
                ],
                indent=2,
            )
            + "\n"
        )
        manifest[name] = {
            "dataset": "up_core",
            "partition": "date_start" if name == "meta_insights_daily" else None,
            "cluster": ["store_id", "account_id"],
            "deletion_protection": True,
        }
    (directory / "tables.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    generate()
