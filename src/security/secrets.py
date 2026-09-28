import re

from src.domain.models import SafeError


def resolve_secret(reference: str) -> str:
    if not re.fullmatch(r"projects/[\w-]+/secrets/[\w-]+/versions/(?:[0-9]+|latest)", reference):
        raise SafeError("invalid_secret_reference")
    try:
        from google.cloud import secretmanager

        result = secretmanager.SecretManagerServiceClient().access_secret_version(name=reference)
        value = result.payload.data.decode("utf-8").strip()
        if not value:
            raise ValueError
        return value
    except Exception:
        raise SafeError("secret_resolution_failed") from None
