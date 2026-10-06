"""Isolated additive period Insights schema, with no clients or IO."""

FIELDS = {
    **dict.fromkeys(
        "row_key store_id account_id connection_id api_version currency timezone level campaign_id adset_id ad_id configuration_hash purchase_action_type version_id payload_hash source_system".split(),
        "STRING",
    ),
    **dict.fromkeys("date_start date_stop".split(), "DATE"),
    **dict.fromkeys("impressions reach clicks link_clicks".split(), "INT64"),
    **dict.fromkeys(
        "spend frequency ctr cpc cpm meta_reported_purchases meta_reported_purchase_value".split(),
        "NUMERIC",
    ),
    "reporting_configuration": "JSON",
    "actions": "JSON",
    "action_values": "JSON",
    "observed_at": "TIMESTAMP",
}
