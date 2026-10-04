"""The independent SQL oracle must compare one lossless, store-scoped snapshot."""

import pytest

from src.analytics.schema import SCHEMAS
from src.analytics.sql_models import SOURCE_FIELDS, compile_model


@pytest.mark.parametrize("model", SCHEMAS)
def test_audit_reference_pins_all_core_inputs(model):
    sql = compile_model(model, project="up-data-intelligence-dev", snapshot=True)
    for table in SOURCE_FIELDS:
        assert (
            f"FROM `up-data-intelligence-dev.up_core.{table}` "
            "FOR SYSTEM_TIME AS OF @source_snapshot_at WHERE store_id=@store"
        ) in sql
    assert sql.count("FOR SYSTEM_TIME AS OF @source_snapshot_at") == len(SOURCE_FIELDS)
    assert "@date_from" in sql and "@date_to" in sql
    assert "mx-fashion" not in sql
    assert "2026-10" not in sql
    assert "FOR SYSTEM_TIME" not in compile_model(model, project="up-data-intelligence-dev")


def test_fixture_snapshot_cannot_silently_use_live_sources():
    with pytest.raises(ValueError, match="fixture_snapshot_not_supported"):
        compile_model(
            "analytics_store_daily",
            project="up-data-intelligence-dev",
            fixtures=True,
            snapshot=True,
        )
