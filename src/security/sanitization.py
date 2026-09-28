"""Remove authentication material before ANY persistence; keep business/tracking values."""

import json
import re
from typing import Any
from urllib.parse import unquote, urlsplit

REDACTED = "[REDACTED]"
POLICY_VERSION = "1.0.0"
BLOCKED = frozenset(
    {
        "password",
        "passwordhash",
        "passwd",
        "pwd",
        "apikey",
        "xapikey",
        "secret",
        "clientsecret",
        "accesssecret",
        "accesstoken",
        "refreshtoken",
        "recoverytoken",
        "authorization",
        "proxyauthorization",
        "idtoken",
        "bearertoken",
        "authtoken",
        "token",
        "privatekey",
        "signingkey",
        "sessiontoken",
        "sessioncookie",
        "cookie",
        "setcookie",
        "recoveryurl",
        "jwt",
        "sessionkey",
        "resettoken",
        "credentials",
        "signature",
        "xamzsignature",
        "xgoogsignature",
        "xgoogcredential",
        "headers",
        "requestheaders",
        "responseheaders",
    }
)


def blocked(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in BLOCKED or normalized.endswith(
        (
            "password",
            "passwordhash",
            "secret",
            "accesstoken",
            "refreshtoken",
            "apikey",
            "privatekey",
        )
    )


def sanitize(value: Any, known_secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            k: REDACTED if blocked(str(k)) else sanitize(v, known_secrets) for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v, known_secrets) for v in value]
    if not isinstance(value, str):
        return value
    result = value
    for secret in known_secrets:
        if secret:
            result = result.replace(secret, REDACTED)
    # Nested JSON in free-form metadata is not a safe hiding place for credentials.
    if result.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(result)
            safe = sanitize(parsed, known_secrets)
            if safe != parsed:
                return json.dumps(safe, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
    # Preserve untouched URLs byte-for-byte; redact only credential query/fragment pairs.
    result = re.sub(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", result)
    result = re.sub(
        r"(?i)(password(?:_hash)?|api[_-]?key|access[_-]?token|refresh[_-]?token|secret|authorization)\s*[:=]\s*([^\s&,;]+)",
        lambda m: m.group(1) + "=" + REDACTED,
        result,
    )
    if "://" in result:
        try:
            u = urlsplit(result)
            if u.username is not None:
                result = result.replace(u.netloc, u.netloc.rsplit("@", 1)[-1], 1)
        except ValueError:
            return REDACTED

    def pair(m: re.Match[str]) -> str:
        return (
            m.group(1) + m.group(2) + "=" + REDACTED if blocked(unquote(m.group(2))) else m.group(0)
        )

    return re.sub(r"([?&#;])([^=&#;]+)=([^&#;]*)", pair, result)
