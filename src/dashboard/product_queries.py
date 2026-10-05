"""Scoped product UI reads. No browser identifiers are interpolated into SQL."""

from src.analytics.sql_models import key
from src.dashboard.queries import Query, table


def product_key_sql(alias: str = "i") -> str:
    # Identical to Analytics V1: asset alone never proves a resolved variant.
    parts = f"{alias}.asset_id,{alias}.variant_id,{alias}.sku"
    return (
        f"IF(({alias}.variant_id IS NULL OR {alias}.variant_id='') AND "
        f"({alias}.sku IS NULL OR {alias}.sku=''),"
        f"{key(parts + ',' + alias + '.order_id,' + alias + '.item_id')},{key(parts)})"
    )


def build_product_read(project: str, name: str, **values: object) -> Query:
    history = "FOR SYSTEM_TIME AS OF @snapshot_at"
    orders = table(project, "up_core", "orders")
    customers = table(project, "up_core", "customers")
    items = table(project, "up_core", "order_items")
    params: dict[str, tuple[str, object]] = {
        "store": ("STRING", values.get("store")),
        "snapshot_at": ("TIMESTAMP", values.get("snapshot_at")),
    }
    if name == "order_detail":
        params.update(
            order=("STRING", values.get("order")), as_of=("TIMESTAMP", values.get("as_of"))
        )
        sql = f"""SELECT o.store_id,o.order_id,o.customer_id,o.version_id,o.created_at,
 o.order_status,o.payment_status,o.requested_total,o.fulfilled_total,
 o.requested_items_qty,o.fulfilled_items_qty,o.items_count,
 c.name AS customer_name,c.trade_name AS customer_trade_name,c.company_name AS customer_company_name,
 c.state AS customer_state,c.city AS customer_city
FROM {orders} AS o {history}
LEFT JOIN {customers} AS c {history} ON c.store_id=o.store_id
 AND c.source_system='upzero' AND c.customer_id=o.customer_id
WHERE o.store_id=@store AND o.source_system='upzero' AND o.order_id=@order
 AND o.created_at<@as_of LIMIT 3"""
    elif name == "order_detail_items":
        params.update(order=("STRING", values.get("order")))
        sql = f"""SELECT i.order_id,i.item_id,i.parent_order_version_id,i.asset_id,i.variant_id,
 i.asset_name,i.asset_image_url,i.image_url,i.sku,i.status,i.original_qty,i.qty,i.unit_price,
 {product_key_sql()} AS product_key
FROM {items} AS i {history}
WHERE i.store_id=@store AND i.source_system='upzero' AND i.order_id=@order
 AND i.present_in_latest_snapshot ORDER BY i.item_id LIMIT 1001"""
    elif name == "variant_sales":
        params.update(
            {
                "from": ("DATE", values.get("from_day")),
                "to": ("DATE", values.get("to_day")),
                "timezone": ("STRING", values.get("timezone")),
                "as_of": ("TIMESTAMP", values.get("as_of")),
                "variants": ("STRING", values.get("variants")),
            }
        )
        sql = f"""SELECT i.variant_id,
 COUNT(*)-COUNT(DISTINCT TO_JSON_STRING(STRUCT(i.order_id,i.item_id))) duplicate_items,
 COUNT(DISTINCT i.order_id) orders,
 IF(COUNTIF(o.customer_id IS NULL)>0,NULL,COUNT(DISTINCT o.customer_id)) buyers,
 IF(COUNTIF(i.original_qty IS NULL)>0,NULL,SUM(i.original_qty)) units_requested,
 IF(COUNTIF(i.status!='removed' AND i.qty IS NULL)>0,NULL,SUM(IF(i.status='removed',CAST(0 AS NUMERIC),i.qty))) units_fulfilled,
 IF(COUNTIF(i.original_qty IS NULL OR i.unit_price IS NULL)>0,NULL,SUM(i.original_qty*i.unit_price)) requested,
 IF(COUNTIF(i.status!='removed' AND (i.qty IS NULL OR i.unit_price IS NULL))>0,NULL,SUM(IF(i.status='removed',CAST(0 AS NUMERIC),i.qty*i.unit_price))) fulfilled
 FROM {items} AS i {history}
 JOIN {orders} AS o {history} ON o.store_id=i.store_id AND o.order_id=i.order_id
 AND o.source_system='upzero' AND o.version_id=i.parent_order_version_id
 WHERE i.store_id=@store AND i.source_system='upzero' AND i.present_in_latest_snapshot
 AND i.status IN ('active','attended','removed') AND o.created_at<@as_of
 AND DATE(o.created_at,@timezone)>=@from AND DATE(o.created_at,@timezone)<@to
 AND DATE(i.order_created_at,@timezone)>=@from AND DATE(i.order_created_at,@timezone)<@to
 AND i.variant_id IN (SELECT JSON_VALUE(v) FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@variants))) v)
 GROUP BY i.variant_id ORDER BY i.variant_id LIMIT 1001"""
    elif name == "geography":
        params.update(
            {
                "from": ("DATE", values.get("from_day")),
                "to": ("DATE", values.get("to_day")),
                "timezone": ("STRING", values.get("timezone")),
                "as_of": ("TIMESTAMP", values.get("as_of")),
            }
        )
        sql = f"""WITH selected AS (
 SELECT order_id,customer_id,requested_total,fulfilled_total,
 JSON_VALUE(shipping_address,'$.state') AS state,
 NULLIF(TRIM(JSON_VALUE(shipping_address,'$.city')),'') AS city
 FROM {orders} {history}
 WHERE store_id=@store AND source_system='upzero' AND created_at<@as_of
 AND DATE(created_at,@timezone)>=@from AND DATE(created_at,@timezone)<@to
), cities AS (
 SELECT state,city,COUNT(*) AS orders,IF(COUNTIF(customer_id IS NULL)>0,NULL,COUNT(DISTINCT customer_id)) AS customers,
 IF(COUNTIF(requested_total IS NULL)>0,NULL,SUM(requested_total)) AS requested,
 IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,SUM(fulfilled_total)) AS fulfilled
 FROM selected GROUP BY state,city
), states AS (
 SELECT state,COUNT(*) AS orders,IF(COUNTIF(customer_id IS NULL)>0,NULL,COUNT(DISTINCT customer_id)) AS customers,
 IF(COUNTIF(requested_total IS NULL)>0,NULL,SUM(requested_total)) AS requested,
 IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,SUM(fulfilled_total)) AS fulfilled,
 COUNTIF(customer_id IS NULL) AS orders_without_customer
 FROM selected GROUP BY state
), city_groups AS (
 SELECT state,ARRAY_AGG(STRUCT(city,orders,customers,requested,fulfilled)
 ORDER BY requested DESC,city) AS cities FROM cities GROUP BY state
)
SELECT s.*,c.cities
FROM states s JOIN city_groups c ON c.state IS NOT DISTINCT FROM s.state
ORDER BY s.state LIMIT 29"""
    elif name == "product_evidence":
        params.update(
            {
                "from": ("DATE", values.get("from_day")),
                "to": ("DATE", values.get("to_day")),
                "timezone": ("STRING", values.get("timezone")),
                "product": ("STRING", values.get("product")),
                "as_of": ("TIMESTAMP", values.get("as_of")),
            }
        )
        sql = f"""WITH lines AS (
 SELECT {product_key_sql()} AS product_key,i.order_id,i.item_id,
 i.asset_name,i.asset_image_url,i.image_url,i.variant_id,o.customer_id
 FROM {items} AS i {history}
 JOIN {orders} AS o {history} ON o.store_id=i.store_id AND o.order_id=i.order_id
 AND o.source_system='upzero' AND o.version_id=i.parent_order_version_id
 WHERE i.store_id=@store AND i.source_system='upzero' AND i.present_in_latest_snapshot
 AND i.status IN ('active','attended','removed') AND o.created_at<@as_of
 AND DATE(o.created_at,@timezone)>=@from AND DATE(o.created_at,@timezone)<@to
 AND DATE(i.order_created_at,@timezone)>=@from AND DATE(i.order_created_at,@timezone)<@to
)
SELECT product_key,
 IF(COUNT(DISTINCT asset_name)=1,MAX(asset_name),NULL) AS name,
 IF(COUNT(DISTINCT COALESCE(asset_image_url,image_url))=1,MAX(COALESCE(asset_image_url,image_url)),NULL) AS image,
 IF(COUNT(DISTINCT variant_id)=1,MAX(variant_id),NULL) AS variant_id,
 IF(COUNTIF(customer_id IS NULL)>0,NULL,COUNT(DISTINCT customer_id)) AS buyers_unique,
 COUNT(*)-COUNT(DISTINCT TO_JSON_STRING(STRUCT(order_id,item_id))) AS duplicate_items
FROM lines WHERE product_key=@product GROUP BY product_key LIMIT 2"""
    else:
        raise ValueError("dashboard_product_query_not_allowed")
    return Query(name, f"/* dashboard:{name} */\n" + sql, params)
