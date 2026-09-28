import json
import re
import sqlite3
from collections.abc import Iterator, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from src.bigquery.catalog import TABLES
from src.bigquery.writer import AtomicWriter
from src.domain.models import SafeError
from src.utils.data import canonical


def decode_row(body: str, table: str) -> dict[str, Any]:
    row: dict[str, Any] = json.loads(body, parse_float=Decimal)
    for key, typ in TABLES[table].fields.items():
        if typ == "NUMERIC" and row.get(key) is not None:
            row[key] = str(row[key])

    def json_numbers(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {k: json_numbers(v) for k, v in value.items()}
        if isinstance(value, list):
            return [json_numbers(v) for v in value]
        return value

    return {k: json_numbers(v) for k, v in row.items()}


class Repository(Protocol):
    def read(
        self, table: str, store: str, keys: Sequence[str] | None = None
    ) -> list[dict[str, Any]]: ...
    def write(self, tables: dict[str, list[dict[str, Any]]]) -> None: ...
    def find(
        self, table: str, store: str, field: str, values: Sequence[str]
    ) -> list[dict[str, Any]]: ...

    def iter_find(
        self, table: str, store: str, field: str, values: Sequence[str]
    ) -> Iterator[dict[str, Any]]: ...


class SQLiteRepository:
    """Offline integration adapter. Writes across tables are atomic, same as BQ script."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (tbl TEXT, store TEXT, key TEXT, body TEXT, PRIMARY KEY(tbl, store, key))"
        )

    def close(self) -> None:
        self.db.close()

    def read(
        self, table: str, store: str, keys: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        if table not in TABLES:
            raise SafeError("invalid_table")
        rows = [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT body FROM records WHERE tbl=? AND store=?", (table, store)
            )
        ]
        return [r for r in rows if keys is None or r["row_key"] in keys]

    def find(
        self, table: str, store: str, field: str, values: Sequence[str]
    ) -> list[dict[str, Any]]:
        return [r for r in self.read(table, store) if r.get(field) in values]

    def iter_find(
        self, table: str, store: str, field: str, values: Sequence[str]
    ) -> Iterator[dict[str, Any]]:
        if field not in TABLES[table].fields:
            raise SafeError("invalid_column")
        placeholders = ",".join("?" for _ in values)
        query = f"SELECT body FROM records WHERE tbl=? AND store=? AND json_extract(body, ?) IN ({placeholders}) ORDER BY json_extract(body, '$.ingested_at')"
        for row in self.db.execute(query, (table, store, "$." + field, *values)):
            yield json.loads(row[0])

    def write(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        with self.db:
            for table, rows in tables.items():
                if table not in TABLES:
                    raise SafeError("invalid_table")
                for row in rows:
                    if set(row) - TABLES[table].fields.keys():
                        raise SafeError("unknown_column")
                    self.db.execute(
                        "INSERT OR REPLACE INTO records VALUES (?,?,?,?)",
                        (table, row["store_id"], row["row_key"], canonical(row)),
                    )


def merge_sql(project: str, table: str, *, staged: bool = False) -> str:
    spec = TABLES[table]
    source = "_SESSION.write_records" if staged else "UNNEST(@records) item"
    projection = []
    for name, typ in spec.fields.items():
        if typ == "JSON":
            expression = f"JSON_QUERY(record, '$.{name}')"
        else:
            expression = f"JSON_VALUE(record, '$.{name}')"
            if typ != "STRING":
                expression = f"CAST({expression} AS {typ})"
        projection.append(f"{expression} AS `{name}`")
    columns = ", ".join(f"`{c}`" for c in spec.fields)
    updates = ", ".join(f"T.`{c}`=S.`{c}`" for c in spec.fields if c not in {"row_key", "store_id"})
    return f"""MERGE `{project}.{spec.dataset}.{table}` T
USING (SELECT {", ".join(projection)} FROM (
 SELECT JSON_QUERY(PARSE_JSON(item), '$.record') AS record
 FROM {source} WHERE JSON_VALUE(item, '$.target_table')='{table}'
)
QUALIFY ROW_NUMBER() OVER (PARTITION BY JSON_VALUE(record, '$.store_id'), JSON_VALUE(record, '$.row_key') ORDER BY JSON_VALUE(record, '$.row_key'))=1) S
ON T.row_key=S.row_key AND T.store_id=S.store_id
WHEN MATCHED THEN UPDATE SET {updates}
WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({", ".join("S.`" + c + "`" for c in spec.fields)});"""


class BigQueryRepository:
    def __init__(self, project: str, location: str):
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project) or not location:
            raise SafeError("invalid_bigquery_configuration")
        from google.cloud import bigquery

        self.client = bigquery.Client(project=project, location=location)
        self.project, self.location = project, location

    def read(
        self, table: str, store: str, keys: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        from google.cloud import bigquery

        spec = TABLES[table]
        params: list[Any] = [bigquery.ScalarQueryParameter("store", "STRING", store)]
        query = f"SELECT TO_JSON_STRING(t) AS body FROM `{self.project}.{spec.dataset}.{table}` t WHERE store_id=@store"
        if keys is not None:
            if not keys:
                return []
            params.append(bigquery.ArrayQueryParameter("keys", "STRING", list(keys)))
            query += " AND row_key IN UNNEST(@keys)"
        try:
            return [
                decode_row(r.body, table)
                for r in self.client.query(
                    query, job_config=bigquery.QueryJobConfig(query_parameters=params)
                ).result()
            ]
        except Exception:
            raise SafeError("bigquery_read_failed") from None

    def find(
        self, table: str, store: str, field: str, values: Sequence[str]
    ) -> list[dict[str, Any]]:
        from google.cloud import bigquery

        spec = TABLES[table]
        if field not in spec.fields:
            raise SafeError("invalid_column")
        query = f"SELECT TO_JSON_STRING(t) AS body FROM `{self.project}.{spec.dataset}.{table}` t WHERE store_id=@store AND `{field}` IN UNNEST(@values)"
        try:
            return [
                decode_row(r.body, table)
                for r in self.client.query(
                    query,
                    job_config=bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("store", "STRING", store),
                            bigquery.ArrayQueryParameter("values", "STRING", list(values)),
                        ]
                    ),
                ).result()
            ]
        except Exception:
            raise SafeError("bigquery_read_failed") from None

    def iter_find(
        self, table: str, store: str, field: str, values: Sequence[str]
    ) -> Iterator[dict[str, Any]]:
        from google.cloud import bigquery

        spec = TABLES[table]
        if field not in spec.fields:
            raise SafeError("invalid_column")
        order = "ingested_at" if "ingested_at" in spec.fields else "row_key"
        query = f"SELECT TO_JSON_STRING(t) AS body FROM `{self.project}.{spec.dataset}.{table}` t WHERE store_id=@store AND `{field}` IN UNNEST(@values) ORDER BY `{order}`"
        try:
            rows = self.client.query(
                query,
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("store", "STRING", store),
                        bigquery.ArrayQueryParameter("values", "STRING", list(values)),
                    ]
                ),
            ).result()
            for row in rows:
                yield decode_row(row.body, table)
        except Exception:
            raise SafeError("bigquery_read_failed") from None

    def write(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        records: list[str] = []
        for table, rows in tables.items():
            if table not in TABLES:
                raise SafeError("invalid_table")
            for row in {(r["store_id"], r["row_key"]): r for r in rows}.values():
                if set(row) - TABLES[table].fields.keys():
                    raise SafeError("unknown_column")
                records.append(canonical({"target_table": table, "record": row}))
        if not records:
            return

        def script(staged: bool) -> str:
            return (
                "BEGIN TRANSACTION;\n"
                + "\n".join(
                    merge_sql(self.project, table, staged=staged)
                    for table, rows in tables.items()
                    if rows
                )
                + "\nCOMMIT TRANSACTION;"
            )

        AtomicWriter(self.client, self.location).write(records, script(False), script(True))
