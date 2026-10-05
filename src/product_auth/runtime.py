"""Explicit production composition; deployment commands select Read or Admin only."""

import hashlib
import os
from typing import Any

from src.admin.connections import ConnectionService
from src.admin.history import HistoryService
from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.product_auth.http import WSGI, create_admin_app, create_read_app
from src.product_auth.repository import BigQueryAccess
from src.product_auth.session import FirebaseVerifier, Sessions


def configuration() -> tuple[str, str]:
    project, location = os.environ["UP_PRODUCT_PROJECT"], os.environ["UP_PRODUCT_LOCATION"]
    if project != "up-data-intelligence-dev" or location != "southamerica-east1":
        raise ValueError("product_dev_configuration_required")
    return project, location


def compose(kind: str) -> WSGI:
    # Never read credentials, build SDKs or start servers during module import.
    import firebase_admin
    from google.cloud import bigquery

    project, location = configuration()
    app = firebase_admin.initialize_app(options={"projectId": project}, name="up-product-" + kind)
    client = bigquery.Client(project=project, location=location)
    # Product composition adds Registry/HEAD/session metadata reads. A lower per-query
    # ceiling permits that bounded chain without increasing the existing 8GiB total guard.
    budget = ReadBudget(project, location, maximum_bytes_billed=268435456, timeout_seconds=60)
    access_budget = ReadBudget(
        project,
        location,
        maximum_bytes_billed=67108864,
        maximum_total_bytes_billed=134217728,
        timeout_seconds=30,
    )

    def sessions() -> Sessions:
        return Sessions(
            FirebaseVerifier(app),
            BigQueryAccess(BigQueryReadSession(client, access_budget), project),
        )

    if kind == "read":
        from src.dashboard.intelligence import IntelligenceDashboardService

        def dashboard(cookie: str) -> IntelligenceDashboardService:
            # Stable across replicas, bound to the verified 12h session, never logged/exported.
            cursor_key = hashlib.sha256(("up-pagination-v1:" + cookie).encode()).digest()
            return IntelligenceDashboardService(
                project,
                {},
                lambda: BigQueryReadSession(client, budget),
                cursor_key,
                installation_v2=True,
                catalog_enabled=os.environ.get("UP_PRODUCT_CATALOG_ENABLED") == "1",
                creatives_enabled=os.environ.get("UP_PRODUCT_CREATIVES_ENABLED") == "1",
            )

        from src.admin.integration_reads import IntegrationReader

        return create_read_app(
            sessions,
            dashboard,
            lambda: IntegrationReader(project, BigQueryReadSession(client, budget)),
        )
    if kind == "admin":
        from google.cloud import secretmanager

        from src.admin.repository import BigQueryOnboarding
        from src.admin.secrets import SecretManagerStore
        from src.admin.service import OnboardingService
        from src.analytics.cloud.transport import CloudConfig, Transport
        from src.security.lease import cloud_lease

        def onboarding() -> OnboardingService:
            number, bucket = (
                os.environ["UP_PRODUCT_PROJECT_NUMBER"],
                os.environ["UP_PRODUCT_LEASE_BUCKET"],
            )
            # This key must be stable across instances/restarts for SAGA idempotency.
            subject_key = bytes.fromhex(os.environ["UP_PRODUCT_SUBJECT_KEY"])
            transport = Transport(
                client,
                CloudConfig(
                    project, location, 1073741824, 60, False, maximum_total_bytes_billed=8589934592
                ),
            )
            return OnboardingService(
                BigQueryOnboarding(transport),
                SecretManagerStore(
                    secretmanager.SecretManagerServiceClient(),
                    project=project,
                    project_number=number,
                    region=location,
                    environment="dev",
                ),
                lambda key: cloud_lease(bucket, key),
                subject_key,
            )

        def history() -> HistoryService:
            from src.installation.extension_repository import ExtensionLedger

            if os.environ.get("UP_INSTALLATION_EXTENSIONS_ENABLED") != "1":
                from src.dashboard.contracts import ReadError

                raise ReadError(424, "history_management_unavailable")
            transport = Transport(
                client,
                CloudConfig(
                    project, location, 268435456, 60, False, maximum_total_bytes_billed=8589934592
                ),
            )
            return HistoryService(
                ExtensionLedger(transport),
                lambda key: cloud_lease(os.environ["UP_PRODUCT_LEASE_BUCKET"], key),
                bytes.fromhex(os.environ["UP_PRODUCT_SUBJECT_KEY"]),
            )

        def connections() -> ConnectionService:
            from src.admin.connection_repository import BigQueryConnections
            from src.admin.rotation import RotationStore
            from src.connectors.meta.live import MetaFoundationLiveConnector
            from src.connectors.upzero.client import UpZeroConnector
            from src.control_plane.preflight import Prerequisites
            from src.domain.models import SafeError
            from src.intelligence.live.cli import validated_secret_reference
            from src.security.secrets import resolve_secret

            if os.environ.get("UP_INSTALLATION_EXTENSIONS_ENABLED") != "1":
                from src.dashboard.contracts import ReadError

                raise ReadError(424, "connection_management_unavailable")
            transport = Transport(
                client,
                CloudConfig(
                    project, location, 268435456, 60, False, maximum_total_bytes_billed=8589934592
                ),
            )

            def probe(config: Any, provider: str, reference: str | None) -> None:
                if provider == "upzero":
                    if not reference:
                        raise SafeError("approved_upzero_secret_version_required")
                    connector = UpZeroConnector(resolve_secret(reference), attempts=1)
                    try:
                        page = next(connector.pages("customers", {"limit": 1}))
                        if page.pagination_error:
                            raise SafeError("source_verification_failed")
                    finally:
                        connector.close()
                else:
                    if provider == "meta-add":
                        from src.connectors.meta.config import Account

                        account = Account(
                            config.store_id,
                            config.meta_account_id,
                            config.meta_connection_id,
                            config.meta_api_version,
                            config.timezone,
                            config.currency,
                        )
                    else:
                        account = Prerequisites(transport).account(config)
                    connector_meta = MetaFoundationLiveConnector(
                        account,
                        project=project,
                        live=True,
                        confirm_store=config.store_id,
                        confirm_account=account.account_id,
                        token=resolve_secret(
                            validated_secret_reference(
                                os.environ.get("UP_META_SECRET_REFERENCE", "")
                            )
                        ),
                        page_limit=1,
                        attempts=1,
                    )
                    try:
                        page = next(connector_meta.pages("accounts", None, {}))
                        if page.pagination_error:
                            raise SafeError("source_verification_failed")
                        if provider == "meta-add":
                            from src.admin.source_addition import verify_meta_account

                            verify_meta_account(page, account)
                    finally:
                        connector_meta.close()

            from src.admin.source_addition import SourceAddition

            repository = BigQueryConnections(transport)

            def lease(key: str) -> Any:
                return cloud_lease(os.environ["UP_PRODUCT_LEASE_BUCKET"], key)

            subject_key = bytes.fromhex(os.environ["UP_PRODUCT_SUBJECT_KEY"])
            addition = SourceAddition(repository, history().publication, probe, lease, subject_key)
            return ConnectionService(
                repository,
                RotationStore(
                    secretmanager.SecretManagerServiceClient(),
                    project,
                    os.environ["UP_PRODUCT_PROJECT_NUMBER"],
                ),
                probe,
                lease,
                subject_key,
                addition=addition.create,
            )

        return create_admin_app(sessions, onboarding, history, connections)
    raise ValueError("explicit_product_service_required")


def read_app() -> Any:
    return compose("read")


def admin_app() -> Any:
    return compose("admin")
