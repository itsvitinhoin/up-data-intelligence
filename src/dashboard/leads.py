"""Operational registration counts. Person identity is not event identity."""

from decimal import Decimal
from typing import Any

from src.dashboard.contracts import ReadError, integer


def operational_counts(row: dict[str, Any], *, facts_complete: bool) -> dict[str, Any]:
    """The reader deduplicates explicit fact IDs in one certified period/snapshot.

    Approval backlog is allowed: qualification may exceed 100%. Conversion is
    unavailable until registration/customer evidence can prove the exact join.
    It must never be derived from user-ID equality or fulfillment/payment.
    """
    generated, approved, invalid, conflicts = (
        integer(row.get(k)) for k in ("generated", "approved", "invalid_identity", "conflicts")
    )
    if any(v is None or v < 0 for v in (generated, approved, invalid, conflicts)):
        raise ReadError(503, "lead_evidence_invalid")
    assert generated is not None and approved is not None
    if conflicts:
        raise ReadError(503, "lead_event_identity_conflict")
    covered = facts_complete and invalid == 0
    unresolved, converted = integer(row.get("unresolved_approved")), integer(row.get("converted"))
    if any(v is not None and v < 0 for v in (unresolved, converted)) or (
        converted is not None and converted > approved
    ):
        raise ReadError(503, "lead_conversion_evidence_invalid")
    conversion_covered = covered and unresolved == 0 and converted is not None
    return {
        "leads_generated": generated if covered else None,
        "leads_approved": approved if covered else None,
        "lead_qualification_rate": format(Decimal(approved) * 100 / Decimal(generated), "f")
        if covered and generated
        else None,
        "approved_conversion_rate": format(Decimal(converted) * 100 / Decimal(approved), "f")
        if conversion_covered and approved and converted is not None
        else None,
        "approved_converted": converted if conversion_covered else None,
        "lead_coverage": {
            "operational_counts": covered,
            "conversion": conversion_covered,
            "basis": "canonical_registration_events_in_selected_period",
            "limitations": (
                [] if conversion_covered else ["registration_customer_identity_not_certified"]
            )
            + ([] if covered else ["registration_event_coverage_incomplete"]),
        },
    }
