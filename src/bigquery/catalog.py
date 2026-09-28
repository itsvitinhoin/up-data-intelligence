"""Single schema source shared by persistence, SQL and Terraform JSON schemas."""

from dataclasses import dataclass

from src.ingestion.metrics import COUNTERS


@dataclass(frozen=True)
class Table:
    dataset: str
    fields: dict[str, str]
    partition: str | None = None
    cluster: tuple[str, ...] = ("store_id",)


COMMON = {"row_key": "STRING", "store_id": "STRING"}
META = {
    "source_system": "STRING",
    "raw_record_id": "STRING",
    "run_id": "STRING",
    "observed_at": "TIMESTAMP",
    "source_updated_at": "TIMESTAMP",
    "payload_hash": "STRING",
    "version_id": "STRING",
    "transform_version": "STRING",
}
CUSTOMER = {
    k: "STRING"
    for k in "customer_id customer_type status name email phone cpf cnpj company_name trade_name".split()
} | {"seller": "JSON", "retail_profile": "JSON", "wholesale_profile": "JSON"}
# Additive only: preserve originals and the currently deployed JSON fields.
CUSTOMER |= {
    k: "STRING"
    for k in "email_normalized phone_normalized phone_e164 cnpj_digits cpf_digits seller_id state city identity_normalization_version".split()
} | {"external_ref": "JSON", "identity_normalization_issues": "JSON"}
ORDER = (
    {
        k: "STRING"
        for k in "order_id customer_id order_status payment_status payment_method payment_method_name".split()
    }
    | {
        "installments": "INT64",
        "customer_snapshot": "JSON",
        "shipping_address": "JSON",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    }
    | {
        k: "NUMERIC"
        for k in "subtotal discount shipping total requested_total fulfilled_total".split()
    }
    | {
        k: "INT64"
        for k in "total_items_qty requested_items_qty fulfilled_items_qty items_count".split()
    }
)
ORDER["item_ids"] = "JSON"
ITEM = {
    k: "STRING"
    for k in "order_id item_id variant_id asset_id asset_name asset_image_url image_url sku status parent_order_version_id".split()
} | {
    "qty": "NUMERIC",
    "original_qty": "INT64",
    "unit_price": "NUMERIC",
    "order_created_at": "TIMESTAMP",
    "present_in_latest_snapshot": "BOOL",
}
EVENT = {
    k: "STRING"
    for k in "fact_id event_id event_name user_id anonymous_id session_id visitor_id fbclid fbc fbp gclid utm_source utm_medium utm_campaign utm_content utm_term source channel device_type landing_url referrer landing_host landing_path referrer_host product_id product_variant_id category_id order_id meta_campaign_id meta_adset_id meta_ad_id meta_adset_name parser_version parse_status".split()
} | {"occurred_at": "TIMESTAMP", "quantity": "INT64", "value": "NUMERIC"}
RAW = {
    k: "STRING"
    for k in "source_system resource source_connection_id run_id request_id raw_record_id payload_hash connector_version spec_version spec_sha256 sanitization_version".split()
} | {
    "ingested_at": "TIMESTAMP",
    "position": "JSON",
    "next_position": "JSON",
    "request_filters": "JSON",
    "payload": "JSON",
    "bytes_read": "INT64",
    "pagination_error": "STRING",
}
TABLES: dict[str, Table] = {}
for name in ("customers", "orders", "analytics_facts"):
    TABLES["upzero_" + name] = Table(
        "up_raw", COMMON | RAW, "ingested_at", ("store_id", "resource")
    )
for name, fields, partition, key in [
    ("customers", CUSTOMER, None, "customer_id"),
    ("orders", ORDER, "created_at", "order_id"),
    ("order_items", ITEM, "order_created_at", "order_id"),
    ("analytics_events", EVENT, "occurred_at", "fact_id"),
]:
    TABLES[name] = Table("up_core", COMMON | META | fields, partition, ("store_id", key))
    TABLES[name + "_versions"] = Table(
        "up_core", COMMON | META | fields, "observed_at", ("store_id", key)
    )
TABLES["touchpoints"] = Table(
    "up_core",
    COMMON | META | EVENT | {"touchpoint_id": "STRING", "source_fact_id": "STRING"},
    "occurred_at",
    ("store_id", "session_id"),
)
TABLES["identity_links"] = Table(
    "up_core",
    COMMON
    | META
    | {
        k: "STRING"
        for k in "link_id source_fact_id source_version_id left_namespace left_id right_namespace right_id evidence_type".split()
    }
    | {"occurred_at": "TIMESTAMP"}
    | {
        k: "STRING"
        for k in "source_entity_type source_entity_id identifier_type_from identifier_value_from identifier_type_to identifier_value_to confidence_type".split()
    }
    | {"first_seen_at": "TIMESTAMP", "last_seen_at": "TIMESTAMP"},
    "observed_at",
    ("store_id", "source_fact_id"),
)
TABLES["event_order_links"] = Table(
    "up_core",
    COMMON
    | {
        "fact_id": "STRING",
        "order_id": "STRING",
        "source_version_id": "STRING",
        "link_status": "STRING",
        "updated_at": "TIMESTAMP",
    },
    None,
    ("store_id", "order_id"),
)
TABLES["stores"] = Table(
    "up_core",
    COMMON
    | {
        k: "STRING"
        for k in "store_name store_slug status upzero_store_identifier timezone meta_ad_account_id".split()
    }
    | {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP"},
)
TABLES["source_connections"] = Table(
    "up_core",
    COMMON
    | {k: "STRING" for k in "connection_id source_system secret_resource_name status".split()}
    | {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP"},
)
TABLES["sync_runs"] = Table(
    "up_ops",
    COMMON
    | {k: "STRING" for k in "run_id source resource status error_summary plan_key mode".split()}
    | {"started_at": "TIMESTAMP", "finished_at": "TIMESTAMP"}
    | {
        k: "INT64"
        for k in [
            *"records_read records_written records_updated records_failed pages retries bytes".split(),
            "metrics_version",
            *COUNTERS,
        ]
    },
    "started_at",
    ("store_id", "resource"),
)
TABLES["sync_checkpoints"] = Table(
    "up_ops",
    COMMON
    | {
        k: "STRING"
        for k in "resource connection_id plan_key run_id status pending_raw_id mode".split()
    }
    | {
        "filters": "JSON",
        "position": "JSON",
        "updated_at": "TIMESTAMP",
        "completed_to": "TIMESTAMP",
        "high_id": "STRING",
    },
)
TABLES["quality_results"] = Table(
    "up_ops",
    COMMON
    | {k: "STRING" for k in "run_id resource rule_id severity record_id".split()}
    | {"failed_count": "INT64", "checked_count": "INT64", "checked_at": "TIMESTAMP"},
    "checked_at",
    ("store_id", "rule_id"),
)
TABLES["source_capabilities"] = Table(
    "up_ops",
    COMMON
    | {
        "connection_id": "STRING",
        "purchase_order_id_effective_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
)
