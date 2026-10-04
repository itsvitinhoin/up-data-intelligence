"""Explicit production composition; deployment commands select Read or Admin only."""

import hashlib
import os
from typing import Any

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
            )

        return create_read_app(sessions, dashboard)
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

        return create_admin_app(sessions, onboarding)
    raise ValueError("explicit_product_service_required")


def read_app() -> Any:
    return compose("read")


def admin_app() -> Any:
    return compose("admin")
