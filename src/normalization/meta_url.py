import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

VERSION = "1.0.0"
FIELDS = ("campaign_id", "adset_id", "ad_id", "adset_name")


def parse_meta_url(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"meta_" + k: None for k in FIELDS}
    result.update(parser_version=VERSION, parse_status="absent")
    if not value:
        return result
    try:
        if (
            not isinstance(value, str)
            or len(value) > 32768
            or re.search(r"%(?![0-9a-fA-F]{2})", value)
        ):
            raise ValueError
        u = urlsplit(value)
        if (
            u.scheme not in {"https", "http"}
            or not u.hostname
            or u.username
            or re.search(r"[\s\x00-\x1f]", u.netloc)
        ):
            raise ValueError
        params = parse_qs(u.query, keep_blank_values=True, max_num_fields=256, errors="strict")
    except (ValueError, UnicodeError):
        result["parse_status"] = "invalid_url"
        return result
    statuses: set[str] = set()
    for field in FIELDS:
        values = params.get(field, [])
        if not values:
            continue
        if len(set(values)) > 1:
            statuses.add("conflict")
            continue
        v = values[0]
        if not v:
            continue
        if any(x in v for x in ("{", "}", "<", ">", "[", "]")) or re.search(
            r"(?i)(placeholder|campaign\.id|adset\.id|ad\.id)", v
        ):
            statuses.add("placeholder")
            continue
        if field != "adset_name" and not re.fullmatch(r"[0-9]+", v):
            statuses.add("invalid_id")
            continue
        result["meta_" + field] = v
        statuses.add("duplicate" if len(values) > 1 else "ok")
    result["parse_status"] = next(
        (s for s in ("conflict", "placeholder", "invalid_id", "duplicate", "ok") if s in statuses),
        "absent",
    )
    return result
