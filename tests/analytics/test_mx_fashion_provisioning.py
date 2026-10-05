"""Approved non-secret policy and table-only activation; no Terraform/cloud calls."""

import json
import shutil
from pathlib import Path

from src.analytics.config import AnalyticsPolicy
from src.analytics.provisioning import ACTIVE_ANALYTICS_TABLES
from src.analytics.schema import SCHEMAS
from src.bigquery.catalog import META_TABLE_NAMES, TABLES
from src.bigquery.schema import generate

ROOT = Path(__file__).resolve().parents[2]
POLICY_HASH = "3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c"


def test_official_mx_fashion_policy_exact_approved_contract():
    data = json.loads((ROOT / "config/analytics/mx-fashion.dev.json").read_text())
    assert data == {
        "store_id": "mx-fashion",
        "policy_version": "1.0.0",
        "reporting_timezone": "America/Sao_Paulo",
        "currency": "BRL",
        "qualifying_order_statuses": ["RESERVED", "CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED"],
        "history_complete": False,
        "facts_complete": True,
        "history_from": "2026-09-01T00:00:00Z",
        "report_from": "2026-09-01",
        "report_to": "2026-09-28",
        "as_of": "2026-09-28T03:00:00Z",
        "history_coverage": None,
        "allow_unknown_currency_local": False,
    }
    policy = AnalyticsPolicy.from_dict(data)
    reference = policy.reference()
    assert policy.policy_hash == reference.key == POLICY_HASH
    assert "RESERVED" in reference.purchase_statuses
    assert "CANCELED" not in reference.purchase_statuses
    assert reference.local_date(reference.as_of) == "2026-09-28"


def test_exactly_eight_active_tables_preserve_schemas_and_existing_metadata():
    folder = ROOT / "infra/terraform"
    active = json.loads((folder / "tables.json").read_text())
    assert len(ACTIVE_ANALYTICS_TABLES) == 8
    from src.intelligence.live.schema import META_ACTIVE

    creative_tables = {"meta_creative_insights_daily", "meta_creative_insights_daily_versions"}
    from src.intelligence.live.schema import SCHEMAS as LIVE

    assert (
        set(active)
        == (set(TABLES) - META_TABLE_NAMES)
        | ACTIVE_ANALYTICS_TABLES
        | META_ACTIVE
        | set(LIVE)
        | creative_tables
    )
    for name, spec in TABLES.items():
        if name not in META_TABLE_NAMES:
            assert active[name] == {
                "dataset": spec.dataset,
                "partition": spec.partition,
                "cluster": list(spec.cluster),
            }
    for name in ACTIVE_ANALYTICS_TABLES:
        assert (folder / "schemas" / f"{name}.json").read_bytes() == (
            folder / "analytics_proposed/schemas" / f"{name}.json"
        ).read_bytes()
        assert active[name]["dataset"] == "up_analytics"
    for name, spec in SCHEMAS.items():
        assert active[name]["partition"] == spec.partition
        assert active[name]["cluster"] == list(spec.cluster)
    assert active["analytics_publications"] == {
        "dataset": "up_analytics",
        "partition": None,
        "cluster": ["store_id", "policy_hash", "record_kind"],
    }
    assert set(active) & META_TABLE_NAMES == META_ACTIVE | creative_tables


def test_regeneration_keeps_table_promotion_idempotent(tmp_path, monkeypatch):
    source = ROOT / "infra/terraform"
    shutil.copytree(source / "analytics_proposed", tmp_path / "infra/terraform/analytics_proposed")
    monkeypatch.chdir(tmp_path)
    generate()
    active = tmp_path / "infra/terraform"
    assert (active / "tables.json").read_bytes() == (source / "tables.json").read_bytes()
    for schema in (source / "schemas").glob("*.json"):
        assert (active / "schemas" / schema.name).read_bytes() == schema.read_bytes()
    before = (active / "tables.json").read_bytes()
    generate()
    assert (active / "tables.json").read_bytes() == before
