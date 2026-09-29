"""Seven-slice publication using session TEMP staging and one BigQuery transaction.

An externally provisioned singleton HEAD per store/policy is mandatory. This
avoids unsafe concurrent INSERT-based lock acquisition (BQ keys are unenforced).
"""

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.analytics.cloud.reader import SourceGeneration
from src.analytics.cloud.transport import Transport, array, scalar
from src.analytics.config import AnalyticsPolicy
from src.analytics.engine import Row
from src.analytics.materialization import SCOPE_FIELDS, Plan
from src.analytics.policy import VERSION
from src.analytics.quality import GRAINS, validate_outputs
from src.analytics.schema import SCHEMAS
from src.analytics.serialization import encode_tables
from src.observability.logging import event
from src.utils.data import canonical, digest


@dataclass(frozen=True)
class Publication:
    policy: AnalyticsPolicy
    source: SourceGeneration
    plan: Plan
    expected_generation: int
    full_refresh_authorized: bool = False

    def __post_init__(self) -> None:
        if set(self.plan.scopes) != set(SCHEMAS) or self.expected_generation < 0:
            raise ValueError("invalid_publication_scope")
        if (
            self.plan.full or any(s is None for s in self.plan.scopes.values())
        ) and not self.full_refresh_authorized:
            raise ValueError("full_refresh_requires_authorization")
        if not self.source.completeness_confirmed and not self.full_refresh_authorized:
            raise ValueError("unsealed_source_generation")

    @property
    def publication_id(self) -> str:
        return digest(
            [
                self.policy.to_dict(),
                self.source.generation,
                self.source.snapshot_at,
                {m: sorted(v) if v is not None else None for m, v in self.plan.scopes.items()},
            ]
        )

    def parameters(self) -> list[Any]:
        p = self.policy
        params = [
            scalar("publication", "STRING", self.publication_id),
            scalar("store", "STRING", p.store_id),
            scalar("policy", "STRING", p.policy_hash),
            scalar("currency", "STRING", p.currency),
            scalar("as_of", "TIMESTAMP", p.as_of),
            scalar("report_from", "DATE", p.report_from),
            scalar("report_to", "DATE", p.report_to),
            scalar("expected", "INT64", self.expected_generation),
            scalar("version", "STRING", VERSION),
            scalar("watermark", "STRING", self.source.generation),
        ]
        for n, model in enumerate(SCHEMAS):
            scope = self.plan.scopes[model]
            params += [
                scalar(f"full_{n}", "BOOL", scope is None),
                array(f"scope_{n}", sorted(scope or [])),
            ]
        return params


def validate_staging(
    pub: Publication, tables: dict[str, list[Row]], findings: list[Row]
) -> dict[str, list[Row]]:
    if set(tables) != set(SCHEMAS):
        raise ValueError("analytics_schema_mismatch")
    encoded = encode_tables(tables)
    for model, rows in encoded.items():
        seen = set()
        for row in rows:
            if (
                not isinstance(row["row_key"], str)
                or not row["row_key"].strip()
                or row["row_key"] in seen
            ):
                raise ValueError("analytics_materialization_duplicate_key")
            seen.add(row["row_key"])
            if (
                row["store_id"] != pub.policy.store_id
                or row["policy_hash"] != pub.policy.policy_hash
            ):
                raise ValueError("policy_hash_mismatch")
            if row["currency"] != pub.policy.currency or not pub.plan.contains(model, row):
                raise ValueError("analytics_invalid_staging_scope_or_currency")
    if any(q["severity"] == "blocking" for q in findings + validate_outputs(encoded)):
        raise ValueError("analytics_materialization_quality_failed")
    return encoded


def stage_ddl() -> str:
    return "\n".join(
        "CREATE TEMP TABLE stage_"
        + m
        + " ("
        + ",".join(f"`{f}` {t}" for f, t in s.fields.items())
        + ");"
        for m, s in SCHEMAS.items()
    )


def stage_insert(model: str) -> str:
    expressions = []
    for f, t in SCHEMAS[model].fields.items():
        expressions.append(f"CAST(JSON_VALUE(r,'$.{f}') AS {t})")
    fields = ",".join(f"`{f}`" for f in SCHEMAS[model].fields)
    return (
        f"INSERT INTO _SESSION.stage_{model} ({fields}) SELECT "
        + ",".join(expressions)
        + " FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@rows))) r"
    )


