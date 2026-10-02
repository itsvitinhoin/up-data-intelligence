"""Only operational metadata. Filters are allowlisted connector parameters, not payloads."""

PLANS = (
    dict.fromkeys(
        "row_key plan_id onboarding_operation_id store_id status planner_version config_hash error_code".split(),
        "STRING",
    )
    | dict.fromkeys("revision registry_revision priority".split(), "INT64")
    | dict.fromkeys(
        "requested_from target_as_of created_at updated_at completed_at".split(), "TIMESTAMP"
    )
    | {"adopted_coverage": "JSON"}
)
UNITS = (
    dict.fromkeys(
        "row_key work_unit_id plan_id store_id source connection_id pipeline resource unit_kind mode status dispatch_token dispatch_operation_name execution_name checkpoint_plan_key run_id last_error_code".split(),
        "STRING",
    )
    | dict.fromkeys(
        "sequence revision reservation_revision attempt_count failure_count records_processed pages_processed".split(),
        "INT64",
    )
    | dict.fromkeys("next_eligible_at started_at updated_at finished_at".split(), "TIMESTAMP")
    | {
        "filters": "JSON",
        "dependencies": "JSON",
        "required": "BOOL",
        "duration_seconds": "FLOAT64",
        "slice_seconds": "FLOAT64",
    }
)
