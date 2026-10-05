"""No Graph/credential IO. Ad/day proof and nullable ranking semantics."""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, ReadError
from src.dashboard.creatives import CreativeReader
from src.dashboard.service import DashboardService
from src.utils.data import digest
from tests.dashboard.test_read_api import GRANT, KEY, PRINCIPAL, FakeReader
from tests.unit.test_meta_foundation import ACCOUNT, INSIGHTS


@pytest.fixture
def policy():
    return AnalyticsPolicy.from_dict(
        json.loads(Path("config/analytics/mx-fashion.dev.json").read_text())
    )


ACCOUNT = replace(ACCOUNT, store_id=GRANT.store_id)
START, END, SNAPSHOT = "2026-01-01", "2026-01-02", "2026-01-03T03:00:00Z"


def proof():
    cps, runs = [], []
    for resource, level in [
        ("meta_live_insights_daily", "campaign"),
        ("meta_creative_insights_daily", "ad"),
        ("meta_live_ads", None),
    ]:
        filters = {
            "account": ACCOUNT.snapshot(),
            "insights": {**INSIGHTS.snapshot(), "level": level} if level else None,
        }
        key = digest([resource, filters])
        cp = dict(
            store_id=ACCOUNT.store_id,
            connection_id=ACCOUNT.connection_id,
            resource=resource,
            filters=filters,
            status="complete",
            pending_raw_id=None,
            plan_key=key,
            run_id=key,
            updated_at="2026-01-02T03:05:00Z",
        )
        run = dict(
            store_id=ACCOUNT.store_id,
            source="meta",
            resource=resource,
            status="completed",
            plan_key=key,
            run_id=key,
            core_records_failed=0,
            finished_at="2026-01-02T03:05:00Z",
        )
        cps.append(cp)
        runs.append(run)
    return cps, runs


class Reader:
    def __init__(self):
        self.calls = []
        self.cps, self.runs = proof()
        self.grain = {"row_count": 1, "identities": 1, "grains": 1, "invalid": 0}
        self.rows = [
            dict(
                ad_id="000401",
                campaign_id="000201",
                adset_id="000301",
                campaigns=1,
                adsets=1,
                catalog_matches=1,
                name="Sintético",
                status="ACTIVE",
                creative_id="000501",
                video_id=None,
                image_url=None,
                thumbnail_url="https://media.fbcdn.net/synthetic.jpg",
                preview_observed_at="2026-01-02T03:04:00Z",
                spend=Decimal("123.450000001"),
                impressions=1000,
                clicks=10,
                link_clicks=8,
                ctr=Decimal("1"),
                cpa=Decimal("61.7250000005"),
                meta_reported_purchases=Decimal("2"),
                meta_reported_purchase_value=Decimal("250.12"),
            )
        ]

    def query(self, q, **context):
        self.calls.append(q)
        assert context["store_id"] == ACCOUNT.store_id and context["generation"] is None
        assert q.parameters["store"] == ("STRING", ACCOUNT.store_id)
        assert ACCOUNT.store_id not in q.sql
        if q.name == "creative_source":
            return [
                dict(
                    store_id=ACCOUNT.store_id,
                    account_id=ACCOUNT.account_id,
                    connection_id=ACCOUNT.connection_id,
                    api_version=ACCOUNT.api_version,
                    source_timezone=ACCOUNT.timezone,
                    currency=ACCOUNT.currency,
                )
            ]
        if q.name == "creative_evidence":
            return [
                {
                    "checkpoints": [{"value": json.dumps(c)} for c in self.cps],
                    "runs": [{"value": json.dumps(r)} for r in self.runs],
                }
            ]
        if q.name == "creative_grain":
            return [self.grain]
        if q.name == "creative_rankings":
            return self.rows
        raise AssertionError(q.name)


def read(reader):
    return CreativeReader(
        "synthetic-project", reader, ACCOUNT.store_id, "synthetic-request", SNAPSHOT
    ).read(START, END)


