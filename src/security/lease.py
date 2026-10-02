"""One writer per store. Cloud lock never auto-expires: crash recovery is explicit."""

import fcntl
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.domain.models import SafeError
from src.utils.data import digest


@contextmanager
def local_lease(path: str) -> Iterator[None]:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafeError("store_busy") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def cloud_lease(bucket: str, store: str) -> Iterator[None]:
    import google.cloud.storage as storage

    blob = storage.Client().bucket(bucket).blob("leases/" + digest(store))
    try:
        blob.upload_from_string(str(uuid.uuid4()), if_generation_match=0, content_type="text/plain")
    except Exception:
        raise SafeError("store_busy_or_lease_unavailable") from None
    uncertain = False
    try:
        yield
    except SafeError as exc:
        uncertain = exc.code in {
            "bigquery_write_outcome_unknown",
            "worker_execution_outcome_unknown",
            "registry_write_outcome_unknown",
            "checkpoint_recovery_outcome_unknown",
        }
        raise
    finally:
        if uncertain:
            # The previous BigQuery job might still commit. Operator must resolve
            # it before any retry; do not release the single-writer lease.
            pass
        else:
            _release(blob)


def _release(blob: Any) -> None:
    try:
        blob.delete(if_generation_match=blob.generation)
    except Exception:
        raise SafeError("lease_release_failed_operator_recovery_required") from None
