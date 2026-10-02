"""One metadata-only recovery proof query, shared by reads and atomic mutation.

Table identifiers come only from validated CloudConfig, never CLI run/store values.
No RAW/CORE/quality data is selected. TEMP proof exists only inside the write script.
"""

from src.domain.models import RESOURCES
from src.ingestion.checkpoints import CHECKPOINT_NEEDS_REVIEW, CHECKPOINT_RECOVERED

CHECKPOINT_COLUMNS = "row_key,store_id,run_id,resource,mode,status,pending_raw_id"
RUN_COLUMNS = (
    "store_id,run_id,source,resource,mode,plan_key,status,metrics_version,"
    "core_records_failed,core_records_processed,source_records_read,raw_pages_written,"
    "replay_records_read"
)


def proof_query(project: str, *, snapshot: bool = False) -> str:
    historical = " FOR SYSTEM_TIME AS OF @snapshot" if snapshot else ""
    checkpoints = f"`{project}.up_ops.sync_checkpoints`{historical}"
    runs = f"`{project}.up_ops.sync_runs`{historical}"
    # Keep this explicitly SELECT-only for BoundedClient's mutation-outcome guard.
    return f"""SELECT * FROM (
WITH checkpoint_rows AS (
 SELECT {CHECKPOINT_COLUMNS} FROM {checkpoints}
 WHERE store_id=@store AND run_id=@original
), original_rows AS (
 SELECT {RUN_COLUMNS} FROM {runs}
 WHERE store_id=@store AND run_id=@original
), replay_rows AS (
 SELECT {RUN_COLUMNS} FROM {runs}
 WHERE store_id=@store AND mode='replay' AND plan_key=@original
), checkpoints AS (
 SELECT COUNT(*) checkpoint_count, MIN(row_key) checkpoint_key,
 MIN(resource) resource, MIN(mode) mode, MIN(status) checkpoint_status,
 COALESCE(COUNTIF(pending_raw_id IS NOT NULL),0) pending_count
 FROM checkpoint_rows
), originals AS (
 SELECT COUNT(*) original_count,
 COALESCE(COUNTIF(o.source='upzero' AND o.resource=c.resource AND o.mode=c.mode
  AND o.status='completed_with_errors' AND o.core_records_failed>0
  AND (o.metrics_version IS NULL OR o.metrics_version=1
   OR (o.metrics_version=2 AND o.core_records_processed>=o.core_records_failed))),0) original_valid_count,
 MIN(o.metrics_version) metrics_version, MIN(o.core_records_processed) original_processed
 FROM original_rows o CROSS JOIN checkpoints c
), successful_replays AS (
 SELECT r.run_id FROM replay_rows r CROSS JOIN checkpoints c CROSS JOIN originals o
 WHERE r.source='upzero' AND r.resource=c.resource AND r.mode='replay'
 AND r.plan_key=@original AND r.status='completed' AND r.core_records_failed=0
 AND r.source_records_read=0 AND r.raw_pages_written=0 AND r.replay_records_read>0
 AND r.core_records_processed=r.replay_records_read
 AND (o.metrics_version IS NULL OR o.metrics_version=1
  OR (o.metrics_version=2 AND r.replay_records_read=o.original_processed))
), replays AS (
 SELECT COUNT(*) successful_replay_count, MIN(run_id) successful_replay_id
 FROM successful_replays
)
SELECT @store store_id, @original original_run_id,
 c.*, o.original_count, o.original_valid_count,
 r.successful_replay_count, r.successful_replay_id
FROM checkpoints c CROSS JOIN originals o CROSS JOIN replays r
)"""


def mutation_query(project: str) -> str:
    # All proof checks occur again in the SAME transaction snapshot as UPDATE.
    # @@row_count is asserted immediately, before any subsequent statement.
    supported = ",".join(f"'{resource}'" for resource in sorted(RESOURCES))
    return f"""BEGIN TRANSACTION;
CREATE TEMP TABLE recovery_proof AS {proof_query(project)};
ASSERT (SELECT checkpoint_count=1 AND checkpoint_key=@checkpoint
 AND resource IN ({supported}) AND resource=@resource
 AND checkpoint_status='{CHECKPOINT_NEEDS_REVIEW}' AND pending_count=0
 FROM recovery_proof) AS 'checkpoint_recovery_failed';
ASSERT (SELECT original_count=1 AND original_valid_count=1
 FROM recovery_proof) AS 'checkpoint_recovery_failed';
ASSERT (SELECT successful_replay_count=1 AND successful_replay_id=@replay
 FROM recovery_proof) AS 'checkpoint_recovery_failed';
UPDATE `{project}.up_ops.sync_checkpoints`
SET status='{CHECKPOINT_RECOVERED}', updated_at=CURRENT_TIMESTAMP()
WHERE store_id=@store AND run_id=@original AND row_key=@checkpoint
 AND status='{CHECKPOINT_NEEDS_REVIEW}' AND pending_raw_id IS NULL;
ASSERT @@row_count=1 AS 'checkpoint_recovery_failed';
COMMIT TRANSACTION;"""
