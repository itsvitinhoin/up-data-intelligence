import pytest

from scripts.audit_meta_parser import categories
from src.normalization.meta_url import parse_meta_url


@pytest.mark.parametrize(
    "value,status,category",
    [
        (None, "absent", "parameters:absent"),
        ("https://example.invalid/", "absent", "parameters:absent"),
        (
            "https://example.invalid/?campaign_id=001&campaign_id=001",
            "duplicate",
            "parameters:duplicate",
        ),
        (
            "https://example.invalid/?campaign_id=001&campaign_id=002",
            "conflict",
            "campaign_id:conflict",
        ),
        ("https://example.invalid/?ad_id=text", "invalid_id", "ad_id:invalid_id"),
        ("https://example.invalid/?adset_id={{adset.id}}", "placeholder", "adset_id:placeholder"),
        (
            "https://example.invalid/?adset_name=Group[Remarketing]",
            "placeholder",
            "adset_name:placeholder",
        ),
        ("relative/path", "invalid_url", "url:invalid_url"),
        ("https://example.invalid/?campaign_id=%XX", "invalid_url", "url:invalid_url"),
    ],
)
def test_safe_aggregate_categories(value, status, category):
    assert parse_meta_url(value)["parse_status"] == status
    assert categories(value) == [category]


def test_multiple_bad_fields_no_values_or_pii():
    value = "https://example.invalid/?ad_id=private-value&adset_id={{adset.id}}&email=pii@example.invalid"
    assert categories(value) == ["adset_id:placeholder", "ad_id:invalid_id"]
