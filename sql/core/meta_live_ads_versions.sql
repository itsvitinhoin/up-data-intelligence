CREATE TABLE IF NOT EXISTS `${project_id}.up_core.meta_live_ads_versions` (
  `row_key` STRING NOT NULL,
  `store_id` STRING NOT NULL,
  `account_id` STRING,
  `api_version` STRING,
  `contract_version` STRING,
  `observed_at` TIMESTAMP,
  `source_updated_at` TIMESTAMP,
  `ad_id` STRING,
  `adset_id` STRING,
  `campaign_id` STRING,
  `ad_name` STRING,
  `creative_id` STRING,
  `status` STRING,
  `effective_status` STRING,
  `creative_name` STRING,
  `creative_image_url` STRING,
  `creative_thumbnail_url` STRING,
  `creative_video_id` STRING,
  `creative_story_id` STRING,
  `version_id` STRING,
  `payload_hash` STRING,
  `source_system` STRING
)
PARTITION BY DATE(observed_at)
CLUSTER BY store_id, account_id;
