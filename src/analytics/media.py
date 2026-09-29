"""Future aggregate input contracts. No attribution, API or CORE joins are performed."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from src.analytics.engine import amount, ratio
from src.connectors.meta.config import meta_id


@dataclass(frozen=True)
class AttributionEvidence:
    attribution_model: str
    attribution_window_days: int
    touchpoint_id: str
    account_id: str
    campaign_id: str | None
    adset_id: str | None
    ad_id: str | None

    def __post_init__(self) -> None:
        if (
            self.attribution_model != "LAST_PAID_TOUCH"
            or self.attribution_window_days <= 0
            or not self.touchpoint_id
        ):
            raise ValueError("explicit_attribution_policy_and_evidence_required")
        for value in (self.account_id, self.campaign_id, self.adset_id, self.ad_id):
            if value is not None:
                meta_id(value)


@dataclass(frozen=True)
class MeasurementScope:
    store_id: str
    currency: str
    timezone: str
    date_from: str
    date_to: str
    account_configuration_hash: str  # selected accounts/report configurations; no mixed totals

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if (
            not self.store_id
            or not self.account_configuration_hash
            or not re.fullmatch(r"[A-Z]{3}", self.currency)
        ):
            raise ValueError("explicit_media_scope_required")
        if date.fromisoformat(self.date_from) >= date.fromisoformat(self.date_to):
            raise ValueError("invalid_media_period")


@dataclass(frozen=True)
class PaidMedia:
    scope: MeasurementScope
    spend: Decimal
    impressions: int
    clicks: int
    meta_reported_purchases: Decimal | None
    meta_reported_purchase_value: Decimal | None


@dataclass(frozen=True)
class AttributedFirstParty:
    scope: MeasurementScope
    policy: AttributionEvidence
    new_customers: int
    orders: int
    revenue_generated: Decimal
    revenue_paid: Decimal | None


def media_metrics(
    media: PaidMedia | None, attributed: AttributedFirstParty | None
) -> dict[str, Any]:
    out: dict[str, Any] = dict.fromkeys(
        (
            "meta_spend",
            "meta_impressions",
            "meta_clicks",
            "meta_reported_purchases",
            "meta_reported_purchase_value",
            "new_customer_cac",
            "roas_generated",
            "roas_paid",
        )
    )
    if media is None:
        return out
    if min(media.impressions, media.clicks) < 0:
        raise ValueError("negative_media_counter")
    spend = amount(media.spend)
    out.update(
        meta_spend=spend,
        meta_impressions=media.impressions,
        meta_clicks=media.clicks,
        meta_reported_purchases=amount(media.meta_reported_purchases),
        meta_reported_purchase_value=amount(media.meta_reported_purchase_value),
    )
    if attributed is None:
        return out
    if media.scope != attributed.scope:
        raise ValueError("incompatible_media_and_first_party_scope")
    if not 0 <= attributed.new_customers <= attributed.orders:
        raise ValueError("invalid_first_party_denominator")
    out.update(
        new_customer_cac=ratio(spend, attributed.new_customers),
        roas_generated=ratio(amount(attributed.revenue_generated), spend),
        roas_paid=ratio(amount(attributed.revenue_paid), spend),
    )
    return out
