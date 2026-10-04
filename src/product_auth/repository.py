"""Bounded parameterized metadata reads; no authorization cache."""

from typing import Any
from uuid import uuid4

from src.dashboard.queries import Query, table
from src.dashboard.repository import Reader


class BigQueryAccess:
    def __init__(self, reader: Reader, project: str):
        table(project, "up_analytics", "analytics_publications")
        self.reader, self.project = reader, project

    def access(self, identity_hash: str) -> list[dict[str, Any]]:
        return self.reader.query(
            Query(
                "principal_access",
                f"SELECT * FROM `{self.project}.up_ops.principal_access` WHERE identity_hash=@identity LIMIT 101",
                {"identity": ("STRING", identity_hash)},
            ),
            request_id=uuid4().hex,
            store_id="authorization",
            generation=None,
        )

    def bindings(self, tenants: frozenset[str]) -> list[dict[str, Any]]:
        import json

        return self.reader.query(
            Query(
                "workspace_bindings",
                f"SELECT * FROM `{self.project}.up_ops.workspace_store_bindings` WHERE tenant_id IN (SELECT JSON_VALUE(v) FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@tenants))) v) LIMIT 1001",
                {"tenants": ("STRING", json.dumps(sorted(tenants)))},
            ),
            request_id=uuid4().hex,
            store_id="authorization",
            generation=None,
        )
