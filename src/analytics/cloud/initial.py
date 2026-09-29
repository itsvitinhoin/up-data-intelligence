"""First manual DEV publication only. No implicit HEAD creation or CDC."""

from src.analytics.cloud.reader import BigQueryAnalyticsReader, SourceGeneration
from src.analytics.cloud.runner import materialize
from src.analytics.cloud.transport import Transport, scalar
from src.analytics.cloud.writer import BigQueryAnalyticsWriter, Publication
from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row
from src.analytics.materialization import CoreSnapshot, plan_changes
from src.analytics.policy import VERSION
from src.analytics.schema import SCHEMAS
from src.observability.logging import event
from src.utils.data import digest, now, timestamp

PROJECT = "up-data-intelligence-dev"
STORE = "mx-fashion"
LOCATION = "southamerica-east1"
POLICY_HASH = "3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c"


def validate_policy(policy: AnalyticsPolicy) -> None:
    if (
        policy.store_id != STORE
        or policy.policy_hash != POLICY_HASH
        or policy.history_complete is not False
        or policy.facts_complete is not True
        or policy.history_coverage is not None
        or policy.allow_unknown_currency_local is not False
        or policy.history_from != "2026-09-01T00:00:00Z"
        or policy.report_from != "2026-09-01"
        or policy.report_to != "2026-09-28"
        or policy.as_of != "2026-09-28T03:00:00Z"
    ):
        raise ValueError("unapproved_initial_policy")


def initial_generation(policy: AnalyticsPolicy, snapshot_at: str) -> SourceGeneration:
    manifest = {
        "store": policy.store_id,
        "policy_hash": policy.policy_hash,
        "snapshot_at": timestamp(snapshot_at),
        "mode": "full_refresh_initial",
    }
    return SourceGeneration(manifest["snapshot_at"], digest(manifest), False)


def preflight(transport: Transport, policy: AnalyticsPolicy) -> Row | None:
    """Read-only. Protect generations >0; return only the matching first receipt."""
    table = f"`{transport.config.project}.up_analytics.analytics_publications`"
    params = [
        scalar("store", "STRING", policy.store_id),
        scalar("policy", "STRING", policy.policy_hash),
    ]
    heads, _ = transport.query(
        f"SELECT publication_id,generation,source_watermark FROM {table} WHERE record_kind='HEAD' AND store_id=@store AND policy_hash=@policy",
        params,
    )
    if not heads:
        raise ValueError("analytics_head_missing")
    if len(heads) != 1:
        raise ValueError("analytics_duplicate_head")
    head = heads[0]
    generation = head.get("generation")
    receipts, _ = transport.query(
        f"SELECT publication_id,store_id,policy_hash,generation,as_of,report_from,report_to,status,analytics_version,source_watermark FROM {table} WHERE record_kind='RECEIPT' AND store_id=@store AND policy_hash=@policy",
        params,
    )
    if generation == 0:
        if receipts or head.get("publication_id") or head.get("source_watermark"):
            raise ValueError("analytics_initial_head_inconsistent")
        # First publication cannot silently replace previously populated analytics.
        for model in SCHEMAS:
            counts, _ = transport.query(
                f"SELECT COUNT(*) AS row_count FROM `{transport.config.project}.up_analytics.{model}` WHERE store_id=@store AND policy_hash=@policy",
                params,
            )
            if len(counts) != 1 or counts[0]["row_count"] != 0:
                raise ValueError("analytics_initial_target_not_empty")
        return None
    if generation != 1 or len(receipts) != 1:
        raise ValueError("analytics_initial_generation_already_advanced")
    receipt = receipts[0]
    if (
        receipt.get("publication_id") != head.get("publication_id")
        or not head.get("publication_id")
        or receipt.get("source_watermark") != head.get("source_watermark")
        or not head.get("source_watermark")
        or receipt.get("store_id") != policy.store_id
        or receipt.get("policy_hash") != policy.policy_hash
        or receipt.get("generation") != 1
        or receipt.get("status") != "completed"
        or receipt.get("analytics_version") != VERSION
        or str(receipt.get("report_from")) != policy.report_from
        or str(receipt.get("report_to")) != policy.report_to
        or timestamp(str(receipt.get("as_of"))) != timestamp(policy.as_of)
    ):
        raise ValueError("analytics_initial_receipt_mismatch")
    return receipt


def run_initial(
    transport: Transport, policy: AnalyticsPolicy, *, full_refresh: bool, backfill_confirmed: bool
) -> Row:
    validate_policy(policy)
    if transport.config.project != PROJECT or transport.config.location != LOCATION:
        raise ValueError("unapproved_initial_environment")
    if not full_refresh or not backfill_confirmed:
        raise ValueError("explicit_full_refresh_and_backfill_confirmation_required")
    snapshot_at = now()  # Captured once, after operator confirmation; identical for all CORE reads.
    if receipt := preflight(transport, policy):
        event(
            "analytics_publication_reconciled",
            publication_id=receipt["publication_id"],
            store_id=policy.store_id,
            policy_hash=policy.policy_hash,
        )
        return receipt
    source = initial_generation(policy, snapshot_at)
    event(
        "analytics_initial_source",
        store_id=policy.store_id,
        policy_hash=policy.policy_hash,
        snapshot_at=source.snapshot_at,
        source_generation=source.generation,
    )
    plan = plan_changes(policy, CoreSnapshot([], [], [], []), None, None)
    publication = Publication(
        policy, source, plan, expected_generation=0, full_refresh_authorized=True
    )
    return materialize(
        BigQueryAnalyticsReader(transport, policy), BigQueryAnalyticsWriter(transport), publication
    )
