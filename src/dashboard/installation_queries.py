"""Operational metadata only. No RAW payload, secrets, cursors or CORE scans."""

from src.dashboard.queries import Query, build, table

OPS = {
    "store_runtime_config",
    "source_connections",
    "sync_checkpoints",
    "sync_runs",
    "installation_plans",
    "installation_work_units",
}


def build_installation(project: str, name: str, store: str, snapshot: str | None) -> Query:
    # Reuse the project identifier validator; table names below are constants.
    table(project, "up_analytics", "analytics_publications")

    def ops(name: str) -> str:
        if name not in OPS:
            raise ValueError("installation_table_not_allowed")
        dataset = "up_core" if name == "source_connections" else "up_ops"
        return f"`{project}.{dataset}.{name}`"

    params: dict[str, tuple[str, object]] = {"store": ("STRING", store)}
    history = "FOR SYSTEM_TIME AS OF @snapshot_at"
    if snapshot is not None:
        params["snapshot_at"] = ("TIMESTAMP", snapshot)
    if name == "installation_context":
        # One fresh statement resolves Registry, immutable work, HEAD/RECEIPT
        # and published coverage. No authorization/publication cache is involved.
        head_sql = (
            build(project, "head", snapshot_at="unused")
            .sql.replace("@snapshot_at", "CURRENT_TIMESTAMP()")
            .replace(" AND h.policy_hash=@policy", "")
        )
        daily = table(project, "up_analytics", "analytics_store_daily")
        funnel = table(project, "up_analytics", "analytics_funnel_daily")
        sql = f"""WITH candidates AS (
 SELECT *,ROW_NUMBER() OVER() candidate_number FROM ({head_sql})
), store_flags AS (
 SELECT h.candidate_number, COUNT(s.store_id) observed_rows,
 ARRAY_AGG(DISTINCT TO_JSON_STRING(STRUCT(s.history_complete,s.currency,s.reporting_timezone))) flags
 FROM candidates h LEFT JOIN {daily} AS s FOR SYSTEM_TIME AS OF CURRENT_TIMESTAMP()
 ON s.store_id=h.store_id AND s.policy_hash=h.policy_hash
 AND s.order_date>=h.receipt_from AND s.order_date<h.receipt_to
 GROUP BY h.candidate_number
), fact_flags AS (
 SELECT h.candidate_number, COUNT(f.store_id) observed_rows,
 ARRAY_AGG(DISTINCT TO_JSON_STRING(STRUCT(f.observation_complete AS facts_complete))) flags
 FROM candidates h LEFT JOIN {funnel} AS f FOR SYSTEM_TIME AS OF CURRENT_TIMESTAMP()
 ON f.store_id=h.store_id AND f.policy_hash=h.policy_hash
 AND f.event_date>=h.receipt_from AND f.event_date<h.receipt_to
 GROUP BY h.candidate_number
) SELECT CURRENT_TIMESTAMP() snapshot_at,
 ARRAY(SELECT AS STRUCT * FROM {ops("store_runtime_config")}
 FOR SYSTEM_TIME AS OF CURRENT_TIMESTAMP() WHERE store_id=@store LIMIT 2) registry,
 ARRAY(SELECT AS STRUCT * FROM {ops("installation_plans")}
 FOR SYSTEM_TIME AS OF CURRENT_TIMESTAMP() WHERE store_id=@store
 ORDER BY created_at DESC LIMIT 2) plans,
 ARRAY(SELECT AS STRUCT * FROM {ops("installation_work_units")}
 FOR SYSTEM_TIME AS OF CURRENT_TIMESTAMP() WHERE store_id=@store
 ORDER BY sequence,work_unit_id LIMIT 10001) units,
 ARRAY(SELECT AS STRUCT h.* EXCEPT(candidate_number),
 s.observed_rows AS store_observed_rows,s.flags AS store_flags,
 f.observed_rows AS facts_observed_rows,f.flags AS facts_flags
 FROM candidates h JOIN store_flags s USING(candidate_number)
 JOIN fact_flags f USING(candidate_number) LIMIT 1001) heads"""
    elif name == "installation_registry":
        sql = f"""SELECT *, CURRENT_TIMESTAMP() AS snapshot_at
 FROM {ops("store_runtime_config")} WHERE store_id=@store LIMIT 2"""
    elif name == "installation_plans":
        sql = f"SELECT * FROM {ops('installation_plans')} {history} WHERE store_id=@store ORDER BY created_at DESC LIMIT 2"
    elif name == "installation_units":
        sql = f"SELECT * FROM {ops('installation_work_units')} {history} WHERE store_id=@store ORDER BY sequence,work_unit_id LIMIT 10001"
    elif name == "installation_sources":
        sql = f"""SELECT source_system,connection_id,status,updated_at
 FROM {ops("source_connections")} {history} WHERE store_id=@store
 ORDER BY source_system,connection_id LIMIT 101"""
    elif name == "installation_resources":
        sql = f"""WITH checkpoints AS (
 SELECT c.store_id,c.connection_id,c.resource,c.run_id,c.status AS checkpoint_status,
 c.mode,c.updated_at,c.filters,c.pending_raw_id IS NOT NULL AS pending_raw,
 s.source_system AS source,r.status AS run_status,r.finished_at,
 r.metrics_version,r.source_records_read,r.core_records_processed,r.core_records_failed,
 COUNTIF(c.status='needs_review' OR (c.status NOT IN ('complete','recovered') AND r.status IN ('failed','completed_with_errors')))
 OVER(PARTITION BY c.connection_id,c.resource) AS blocked_count,
 COUNTIF(c.status NOT IN ('complete','recovered') OR c.pending_raw_id IS NOT NULL)
 OVER(PARTITION BY c.connection_id,c.resource) AS pending_count,
 COUNTIF(c.pending_raw_id IS NOT NULL) OVER(PARTITION BY c.connection_id,c.resource) AS pending_raw_count,
 MAX(IF(c.status IN ('complete','recovered') AND c.pending_raw_id IS NULL,c.updated_at,NULL))
 OVER(PARTITION BY c.connection_id,c.resource) AS last_success_at,
 ROW_NUMBER() OVER(PARTITION BY c.connection_id,c.resource ORDER BY c.updated_at DESC,c.row_key DESC) AS rank
 FROM {ops("sync_checkpoints")} AS c {history}
 JOIN {ops("source_connections")} AS s {history}
 ON s.store_id=c.store_id AND s.connection_id=c.connection_id
 LEFT JOIN {ops("sync_runs")} AS r {history}
 ON r.store_id=c.store_id AND r.run_id=c.run_id AND r.resource=c.resource AND r.source=s.source_system
 WHERE c.store_id=@store
 ) SELECT source,connection_id,resource,run_id,checkpoint_status,mode,updated_at,
 filters,pending_raw,run_status,metrics_version,source_records_read,core_records_processed,
 core_records_failed,blocked_count,pending_count,pending_raw_count,last_success_at
 FROM checkpoints WHERE rank=1 ORDER BY source,connection_id,resource LIMIT 501"""
    else:
        raise ValueError("installation_query_not_allowed")
    return Query(name, f"/* dashboard:{name} */\n{sql}", params)
