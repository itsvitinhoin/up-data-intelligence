import pytest

from src.bigquery.catalog import TABLES
from src.connectors.meta.foundation import FOUNDATION_FIELDS
from src.connectors.meta.live import MetaFoundationLiveConnector
from src.domain.models import SafeError
from src.normalization.meta_enrichment import enrichment, media_url
from tests.unit.test_meta_foundation import INSIGHTS


def test_official_creative_expansion_only_live_and_no_n_plus_one():
    assert "creative{id}" in FOUNDATION_FIELDS["ads"]
    fields = MetaFoundationLiveConnector.fields["ads"]
    assert "creative{id,name,image_url,thumbnail_url,video_id,effective_object_story_id}" in fields
    assert "creative_thumbnail_url" in TABLES["meta_live_ads"].fields
    assert "frequency" in TABLES["meta_live_insights_daily"].fields


def test_platform_values_keep_decimal_and_only_configured_purchase_action():
    action = INSIGHTS.purchase_action_type
    row = enrichment(
        "insights",
        {
            "frequency": "1.23456789",
            "actions": [
                {"action_type": action, "value": "2.5"},
                {"action_type": "other_purchase", "value": "99"},
            ],
            "action_values": [{"action_type": action, "value": "32.10"}],
        },
        INSIGHTS,
    )
    assert row["frequency"] == "1.23456789"
    assert row["meta_reported_purchases"] == "2.5"
    assert row["meta_reported_purchase_value"] == "32.10"
    assert "influenced" not in str(row)


def test_missing_conversion_not_zero_and_duplicate_purchase_not_added():
    value = enrichment("insights", {}, INSIGHTS)
    assert value["frequency"] is None and value["meta_reported_purchases"] is None
    with pytest.raises(SafeError, match="ambiguous_meta_action"):
        enrichment(
            "insights",
            {"actions": [{"action_type": INSIGHTS.purchase_action_type, "value": "1"}] * 2},
            INSIGHTS,
        )


def test_creative_durable_identity_separate_from_temporary_url():
    url = "https://scontent.example.fbcdn.net/preview.jpg?oh=temporary&oe=123"
    result = enrichment(
        "ads",
        {
            "creative": {
                "id": "001",
                "image_url": url,
                "video_id": "000123",
                "effective_object_story_id": "123_456",
            }
        },
        None,
    )
    assert result["creative_image_url"] == url
    assert result["creative_video_id"] == "000123"
    assert result["creative_name"] is None


@pytest.mark.parametrize(
    "value",
    [
        "http://scontent.fbcdn.net/image",
        "https://evil.test/image",
        "https://fbcdn.net.evil.test/image",
        "https://user:password@fbcdn.net/image",
        "https://fbcdn.net/image#[REDACTED]",
        "https://fbcdn.net/image?token=[REDACTED]",
    ],
)
def test_creative_url_cannot_be_arbitrary_browser_target(value):
    with pytest.raises(SafeError):
        media_url(value)
