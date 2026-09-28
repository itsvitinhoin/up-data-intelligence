from unittest.mock import Mock

import pytest

from src.domain.models import SafeError
from src.security.lease import cloud_lease
from src.security.secrets import resolve_secret


def test_secret_reference_only(monkeypatch):
    import google.cloud.secretmanager as sm

    client = Mock()
    client.access_secret_version.return_value.payload.data = b"SYNTHETIC"
    monkeypatch.setattr(sm, "SecretManagerServiceClient", lambda: client)
    assert resolve_secret("projects/example-project/secrets/pilot/versions/latest") == "SYNTHETIC"
    client.access_secret_version.assert_called_once_with(
        name="projects/example-project/secrets/pilot/versions/latest"
    )


def test_secret_error_never_leaks(monkeypatch):
    import google.cloud.secretmanager as sm

    monkeypatch.setattr(
        sm, "SecretManagerServiceClient", Mock(side_effect=RuntimeError("DO_NOT_LEAK"))
    )
    with pytest.raises(SafeError, match="secret_resolution_failed") as e:
        resolve_secret("projects/example-project/secrets/pilot/versions/1")
    assert "DO_NOT_LEAK" not in str(e.value)
    with pytest.raises(SafeError, match="invalid_secret_reference"):
        resolve_secret("an actual key")


def test_cloud_lock_generation_guard(monkeypatch):
    import google.cloud.storage as storage

    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.generation = 7
    monkeypatch.setattr(storage, "Client", lambda: client)
    with cloud_lease("synthetic-bucket", "A"):
        pass
    assert blob.upload_from_string.call_args.kwargs["if_generation_match"] == 0
    blob.delete.assert_called_once_with(if_generation_match=7)


def test_cloud_lock_contention_safe(monkeypatch):
    import google.cloud.storage as storage

    client = Mock()
    client.bucket.return_value.blob.return_value.upload_from_string.side_effect = RuntimeError(
        "DO_NOT_LEAK"
    )
    monkeypatch.setattr(storage, "Client", lambda: client)
    with pytest.raises(SafeError, match="store_busy_or_lease_unavailable"):
        with cloud_lease("synthetic", "A"):
            pass
