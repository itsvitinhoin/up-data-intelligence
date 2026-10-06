"""Official images from certified catalog membership, never an on-demand source call."""

import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from src.dashboard.contracts import ReadError
from src.domain.models import SafeError
from src.quality.catalog import certify_catalog_summary

if TYPE_CHECKING:
    from src.dashboard.catalog import CatalogReader


def attach_images(reader: "CatalogReader", rows: dict[str, dict[str, Any]]) -> None:
    from src.dashboard.catalog import table

    proof = reader.resolve()
    if not rows or proof is None:
        return
    obs = table(reader.project, "up_core", "catalog_observations")
    images = table(reader.project, "up_core", "catalog_images_versions")
    variants = table(reader.project, "up_core", "catalog_variants_versions")
    checkpoints = table(reader.project, "up_ops", "sync_checkpoints")
    runs = table(reader.project, "up_ops", "sync_runs")
    params: dict[str, tuple[str, object]] = {
        "store": ("STRING", reader.store),
        "connection": ("STRING", reader.connection),
        "cutoff": ("STRING", proof["snapshot_as_of"]),
        "products_run": ("STRING", proof["resources"]["products"]["run_id"]),
        "variants_run": ("STRING", proof["resources"]["variants"]["run_id"]),
    }
    sql = f"""WITH chosen AS (
 SELECT c.* FROM {checkpoints} c WHERE c.store_id=@store AND c.connection_id=@connection
 AND c.resource='images' AND JSON_VALUE(c.filters,'$.catalog_as_of')=@cutoff
), membership AS (
 SELECT o.*,i.image_id,i.product_id,i.variant_ids,i.version_id
 FROM {obs} o LEFT JOIN {images} i ON i.store_id=o.store_id
 AND i.version_id=o.entity_version_id AND i.image_id=o.entity_id
 WHERE o.store_id=@store AND o.resource='images' AND o.run_id IN (SELECT run_id FROM chosen)
), variants AS (
 SELECT v.variant_id,v.product_id FROM {variants} v JOIN {obs} o
 ON o.store_id=v.store_id AND o.entity_version_id=v.version_id AND o.entity_id=v.variant_id
 WHERE o.store_id=@store AND o.resource='variants' AND o.run_id=@variants_run
), variant_counts AS (SELECT variant_id,product_id,COUNT(*) matches FROM variants GROUP BY variant_id,product_id), products AS (
 SELECT entity_id FROM {obs} WHERE store_id=@store AND resource='products' AND run_id=@products_run
)
 , invalid_images AS (
 SELECT m.entity_id FROM membership m LEFT JOIN products p ON p.entity_id=m.product_id
 WHERE p.entity_id IS NULL OR m.variant_ids IS NULL
 UNION DISTINCT
 SELECT m.entity_id FROM membership m CROSS JOIN UNNEST(JSON_QUERY_ARRAY(m.variant_ids)) x
 LEFT JOIN variant_counts v ON v.variant_id=JSON_VALUE(x) AND v.product_id=m.product_id
 WHERE COALESCE(v.matches,0)!=1
)
SELECT TO_JSON_STRING(c) checkpoint,TO_JSON_STRING(r) run,
 (SELECT COUNT(*) FROM membership) observations,
 (SELECT COUNT(DISTINCT entity_id) FROM membership) distinct_entities,
 (SELECT COUNTIF(version_id IS NOT NULL AND raw_record_id IS NOT NULL AND observed_at IS NOT NULL) FROM membership) valid_version_links,
 ARRAY(SELECT entity_id FROM products ORDER BY entity_id LIMIT 10001) product_ids,
 (SELECT COUNT(*) FROM invalid_images) invalid_relationships
FROM chosen c LEFT JOIN {runs} r ON r.store_id=c.store_id AND r.run_id=c.run_id LIMIT 2"""
    evidence = reader.rows("catalog_images_proof", sql, params)
    if not evidence:
        return
    if len(evidence) != 1:
        raise ReadError(503, "catalog_images_ambiguous")
    row = evidence[0]
    try:
        cp, run = json.loads(row["checkpoint"]), json.loads(row["run"])
        if (
            not isinstance(cp, dict)
            or not isinstance(run, dict)
            or not isinstance(cp.get("filters"), dict)
        ):
            raise ValueError
        # In-progress image scanning does not make current images certified.
        if cp["status"] != "complete":
            return
        expected = row["product_ids"]
        if (
            len(expected) > 10000
            or len(expected) != len(set(expected))
            or cp["filters"].get("product_ids") != expected
            or row["invalid_relationships"] != 0
        ):
            raise ValueError
        certify_catalog_summary(
            reader.store,
            reader.connection or "",
            "images",
            proof["snapshot_as_of"],
            cp,
            run,
            observations=row["observations"],
            distinct_entities=row["distinct_entities"],
            valid_version_links=row["valid_version_links"],
        )
    except (SafeError, ValueError, KeyError, TypeError):
        raise ReadError(503, "catalog_images_not_certified") from None
    params = {
        "store": ("STRING", reader.store),
        "run": ("STRING", run["run_id"]),
        "products": (
            "STRING",
            json.dumps(sorted({r["product_id"] for r in rows.values() if r.get("product_id")})),
        ),
    }
    selected = reader.rows(
        "catalog_images_projection",
        f"""SELECT i.store_id,i.image_id,i.product_id,i.image_url,i.variant_ids,i.is_primary,i.display_order
 FROM {images} i JOIN {obs} o ON o.store_id=i.store_id AND o.entity_version_id=i.version_id AND o.entity_id=i.image_id
 WHERE o.store_id=@store AND o.resource='images' AND o.run_id=@run
 AND i.product_id IN (SELECT JSON_VALUE(x) FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@products))) x)
 ORDER BY i.is_primary DESC,i.display_order,i.image_id LIMIT 10001""",
        params,
    )
    if len(selected) > 10000:
        raise ReadError(503, "catalog_images_limit")
    seen = set()
    product_ids = {item["product_id"] for item in rows.values()}
    for image in selected:
        url = image.get("image_url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
        except ValueError:
            raise ReadError(503, "catalog_image_projection_invalid") from None
        assigned = image.get("variant_ids")
        assigned = json.loads(assigned) if isinstance(assigned, str) else assigned
        if (
            image.get("store_id") != reader.store
            or image.get("product_id") not in product_ids
            or image.get("image_id") in seen
            or parsed is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or not isinstance(assigned, list)
            or any(not isinstance(v, str) or not v for v in assigned)
            or len(set(assigned)) != len(assigned)
            or len(url or "") > 2048
        ):
            raise ReadError(503, "catalog_image_projection_invalid")
        seen.add(image["image_id"])
        for variant, item in rows.items():
            if item["product_id"] == image["product_id"] and (not assigned or variant in assigned):
                if item.get("image") is None:
                    item["image"] = url
                    item["image_basis"] = "official_current_catalog_snapshot"
