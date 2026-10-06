from dataclasses import replace
from pathlib import Path

import pytest

from src.connectors.meta.config import Insights
from src.connectors.meta.purchase_reporting import (
    PurchaseCertificate,
    load_certificates,
    selected_reporting,
)
from src.domain.models import SafeError
from src.normalization.meta_enrichment import enrichment
from tests.unit.test_meta_foundation import ACCOUNT


def certificate():
    return PurchaseCertificate(
        ACCOUNT,
        "impression",
        ("7d_click",),
        "offsite_conversion.fb_pixel_purchase",
        "synthetic parity evidence",
    )


def test_purchase_selection_preserves_reporting_and_does_not_sum_overlapping_families():
    report = Insights("2026-01-01", "2026-01-02", "impression", ("7d_click",), None)
    selected = selected_reporting(ACCOUNT, report, (certificate(),))
    assert report.purchase_action_type is None
    assert selected.since == report.since and selected.until == report.until
    result = enrichment(
        "insights",
        {
            "actions": [
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2"},
                {"action_type": "purchase", "value": "2"},
                {"action_type": "omni_purchase", "value": "2"},
            ],
            "action_values": [
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "6514.69"},
                {"action_type": "purchase", "value": "999"},
            ],
        },
        selected,
    )
    assert result["meta_reported_purchases"] == "2"
    assert result["meta_reported_purchase_value"] == "6514.69"
    assert "requested" not in result and "influenced" not in result


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", "000102"),
        ("connection_id", "different"),
        ("api_version", "v24.0"),
        ("currency", "USD"),
        ("timezone", "UTC"),
    ],
)
def test_certificate_never_survives_account_configuration_drift(field, value):
    account = replace(ACCOUNT, **{field: value})
    with pytest.raises(SafeError, match="definition_mismatch"):
        selected_reporting(
            account,
            Insights("2026-01-01", "2026-01-01", "impression", ("7d_click",), None),
            (certificate(),),
        )


def test_uncertified_store_and_default_composition_remain_unavailable():
    assert load_certificates() == ()
    report = Insights("2026-01-01", "2026-01-01", "impression", ("7d_click",), None)
    assert (
        selected_reporting(replace(ACCOUNT, store_id="different"), report, (certificate(),))
        is report
    )
    with pytest.raises(SafeError, match="conflict"):
        selected_reporting(ACCOUNT, report, (certificate(), certificate()))
    with pytest.raises(SafeError, match="definition_mismatch"):
        selected_reporting(
            ACCOUNT, replace(report, action_report_time="conversion"), (certificate(),)
        )
    with pytest.raises(SafeError, match="definition_mismatch"):
        selected_reporting(
            ACCOUNT, replace(report, action_attribution_windows=("1d_click",)), (certificate(),)
        )


def test_versioned_mx_certificate_is_nonsecret_and_exact():
    rows = load_certificates(enabled=True)
    assert len(rows) == 1 and rows[0].account.store_id == "mx-fashion"
    assert rows[0].account.api_version == "v26.0"
    assert rows[0].purchase_action_type == "offsite_conversion.fb_pixel_purchase"


def test_build_upload_and_image_preserve_only_the_reviewed_reporting_json():
    root = Path(__file__).resolve().parents[2]
    entry = "!src/connectors/meta/approved_purchase_reporting.json"
    for filename in (".gcloudignore", ".dockerignore"):
        rules = (root / filename).read_text().splitlines()
        assert entry in rules
        assert "!src/**/*.json" not in rules
        assert "!**/*.json" not in rules
