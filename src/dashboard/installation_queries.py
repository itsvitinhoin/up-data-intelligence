"""Operational metadata only. No RAW payload, secrets, cursors or CORE scans."""

from src.dashboard.queries import Query, table

OPS = {"store_runtime_config", "source_connections", "sync_checkpoints", "sync_runs"}


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
    if name == "installation_registry":
        sql = f"""SELECT store_id,status,operation_b2b,history_complete,facts_complete,
 timezone,currency,policy_version,history_coverage,facts_coverage_from,facts_coverage_to,
 upzero_enabled,meta_enabled,upzero_connection_id,meta_connection_id,updated_at,
 CURRENT_TIMESTAMP() AS snapshot_at
 FROM {ops("store_runtime_config")} WHERE store_id=@store LIMIT 2"""
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
