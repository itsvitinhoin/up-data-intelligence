from decimal import Decimal

import pytest

from src.dashboard.contracts import ReadError
from src.dashboard.monthly import monthly_performance


def inputs():
    commercial = {
        "series": [
            {
                "date": "2026-09-01",
                "requested": "0.10",
                "fulfilled": "0.05",
                "cancelled_requested": "0",
                "orders": 1,
            },
            {
                "date": "2026-09-02",
                "requested": "0.20",
                "fulfilled": "0.10",
                "cancelled_requested": "0",
                "orders": 1,
            },
        ],
        "monthly_customers": [
            {"month": "2026-09-01", "buyers_observed": 1, "recurring_buyers_observed": 1}
        ],
        "monthly_payments": [
            {"month": "2026-09-01", "orders": 2, "paid_orders": 1, "unknown_payment_status": 0}
        ],
    }
    funnel = [
        {
            "event_date": "2026-09-01",
            "sessions": 4,
            "add_to_cart": 2,
            "checkout_started": 1,
            "sessions_with_cart": 2,
            "sessions_cart_then_checkout": 1,
            "sessions_cart_checkout_purchase": 1,
            "sessions_with_purchase": 1,
        }
    ]
    media = [{"date": "2026-09-01", "spend": "0.10"}]
    return commercial, funnel, media


def calculate(commercial, funnel, media, complete=True):
    return monthly_performance(
        commercial, funnel, media, "2026-09-01", "2026-10-01", meta_complete=complete
    )[0]


def test_monthly_decimal_authority_distinct_customers_and_explicit_paid_status():
    row = calculate(*inputs())
    assert Decimal(row["requested"]) == Decimal("0.30")
    assert row["requested_ticket"] == "0.15"
    assert row["commercial_roas_requested"] == "3"
    assert row["cost_per_session"] == "0.025"
    assert row["cost_per_paid_order"] == "0.10"
    assert row["paid_orders"] == 1
    assert row["buyers"] == 1  # Not the sum of daily customer counts.
    assert row["recurring_rate"] == "100"
    assert row["session_purchase_rate"] == "25.00"
    assert row["paid_revenue"] is None and row["commercial_roas_paid"] is None


def test_unknown_money_and_payment_status_do_not_become_zero():
    c, f, m = inputs()
    c["series"][1]["requested"] = None
    c["monthly_payments"][0]["unknown_payment_status"] = 1
    row = calculate(c, f, m)
    assert row["requested"] is None and row["requested_ticket"] is None
    assert row["paid_orders"] is None and row["cost_per_paid_order"] is None
    row = calculate(c, f, m, False)
    assert row["meta_spend"] is None and row["cost_per_session"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_day",
        "outside_period",
        "payment_count",
        "duplicate_month",
        "exclusive_end_month",
        "not_month_start",
        "unknown_overlap",
    ],
)
def test_monthly_grain_and_period_fail_closed(mutation):
    c, f, m = inputs()
    if mutation == "duplicate_day":
        c["series"].append(c["series"][0])
    elif mutation == "outside_period":
        m[0]["date"] = "2026-10-01"
    elif mutation == "payment_count":
        c["monthly_payments"][0]["orders"] = 3
    elif mutation == "exclusive_end_month":
        c["monthly_customers"][0]["month"] = "2026-10-01"
    elif mutation == "not_month_start":
        c["monthly_customers"][0]["month"] = "2026-09-02"
    elif mutation == "unknown_overlap":
        c["monthly_payments"][0]["unknown_payment_status"] = 2
    else:
        c["monthly_customers"].append(c["monthly_customers"][0])
    with pytest.raises(ReadError):
        calculate(c, f, m)
