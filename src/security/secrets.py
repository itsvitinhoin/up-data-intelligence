import re

from src.domain.models import SafeError


def validate_secret_reference(reference: str, *, numeric_only: bool = False) -> None:
    version = r"[1-9][0-9]*" if numeric_only else r"(?:[0-9]+|latest)"
    if not re.fullmatch(r"projects/[\w-]+/secrets/[\w-]+/versions/" + version, reference):
        raise SafeError("invalid_secret_reference")


def resolve_secret(reference: str) -> str:
    validate_secret_reference(reference)
    try:
        from google.cloud import secretmanager

        result = secretmanager.SecretManagerServiceClient().access_secret_version(name=reference)
        value = result.payload.data.decode("utf-8").strip()
        if not value:
            raise ValueError
        return value
    except Exception:
        raise SafeError("secret_resolution_failed") from None
