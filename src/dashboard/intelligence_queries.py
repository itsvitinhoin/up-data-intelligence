"""Bounded campaign aggregates over one immutable intelligence generation."""


def campaigns(project: str, *, customer_scoped: bool = False) -> str:
    daily = f"`{project}.up_analytics.analytics_campaign_performance_daily`"
    scoped = "store_id=@store AND policy_hash=@policy AND generation=@generation AND influence_scope='LIFETIME'"
    # Participation is an exact campaign/customer/order relation in this period.
    # EXISTS preserves the campaign grain, including campaigns with many orders.
    participation = (
        f" AND EXISTS (SELECT 1 FROM ({period_order_relations(project)}) AS p "
        "WHERE p.campaign_id=d.campaign_id AND p.customer_id=@customer)"
        if customer_scoped
        else ""
    )
    customer_projection = ",@customer customer_id" if customer_scoped else ""
    return f"""WITH daily AS (
      SELECT store_id,policy_hash,generation,campaign_id,ANY_VALUE(campaign_name) campaign_name,
        ANY_VALUE(campaign_status) campaign_status,
        IF(COUNTIF(spend IS NULL)>0,NULL,SUM(spend)) spend,
        SUM(observed_spend) observed_spend,
        IF(COUNTIF(impressions IS NULL)>0,NULL,SUM(impressions)) impressions,
        IF(COUNTIF(clicks IS NULL)>0,NULL,SUM(clicks)) clicks,
        LOGICAL_AND(influence_complete) influence_complete
      FROM {daily} FOR SYSTEM_TIME AS OF @snapshot WHERE {scoped} AND date>=@from AND date<@to
      GROUP BY store_id,policy_hash,generation,campaign_id
    ), orders AS (
      SELECT campaign_id,COUNT(DISTINCT order_id) influenced_orders,
        IF(COUNTIF(requested_total IS NULL)>0,NULL,SUM(requested_total)) requested_revenue_influenced,
        IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,SUM(fulfilled_total)) fulfilled_revenue_influenced
      FROM ({period_order_relations(project)}) GROUP BY campaign_id
    ), customers AS (
      SELECT campaign_id,COUNT(DISTINCT customer_id) influenced_customers
      FROM ({period_order_relations(project)}) GROUP BY campaign_id
    ) SELECT d.*{customer_projection},d.campaign_id row_key,
      COALESCE(o.influenced_orders,0) influenced_orders,COALESCE(c.influenced_customers,0) influenced_customers,
      IF(o.campaign_id IS NULL,0,o.requested_revenue_influenced) requested_revenue_influenced,
      IF(o.campaign_id IS NULL,0,o.fulfilled_revenue_influenced) fulfilled_revenue_influenced,
      SAFE_DIVIDE(CAST(d.clicks AS NUMERIC),CAST(d.impressions AS NUMERIC))*100 ctr,SAFE_DIVIDE(d.spend,d.clicks) cpc,
      SAFE_DIVIDE(d.spend,d.impressions)*1000 cpm,
      IF(d.influence_complete,SAFE_DIVIDE(IF(o.campaign_id IS NULL,0,o.requested_revenue_influenced),d.spend),NULL) roas_requested,
      IF(d.influence_complete,SAFE_DIVIDE(IF(o.campaign_id IS NULL,0,o.fulfilled_revenue_influenced),d.spend),NULL) roas_fulfilled
    FROM daily d LEFT JOIN orders o USING(campaign_id) LEFT JOIN customers c USING(campaign_id)
    WHERE d.campaign_id>@after AND (@campaign IS NULL OR d.campaign_id=@campaign){participation}
    ORDER BY d.campaign_id LIMIT @limit"""


def customer_context(project: str) -> str:
    """Read two scoped projections in one job without increasing the request budget."""
    from src.intelligence.api import JOURNEY

    identity = "store_id policy_hash generation customer_id"
    marketing = "influence_scope paid_media_influenced first_paid_touch_at last_paid_touch_at first_campaign_id last_campaign_id paid_touch_count campaign_count influenced_orders evidence_type"
    where = "store_id=@store AND policy_hash=@policy AND generation=@generation AND customer_id=@customer"

    def projection(table: str, fields: str, limit: int) -> str:
        columns = ",".join("`" + k + "`" for k in (identity + " " + fields).split())
        return f"SELECT {columns} FROM `{project}.up_analytics.{table}` FOR SYSTEM_TIME AS OF @snapshot WHERE {where} ORDER BY row_key LIMIT {limit}"

    journey = projection("analytics_customer_journey_summary", JOURNEY, 2)
    influence = projection("analytics_customer_paid_influence", marketing, 4)
    return f"SELECT ARRAY({journey}) journey, ARRAY({influence}) marketing".replace(
        "ARRAY(SELECT ", "ARRAY(SELECT AS STRUCT "
    )


