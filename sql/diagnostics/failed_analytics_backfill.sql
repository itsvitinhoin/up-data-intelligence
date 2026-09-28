-- READ ONLY diagnostic, not executed. Counts/metadata only, no source payload.
-- Match candidate runs, then correlate started_at to the failed execution logs.
-- Execution name is NOT stored in the old sync_runs schema; don't infer a match.
SELECT
  r.run_id, r.status AS run_status, r.error_summary, r.started_at, r.finished_at,
  r.pages AS completed_pages, r.records_read, r.bytes,
  c.status AS checkpoint_status, c.pending_raw_id,
  c.pending_raw_id IS NOT NULL AS has_pending_raw,
  raw.raw_record_id IS NOT NULL AS pending_raw_exists,
  raw.bytes_read AS pending_response_bytes,
  BYTE_LENGTH(TO_JSON_STRING(raw.payload)) AS pending_payload_json_bytes,
  ARRAY_LENGTH(JSON_QUERY_ARRAY(raw.payload, '$.data')) AS pending_fact_count,
  (SELECT COUNT(*) FROM `up-data-intelligence-dev.up_core.analytics_events_versions` v
   WHERE v.store_id=r.store_id AND v.run_id=r.run_id) AS committed_event_versions
FROM `up-data-intelligence-dev.up_ops.sync_runs` r
JOIN `up-data-intelligence-dev.up_ops.sync_checkpoints` c
  ON r.run_id=c.run_id AND r.store_id=c.store_id
LEFT JOIN `up-data-intelligence-dev.up_raw.upzero_analytics_facts` raw
  ON raw.raw_record_id=c.pending_raw_id AND raw.store_id=c.store_id
WHERE r.store_id='mx-fashion' AND r.resource='analytics_facts' AND r.mode='backfill'
  AND TIMESTAMP(JSON_VALUE(c.filters, '$.from'))=TIMESTAMP('2026-09-25T12:00:00Z')
  AND TIMESTAMP(JSON_VALUE(c.filters, '$.to'))=TIMESTAMP('2026-09-25T13:00:00Z')
ORDER BY r.started_at DESC;