def commit_sql(project: str) -> str:
    # project is validated by CloudConfig before reaching this function.
    from src.analytics.cloud.transport import CloudConfig

    CloudConfig(project, "validation-only", 1, 1, False)
    receipt = f"`{project}.up_analytics.analytics_publications`"
    head = "record_kind='HEAD' AND store_id=@store AND policy_hash=@policy"
    pieces = [
        "BEGIN TRANSACTION;",
        f"ASSERT (SELECT COUNT(*) FROM {receipt} WHERE {head})=1 AS 'publication_head_required';",
        f"ASSERT (SELECT generation FROM {receipt} WHERE {head})=@expected AS 'stale_publication_generation';",
        f"ASSERT NOT EXISTS(SELECT publication_id FROM {receipt} WHERE record_kind='RECEIPT' AND store_id=@store AND policy_hash=@policy AND publication_id=@publication) AS 'receipt_already_committed';",
        f"ASSERT NOT EXISTS(SELECT as_of FROM {receipt} WHERE {head} AND as_of>@as_of) AS 'analytics_model_stale';",
        "CREATE TEMP TABLE publication_counts(model STRING, rows_generated INT64, rows_inserted INT64, rows_updated INT64, rows_deleted INT64);",
    ]
    for n, (model, spec) in enumerate(SCHEMAS.items()):
        stage = "_SESSION.stage_" + model
        target = f"`{project}.up_analytics.{model}`"
        scope = f"(@full_{n} OR CAST({SCOPE_FIELDS[model]} AS STRING) IN UNNEST(@scope_{n}))"
        where = f"store_id=@store AND policy_hash=@policy AND {scope}"
        grain = ",".join(GRAINS[model])
        pieces += [
            f"ASSERT NOT EXISTS(SELECT row_key FROM {stage} WHERE row_key IS NULL OR TRIM(row_key)='' OR store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR currency IS DISTINCT FROM @currency OR NOT {scope}) AS 'invalid_staging_scope';",
            f"ASSERT NOT EXISTS(SELECT row_key FROM {stage} GROUP BY row_key HAVING COUNT(*)>1) AS 'duplicate_staging_key';",
            f"ASSERT NOT EXISTS(SELECT {grain} FROM {stage} GROUP BY {grain} HAVING COUNT(*)>1) AS 'duplicate_staging_grain';",
            f"ASSERT NOT EXISTS(SELECT row_key FROM {target} WHERE {where} GROUP BY row_key HAVING COUNT(*)>1) AS 'duplicate_target_key';",
            f"INSERT INTO _SESSION.publication_counts SELECT '{model}',(SELECT COUNT(*) FROM {stage}),(SELECT COUNT(*) FROM {stage} s WHERE NOT EXISTS(SELECT t.row_key FROM {target} t WHERE t.store_id=@store AND t.policy_hash=@policy AND t.row_key=s.row_key)),(SELECT COUNT(*) FROM {stage} s JOIN {target} t ON t.store_id=@store AND t.policy_hash=@policy AND t.row_key=s.row_key WHERE TO_JSON_STRING(s)!=TO_JSON_STRING(t)),(SELECT COUNT(*) FROM {target} WHERE {where} AND row_key NOT IN (SELECT row_key FROM {stage}));",
            f"DELETE FROM {target} WHERE {where};",
        ]
        fields = ",".join(f"`{f}`" for f in spec.fields)
        pieces.append(f"INSERT INTO {target} ({fields}) SELECT {fields} FROM {stage};")
    pieces += [
        f"UPDATE {receipt} SET generation=@expected+1, publication_id=@publication, as_of=@as_of, finished_at=CURRENT_TIMESTAMP(), status='completed', source_watermark=@watermark WHERE {head} AND generation=@expected;",
        "ASSERT @@row_count=1 AS 'stale_publication_generation';",
        f"INSERT INTO {receipt} (record_kind,publication_id,store_id,policy_hash,generation,as_of,report_from,report_to,started_at,finished_at,status,analytics_version,source_watermark,models,row_counts,bytes_processed,bytes_processed_before_commit,commit_job_id) SELECT 'RECEIPT',@publication,@store,@policy,@expected+1,@as_of,@report_from,@report_to,@started_at,CURRENT_TIMESTAMP(),'completed',@version,@watermark,TO_JSON(ARRAY(SELECT model FROM _SESSION.publication_counts ORDER BY model)),TO_JSON(ARRAY(SELECT AS STRUCT model,rows_generated,rows_inserted,rows_updated,rows_deleted FROM _SESSION.publication_counts ORDER BY model)),CAST(NULL AS INT64),@bytes_before_commit,@commit_job_id;",
        "COMMIT TRANSACTION;",
    ]
    return "\n".join(pieces)


