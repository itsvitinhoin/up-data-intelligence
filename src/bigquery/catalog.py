"""Single schema source shared by persistence, SQL and Terraform JSON schemas."""

from dataclasses import dataclass

from src.connectors.meta.foundation_schema import SCHEMAS as META_FOUNDATION_SCHEMAS
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

# Meta is an additive, separately gated schema proposal. Existing schemas stay unchanged.
META_ENTITY = {
    k: "STRING" for k in "account_id api_version name status effective_status".split()
} | {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP"}
META_INSIGHTS = (
    {
        k: "STRING"
        for k in "account_id campaign_id adset_id ad_id api_version account_currency source_timezone configuration_hash purchase_action_type".split()
    }
    | {"date_start": "DATE", "date_stop": "DATE"}
    | {
        k: "NUMERIC"
        for k in "spend frequency cpm cpc ctr landing_page_views meta_reported_purchases meta_reported_purchase_value".split()
    }
    | {k: "INT64" for k in "impressions reach clicks inline_link_clicks".split()}
    | {k: "JSON" for k in "actions action_values breakdown_values reporting_configuration".split()}
)
META_TABLE_NAMES: set[str] = set()
for resource, fields, key in [
    (
        "accounts",
        META_ENTITY | {"account_status": "INT64", "currency": "STRING", "timezone_name": "STRING"},
        "account_id",
    ),
    ("campaigns", META_ENTITY | {"campaign_id": "STRING", "objective": "STRING"}, "campaign_id"),
    ("adsets", META_ENTITY | {"campaign_id": "STRING", "adset_id": "STRING"}, "adset_id"),
    (
        "ads",
        META_ENTITY | {"campaign_id": "STRING", "adset_id": "STRING", "ad_id": "STRING"},
        "ad_id",
    ),
    ("insights", META_INSIGHTS, "ad_id"),
]:
    raw_name = "meta_raw_" + resource
    name = "meta_" + ("insights_daily" if resource == "insights" else resource)
    TABLES[raw_name] = Table(
        "up_raw", COMMON | RAW, "ingested_at", ("store_id", "source_connection_id")
    )
    cluster = tuple(dict.fromkeys(("store_id", "account_id", key)))
    TABLES[name] = Table(
        "up_core", COMMON | META | fields, "date_start" if resource == "insights" else None, cluster
    )
    TABLES[name + "_versions"] = Table("up_core", COMMON | META | fields, "observed_at", cluster)
    META_TABLE_NAMES.update((raw_name, name, name + "_versions"))
TABLES["meta_account_bindings"] = Table(
    "up_core",
    COMMON
    | {
        k: "STRING"
        for k in "account_id connection_id api_version source_timezone currency configuration_hash".split()
    }
    | {"configured_at": "TIMESTAMP"},
    None,
    ("store_id", "account_id"),
)
META_TABLE_NAMES.add("meta_account_bindings")

# CHANGE #16 canonical Meta current/version tables. Legacy meta_* remain inactive.

for legacy_name, foundation_fields in META_FOUNDATION_SCHEMAS.items():
    live_name = legacy_name.replace("meta_", "meta_live_", 1)
    live_fields = foundation_fields | {
        "version_id": "STRING",
        "payload_hash": "STRING",
        "source_system": "STRING",
    }
    TABLES[live_name] = Table(
        "up_core",
        live_fields,
        "date_start" if live_name.endswith("insights_daily") else None,
        ("store_id", "account_id"),
    )
    TABLES[live_name + "_versions"] = Table(
        "up_core", live_fields, "observed_at", ("store_id", "account_id")
    )
    META_TABLE_NAMES.update((live_name, live_name + "_versions"))
