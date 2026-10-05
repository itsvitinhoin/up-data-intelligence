"""Certified current catalog labels alongside generation-pinned commercial metrics.

Explicit variant IDs only. No fuzzy SKU resolution, current labels are not historical
order labels. Every version is joined through the certified snapshot membership set.
"""

import json
import re
from typing import Any

from src.dashboard.contracts import ReadError, decimal_string
from src.dashboard.queries import Query
from src.dashboard.repository import Reader
from src.domain.models import SafeError
from src.quality.catalog import certify_catalog_summary
from src.utils.data import digest

RESOURCES = ("products", "variants", "attributes", "inventory")


def table(project: str, dataset: str, name: str) -> str:
    allowed = {
        "up_ops": {"store_runtime_config", "sync_checkpoints", "sync_runs"},
        "up_core": {"source_connections", "catalog_observations"}
        | {"catalog_" + resource + "_versions" for resource in RESOURCES},
    }
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project) or name not in allowed.get(
        dataset, set()
    ):
        raise ValueError("catalog_table_not_allowed")
    return f"`{project}.{dataset}.{name}`"


class CatalogReader:
    def __init__(
        self, project: str, reader: Reader, store: str, connection: str | None, request_id: str
    ):
        self.project, self.reader, self.store, self.connection, self.request_id = (
            project,
            reader,
            store,
            connection,
            request_id,
        )
        self.proof: dict[str, Any] | None = None
        self.resolved = False

    def rows(
        self, name: str, sql: str, parameters: dict[str, tuple[str, object]]
    ) -> list[dict[str, Any]]:
        return self.reader.query(
            Query(name, sql, parameters),
            request_id=self.request_id,
            store_id=self.store,
            generation=None,
        )

    def resolve(self) -> dict[str, Any] | None:
        if self.resolved:
            return self.proof
        self.resolved = True
        if self.connection is None:
            sources = self.rows(
                "catalog_source",
                f"SELECT r.store_id,r.upzero_connection_id connection_id FROM {table(self.project, 'up_ops', 'store_runtime_config')} r JOIN {table(self.project, 'up_core', 'source_connections')} c ON c.store_id=r.store_id AND c.connection_id=r.upzero_connection_id AND c.source_system='upzero' WHERE r.store_id=@store AND r.upzero_enabled AND c.status='active' LIMIT 2",
                {"store": ("STRING", self.store)},
            )
            if not sources:
                return None
            if (
                len(sources) != 1
                or sources[0].get("store_id") != self.store
                or not sources[0].get("connection_id")
            ):
                raise ReadError(503, "catalog_source_ambiguous")
            self.connection = sources[0]["connection_id"]
        obs = table(self.project, "up_core", "catalog_observations")
        union = " UNION ALL ".join(
            f"SELECT '{resource}' resource,store_id,version_id,{identity} entity_id FROM {table(self.project, 'up_core', 'catalog_' + resource + '_versions')} WHERE store_id=@store"
            for resource, identity in (
                ("products", "product_id"),
                ("variants", "variant_id"),
                ("attributes", "attribute_id"),
                ("inventory", "variant_id"),
            )
        )
        sql = f"""WITH versions AS ({union}), checkpoints AS (
 SELECT c.*,JSON_VALUE(filters,'$.catalog_as_of') catalog_as_of
 FROM {table(self.project, "up_ops", "sync_checkpoints")} c
 WHERE store_id=@store AND connection_id=@connection AND resource IN ('products','variants','attributes','inventory')
 AND status='complete' AND pending_raw_id IS NULL
), bundle AS (
 SELECT catalog_as_of FROM checkpoints WHERE catalog_as_of IS NOT NULL
 GROUP BY catalog_as_of HAVING COUNT(*)=4 AND COUNT(DISTINCT resource)=4
 ORDER BY SAFE_CAST(catalog_as_of AS TIMESTAMP) DESC LIMIT 1
), version_counts AS (
 SELECT resource,store_id,version_id,entity_id,COUNT(*) version_matches FROM versions GROUP BY resource,store_id,version_id,entity_id
), membership AS (
 SELECT o.resource,o.run_id,COUNT(*) observations,COUNT(DISTINCT o.entity_id) distinct_entities,
 COUNTIF(o.entity_id IS NOT NULL AND o.raw_record_id IS NOT NULL AND o.observed_at IS NOT NULL AND
 v.version_matches=1) valid_version_links
 FROM {obs} o LEFT JOIN version_counts v ON v.store_id=o.store_id AND v.resource=o.resource AND v.version_id=o.entity_version_id AND v.entity_id=o.entity_id
 WHERE o.store_id=@store AND o.run_id IN (SELECT c.run_id FROM checkpoints c JOIN bundle b USING(catalog_as_of)) GROUP BY o.resource,o.run_id
)
SELECT c.catalog_as_of,TO_JSON_STRING(c) checkpoint,TO_JSON_STRING(r) run,
 COALESCE(m.observations,0) observations,COALESCE(m.distinct_entities,0) distinct_entities,COALESCE(m.valid_version_links,0) valid_version_links
 FROM checkpoints c JOIN bundle b USING(catalog_as_of)
 JOIN {table(self.project, "up_ops", "sync_runs")} r ON r.store_id=c.store_id AND r.run_id=c.run_id AND r.resource=c.resource
 LEFT JOIN membership m ON m.resource=c.resource AND m.run_id=c.run_id
 ORDER BY c.resource LIMIT 5"""
        rows = self.rows(
            "catalog_snapshot_proof",
            sql,
            {"store": ("STRING", self.store), "connection": ("STRING", self.connection)},
        )
        if not rows:
            return None
        if len(rows) != 4:
            raise ReadError(503, "catalog_snapshot_ambiguous")
        proofs = {}
        try:
            for row in rows:
                cp, run = json.loads(row["checkpoint"]), json.loads(row["run"])
                resource = cp["resource"]
                if resource in proofs:
                    raise ReadError(503, "catalog_snapshot_ambiguous")
                proofs[resource] = certify_catalog_summary(
                    self.store,
                    self.connection,
                    resource,
                    row["catalog_as_of"],
                    cp,
                    run,
                    observations=row["observations"],
                    distinct_entities=row["distinct_entities"],
                    valid_version_links=row["valid_version_links"],
                )
        except (SafeError, ValueError, TypeError, KeyError):
            raise ReadError(503, "catalog_snapshot_not_certified") from None
        if (
            set(proofs) != set(RESOURCES)
            or len({p["snapshot_as_of"] for p in proofs.values()}) != 1
        ):
            raise ReadError(503, "catalog_snapshot_ambiguous")
        self.proof = {
            "basis": "current_source_snapshot",
            "snapshot_as_of": next(iter(proofs.values()))["snapshot_as_of"],
            "evidence_hash": digest(proofs),
            "resources": proofs,
        }
        return self.proof

    def variants(self, identifiers: list[str]) -> dict[str, dict[str, Any]]:
        if not identifiers:
            return {}
        if len(identifiers) > 1000 or any(
            not isinstance(v, str) or not v or len(v) > 200 for v in identifiers
        ):
            raise ReadError(400, "catalog_variant_limit")
        return self.projection(identifiers, None)

    def family(self, product_id: str) -> dict[str, dict[str, Any]]:
        if not isinstance(product_id, str) or not product_id or len(product_id) > 200:
            raise ReadError(400, "catalog_product_identity_invalid")
        return self.projection([], product_id)

    def projection(
        self, identifiers: list[str], product_id: str | None
    ) -> dict[str, dict[str, Any]]:
        proof = self.resolve()
        if proof is None:
            return {}
        obs = table(self.project, "up_core", "catalog_observations")

        def snapshot(resource: str) -> str:
            return f"SELECT v.* FROM {table(self.project, 'up_core', 'catalog_' + resource + '_versions')} v JOIN {obs} o ON o.store_id=v.store_id AND o.entity_version_id=v.version_id AND o.resource='{resource}' WHERE o.store_id=@store AND o.run_id=@{resource}_run"

        sql = f"""WITH variants AS ({snapshot("variants")}), products AS ({snapshot("products")}), inventory AS ({snapshot("inventory")}), attributes AS ({snapshot("attributes")})
 SELECT v.store_id,v.variant_id,v.product_id,v.sku,v.color,v.color_code,v.size,v.active,v.price,p.name,p.code reference,
 i.qty_available stock,
 (SELECT ARRAY_AGG(a.terms) FROM attributes a WHERE a.code='color') color_terms
 FROM variants v LEFT JOIN products p ON p.store_id=v.store_id AND p.product_id=v.product_id
 LEFT JOIN inventory i ON i.store_id=v.store_id AND i.variant_id=v.variant_id
 WHERE ((@product IS NULL AND v.variant_id IN (SELECT JSON_VALUE(x) FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@variants))) x)) OR (@product IS NOT NULL AND v.product_id=@product))
 ORDER BY v.variant_id LIMIT 1001"""
        params: dict[str, tuple[str, object]] = {
            "store": ("STRING", self.store),
            "variants": ("STRING", json.dumps(sorted(set(identifiers)))),
            "product": ("STRING", product_id),
        }
        params.update(
            {
                resource + "_run": ("STRING", proof["resources"][resource]["run_id"])
                for resource in RESOURCES
            }
        )
        rows = self.rows("catalog_variant_projection", sql, params)
        if len(rows) > 1000:
            raise ReadError(503, "catalog_variant_limit")
        result = {}
        for row in rows:
            if (
                row.get("store_id") != self.store
                or not isinstance(row.get("variant_id"), str)
                or (product_id is None and row.get("variant_id") not in identifiers)
                or (product_id is not None and row.get("product_id") != product_id)
                or row["variant_id"] in result
            ):
                raise ReadError(503, "catalog_variant_identity_ambiguous")
            stock = decimal_string(row.get("stock"))
            terms = row.get("color_terms") or []
            colors: list[Any] = []
            for group in terms:
                values = json.loads(group) if isinstance(group, str) else group
                if isinstance(values, list):
                    colors.extend(
                        t.get("rgb")
                        for t in values
                        if isinstance(t, dict) and t.get("code") == row.get("color_code")
                    )
            rgb = colors[0] if len(colors) == 1 else None
            hex_value = (
                "#" + rgb.removeprefix("#")
                if isinstance(rgb, str) and re.fullmatch(r"#?[a-fA-F0-9]{6}", rgb)
                else None
            )
            result[row["variant_id"]] = {
                "variant_id": row["variant_id"],
                "product_id": row.get("product_id"),
                "name": row.get("name"),
                "reference": row.get("reference"),
                "sku": row.get("sku"),
                "color": row.get("color"),
                "size": row.get("size"),
                "color_hex": hex_value,
                "stock": stock,
                "active": row.get("active"),
                "sale_price": decimal_string(row.get("price")),
                "catalog": {k: proof[k] for k in ("basis", "snapshot_as_of", "evidence_hash")},
            }
        return result
