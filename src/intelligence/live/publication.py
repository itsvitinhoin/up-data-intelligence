"""Session staging, atomic receipt then HEAD; caller MUST hold the shared store lease."""

import json
from uuid import uuid4

from google.cloud import bigquery

from src.analytics.cloud.transport import Transport, scalar
from src.analytics.engine import Row
from src.bigquery.writer import REQUEST_BYTES, request_bytes
from src.domain.models import SafeError
from src.intelligence.live.schema import PUBLICATION, SCHEMAS
from src.utils.data import canonical, digest


def commit_sql(project: str) -> str:
    from src.analytics.cloud.transport import CloudConfig

    CloudConfig(project, "validation-only", 1, 1, False)
    pub = f"`{project}.up_analytics.{PUBLICATION}`"
    head = "record_kind='HEAD' AND store_id=@store AND policy_hash=@policy"
    sql = [
        "BEGIN TRANSACTION;",
        f"IF @initialize_head THEN INSERT INTO {pub}(row_key,record_kind,store_id,policy_hash,generation,status) SELECT @head,'HEAD',@store,@policy,0,'initialized' WHERE NOT EXISTS(SELECT 1 FROM {pub} WHERE store_id=@store AND policy_hash=@policy); END IF;",
        f"ASSERT (SELECT COUNT(*) FROM {pub} WHERE {head})=1 AS 'intelligence_head_required';",
        f"ASSERT (SELECT generation FROM {pub} WHERE {head})=@expected AS 'intelligence_generation_changed';",
        f"ASSERT (SELECT COALESCE(MAX(generation),0)+1 FROM {pub} WHERE store_id=@store AND policy_hash=@policy AND record_kind='RECEIPT')=@generation AS 'intelligence_sequence_changed';",
        f"ASSERT (SELECT COUNT(*) FROM `{project}.up_analytics.analytics_publications` WHERE record_kind='HEAD' AND store_id=@store AND policy_hash=@policy AND generation=@base_generation AND publication_id=@base_publication AND status='completed')=1 AS 'analytics_base_changed';",
    ]
    for name, spec in SCHEMAS.items():
        if name == PUBLICATION:
            continue
        target = f"`{project}.up_analytics.{name}`"
        stage = "_SESSION.stage_" + name
        fields = ",".join(f"`{k}`" for k in spec.fields)
        sql += [
            f"ASSERT (SELECT COUNT(*) FROM {stage})=CAST(JSON_VALUE(@counts,'$.{name}') AS INT64) AS 'intelligence_stage_count_mismatch';",
            f"ASSERT NOT EXISTS(SELECT row_key FROM {stage} WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR generation IS DISTINCT FROM @generation) AS 'invalid_intelligence_stage';",
            f"ASSERT NOT EXISTS(SELECT row_key FROM {stage} GROUP BY row_key,influence_scope HAVING COUNT(*)>1) AS 'duplicate_stage';"
            if "influence_scope" in spec.fields
            else f"ASSERT NOT EXISTS(SELECT row_key FROM {stage} GROUP BY row_key HAVING COUNT(*)>1) AS 'duplicate_stage';",
            f"ASSERT NOT EXISTS(SELECT row_key FROM {target} WHERE store_id=@store AND policy_hash=@policy AND generation=@generation) AS 'generation_already_exists';",
            f"INSERT INTO {target} ({fields}) SELECT {fields} FROM {stage};",
        ]
    fields = ",".join(f"`{k}`" for k in SCHEMAS[PUBLICATION].fields)
    updates = ",".join(
        f"`{k}`=s.`{k}`" for k in SCHEMAS[PUBLICATION].fields if k not in {"row_key", "record_kind"}
    )
    sql += [
        f"ASSERT (SELECT COUNT(*) FROM _SESSION.stage_{PUBLICATION})=1 AS 'intelligence_receipt_stage_required';",
        f"ASSERT NOT EXISTS(SELECT 1 FROM _SESSION.stage_{PUBLICATION} WHERE store_id IS DISTINCT FROM @store OR policy_hash IS DISTINCT FROM @policy OR generation IS DISTINCT FROM @generation OR publication_id IS DISTINCT FROM @publication OR record_kind IS DISTINCT FROM 'RECEIPT' OR status IS DISTINCT FROM 'completed') AS 'invalid_intelligence_receipt_stage';",
        f"INSERT INTO {pub} ({fields}) SELECT {fields} FROM _SESSION.stage_{PUBLICATION};",
        f"UPDATE {pub} h SET {updates} FROM _SESSION.stage_{PUBLICATION} s WHERE h.record_kind='HEAD' AND h.store_id=@store AND h.policy_hash=@policy AND h.generation=@expected;",
        "ASSERT @@row_count=1 AS 'intelligence_head_changed';",
        "COMMIT TRANSACTION;",
    ]
    return "\n".join(sql)


