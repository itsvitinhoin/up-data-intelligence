import pytest

from src.normalization.meta_url import parse_meta_url


@pytest.mark.parametrize(
    "query,status,expected",
    [
        ("campaign_id=001&adset_id=002&ad_id=003&adset_name=Teste%20A", "ok", "001"),
        ("campaign_id=1&campaign_id=1", "duplicate", "1"),
        ("campaign_id=1&campaign_id=2", "conflict", None),
        ("campaign_id=%7B%7Bcampaign.id%7D%7D", "placeholder", None),
        ("campaign_id=abc", "invalid_id", None),
        ("utm_source=a", "absent", None),
        ("campaign_id=%XY", "invalid_url", None),
    ],
)
def test_parser(query, status, expected):
    result = parse_meta_url("https://example.invalid/?" + query)
    assert result["parse_status"] == status
    assert result["meta_campaign_id"] == expected


@pytest.mark.parametrize(
    "value", [None, "", "not a URL", "javascript:alert(1)", "https://u:p@host/"]
)
def test_invalid_or_absent(value):
    assert parse_meta_url(value)["parse_status"] in {"absent", "invalid_url"}
