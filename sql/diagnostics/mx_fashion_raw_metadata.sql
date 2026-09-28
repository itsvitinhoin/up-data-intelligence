-- READ ONLY. Run on DEV using an authorized identity; outputs no payload/PII.
-- Cursor contents are deliberately represented by presence/length/hash.
SELECT r.raw_record_id, r.run_id, r.request_id, r.ingested_at,
  ARRAY_LENGTH(JSON_QUERY_ARRAY(r.payload, '$.data')) AS fact_count,
  r.bytes_read AS response_bytes,
  BYTE_LENGTH(TO_JSON_STRING(r.payload)) AS stored_payload_json_bytes,
  JSON_VALUE(r.request_filters, '$.from') AS window_from,
  JSON_VALUE(r.request_filters, '$.to') AS window_to,
  JSON_VALUE(r.request_filters, '$.limit') AS explicit_page_limit,
  JSON_VALUE(r.position, '$.cursor') IS NOT NULL AS has_cursor,
  LENGTH(JSON_VALUE(r.position, '$.cursor')) AS cursor_length,
  TO_HEX(SHA256(JSON_VALUE(r.position, '$.cursor'))) AS cursor_sha256,
  JSON_VALUE(r.next_position, '$.cursor') IS NOT NULL AS has_next_cursor,
  LENGTH(JSON_VALUE(r.next_position, '$.cursor')) AS next_cursor_length,
  TO_HEX(SHA256(JSON_VALUE(r.next_position, '$.cursor'))) AS next_cursor_sha256,
  c.status AS checkpoint_status, c.pending_raw_id, c.completed_to,
  JSON_VALUE(c.position, '$.cursor') IS NOT NULL AS checkpoint_has_cursor,
  c.pending_raw_id=r.raw_record_id AS checkpoint_points_to_raw
FROM `up-data-intelligence-dev.up_raw.upzero_analytics_facts` r
LEFT JOIN `up-data-intelligence-dev.up_ops.sync_checkpoints` c
  ON c.store_id=r.store_id AND c.run_id=r.run_id
WHERE r.store_id='mx-fashion'
  AND r.run_id='affd46d5-3371-448c-aa2b-0afb7e7625db';
