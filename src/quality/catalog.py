"""Pure catalog snapshot certification. Current versions alone prove no coverage."""

from datetime import UTC, datetime, timedelta
from typing import Any

from src.connectors.upzero.catalog_schema import RESOURCES
from src.domain.models import SafeError
from src.utils.data import digest, timestamp


def certify_image_relationships(
    store: str,
    product_ids: set[str],
    variants: list[dict[str, Any]],
    images: list[dict[str, Any]],
) -> None:
    """Exact certified snapshot membership; an empty gallery is valid evidence."""
    owners: dict[str, str] = {}
    for row in variants:
        identity, product = row.get("variant_id"), row.get("product_id")
        if (
            row.get("store_id") != store
            or not isinstance(identity, str)
            or identity in owners
            or product not in product_ids
        ):
            raise SafeError("catalog_image_variant_relationship_invalid")
        owners[identity] = product
    seen: set[str] = set()
    for row in images:
        identity, product = row.get("image_id"), row.get("product_id")
        assigned = row.get("variant_ids")
        if (
            row.get("store_id") != store
            or not isinstance(identity, str)
            or identity in seen
            or product not in product_ids
            or not isinstance(assigned, list)
            or any(owners.get(variant) != product for variant in assigned)
        ):
            raise SafeError("catalog_image_variant_relationship_invalid")
        seen.add(identity)


def certify_catalog_snapshot(
    store: str,
    connection: str,
    resource: str,
    cutoff: str,
    checkpoint: dict[str, Any],
    run: dict[str, Any],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require source exhaustion and an exact membership set, including unchanged rows."""
    if resource not in RESOURCES:
        raise SafeError("catalog_resource_invalid")
    filters, mode = checkpoint.get("filters"), checkpoint.get("mode")
    if not isinstance(filters, dict) or filters.get("catalog_as_of") != cutoff:
        raise SafeError("catalog_snapshot_mismatch")
    key = digest([store, connection, resource, filters, mode])
    if (
        mode != "incremental"
        or run.get("mode") != "incremental"
        or checkpoint.get("store_id") != store
        or checkpoint.get("connection_id") != connection
        or checkpoint.get("resource") != resource
        or checkpoint.get("plan_key") != key
        or checkpoint.get("status") != "complete"
        or checkpoint.get("pending_raw_id") is not None
        or run.get("store_id") != store
        or run.get("source") != "upzero"
        or run.get("resource") != resource
        or run.get("plan_key") != key
        or run.get("run_id") != checkpoint.get("run_id")
        or run.get("status") != "completed"
        or run.get("core_records_failed") != 0
    ):
        raise SafeError("catalog_snapshot_not_certified")
    count = run.get("source_records_read")
    if type(count) is not int or count < 0 or count != len(observations):
        raise SafeError("catalog_snapshot_membership_mismatch")
    identities = set()
    for observation in observations:
        identity = observation.get("entity_id")
        if (
            observation.get("store_id") != store
            or observation.get("resource") != resource
            or observation.get("run_id") != run["run_id"]
            or not isinstance(identity, str)
            or not identity.strip()
            or identity in identities
            or not observation.get("entity_version_id")
            or not observation.get("raw_record_id")
            or not observation.get("observed_at")
        ):
            raise SafeError("catalog_snapshot_membership_mismatch")
        identities.add(identity)
    finished = timestamp(run.get("finished_at"))
    return {
        "resource": resource,
        "run_id": run["run_id"],
        "checkpoint_plan_key": key,
        "snapshot_as_of": timestamp(cutoff),
        "observed_count": count,
        "completed_at": finished,
        "basis": "current_source_snapshot",
        "history_complete": False,
    }


def catalog_freshness(proof: dict[str, Any] | None, at: str, max_age_hours: int = 24) -> str:
    if proof is None:
        return "NOT_CONFIGURED"
    if type(max_age_hours) is not int or not 1 <= max_age_hours <= 48:
        raise SafeError("catalog_freshness_policy_invalid")
    observed = datetime.fromisoformat(timestamp(proof.get("completed_at"))).astimezone(UTC)
    current = datetime.fromisoformat(timestamp(at)).astimezone(UTC)
    if observed > current:
        raise SafeError("catalog_snapshot_future")
    return "HEALTHY" if current - observed <= timedelta(hours=max_age_hours) else "STALE"


def certify_catalog_summary(
    store: str,
    connection: str,
    resource: str,
    cutoff: str,
    checkpoint: dict[str, Any],
    run: dict[str, Any],
    *,
    observations: int,
    distinct_entities: int,
    valid_version_links: int,
) -> dict[str, Any]:
    """Same exhaustion proof with aggregate membership checks, avoiding UI row scans."""
    if resource not in RESOURCES:
        raise SafeError("catalog_resource_invalid")
    filters = checkpoint.get("filters")
    if not isinstance(filters, dict) or filters.get("catalog_as_of") != cutoff:
        raise SafeError("catalog_snapshot_mismatch")
    key = digest([store, connection, resource, filters, checkpoint.get("mode")])
    if (
        checkpoint.get("store_id") != store
        or checkpoint.get("connection_id") != connection
        or checkpoint.get("resource") != resource
        or checkpoint.get("plan_key") != key
        or checkpoint.get("mode") != "incremental"
        or checkpoint.get("status") != "complete"
        or checkpoint.get("pending_raw_id") is not None
        or run.get("store_id") != store
        or run.get("source") != "upzero"
        or run.get("resource") != resource
        or run.get("plan_key") != key
        or run.get("run_id") != checkpoint.get("run_id")
        or run.get("status") != "completed"
        or run.get("core_records_failed") != 0
        or run.get("mode") != "incremental"
    ):
        raise SafeError("catalog_snapshot_not_certified")
    counts = [observations, distinct_entities, valid_version_links, run.get("source_records_read")]
    if any(type(v) is not int or v < 0 for v in counts) or len(set(counts)) != 1:
        raise SafeError("catalog_snapshot_membership_mismatch")
    return {
        "resource": resource,
        "run_id": run["run_id"],
        "checkpoint_plan_key": key,
        "snapshot_as_of": timestamp(cutoff),
        "observed_count": observations,
        "completed_at": timestamp(run.get("finished_at")),
        "basis": "current_source_snapshot",
        "history_complete": False,
    }
