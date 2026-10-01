"""Parameterized registry SQL. All reads and transactions have a query ceiling."""

import json
from typing import Any

from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized

from src.analytics.cloud.transport import Transport, scalar
from src.control_plane.model import PIPELINES, REGISTRY, REGISTRY_FIELDS, StoreConfig
from src.domain.models import SafeError


class BigQueryRegistry:
    def __init__(self, transport: Transport):
        self.transport = transport
        self.table = f"`{transport.config.project}.up_ops.{REGISTRY}`"

    def get(self, store: str) -> StoreConfig | None:
        rows, _ = self.transport.query(
            f"SELECT * FROM {self.table} WHERE store_id=@store LIMIT 2",
            [scalar("store", "STRING", store)],
        )
        if len(rows) > 1:
            raise SafeError("duplicate_store_registry")
        config = StoreConfig.from_row(rows[0]) if rows else None
        if config is not None and config.store_id != store:
            raise SafeError("registry_store_scope_mismatch")
        return config

    def eligible(self, pipeline: str, limit: int) -> list[StoreConfig]:
        if pipeline not in PIPELINES or not 1 <= limit <= 1000:
            raise SafeError("invalid_dispatch_selection")
        rows, _ = self.transport.query(
            f"SELECT * FROM {self.table} WHERE status='ACTIVE' AND sync_enabled=true AND {pipeline}_enabled=true ORDER BY store_id LIMIT @limit",
            [scalar("limit", "INT64", limit + 1)],
        )
        if len(rows) > limit:
            raise SafeError("dispatch_store_limit_exceeded")
        configs = [StoreConfig.from_row(row) for row in rows]
        if len({c.store_id for c in configs}) != len(configs) or any(
            not c.eligible(pipeline) for c in configs
        ):
            raise SafeError("invalid_dispatch_registry")
        return configs

    def save(self, config: StoreConfig, expected_revision: int | None) -> None:
        columns = list(REGISTRY_FIELDS)
        expressions = [
            f"JSON_QUERY(r,'$.{k}')" if t == "JSON" else f"CAST(JSON_VALUE(r,'$.{k}') AS {t})"
            for k, t in REGISTRY_FIELDS.items()
        ]
        params = [
            scalar("store", "STRING", config.store_id),
            scalar("record", "STRING", json.dumps(config.row(), separators=(",", ":"))),
            scalar("revision", "INT64", expected_revision),
        ]
        projection = (
            "SELECT "
            + ",".join(f"{v} `{k}`" for k, v in zip(columns, expressions, strict=True))
            + " FROM (SELECT PARSE_JSON(@record) r)"
        )
        if expected_revision is None:
            guard = f"ASSERT NOT EXISTS(SELECT 1 FROM {self.table} WHERE store_id=@store) AS 'store_already_registered';"
            mutation = f"INSERT INTO {self.table} ({','.join(columns)}) {projection};"
        else:
            guard = f"ASSERT (SELECT COUNT(*) FROM {self.table} WHERE store_id=@store)=1 AND (SELECT revision FROM {self.table} WHERE store_id=@store)=@revision AS 'registry_revision_conflict';"
            mutation = (
                f"MERGE {self.table} t USING ({projection}) s ON t.store_id=s.store_id WHEN MATCHED THEN UPDATE SET "
                + ",".join(f"`{k}`=s.`{k}`" for k in columns if k != "store_id")
                + ";"
            )
        try:
            self.transport.query(
                "BEGIN TRANSACTION; " + guard + mutation + " COMMIT TRANSACTION;", params
            )
        except (BadRequest, Forbidden, Unauthorized):
            raise SafeError("registry_write_failed") from None
        except Exception:
            raise SafeError("registry_write_outcome_unknown") from None


def decoded(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: json.loads(v) if isinstance(v, str) and k in {"filters"} else v for k, v in row.items()
    }
