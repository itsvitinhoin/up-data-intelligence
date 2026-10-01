"""DEV-gated operational CLI. --help/import never creates a client or reads a secret."""

import argparse
import json
import os
import re
from pathlib import Path

from src.analytics.cloud.transport import CloudConfig, Transport, scalar
from src.analytics.config import AnalyticsPolicy
from src.bigquery.repository import BigQueryRepository
from src.connectors.meta.config import Account
from src.connectors.meta.live import MetaAccountLister, MetaFoundationLiveConnector
from src.domain.models import SafeError
from src.ingestion.meta_live import MetaLiveEngine
from src.intelligence.live.runtime import binding, materialize, reporting
from src.observability.logging import configure, event
from src.security.lease import cloud_lease
from src.security.secrets import resolve_secret
from src.utils.data import digest, now


def validated_secret_reference(reference: str) -> str:
    if not re.fullmatch(
        r"projects/up-data-intelligence-dev/secrets/up-intelligence-meta-global-token/versions/[1-9][0-9]*",
        reference,
    ):
        raise SafeError("global_dev_meta_secret_version_required")
    return reference


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CHANGE #16 explicit DEV pilot; no implicit live mode"
    )
    parser.add_argument(
        "command",
        choices=[
            "list-accounts",
            "bind-account",
            "read-binding",
            "meta-sync",
            "materialize",
            "preflight",
            "validate",
        ],
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--confirm-store", required=True)
    parser.add_argument("--account-id")
    parser.add_argument("--confirm-account-id")
    parser.add_argument("--api-version")
    parser.add_argument("--connection-id")
    parser.add_argument("--secret-reference")
    parser.add_argument("--allow-local-token-env", action="store_true")
    parser.add_argument("--lease-bucket")
    parser.add_argument("--source-snapshot-at")
    parser.add_argument("--calculated-at")
    parser.add_argument("--initialize-head", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--replay-run")
    parser.add_argument(
        "--resource",
        choices=["accounts", "campaigns", "adsets", "ads", "insights", "all"],
        default="all",
    )
    parser.add_argument("--page-limit", type=int, default=100)
    parser.add_argument("--maximum-bytes-billed", type=int, default=1073741824)
    parser.add_argument("--maximum-total-bytes-billed", type=int, default=34359738368)
    args = parser.parse_args()
    configure()
    connector: MetaFoundationLiveConnector | None = None
    repo: BigQueryRepository | None = None
    try:
        if (
            not args.live
            or args.project != "up-data-intelligence-dev"
            or args.confirm_project != args.project
            or args.confirm_store != args.store_id
        ):
            raise SafeError("change16_dev_confirmation_required")
        policy = AnalyticsPolicy.from_dict(json.loads(args.policy.read_text()))
        if policy.store_id != args.store_id:
            raise SafeError("policy_store_mismatch")
        if args.command != "list-accounts" and (
            not args.account_id or args.confirm_account_id != args.account_id
        ):
            raise SafeError("meta_account_confirmation_required")
        token = ""
        if args.command in {"list-accounts", "bind-account", "meta-sync"} and not args.replay_run:
            if args.allow_local_token_env and not args.secret_reference:
                token = os.environ.get("UP_META_DEV_TOKEN", "")
            elif args.secret_reference and not args.allow_local_token_env:
                token = resolve_secret(validated_secret_reference(args.secret_reference))
            if not token:
                raise SafeError("server_side_meta_token_required")
        if args.command == "list-accounts":
            connector = MetaAccountLister(
                project=args.project,
                live=True,
                store=args.store_id,
                confirm_store=args.confirm_store,
                api_version=args.api_version or "",
                token=token,
            )
            print(json.dumps(connector.list_accounts()))
            return 0
        from google.cloud import bigquery

        client = bigquery.Client(project=args.project, location=args.location)
        transport = Transport(
            client,
            CloudConfig(
                args.project,
                args.location,
                args.maximum_bytes_billed,
                300,
                False,
                maximum_total_bytes_billed=args.maximum_total_bytes_billed,
            ),
        )
        if args.command == "bind-account":
            if not args.lease_bucket or not args.connection_id or not args.api_version:
                raise SafeError("explicit_binding_configuration_required")
            account = Account(
                args.store_id,
                args.account_id,
                args.connection_id,
                args.api_version,
                policy.reporting_timezone,
                policy.currency or "",
            )
            connector = MetaFoundationLiveConnector(
                account,
                project=args.project,
                live=True,
                confirm_store=args.store_id,
                confirm_account=args.account_id,
                token=token,
            )
            from src.normalization.meta import normalize_foundation

            pages = list(connector.pages("accounts", None))
            if len(pages) != 1 or pages[0].pagination_error or len(pages[0].payload["data"]) != 1:
                raise SafeError("meta_account_validation_failed")
            normalize_foundation(
                "accounts", pages[0].payload["data"][0], account, None, observed_at=now()
            )
            with (
                cloud_lease(args.lease_bucket, "meta-bindings-global"),
                cloud_lease(args.lease_bucket, args.store_id),
            ):
                params = [
                    scalar("store", "STRING", args.store_id),
                    scalar("account", "STRING", args.account_id),
                    scalar("connection", "STRING", args.connection_id),
                    scalar("version", "STRING", args.api_version),
                    scalar("timezone", "STRING", account.timezone),
                    scalar("currency", "STRING", account.currency),
                    scalar("key", "STRING", digest([args.store_id, "meta", args.account_id])),
                    scalar("hash", "STRING", digest(account.snapshot())),
                ]
                target = f"`{args.project}.up_core.meta_account_bindings`"
                transport.query(
                    f"BEGIN TRANSACTION; ASSERT NOT EXISTS(SELECT 1 FROM {target} WHERE account_id=@account AND store_id!=@store) AS 'account_already_bound'; ASSERT (SELECT COUNT(*) FROM {target} WHERE store_id=@store)<=1 AS 'duplicate_binding'; MERGE {target} t USING (SELECT @key row_key,@store store_id) s ON t.store_id=s.store_id WHEN MATCHED THEN UPDATE SET account_id=@account,connection_id=@connection,api_version=@version,source_timezone=@timezone,currency=@currency,configuration_hash=@hash,configured_at=CURRENT_TIMESTAMP() WHEN NOT MATCHED THEN INSERT(row_key,store_id,account_id,connection_id,api_version,source_timezone,currency,configuration_hash,configured_at) VALUES(@key,@store,@account,@connection,@version,@timezone,@currency,@hash,CURRENT_TIMESTAMP()); COMMIT TRANSACTION;",
                    params,
                )
            event(
                "change16_finished", store_id=args.store_id, resource="binding", status="completed"
            )
            return 0
        account = binding(transport, args.store_id, args.account_id)
        if not args.api_version or args.api_version != account.api_version:
            raise SafeError("explicit_bound_api_version_required")
        if account.currency != policy.currency or account.timezone != policy.reporting_timezone:
            raise SafeError("incompatible_meta_binding")
        if args.command == "validate":
            from src.intelligence.live.validation import validate

            print(json.dumps(validate(transport, policy, tenant="demo-up")))
            return 0
        if args.command in {"read-binding", "preflight"}:
            from src.dashboard.contracts import Grant, Principal
            from src.dashboard.repository import BigQueryReadSession, ReadBudget
            from src.dashboard.service import DashboardService

            grant = Grant("dev-operator", policy.store_id, "B2B")
            service = DashboardService(
                args.project,
                {policy.store_id: policy},
                lambda: BigQueryReadSession(client, ReadBudget(args.project, args.location)),
                b"preflight-internal-no-client-cursors",
            )
            service._scope(Principal("dev-operator", "ADMIN_UP", frozenset({grant})), grant)
            event(
                "change16_finished",
                store_id=args.store_id,
                resource="preflight",
                generation=service.publication.generation,
                status="completed",
            )
            return 0
        if not args.lease_bucket:
            raise SafeError("shared_store_lease_required")
        if args.command == "meta-sync":
            # Replay resolves only stored sanitized RAW; no API token needed.
            connector = MetaFoundationLiveConnector(
                account,
                project=args.project,
                live=True,
                confirm_store=args.store_id,
                confirm_account=args.account_id,
                token=token or "replay-no-network",
                page_limit=args.page_limit,
            )
            repo = BigQueryRepository(args.project, args.location)
            engine = MetaLiveEngine(
                repo,
                connector,
                accounts=(account,),
                lease=lambda: cloud_lease(args.lease_bucket, args.store_id),
            )
            resources = (
                ["accounts", "campaigns", "adsets", "ads", "insights"]
                if args.resource == "all"
                else [args.resource]
            )
            for resource in resources:
                if args.replay_run:
                    engine.replay(resource, args.replay_run)
                else:
                    engine.run(
                        resource,
                        reporting(account, policy) if resource == "insights" else None,
                        refresh=args.refresh,
                    )
        else:
            if not args.source_snapshot_at or not args.calculated_at:
                raise SafeError("controlled_snapshot_and_calculation_required")
            with cloud_lease(args.lease_bucket, args.store_id):
                result = materialize(
                    transport,
                    policy,
                    account,
                    tenant="dev-operator",
                    snapshot_at=args.source_snapshot_at,
                    calculated_at=args.calculated_at,
                    initialize_head=args.initialize_head,
                )
                event(
                    "change16_finished",
                    store_id=args.store_id,
                    resource="intelligence",
                    generation=result["generation"],
                    query_count=transport.query_count,
                    reserved_query_bytes=transport.reserved_query_bytes,
                    bytes_processed=transport.bytes_processed,
                    query_duration_ms=transport.duration_ms,
                    rows_read=transport.rows_read,
                    status="completed",
                )
        return 0
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, SafeError)
            else str(exc)
            if isinstance(exc, ValueError) and str(exc).isidentifier()
            else "change16_failed"
        )
        event("job_failed", store_id=args.store_id, resource="change16", code=code)
        return 1
    finally:
        if connector:
            connector.close()


if __name__ == "__main__":
    raise SystemExit(main())
