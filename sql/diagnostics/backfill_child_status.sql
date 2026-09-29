-- READ ONLY. Bind @store STRING and @run_ids ARRAY<STRING> obtained from execution logs.
-- Do not infer membership solely from time or only select the latest successful runs.
SELECT run_id, resource, mode, status, started_at, finished_at, error_summary,
  metrics_version, source_records_read, raw_pages_written, core_records_processed,
  core_records_inserted, core_records_updated, core_records_failed
FROM `up-data-intelligence-dev.up_ops.sync_runs`
WHERE store_id = @store AND run_id IN UNNEST(@run_ids)
ORDER BY started_at, run_id;

-- Cumulative distinct child-run totals; not delta work of one execution attempt.
SELECT resource, status, COUNT(DISTINCT run_id) AS child_runs,
  COUNTIF(metrics_version IS NULL OR metrics_version != 2) AS legacy_metric_runs,
  SUM(source_records_read) AS source_records_read,
  SUM(raw_pages_written) AS raw_pages_written,
  SUM(core_records_processed) AS core_records_processed,
  SUM(core_records_inserted) AS core_records_inserted,
  SUM(core_records_updated) AS core_records_updated,
  SUM(core_records_failed) AS core_records_failed
FROM `up-data-intelligence-dev.up_ops.sync_runs`
WHERE store_id = @store AND run_id IN UNNEST(@run_ids)
GROUP BY resource, status;
