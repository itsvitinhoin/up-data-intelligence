"""Explicit DEV grant administration. Email input is private; only its hash is stored."""

import argparse
import getpass
import json
import re
from typing import Any

from src.analytics.cloud.transport import CloudConfig, Transport, scalar
from src.dashboard.contracts import ReadError
from src.product_auth.access import verified_identity
from src.utils.data import digest


def validate(args: Any) -> None:
    if (
        not args.live
        or args.project != "up-data-intelligence-dev"
        or args.confirm_project != args.project
        or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", args.tenant)
    ):
        raise ReadError(403, "explicit_dev_tenant_confirmation_required")
    if args.command == "grant" and args.role not in {"ADMIN_UP", "CLIENT_USER"}:
        raise ReadError(400, "role_required")
    if (
        args.command == "grant"
        and args.role == "CLIENT_USER"
        and (
            not args.workspace_operation_id
            or args.confirm_workspace_operation != args.workspace_operation_id
        )
    ):
        raise ReadError(403, "workspace_confirmation_required")
    if (
        args.command == "grant"
        and args.role == "ADMIN_UP"
        and (args.workspace_operation_id or args.confirm_workspace_operation)
    ):
        raise ReadError(400, "admin_tenant_scope_required")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DEV principal access grants; no clear emails in metadata"
    )
    parser.add_argument("command", choices=["grant", "revoke", "list"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--role", choices=["ADMIN_UP", "CLIENT_USER"])
    parser.add_argument("--workspace-operation-id")
    parser.add_argument("--confirm-workspace-operation")
    args = parser.parse_args()
    validate(args)
    import firebase_admin
    from firebase_admin import auth
    from google.cloud import bigquery

    transport = Transport(
        bigquery.Client(project=args.project, location="southamerica-east1"),
        CloudConfig(
            args.project,
            "southamerica-east1",
            1073741824,
            60,
            False,
            maximum_total_bytes_billed=8589934592,
        ),
    )
    table = f"`{args.project}.up_ops.principal_access`"
    if args.command == "list":
        rows, _ = transport.query(
            f"SELECT identity_hash,role,tenant_id,workspace_operation_id,status FROM {table} WHERE tenant_id=@tenant ORDER BY identity_hash,workspace_operation_id LIMIT 101",
            [scalar("tenant", "STRING", args.tenant)],
        )
        if len(rows) > 100:
            raise ReadError(403, "access_inventory_limit")
        print(json.dumps(rows, default=str))
        return 0
    email = getpass.getpass("Verified identity email (not echoed): ")
    app = firebase_admin.initialize_app(options={"projectId": args.project})
    try:
        user = auth.get_user_by_email(email.strip().lower(), app=app)
    except Exception:
        raise ReadError(403, "verified_identity_required") from None
    email = ""
    identity = verified_identity(
        {"uid": user.uid, "email": user.email, "email_verified": user.email_verified}
    )
    if user.disabled:
        raise ReadError(403, "identity_disabled")
    params = [
        scalar("tenant", "STRING", args.tenant),
        scalar("identity", "STRING", identity.identity_hash),
    ]
    if args.command == "revoke":
        sql = f'BEGIN TRANSACTION; ASSERT (SELECT COUNT(*) FROM {table} WHERE tenant_id=@tenant AND identity_hash=@identity)>0 AS "access_not_provisioned"; UPDATE {table} SET status="DISABLED",updated_at=CURRENT_TIMESTAMP() WHERE tenant_id=@tenant AND identity_hash=@identity; COMMIT TRANSACTION;'
    else:
        if not args.role:
            raise ReadError(400, "role_required")
        workspace = args.workspace_operation_id
        bindings = f"`{args.project}.up_ops.workspace_store_bindings`"
        if workspace:
            rows, _ = transport.query(
                f'SELECT row_key FROM {bindings} WHERE tenant_id=@tenant AND workspace_operation_id=@workspace AND status IN ("DRAFT","READY","ACTIVE") LIMIT 2',
                params[:1] + [scalar("workspace", "STRING", workspace)],
            )
            if len(rows) != 1 or rows[0]["row_key"] != digest([args.tenant, workspace]):
                raise ReadError(403, "workspace_binding_required")
        else:
            rows, _ = transport.query(
                f"SELECT row_key FROM {bindings} WHERE tenant_id=@tenant LIMIT 1", params[:1]
            )
            if not rows:
                raise ReadError(403, "canonical_tenant_binding_required")
        params += [
            scalar("workspace", "STRING", workspace),
            scalar("role", "STRING", args.role),
            scalar("key", "STRING", digest([identity.identity_hash, args.tenant, workspace])),
        ]
        sql = f"""BEGIN TRANSACTION;
ASSERT NOT EXISTS(SELECT 1 FROM {table} WHERE identity_hash=@identity AND role!=@role) AS "conflicting_access";
ASSERT (SELECT COUNT(*) FROM {table} WHERE row_key=@key)<=1 AS "duplicate_access";
MERGE {table} t USING (SELECT @key row_key) s ON t.row_key=s.row_key
WHEN MATCHED THEN UPDATE SET status="ACTIVE",updated_at=CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT(row_key,identity_hash,role,tenant_id,workspace_operation_id,status,created_at,updated_at) VALUES(@key,@identity,@role,@tenant,@workspace,"ACTIVE",CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
COMMIT TRANSACTION;"""
    try:
        transport.query(sql, params)
    except Exception:
        # No blind mutation retry. Query outcome must be reconciled read-only.
        raise ReadError(503, "principal_access_write_requires_reconciliation") from None
    print(
        json.dumps(
            {
                "operation": args.command,
                "tenant_id": args.tenant,
                "identity_hash": identity.identity_hash,
                "status": "completed",
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReadError as error:
        print(json.dumps({"error": {"code": error.code}}))
        raise SystemExit(1) from None
