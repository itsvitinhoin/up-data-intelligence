from datetime import datetime
from typing import Any

from src.utils.data import digest, now, timestamp


def result(
    store: str,
    run: str,
    resource: str,
    rule: str,
    severity: str,
    record: str = "",
    failed: int = 1,
    checked: int = 1,
) -> dict[str, Any]:
    return {
        "row_key": digest([store, run, resource, rule, record]),
        "store_id": store,
        "run_id": run,
        "resource": resource,
        "rule_id": rule,
        "severity": severity,
        "record_id": record,
        "failed_count": failed,
        "checked_count": checked,
        "checked_at": now(),
    }


def purchase_severity(occurred: str, effective: str | None) -> str:
    return (
        "alert"
        if effective
        and datetime.fromisoformat(timestamp(occurred))
        >= datetime.fromisoformat(timestamp(effective))
        else "warning"
    )


def stale(last_success: str | None, at: str, minutes: int) -> bool:
    return (
        last_success is None
        or (
            datetime.fromisoformat(timestamp(at)) - datetime.fromisoformat(timestamp(last_success))
        ).total_seconds()
        > minutes * 60
    )