def test_ad_metrics_exact_money_current_preview_and_not_attribution():
    fake = Reader()
    rows = read(fake)
    row = rows[0]
    assert row["spend"] == "123.450000001" and row["cpa"] == "61.7250000005"
    assert row["basis"] == "meta_reported_ad_day"
    assert row["reach"] is None and row["frequency"] is None
    assert row["reporting_definition"]["level"] == "ad"
    assert len(row["evidence_hash"]) == 64
    assert row["preview_observed_at"] == "2026-01-02T03:04:00+00:00"
    assert len(fake.calls) == 4
    sql = fake.calls[-1].sql
    assert "meta_live_insights_daily" not in sql
    assert "ROW_NUMBER()" in sql and "LIMIT 10" in sql
    assert "COUNTIF(meta_reported_purchases IS NULL)>0" in sql
    assert fake.calls[-1].parameters["from"] == ("DATE", START)


@pytest.mark.parametrize("field", ["impressions", "clicks", "link_clicks"])
def test_negative_creative_counts_are_not_valid_metrics(field):
    fake = Reader()
    fake.rows[0][field] = -1
    with pytest.raises(ReadError, match="creative_metrics_invalid"):
        read(fake)


@pytest.mark.parametrize(
    "issue",
    [
        "missing-ad",
        "gap",
        "raw",
        "failed-run",
        "wrong-account",
        "catalog-running",
        "duplicate-catalog",
        "duplicate-grain",
        "preview-after-run",
    ],
)
def test_incomplete_or_ambiguous_evidence_fails_closed(issue):
    fake = Reader()
    if issue == "missing-ad":
        fake.cps.pop(1)
    if issue == "gap":
        fake.cps[1]["filters"]["insights"]["since"] = "2026-01-02"
        fake.cps[1]["filters"]["insights"]["until"] = "2026-01-02"
    if issue == "raw":
        fake.cps[1]["pending_raw_id"] = "synthetic-raw"
    if issue == "failed-run":
        fake.runs[1]["core_records_failed"] = 1
    if issue == "wrong-account":
        fake.cps[1]["filters"]["account"]["account_id"] = "999"
    if issue == "catalog-running":
        fake.cps[-1]["status"] = "running"
    if issue == "duplicate-catalog":
        fake.rows[0]["catalog_matches"] = 2
    if issue == "duplicate-grain":
        fake.grain["row_count"] = 2
    if issue == "preview-after-run":
        fake.rows[0]["preview_observed_at"] = "2026-01-02T03:06:00Z"
    with pytest.raises(ReadError):
        read(fake)


def test_unknown_purchase_and_unsafe_preview_never_become_zero_or_browser_url():
    fake = Reader()
    fake.rows[0].update(
        meta_reported_purchases=None,
        meta_reported_purchase_value=None,
        cpa=None,
        thumbnail_url="https://untrusted.invalid/private.jpg",
    )
    row = read(fake)[0]
    assert row["meta_reported_purchases"] is None and row["cpa"] is None
    assert row["preview_url"] is None


def test_rank_limit_duplicate_ad_and_float_are_rejected():
    for issue in ("too-many", "duplicate", "float"):
        fake = Reader()
        if issue == "too-many":
            fake.rows *= 10
        if issue == "duplicate":
            fake.rows.append(deepcopy(fake.rows[0]))
        if issue == "float":
            fake.rows[0]["spend"] = 1.25
        with pytest.raises(ReadError):
            read(fake)


def test_service_authorizes_before_any_creative_or_publication_io(policy):
    fake = FakeReader(policy)
    service = DashboardService(
        "synthetic-project", {GRANT.store_id: policy}, lambda: fake, KEY, creatives_enabled=True
    )
    with pytest.raises(ReadError) as error:
        service.creatives(PRINCIPAL, Grant("foreign", GRANT.store_id, "B2B"))
    assert error.value.status == 403 and not fake.calls
    service.creatives_enabled = False
    with pytest.raises(ReadError) as error:
        service.creatives(PRINCIPAL, GRANT)
    assert error.value.status == 424
    assert [q.name for q in fake.calls] == ["head"]