class BigQueryAnalyticsWriter:
    def __init__(self, transport: Transport, *, max_chunk_bytes: int = 500000):
        if max_chunk_bytes < 1000 or max_chunk_bytes > 1000000:
            raise ValueError("invalid_staging_chunk_budget")
        self.transport = transport
        self.max_chunk_bytes = max_chunk_bytes

    def reconcile(self, pub: Publication) -> Row | None:
        sql = f"SELECT publication_id,store_id,policy_hash,generation,status,source_watermark,row_counts,bytes_processed FROM `{self.transport.config.project}.up_analytics.analytics_publications` WHERE record_kind='RECEIPT' AND store_id=@store AND policy_hash=@policy AND publication_id=@publication"
        rows, _ = self.transport.query(sql, pub.parameters())
        if len(rows) > 1:
            raise ValueError("duplicate_publication_receipt")
        if rows:
            row = rows[0]
            if (
                row["publication_id"] != pub.publication_id
                or row["store_id"] != pub.policy.store_id
                or row["policy_hash"] != pub.policy.policy_hash
                or row["status"] != "completed"
                or row["source_watermark"] != pub.source.generation
            ):
                raise ValueError("invalid_publication_receipt")
            return row
        return None

    def publish(
        self, pub: Publication, tables: dict[str, list[Row]], *, findings: list[Row]
    ) -> Row:
        encoded = validate_staging(pub, tables, findings)
        meta = {
            "publication_id": pub.publication_id,
            "store_id": pub.policy.store_id,
            "policy_hash": pub.policy.policy_hash,
        }
        if saved := self.reconcile(pub):
            event("analytics_publication_reconciled", **meta)
            return saved
        event("analytics_publication_started", **meta)
        session = None
        try:
            _, session = self.transport.query(stage_ddl(), [], create_session=True)
            if not session:
                raise ValueError("bigquery_session_required")
            for model, rows in encoded.items():
                event("analytics_model_started", model=model, **meta)
                chunk: list[Row] = []
                for row in rows:
                    if len(canonical([row]).encode()) > self.max_chunk_bytes:
                        raise ValueError("analytics_staging_row_too_large")
                    if chunk and len(canonical(chunk + [row]).encode()) > self.max_chunk_bytes:
                        self.transport.query(
                            stage_insert(model),
                            [scalar("rows", "STRING", canonical(chunk))],
                            session=session,
                        )
                        chunk = []
                    chunk.append(row)
                if chunk:
                    self.transport.query(
                        stage_insert(model),
                        [scalar("rows", "STRING", canonical(chunk))],
                        session=session,
                    )
            from src.utils.data import now

            attempt_id = "analytics_" + pub.publication_id + "_" + uuid4().hex
            params = pub.parameters() + [
                scalar("started_at", "TIMESTAMP", now()),
                scalar("commit_job_id", "STRING", attempt_id),
                scalar("bytes_before_commit", "INT64", self.transport.bytes_processed),
            ]
            # Unique attempt ID, job_retry=None. Receipt is the idempotency boundary.
            self.transport.query(
                commit_sql(self.transport.config.project),
                params,
                session=session,
                job_id=attempt_id,
            )
            saved = self.reconcile(pub)
            if not saved:
                raise ValueError("publication_receipt_not_visible")
            event(
                "analytics_publication_committed",
                bytes_processed=self.transport.bytes_processed,
                duration_ms=self.transport.duration_ms,
                **meta,
            )
            raw_counts = saved.get("row_counts")
            counts = json.loads(raw_counts) if isinstance(raw_counts, str) else raw_counts
            by_model = {r["model"]: r for r in counts} if isinstance(counts, list) else {}
            for model, rows in encoded.items():
                scope = pub.plan.scopes[model]
                stats = by_model.get(model, {})
                event(
                    "analytics_model_finished",
                    model=model,
                    rows_generated=len(rows),
                    rows_inserted=stats.get("rows_inserted"),
                    rows_updated=stats.get("rows_updated"),
                    rows_deleted=stats.get("rows_deleted"),
                    rows_failed=0,
                    affected_scope_count=len(scope) if scope is not None else None,
                    **meta,
                )
            return saved
        except Exception:
            # Ambiguous COMMIT acknowledgement is resolved by receipt, never blind replay.
            if saved := self.reconcile(pub):
                event("analytics_publication_reconciled", **meta)
                return saved
            raise
        finally:
            if session:
                try:
                    self.transport.query("CALL BQ.ABORT_SESSION();", [], session=session)
                except Exception:
                    pass  # Session expiry is the fallback; never mask publication outcome.
