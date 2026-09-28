import json
import logging
from typing import Any

# Allowlist, not best-effort regex over exceptions containing arbitrary PII.
SAFE_FIELDS = {
    "run_id",
    "store_id",
    "resource",
    "status",
    "http_status",
    "attempt",
    "records",
    "pages",
    "code",
    "duration_ms",
    "rule_id",
    "severity",
    "failed_count",
    "checked_count",
}


def configure() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("httpx", "httpcore", "google", "urllib3"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def event(name: str, **fields: Any) -> None:
    logging.getLogger("upzero").info(
        json.dumps({"event": name, **{k: v for k, v in fields.items() if k in SAFE_FIELDS}})
    )