def period_order_relations(project: str) -> str:
    """Exact campaign/order grain; the generation's order summary owns the date."""
    from src.intelligence.live.schema import SCHEMAS

    columns = ",".join(
        "p.`" + k + "`"
        for k in SCHEMAS["analytics_campaign_order_performance"].fields
        if k != "identity_path"
    )
    return f"""SELECT {columns},o.created_at,o.order_status,o.paid_media_influenced
 FROM `{project}.up_analytics.analytics_campaign_order_performance` AS p FOR SYSTEM_TIME AS OF @snapshot
 JOIN `{project}.up_analytics.analytics_customer_orders_summary` AS o FOR SYSTEM_TIME AS OF @snapshot
 ON o.store_id=p.store_id AND o.policy_hash=p.policy_hash AND o.generation=p.generation
 AND o.customer_id=p.customer_id AND o.order_id=p.order_id AND o.influence_scope=p.influence_scope
 WHERE p.store_id=@store AND p.policy_hash=@policy AND p.generation=@generation
 AND p.influence_scope='LIFETIME' AND DATE(o.created_at,@timezone)>=@from AND DATE(o.created_at,@timezone)<@to"""


def performance_period(project: str) -> str:
    """Deduplicate commercial orders independently of the additive Meta daily grain."""
    daily = f"""SELECT date,spend,observed_spend,impressions,clicks
 FROM `{project}.up_analytics.analytics_campaign_performance_daily` FOR SYSTEM_TIME AS OF @snapshot
 WHERE store_id=@store AND policy_hash=@policy AND generation=@generation AND influence_scope='LIFETIME'
 AND date>=@from AND date<@to"""
    orders = f"""SELECT customer_id,order_id,created_at,purchase_number,requested_total,fulfilled_total,requested_items_qty,fulfilled_items_qty FROM `{project}.up_analytics.analytics_customer_orders_summary` FOR SYSTEM_TIME AS OF @snapshot
 WHERE store_id=@store AND policy_hash=@policy AND generation=@generation AND influence_scope='LIFETIME'
 AND paid_media_influenced IS TRUE AND DATE(created_at,@timezone)>=@from AND DATE(created_at,@timezone)<@to"""

    def total(field: str) -> str:
        return f"IF(COUNTIF({field} IS NULL)>0,NULL,COALESCE(SUM({field}),NUMERIC '0'))"

    return f"""WITH media AS ({daily}), orders AS ({orders}), spend AS (
 SELECT IF(@meta_complete,{total("spend")},NULL) AS meta_spend,{total("observed_spend")} AS observed_meta_spend,
 IF(COUNTIF(impressions IS NULL)>0,NULL,COALESCE(SUM(impressions),0)) impressions,
 IF(COUNTIF(clicks IS NULL)>0,NULL,COALESCE(SUM(clicks),0)) clicks FROM media
), commercial AS (
 SELECT COUNT(DISTINCT customer_id) influenced_customers,COUNT(DISTINCT order_id) influenced_orders,
 IF(@history_complete AND @influence_complete,COUNT(DISTINCT IF(purchase_number=1,customer_id,NULL)),NULL) new_customers_influenced,
 {total("requested_total")} requested_revenue_influenced,{total("fulfilled_total")} fulfilled_revenue_influenced,
 {total("requested_items_qty")} requested_quantity_influenced,{total("fulfilled_items_qty")} fulfilled_quantity_influenced
 FROM orders
), summary AS (
 SELECT s.*,c.*,SAFE_DIVIDE(s.meta_spend,c.new_customers_influenced) cac_new_customer,
 SAFE_DIVIDE(c.fulfilled_revenue_influenced,c.requested_revenue_influenced) fulfillment_rate,
 IF(@influence_complete,SAFE_DIVIDE(c.requested_revenue_influenced,s.meta_spend),NULL) roas_requested,
 IF(@influence_complete,SAFE_DIVIDE(c.fulfilled_revenue_influenced,s.meta_spend),NULL) roas_fulfilled,
 SAFE_DIVIDE(CAST(s.clicks AS NUMERIC),s.impressions)*100 ctr,
 SAFE_DIVIDE(s.meta_spend,s.clicks) cpc,SAFE_DIVIDE(s.meta_spend,s.impressions)*1000 cpm
 FROM spend s CROSS JOIN commercial c
), media_daily AS (
 SELECT date,{total("spend")} spend,
 IF(COUNTIF(impressions IS NULL)>0,NULL,COALESCE(SUM(impressions),0)) impressions,
 IF(COUNTIF(clicks IS NULL)>0,NULL,COALESCE(SUM(clicks),0)) clicks FROM media GROUP BY date
), commercial_daily AS (
 SELECT DATE(created_at,@timezone) date,COUNT(DISTINCT order_id) influenced_orders,
 {total("requested_total")} requested_revenue_influenced,{total("fulfilled_total")} fulfilled_revenue_influenced
 FROM orders GROUP BY date
)
SELECT @store store_id,@policy policy_hash,@generation generation,
 (SELECT AS STRUCT * FROM summary) summary,
 ARRAY(SELECT AS STRUCT day date,
 IF(m.date IS NULL,IF(@meta_complete,NUMERIC '0',NULL),m.spend) spend,
 IF(m.date IS NULL,IF(@meta_complete,0,NULL),m.impressions) impressions,
 IF(m.date IS NULL,IF(@meta_complete,0,NULL),m.clicks) clicks,
 IF(c.date IS NULL,NUMERIC '0',c.requested_revenue_influenced) requested_revenue_influenced,
 IF(c.date IS NULL,NUMERIC '0',c.fulfilled_revenue_influenced) fulfilled_revenue_influenced,
 IF(c.date IS NULL,0,c.influenced_orders) influenced_orders
 FROM UNNEST(GENERATE_DATE_ARRAY(@from,DATE_SUB(@to,INTERVAL 1 DAY))) AS day
 LEFT JOIN media_daily m ON m.date=day LEFT JOIN commercial_daily c ON c.date=day ORDER BY day) series"""


