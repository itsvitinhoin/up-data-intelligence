"""Proposed fields/report level for the existing mock-only transport."""

from src.connectors.meta.client import FIELDS, MetaConnector
from src.domain.models import SafeError

FOUNDATION_FIELDS = {
    **FIELDS,
    "adsets": FIELDS["adsets"] + ",optimization_goal,billing_event,targeting",
    "ads": FIELDS["ads"] + ",creative{id}",
}


class MetaFoundationConnector(MetaConnector):
    """No live transport or credential provider; caller supplies synthetic mock inputs."""

    fields = FOUNDATION_FIELDS

    def set_insights_level(self, level: str) -> None:
        if level not in {"campaign", "adset", "ad"}:
            raise SafeError("invalid_meta_level")
        self.insights_level = level
