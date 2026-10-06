"""Current catalog snapshots, separate from historical commercial fact grain."""

VERSION = "1.0.0"
PRODUCT = {
    "product_id": "STRING",
    "code": "STRING",
    "name": "STRING",
    "status": "STRING",
    "category_ids": "JSON",
    "category_names": "JSON",
    "product_category_ids": "JSON",
    "product_category_names": "JSON",
    "external_ref": "JSON",
    "created_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}
VARIANT = {
    "variant_id": "STRING",
    "product_id": "STRING",
    "sku": "STRING",
    "price": "NUMERIC",
    "promotional_price": "NUMERIC",
    "attributes": "JSON",
    "active": "BOOL",
    "color": "STRING",
    "color_code": "STRING",
    "size": "STRING",
    "size_code": "STRING",
    "created_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}
ATTRIBUTE = {
    "attribute_id": "STRING",
    "code": "STRING",
    "name": "STRING",
    "terms": "JSON",
}
INVENTORY = {
    "variant_id": "STRING",
    "warehouse_id": "STRING",
    "qty_total": "NUMERIC",
    "qty_reserved": "NUMERIC",
    "qty_available": "NUMERIC",
    "breakdown": "JSON",
}
IMAGE = {
    "image_id": "STRING",
    "product_id": "STRING",
    "image_url": "STRING",
    "combination_key": "STRING",
    "display_order": "INT64",
    "is_primary": "BOOL",
    "variant_ids": "JSON",
    "created_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}
RESOURCES = {
    "products": ("catalog_products", PRODUCT, "product_id"),
    "variants": ("catalog_variants", VARIANT, "variant_id"),
    "attributes": ("catalog_attributes", ATTRIBUTE, "attribute_id"),
    "inventory": ("catalog_inventory", INVENTORY, "variant_id"),
    "images": ("catalog_images", IMAGE, "image_id"),
}

TABLE_NAMES = frozenset(
    {"upzero_" + resource for resource in RESOURCES}
    | {name for table, _, _ in RESOURCES.values() for name in (table, table + "_versions")}
    | {"catalog_observations"}
)
