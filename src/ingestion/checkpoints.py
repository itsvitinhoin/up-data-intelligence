"""Canonical checkpoint lifecycle; terminal recovery never means fresh collection."""

from typing import Any

CHECKPOINT_COMPLETE = "complete"
CHECKPOINT_RECOVERED = "recovered"
CHECKPOINT_NEEDS_REVIEW = "needs_review"
CHECKPOINT_RUNNING = "running"
CHECKPOINT_EXTRACTED = "extracted"
TERMINAL_CHECKPOINT_STATUSES = frozenset({CHECKPOINT_COMPLETE, CHECKPOINT_RECOVERED})


def checkpoint_pending(checkpoint: dict[str, Any]) -> bool:
    return (
        checkpoint.get("status") not in TERMINAL_CHECKPOINT_STATUSES
        or checkpoint.get("pending_raw_id") is not None
    )
