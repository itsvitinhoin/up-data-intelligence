"""Non-secret persistence contracts, shared with schema generation."""

BINDINGS = dict.fromkeys(
    "row_key tenant_id brand_id workspace_operation_id store_id operation status".split(), "STRING"
) | dict.fromkeys("created_at updated_at".split(), "TIMESTAMP")
OPERATIONS = (
    dict.fromkeys(
        "row_key operation_id idempotency_key admin_subject_hash request_hash tenant_id store_id status current_step error_code secret_version_name".split(),
        "STRING",
    )
    | {"revision": "INT64"}
    | dict.fromkeys("created_at updated_at completed_at".split(), "TIMESTAMP")
)
