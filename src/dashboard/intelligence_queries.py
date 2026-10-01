"""Bounded campaign aggregates over one immutable intelligence generation."""


def campaigns(project: str) -> str:
    daily = f"`{project}.up_analytics.analytics_campaign_performance_daily`"
    orders = f"`{project}.up_analytics.analytics_campaign_order_performance`"
    customers = f"`{project}.up_analytics.analytics_campaign_customer_performance`"
    scoped = "store_id=@store AND policy_hash=@policy AND generation=@generation AND influence_scope='LIFETIME'"
    return f"""WITH daily AS (
      SELECT store_id,policy_hash,generation,campaign_id,ANY_VALUE(campaign_name) campaign_name,
        ANY_VALUE(campaign_status) campaign_status,
        IF(COUNTIF(spend IS NULL)>0,NULL,SUM(spend)) spend,
        SUM(observed_spend) observed_spend,
        IF(COUNTIF(impressions IS NULL)>0,NULL,SUM(impressions)) impressions,
        IF(COUNTIF(clicks IS NULL)>0,NULL,SUM(clicks)) clicks,
        LOGICAL_AND(influence_complete) influence_complete
      FROM {daily} FOR SYSTEM_TIME AS OF @snapshot WHERE {scoped}
      GROUP BY store_id,policy_hash,generation,campaign_id
    ), orders AS (
      SELECT campaign_id,COUNT(DISTINCT order_id) influenced_orders,
        IF(COUNTIF(requested_total IS NULL)>0,NULL,SUM(requested_total)) requested_revenue_influenced,
        IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,SUM(fulfilled_total)) fulfilled_revenue_influenced
      FROM {orders} FOR SYSTEM_TIME AS OF @snapshot WHERE {scoped} GROUP BY campaign_id
    ), customers AS (
      SELECT campaign_id,COUNT(DISTINCT customer_id) influenced_customers
      FROM {customers} FOR SYSTEM_TIME AS OF @snapshot WHERE {scoped} GROUP BY campaign_id
    ) SELECT d.*,d.campaign_id row_key,
      COALESCE(o.influenced_orders,0) influenced_orders,COALESCE(c.influenced_customers,0) influenced_customers,
      IF(o.campaign_id IS NULL,0,o.requested_revenue_influenced) requested_revenue_influenced,
      IF(o.campaign_id IS NULL,0,o.fulfilled_revenue_influenced) fulfilled_revenue_influenced,
      SAFE_DIVIDE(CAST(d.clicks AS NUMERIC),CAST(d.impressions AS NUMERIC))*100 ctr,SAFE_DIVIDE(d.spend,d.clicks) cpc,
      SAFE_DIVIDE(d.spend,d.impressions)*1000 cpm,
      IF(d.influence_complete,SAFE_DIVIDE(IF(o.campaign_id IS NULL,0,o.requested_revenue_influenced),d.spend),NULL) roas_requested,
      IF(d.influence_complete,SAFE_DIVIDE(IF(o.campaign_id IS NULL,0,o.fulfilled_revenue_influenced),d.spend),NULL) roas_fulfilled
    FROM daily d LEFT JOIN orders o USING(campaign_id) LEFT JOIN customers c USING(campaign_id)
    WHERE d.campaign_id>@after AND (@campaign IS NULL OR d.campaign_id=@campaign)
    ORDER BY d.campaign_id LIMIT @limit"""