class Writer:
    def __init__(self, transport: Transport):
        self.transport = transport

    def publish(self, artifact: Row, expected: int, *, initialize_head: bool = False) -> Row:
        p = artifact["publication"]
        params = [
            scalar("store", "STRING", p["store_id"]),
            scalar("policy", "STRING", p["policy_hash"]),
            scalar("publication", "STRING", p["publication_id"]),
        ]

        def reconcile() -> Row | None:
            rows, _ = self.transport.query(
                f"SELECT * FROM `{self.transport.config.project}.up_analytics.{PUBLICATION}` WHERE record_kind='RECEIPT' AND store_id=@store AND policy_hash=@policy AND publication_id=@publication AND status='completed'",
                params,
            )
            if len(rows) > 1:
                raise ValueError("duplicate_intelligence_receipt")
            return rows[0] if rows else None

        if prior := reconcile():
            return prior
        if set(artifact["tables"]) != set(SCHEMAS):
            raise ValueError("incomplete_intelligence_models")
        tables = dict(artifact["tables"])
        publication_rows = iter(tables[PUBLICATION])
        if (
            next(publication_rows, None) != p
            or next(publication_rows, None) is not None
            or p["record_kind"] != "RECEIPT"
            or p["status"] != "completed"
            or type(p["generation"]) is not int
            or p["generation"] <= expected
        ):
            raise ValueError("invalid_intelligence_receipt")
        tables[PUBLICATION] = [p]  # Validation may consume a one-shot receipt iterator.
        if set(p["row_counts"]) != set(SCHEMAS) - {PUBLICATION} or any(
            type(n) is not int or n < 0 for n in p["row_counts"].values()
        ):
            raise ValueError("intelligence_row_counts_mismatch")
        if any(
            hasattr(rows, "__len__") and len(rows) != p["row_counts"][name]
            for name, rows in tables.items()
            if name != PUBLICATION
        ):
            raise ValueError("intelligence_row_counts_mismatch")
        session = None
        committing = False
        try:
            ddl = "\n".join(
                "CREATE TEMP TABLE stage_"
                + name
                + " ("
                + ",".join(f"`{k}` {v}" for k, v in spec.fields.items())
                + ");"
                for name, spec in SCHEMAS.items()
            )
            _, session = self.transport.query(ddl, [], create_session=True)
            if not session:
                raise ValueError("bigquery_session_required")
            for name, rows in tables.items():
                spec = SCHEMAS[name]
                fields = ",".join(f"`{k}`" for k in spec.fields)
                expressions = ",".join(
                    f"JSON_QUERY(r,'$.{k}')"
                    if typ == "JSON"
                    else f"CAST(JSON_VALUE(r,'$.{k}') AS {typ})"
                    for k, typ in spec.fields.items()
                )
                sql = f"INSERT INTO _SESSION.stage_{name} ({fields}) SELECT {expressions} FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@rows))) r"
                chunk: list[str] = []
                size = request_bytes(
                    sql, bigquery.QueryJobConfig(query_parameters=[scalar("rows", "STRING", "[]")])
                )
                base_size = size
                raw_size, seen = 2, 0
                row_ceiling = getattr(self.transport.config, "maximum_rows", 100000)
                payload_ceiling = getattr(
                    self.transport.config, "maximum_payload_bytes", 32 * 1024 * 1024
                )
                for row in rows:
                    if (
                        set(row) != set(spec.fields)
                        or row["store_id"] != p["store_id"]
                        or row["generation"] != p["generation"]
                        or row.get("policy_hash") != p["policy_hash"]
                    ):
                        raise ValueError("invalid_intelligence_stage")
                    encoded = canonical(row)
                    raw_bytes = len(encoded.encode()) + 1
                    if raw_bytes + 1 > 500000:
                        raise ValueError("intelligence_row_too_large")
                    escaped = len(json.dumps(encoded, ensure_ascii=True).encode()) + 1
                    if base_size + escaped > REQUEST_BYTES or raw_bytes + 1 > payload_ceiling:
                        raise ValueError("intelligence_row_too_large")
                    if chunk and (
                        size + escaped > REQUEST_BYTES
                        or raw_size + raw_bytes > payload_ceiling
                        or len(chunk) >= row_ceiling
                    ):
                        self.transport.query(
                            sql,
                            [scalar("rows", "STRING", "[" + ",".join(chunk) + "]")],
                            session=session,
                        )
                        chunk, size, raw_size = [], base_size, 2
                    chunk.append(encoded)
                    size += escaped
                    raw_size += raw_bytes
                    seen += 1
                if chunk:
                    self.transport.query(
                        sql,
                        [scalar("rows", "STRING", "[" + ",".join(chunk) + "]")],
                        session=session,
                    )
                if seen != (1 if name == PUBLICATION else p["row_counts"][name]):
                    raise ValueError("intelligence_row_counts_mismatch")
            committing = True
            self.transport.query(
                commit_sql(self.transport.config.project),
                params
                + [
                    scalar("expected", "INT64", expected),
                    scalar("initialize_head", "BOOL", initialize_head),
                    scalar("head", "STRING", digest([p["store_id"], p["policy_hash"], "HEAD"])),
                    scalar("counts", "STRING", canonical(p["row_counts"])),
                    scalar("generation", "INT64", p["generation"]),
                    scalar("base_generation", "INT64", p["base_generation"]),
                    scalar("base_publication", "STRING", p["base_publication_id"]),
                ],
                session=session,
                job_id="intelligence_" + uuid4().hex,
            )
            saved = reconcile()
            if not saved:
                raise ValueError("intelligence_receipt_missing")
            return saved
        except Exception:
            try:
                if saved := reconcile():
                    return saved
            except Exception:
                if committing:
                    raise SafeError("bigquery_write_outcome_unknown") from None
                raise
            if committing:
                raise SafeError("bigquery_write_outcome_unknown") from None
            raise
        finally:
            if session:
                try:
                    self.transport.query("CALL BQ.ABORT_SESSION();", [], session=session)
                except Exception:
                    pass
