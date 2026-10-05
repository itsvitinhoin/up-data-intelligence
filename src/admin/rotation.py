"""One version write after durable intent; uncertainty permits only metadata reconciliation."""

import hmac
import re
from typing import Any

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.admin.contracts import AdminError
from src.domain.models import SafeError
from src.security.secrets import validate_secret_reference


class RotationStore:
    def __init__(self, client: Any, project: str, project_number: str):
        self.client, self.project, self.number = client, project, project_number

    def parent(self, reference: str) -> str:
        validate_secret_reference(reference, numeric_only=True)
        if not reference.startswith(f"projects/{self.project}/secrets/up-intelligence-upzero-"):
            raise AdminError("integration_secret_adoption_required")
        return reference.rsplit("/versions/", 1)[0]

    def canonical(self, name: str, parent: str) -> str:
        for project in (self.project, self.number):
            prefix = parent.replace("/" + self.project + "/", "/" + project + "/", 1) + "/versions/"
            if name.startswith(prefix) and re.fullmatch("[1-9][0-9]*", name[len(prefix) :]):
                return parent + "/versions/" + name[len(prefix) :]
        raise SafeError("secret_write_outcome_unknown")

    def versions(self, reference: str) -> list[str]:
        parent = self.parent(reference)
        rows = []
        try:
            for v in self.client.list_secret_versions(parent=parent, retry=None, timeout=10):
                rows.append(self.canonical(v.name, parent))
                if len(rows) > 1000:
                    raise AdminError("integration_version_inventory_limit")
            if len(set(rows)) != len(rows):
                raise AdminError("integration_version_inventory_invalid")
            return sorted(rows)
        except (AdminError, SafeError):
            raise
        except Exception:
            raise AdminError("integration_secret_metadata_unavailable", 503) from None

    def compare(self, reference: str, credential: str) -> None:
        self.parent(reference)
        try:
            value = self.client.access_secret_version(
                name=reference, retry=None, timeout=10
            ).payload.data
            if not hmac.compare_digest(bytes(value), credential.encode()):
                raise AdminError("credential_retry_mismatch")
        except AdminError:
            raise
        except Exception:
            raise AdminError("integration_secret_read_failed", 503) from None

    def candidate(self, reference: str, baseline: list[str], credential: str) -> str:
        added = set(self.versions(reference)) - set(baseline)
        if len(added) != 1:
            raise SafeError("secret_write_outcome_unknown")
        result = added.pop()
        self.compare(result, credential)
        return result

    def rotate(
        self, reference: str, baseline: list[str], credential: str, *, reconcile_only: bool
    ) -> str:
        parent = self.parent(reference)
        if reconcile_only:
            return self.candidate(reference, baseline, credential)
        if reference not in baseline or self.versions(reference) != baseline:
            raise AdminError("integration_version_inventory_changed")
        try:
            v = self.client.add_secret_version(
                parent=parent, payload={"data": credential.encode()}, retry=None, timeout=10
            )
        except (BadRequest, Forbidden, Unauthorized):
            raise AdminError("integration_secret_write_rejected", 503) from None
        except Exception:
            # Only metadata/compare. Never repeat the add after a lost response.
            try:
                return self.candidate(reference, baseline, credential)
            except Exception:
                raise SafeError("secret_write_outcome_unknown") from None
        result = self.canonical(v.name, parent)
        self.compare(result, credential)
        return result
