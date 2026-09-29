"""Absence handling for explicitly optional Customer projections only."""

from typing import Any


def optional_value(value: Any) -> Any:
    # Preserve nonempty values (including their spacing) and invalid types for the
    # existing validators. Never use this helper to relax required entity IDs.
    return None if isinstance(value, str) and not value.strip() else value
