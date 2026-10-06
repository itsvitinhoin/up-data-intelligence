"""Server-owned, account-specific purchase reporting decisions; never attribution."""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from src.connectors.meta.config import Account, Insights
from src.domain.models import SafeError


@dataclass(frozen=True)
class PurchaseCertificate:
    account: Account
    action_report_time: str
    attribution_windows: tuple[str, ...]
    purchase_action_type: str
    evidence: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PurchaseCertificate":
        try:
            account = Account(**value["account"])
            report = Insights(
                "2026-01-01",
                "2026-01-01",
                value["action_report_time"],
                tuple(value["action_attribution_windows"]),
                value["purchase_action_type"],
            )
            if (
                not report.purchase_action_type
                or not isinstance(value["evidence"], str)
                or not value["evidence"]
            ):
                raise ValueError
            return cls(
                account,
                report.action_report_time,
                report.action_attribution_windows,
                report.purchase_action_type,
                value["evidence"],
            )
        except (ValueError, KeyError, TypeError):
            raise SafeError("meta_purchase_certificate_invalid") from None


def load_certificates(*, enabled: bool = False) -> tuple[PurchaseCertificate, ...]:
    # Explicit composition only. No SDK, secret or filesystem IO on import.
    if not enabled:
        return ()
    values = json.loads(Path(__file__).with_name("approved_purchase_reporting.json").read_text())
    records = tuple(PurchaseCertificate.from_dict(v) for v in values)
    if len({r.account.store_id for r in records}) != len(records):
        raise SafeError("meta_purchase_certificate_conflict")
    return records


def selected_reporting(
    account: Account, report: Insights, certificates: tuple[PurchaseCertificate, ...]
) -> Insights:
    matches = [c for c in certificates if c.account.store_id == account.store_id]
    if not matches:
        return report  # Uncertified accounts retain NULL platform purchase metrics.
    if len(matches) != 1:
        raise SafeError("meta_purchase_certificate_conflict")
    certificate = matches[0]
    if (
        certificate.account != account
        or certificate.action_report_time != report.action_report_time
        or set(certificate.attribution_windows) != set(report.action_attribution_windows)
        or report.breakdowns
        or report.purchase_action_type not in {None, certificate.purchase_action_type}
    ):
        raise SafeError("meta_purchase_certificate_definition_mismatch")
    return replace(report, purchase_action_type=certificate.purchase_action_type)
