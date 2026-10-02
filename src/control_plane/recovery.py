"""Explicit ADMIN_UP recovery, separate from registry and ingestion/replay."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from src.control_plane.registry import Admin
from src.domain.models import RESOURCES, SafeError
from src.ingestion.checkpoints import CHECKPOINT_NEEDS_REVIEW, CHECKPOINT_RECOVERED
from src.observability.logging import event


def validate_target(store: str, original: str, replay: str) -> None:
    if not isinstance(store, str) or not store.strip():
        raise SafeError("checkpoint_recovery_invalid_target")
    try:
        UUID(original)
        UUID(replay)
    except (ValueError, TypeError, AttributeError):
        raise SafeError("checkpoint_recovery_invalid_target") from None
    if original == replay:
        raise SafeError("checkpoint_recovery_replay_mismatch")


@dataclass(frozen=True)
class RecoveryProof:
    store_id: str
    checkpoint_key: str
    resource: str
    original_run_id: str
    replay_run_id: str

    @classmethod
    def from_row(
        cls,
        row: dict[str, Any],
        store: str,
        original: str,
        replay: str | None,
        *,
        expected_status: str = CHECKPOINT_NEEDS_REVIEW,
    ) -> "RecoveryProof":
        # Computed proof comes from the shared query, including in the CAS transaction.
        if not isinstance(row, dict) or expected_status not in {
            CHECKPOINT_NEEDS_REVIEW,
            CHECKPOINT_RECOVERED,
        }:
            raise SafeError("checkpoint_recovery_invalid_proof")
        counters = (
            "checkpoint_count",
            "pending_count",
            "original_count",
            "original_valid_count",
            "successful_replay_count",
        )
        if (
            row.get("store_id") != store
            or row.get("original_run_id") != original
            or any(type(row.get(k)) is not int or row[k] < 0 for k in counters)
        ):
            raise SafeError("checkpoint_recovery_invalid_proof")
        if row["checkpoint_count"] == 0:
            raise SafeError("checkpoint_recovery_checkpoint_missing")
        if row["checkpoint_count"] != 1:
            raise SafeError("checkpoint_recovery_checkpoint_ambiguous")
        if (
            not isinstance(row.get("resource"), str)
            or row["resource"] not in RESOURCES
            or not isinstance(row.get("checkpoint_key"), str)
            or not row["checkpoint_key"]
            or row["pending_count"] != 0
            or row.get("checkpoint_status") not in {expected_status, CHECKPOINT_RECOVERED}
        ):
            raise SafeError("checkpoint_recovery_checkpoint_invalid")
        if row["original_count"] != 1 or row["original_valid_count"] != 1:
            raise SafeError("checkpoint_recovery_original_invalid")
        if row["successful_replay_count"] == 0:
            raise SafeError("checkpoint_recovery_replay_missing")
        if row["successful_replay_count"] != 1:
            raise SafeError("checkpoint_recovery_replay_ambiguous")
        successful = row.get("successful_replay_id")
        if (
            not isinstance(successful, str)
            or not successful
            or (replay is not None and successful != replay)
        ):
            raise SafeError("checkpoint_recovery_replay_mismatch")
        if (
            expected_status == CHECKPOINT_NEEDS_REVIEW
            and row["checkpoint_status"] == CHECKPOINT_RECOVERED
        ):
            raise SafeError("checkpoint_already_recovered")
        return cls(store, row["checkpoint_key"], row["resource"], original, successful)


class RecoveryRepository(Protocol):
    def proof(self, store: str, original: str, replay: str) -> RecoveryProof: ...
    def recover(self, proof: RecoveryProof) -> None: ...


class CheckpointRecovery:
    def __init__(
        self,
        repository: RecoveryRepository,
        lease: Callable[[str], AbstractContextManager[None]],
    ):
        self.repository, self.lease = repository, lease

    def recover(self, admin: Admin, store: str, original: str, replay: str) -> RecoveryProof:
        admin.authorize()  # Before ALL reads/writes and even lease acquisition.
        validate_target(store, original, replay)
        with self.lease(store):
            event(
                "checkpoint_recovery_started",
                store_id=store,
                resource="checkpoint",
                status="validating",
            )
            proof = self.repository.proof(store, original, replay)
            if (proof.store_id, proof.original_run_id, proof.replay_run_id) != (
                store,
                original,
                replay,
            ):
                raise SafeError("checkpoint_recovery_invalid_proof")
            self.repository.recover(proof)
            event(
                "checkpoint_recovery_completed",
                store_id=store,
                resource=proof.resource,
                status=CHECKPOINT_RECOVERED,
            )
            return proof
