"""Injected Secret Manager client. No blind retry, delete, rotation or global Meta token."""

import hmac
import re
from typing import Any, Protocol

from google.api_core.exceptions import AlreadyExists, BadRequest, Forbidden, NotFound, Unauthorized

from src.admin.contracts import AdminError
from src.control_plane.model import StoreConfig
from src.security.secrets import validate_secret_reference


def pinned_reference(reference: Any, store: str, *, project: str | None = None) -> str:
    try:
        if not isinstance(reference, str):
            raise ValueError
        validate_secret_reference(reference, numeric_only=True)
        parts = reference.split("/")
        if parts[3] != "up-intelligence-upzero-" + store or (
            project is not None and parts[1] != project
        ):
            raise ValueError
        return reference
    except Exception:
        raise AdminError("onboarding_metadata_invalid", 503) from None


class SecretStore(Protocol):
    def container(self, store: str, owner: str, *, reconcile_only: bool) -> None: ...
    def initial(self, store: str, owner: str, credential: str, *, reconcile_only: bool) -> str: ...
    def compare(self, reference: str, credential: str) -> None: ...


class SecretManagerStore:
    def __init__(
        self, client: Any, *, project: str, project_number: str, region: str, environment: str
    ):
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project)
            or not project_number.isdigit()
            or not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", region)
            or environment not in {"dev", "staging", "prod"}
        ):
            raise ValueError("invalid_secret_store_configuration")
        self.client, self.project, self.number, self.region, self.environment = (
            client,
            project,
            project_number,
            region,
            environment,
        )

    def name(self, store: str) -> str:
        StoreConfig(store)  # Existing stable ID validator; namespace is never caller supplied.
        return f"projects/{self.project}/secrets/up-intelligence-upzero-{store}"

    def owned(self, metadata: Any, owner: str) -> None:
        if dict(metadata.labels) != {
            "application": "up-data-intelligence",
            "environment": self.environment,
            "onboarding-operation": owner,
        }:
            raise AdminError("secret_name_collision")
        replicas = metadata.replication.user_managed.replicas
        if [r.location for r in replicas] != [self.region]:
            raise AdminError("secret_name_collision")

    def container(self, store: str, owner: str, *, reconcile_only: bool) -> None:
        name = self.name(store)
        try:
            try:
                found = self.client.get_secret(name=name, retry=None, timeout=10)
            except NotFound:
                if reconcile_only:
                    raise AdminError("secret_write_outcome_unknown", 503) from None
                try:
                    found = self.client.create_secret(
                        parent=f"projects/{self.project}",
                        secret_id=name.rsplit("/", 1)[1],
                        secret={
                            "labels": {
                                "application": "up-data-intelligence",
                                "environment": self.environment,
                                "onboarding-operation": owner,
                            },
                            "replication": {
                                "user_managed": {"replicas": [{"location": self.region}]}
                            },
                        },
                        retry=None,
                        timeout=10,
                    )
                except AlreadyExists:
                    found = self.client.get_secret(name=name, retry=None, timeout=10)
                except (BadRequest, Forbidden, Unauthorized):
                    raise AdminError("secret_write_failed", 503) from None
                except Exception:
                    # Metadata read is safe. Never issue another create after ambiguity.
                    try:
                        found = self.client.get_secret(name=name, retry=None, timeout=10)
                    except Exception:
                        raise AdminError("secret_write_outcome_unknown", 503) from None
            self.owned(found, owner)
        except AdminError:
            raise
        except Exception:
            raise AdminError("secret_read_failed", 503) from None

    def canonical(self, name: str, store: str) -> str:
        expected = self.name(store)
        for project in (self.project, self.number):
            prefix = f"projects/{project}/secrets/up-intelligence-upzero-{store}/versions/"
            if name.startswith(prefix) and re.fullmatch(r"[1-9][0-9]*", name[len(prefix) :]):
                result = expected + "/versions/" + name[len(prefix) :]
                validate_secret_reference(result, numeric_only=True)
                return result
        raise AdminError("secret_write_outcome_unknown", 503)

    def compare(self, reference: str, credential: str) -> None:
        validate_secret_reference(reference, numeric_only=True)
        if not reference.startswith(f"projects/{self.project}/secrets/up-intelligence-upzero-"):
            raise AdminError("secret_name_collision")
        try:
            value = self.client.access_secret_version(
                name=reference, retry=None, timeout=10
            ).payload.data
            if not hmac.compare_digest(bytes(value), credential.encode()):
                raise AdminError("credential_retry_mismatch")
        except AdminError:
            raise
        except Exception:
            raise AdminError("secret_read_failed", 503) from None

    def candidate(self, store: str, credential: str) -> str | None:
        try:
            versions = []
            for version in self.client.list_secret_versions(
                parent=self.name(store), retry=None, timeout=10
            ):
                versions.append(version)
                if len(versions) > 1:
                    raise AdminError("secret_write_outcome_unknown", 503)
            if not versions:
                return None
            # Disabled/destroyed versions cannot be accepted as a safe initial version.
            if int(versions[0].state) != 1:
                raise AdminError("secret_write_outcome_unknown", 503)
            reference = self.canonical(versions[0].name, store)
            self.compare(reference, credential)
            return reference
        except AdminError:
            raise
        except Exception:
            raise AdminError("secret_read_failed", 503) from None

    def initial(self, store: str, owner: str, credential: str, *, reconcile_only: bool) -> str:
        self.container(store, owner, reconcile_only=True)
        reference = self.candidate(store, credential)
        if reference:
            return reference
        if reconcile_only:
            raise AdminError("secret_write_outcome_unknown", 503)
        try:
            version = self.client.add_secret_version(
                parent=self.name(store),
                payload={"data": credential.encode()},
                retry=None,
                timeout=10,
            )
        except (BadRequest, Forbidden, Unauthorized):
            raise AdminError("secret_write_failed", 503) from None
        except Exception:
            try:
                reference = self.candidate(store, credential)
            except AdminError as exc:
                if exc.code == "credential_retry_mismatch":
                    raise
                raise AdminError("secret_write_outcome_unknown", 503) from None
            if reference is None:
                raise AdminError("secret_write_outcome_unknown", 503) from None
            return reference
        reference = self.canonical(version.name, store)
        self.compare(reference, credential)
        return reference
