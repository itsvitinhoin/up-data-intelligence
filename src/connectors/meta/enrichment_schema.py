"""Additive active fields. The reproducible offline foundation remains unchanged."""

FIELDS = {
    "ads": {
        "creative_name": "STRING",
        "creative_image_url": "STRING",
        "creative_thumbnail_url": "STRING",
        "creative_video_id": "STRING",
        "creative_story_id": "STRING",
    },
    "insights": {
        "frequency": "NUMERIC",
        "actions": "JSON",
        "action_values": "JSON",
        "purchase_action_type": "STRING",
        "meta_reported_purchases": "NUMERIC",
        "meta_reported_purchase_value": "NUMERIC",
    },
}

# Official Graph field expansion; no /{creative} N+1 requests or browser token.
CREATIVE_FIELDS = "creative{id,name,image_url,thumbnail_url,video_id,effective_object_story_id}"