def campaign_customers_period(project: str) -> str:
    """Re-aggregate customer participation over the requested order period."""
    from src.intelligence.live.schema import SCHEMAS

    overridden = {
        "orders_influenced",
        "first_paid_touch_at",
        "last_paid_touch_at",
        "requested_revenue",
        "fulfilled_revenue",
        "requested_quantity",
        "fulfilled_quantity",
        "identity_path",
    }
    projection = ",".join(
        "p.`" + k + "`"
        for k in SCHEMAS["analytics_campaign_customer_performance"].fields
        if k not in overridden
    )
    return f"""WITH orders AS ({period_order_relations(project)}), grouped AS (
 SELECT campaign_id,customer_id,COUNT(DISTINCT order_id) orders_influenced,
 MIN(first_paid_touch_at) first_paid_touch_at,MAX(last_paid_touch_at) last_paid_touch_at,
 IF(COUNTIF(requested_total IS NULL)>0,NULL,SUM(requested_total)) requested_revenue,
 IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,SUM(fulfilled_total)) fulfilled_revenue,
 IF(COUNTIF(requested_items_qty IS NULL)>0,NULL,SUM(requested_items_qty)) requested_quantity,
 IF(COUNTIF(fulfilled_items_qty IS NULL)>0,NULL,SUM(fulfilled_items_qty)) fulfilled_quantity
 FROM orders GROUP BY campaign_id,customer_id
)
 SELECT {projection},
 o.* EXCEPT(campaign_id,customer_id)
 FROM `{project}.up_analytics.analytics_campaign_customer_performance` AS p FOR SYSTEM_TIME AS OF @snapshot
 JOIN grouped o ON o.campaign_id=p.campaign_id AND o.customer_id=p.customer_id
 WHERE p.store_id=@store AND p.policy_hash=@policy AND p.generation=@generation AND p.influence_scope='LIFETIME'"""
