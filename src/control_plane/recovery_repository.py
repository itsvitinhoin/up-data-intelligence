"""Bounded metadata reads and fail-closed transactional checkpoint recovery."""

from typing import Any

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.analytics.cloud.transport import Transport, scalar
from src.control_plane.recovery import RecoveryProof
from src.control_plane.recovery_queries import mutation_query, proof_query
from src.domain.models import SafeError
from src.ingestion.checkpoints import CHECKPOINT_NEEDS_REVIEW, CHECKPOINT_RECOVERED


class BigQueryRecovery:
    def __init__(self, transport: Transport):
        self.transport = transport

    def proof(
        self,
        store: str,
        original: str,
        replay: str | None,
        *,
        expected_status: str = CHECKPOINT_NEEDS_REVIEW,
        snapshot: str | None = None,
    ) -> RecoveryProof:
        parameters = [scalar("store", "STRING", store), scalar("original", "STRING", original)]
        if snapshot is not None:
            parameters.append(scalar("snapshot", "TIMESTAMP", snapshot))
        try:
            rows, _ = self.transport.query(
                proof_query(self.transport.config.project, snapshot=snapshot is not None),
                parameters,
            )
        except Exception:
            raise SafeError("checkpoint_recovery_read_failed") from None
        if len(rows) != 1:
            raise SafeError("checkpoint_recovery_invalid_proof")
        return RecoveryProof.from_row(
            rows[0], store, original, replay, expected_status=expected_status
        )

    def recovered(
        self, checkpoint: dict[str, Any], store: str, *, snapshot: str | None = None
    ) -> RecoveryProof:
        if (
            checkpoint.get("store_id") != store
            or checkpoint.get("status") != CHECKPOINT_RECOVERED
            or checkpoint.get("pending_raw_id") is not None
        ):
            raise SafeError("checkpoint_recovery_invalid_proof")
        proof = self.proof(
            store,
            checkpoint.get("run_id", ""),
            None,
            expected_status=CHECKPOINT_RECOVERED,
            snapshot=snapshot,
        )
        if proof.checkpoint_key != checkpoint.get("row_key") or proof.resource != checkpoint.get(
            "resource"
        ):
            raise SafeError("checkpoint_recovery_invalid_proof")
        return proof

    def recover(self, proof: RecoveryProof) -> None:
        parameters = [
            scalar("store", "STRING", proof.store_id),
            scalar("original", "STRING", proof.original_run_id),
            scalar("replay", "STRING", proof.replay_run_id),
            scalar("checkpoint", "STRING", proof.checkpoint_key),
            scalar("resource", "STRING", proof.resource),
        ]
        try:
            self.transport.query(mutation_query(self.transport.config.project), parameters)
        except (BadRequest, Forbidden, Unauthorized):
            raise SafeError("checkpoint_recovery_failed") from None
        except Exception:
            # Never retry a script whose COMMIT may have occurred; retain the store lease.
            raise SafeError("checkpoint_recovery_outcome_unknown") from None
