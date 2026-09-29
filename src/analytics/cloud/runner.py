"""Compose injected adapters around the approved Python engine; no credentials/live factory."""

from src.analytics.cloud.reader import BigQueryAnalyticsReader
from src.analytics.cloud.writer import BigQueryAnalyticsWriter, Publication
from src.analytics.engine import Row
from src.analytics.materialization import calculate
from src.observability.logging import event


def materialize(
    reader: BigQueryAnalyticsReader, writer: BigQueryAnalyticsWriter, publication: Publication
) -> Row:
    if reader.policy != publication.policy:
        raise ValueError("policy_hash_mismatch")
    meta = {
        "publication_id": publication.publication_id,
        "store_id": publication.policy.store_id,
        "policy_hash": publication.policy.policy_hash,
        "as_of": publication.policy.as_of,
        "report_from": publication.policy.report_from,
        "report_to": publication.policy.report_to,
    }
    transports = {id(t): t for t in (reader.transport, writer.transport)}
    before = {key: t.bytes_processed for key, t in transports.items()}
    event("analytics_execution_started", **meta)
    try:
        if saved := writer.reconcile(publication):
            event("analytics_publication_reconciled", **meta)
            event("analytics_execution_finished", status="completed", **meta)
            return saved
        snapshot = reader.snapshot(
            publication.source, publication.plan, full_refresh=publication.full_refresh_authorized
        )
        tables, findings, read = calculate(publication.policy, snapshot, publication.plan)
        for finding in findings:
            event("analytics_quality", **finding, **meta)
        receipt = writer.publish(publication, tables, findings=findings)
        measured: list[int | None] = []
        for key, transport in transports.items():
            start = before[key]
            end = transport.bytes_processed
            measured.append(end - start if start is not None and end is not None else None)
        event(
            "analytics_execution_finished",
            status="completed",
            rows_read=read,
            rows_generated=sum(map(len, tables.values())),
            rows_failed=0,
            bytes_processed=sum(v for v in measured if v is not None)
            if all(v is not None for v in measured)
            else None,
            **meta,
        )
        return receipt
    except Exception:
        event("analytics_execution_finished", status="failed", rows_failed=None, **meta)
        raise
