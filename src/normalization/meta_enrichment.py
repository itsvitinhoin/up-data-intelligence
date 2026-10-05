"""Provider evidence only: platform-reported conversions never become influence."""

import re
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from src.connectors.meta.config import Insights, meta_id
from src.domain.models import SafeError
from src.normalization.meta import action_value, optional_text
from src.utils.data import numeric


def media_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 32 for c in value):
        raise SafeError("invalid_meta_creative_url")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
        or not any(
            host == domain or host.endswith("." + domain)
            for domain in ("fbcdn.net", "fbsbx.com", "cdninstagram.com")
        )
        or "[REDACTED]" in value
        or any(
            key.lower() in {"access_token", "token", "api_key", "secret"}
            for key, _ in parse_qsl(parsed.query)
        )
    ):
        # Do not turn credential-bearing/unsupported URLs into browser fetch targets.
        raise SafeError("invalid_meta_creative_url")
    return value


def enrichment(resource: str, source: dict[str, Any], insights: Insights | None) -> dict[str, Any]:
    if resource == "ads":
        creative = source.get("creative")
        if creative is not None and not isinstance(creative, dict):
            raise SafeError("invalid_meta_creative")
        creative = creative or {}
        story = creative.get("effective_object_story_id")
        if story is not None and (
            not isinstance(story, str) or not re.fullmatch(r"[0-9]+_[0-9]+", story)
        ):
            raise SafeError("invalid_meta_creative_story")
        return {
            "creative_name": optional_text(creative.get("name")),
            "creative_image_url": media_url(creative.get("image_url")),
            "creative_thumbnail_url": media_url(creative.get("thumbnail_url")),
            "creative_video_id": meta_id(creative["video_id"])
            if creative.get("video_id") is not None
            else None,
            "creative_story_id": story,
        }
    if resource == "insights":
        if insights is None:
            raise SafeError("meta_insights_configuration_missing")
        frequency = numeric(source.get("frequency"))
        if frequency is not None and Decimal(frequency) < 0:
            raise SafeError("invalid_meta_metric")
        for key in ("actions", "action_values"):
            rows = source.get(key)
            if rows is not None and (
                not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows)
            ):
                raise SafeError("invalid_meta_actions")
        purchases = action_value(source.get("actions"), insights.purchase_action_type)
        value = action_value(source.get("action_values"), insights.purchase_action_type)
        if any(Decimal(v) < 0 for v in (purchases, value) if v is not None):
            raise SafeError("invalid_meta_metric")
        return {
            "frequency": frequency,
            "actions": source.get("actions"),
            "action_values": source.get("action_values"),
            "purchase_action_type": insights.purchase_action_type,
            "meta_reported_purchases": purchases,
            "meta_reported_purchase_value": value,
        }
    return {}
