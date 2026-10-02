"""Synthetic SDK workloads; no credentials, clients or live queries."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import BadRequest, Forbidden

from src.analytics.cloud.transport import CloudConfig, Transport
from src.bigquery.query_budget import QueryBudget, QueryBudgetExceeded
from src.control_plane.budget import BoundedClient, ExecutionBudgetExceeded
from src.observability.logging import SAFE_FIELDS

GIB = 1024**3
MIB = 1024**2


class Job:
    def __init__(self, billed, *, processed=7, rows=None, error=None, terminal=False):
        self.total_bytes_billed = billed
        self.total_bytes_processed = processed
        self.rows = rows or []
        self.error = error
        self.job_id = "synthetic"
        self.state = "DONE" if terminal else "RUNNING"
        self.error_result = {"reason": "synthetic"} if terminal else None
        self.session_info = SimpleNamespace(session_id="synthetic-session")
        self.results = 0

    def result(self, **kwargs):
        self.results += 1
        if self.error:
            raise self.error
        return self.rows


class SDK:
    def __init__(self, jobs, *, submission_error=None):
        self.jobs = iter(jobs)
        self.calls = []
        self.submission_error = submission_error
        self.last_job = None

    def query(self, sql, **kwargs):
        self.calls.append((sql, kwargs))
        if self.submission_error:
            raise self.submission_error
        job = next(self.jobs)
        job.job_id = f"synthetic-{len(self.calls)}"
        self.last_job = job
        return job

    def get_job(self, *args, **kwargs):
        return self.last_job


def config(**changes):
    return CloudConfig(
        **{
            "project": "synthetic-dev",
            "location": "southamerica-east1",
            "maximum_bytes_billed": GIB,
            "maximum_total_bytes_billed": 128 * GIB,
            "timeout_seconds": 30,
            "use_query_cache": False,
            **changes,
        }
    )


def layers(kind, sdk, cfg=None):
    cfg = cfg or config()
    if kind == "bounded":
        return BoundedClient(sdk, cfg)
    if kind == "nested":
        return Transport(BoundedClient(sdk, cfg), cfg)
    return Transport(sdk, cfg)


def execute(layer, sql="SELECT 1"):
    if isinstance(layer, Transport):
        return layer.query(sql, [])
    return layer.query(sql).result()


def assert_counters(budget, settled, unresolved):
    assert budget.metrics() == {
        "settled_billed_bytes": settled,
        "unresolved_reserved_bytes": unresolved,
        "budget_accounted_bytes": settled + unresolved,
    }
    assert budget.accounted_bytes == settled + unresolved
    assert budget.settled_billed_bytes >= 0
    assert budget.unresolved_reserved_bytes >= 0


def test_reserve_settle_zero_and_pre_submission_limit():
    budget = QueryBudget(100)
    first = budget.reserve(60)
    assert_counters(budget, 0, 60)
    with pytest.raises(QueryBudgetExceeded):
        budget.reserve(41)
    second = budget.reserve(40)
    assert budget.settle(first, 10)
    assert_counters(budget, 10, 40)
    assert budget.settle(second, 0)
    assert_counters(budget, 10, 0)


@pytest.mark.parametrize("billing", [None, -1, True, False, "10", 10.0, object()])
def test_unknown_or_invalid_billing_keeps_entire_reservation(billing):
    budget = QueryBudget(100)
    token = budget.reserve(100)
    assert not budget.settle(token, billing)
    budget.retain(token)
    assert_counters(budget, 0, 100)
    with pytest.raises(QueryBudgetExceeded):
        budget.reserve(1)


def test_over_ceiling_billing_poison_tracker_without_releasing_cost():
    budget = QueryBudget(100)
    token = budget.reserve(20)
    with pytest.raises(QueryBudgetExceeded):
        budget.settle(token, 21)
    assert_counters(budget, 0, 20)
    with pytest.raises(QueryBudgetExceeded):
        budget.reserve(1)


def test_double_settle_foreign_and_forged_tokens_cannot_release_cost():
    from src.bigquery.query_budget import Reservation

    budget = QueryBudget(100)
    token = budget.reserve(50)
    other = QueryBudget(100)
    foreign = other.reserve(50)
    for bad in (foreign, Reservation(50)):
        with pytest.raises(ValueError, match="reservation_not_active"):
            budget.settle(bad, 0)
        with pytest.raises(ValueError, match="reservation_not_active"):
            budget.retain(bad)
    assert budget.settle(token, 0)
    with pytest.raises(ValueError, match="reservation_not_active"):
        budget.settle(token, 0)
    assert_counters(budget, 0, 0)
    assert_counters(other, 0, 50)


@pytest.mark.parametrize("value", [0, -1, True, "1", 1.0])
def test_invalid_reservation_cannot_create_negative_counters(value):
    budget = QueryBudget(100)
    with pytest.raises(ValueError):
        budget.reserve(value)
    assert_counters(budget, 0, 0)


@pytest.mark.parametrize("value", [0, -1, True, "1", 1.0])
def test_invalid_execution_budget_rejected(value):
    with pytest.raises(ValueError, match="invalid_execution_budget"):
        QueryBudget(value)


def test_atomic_inflight_reservation_does_not_overcommit():
    budget = QueryBudget(100)

    def submit(_):
        try:
            return budget.reserve(10)
        except QueryBudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=16) as pool:
        tokens = [token for token in pool.map(submit, range(100)) if token is not None]
    assert len(tokens) == 10
    assert_counters(budget, 0, 100)
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert all(pool.map(lambda token: budget.settle(token, 2), tokens))
    assert_counters(budget, 20, 0)


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
def test_200_small_queries_pass_query_129_without_raising_budgets(kind):
    sdk = SDK([Job(10 * MIB, processed=9 * MIB) for _ in range(200)])
    layer = layers(kind, sdk)
    for _ in range(200):
        execute(layer)
    assert layer.query_count == len(sdk.calls) == 200
    assert layer.bytes_processed == 200 * 9 * MIB
    assert_counters(layer.query_budget, 200 * 10 * MIB, 0)
    assert layer.budget_accounted_bytes == 200 * 10 * MIB
    alias = layer.reserved_query_bytes if isinstance(layer, Transport) else layer.reserved_bytes
    assert alias == layer.budget_accounted_bytes
    for _, kwargs in sdk.calls:
        assert kwargs["job_config"].maximum_bytes_billed == GIB
        assert kwargs["job_config"].use_legacy_sql is False
        assert kwargs["job_retry"] is None
    if kind == "nested":
        # Independent trackers; neither metric is a sum of the two layers.
        assert layer.client.query_budget is not layer.query_budget
        assert layer.client.query_count == 200
        assert layer.client.query_budget.metrics() == layer.query_budget.metrics()
        assert layer.client.bytes_processed == layer.bytes_processed


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
def test_real_billed_exhaustion_blocks_next_job_before_sdk_submission(kind):
    sdk = SDK([Job(GIB) for _ in range(127)] + [Job(GIB // 2)])
    layer = layers(kind, sdk)
    for _ in range(127):
        execute(layer)
    assert_counters(layer.query_budget, 127 * GIB, 0)
    execute(layer)  # Worst-case exactly 128 GiB still fits.
    assert_counters(layer.query_budget, 127 * GIB + GIB // 2, 0)
    error = ValueError if isinstance(layer, Transport) else ExecutionBudgetExceeded
    with pytest.raises(
        error, match="execution_query_budget_exhausted|store_execution_budget_exhausted"
    ):
        execute(layer)
    assert layer.query_count == len(sdk.calls) == 128
    if kind == "bounded":
        assert layer.budget_exhausted and not layer.mutation_outcome_unknown


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
@pytest.mark.parametrize("billing", [None, -1, True, False, "1", 1.0])
def test_completed_query_with_unknown_billing_never_uses_processed_as_cost(kind, billing):
    sdk = SDK([Job(billing, processed=123)])
    layer = layers(kind, sdk, config(maximum_total_bytes_billed=GIB))
    execute(layer)
    assert layer.bytes_processed == 123
    assert_counters(layer.query_budget, 0, GIB)
    with pytest.raises(ValueError if isinstance(layer, Transport) else ExecutionBudgetExceeded):
        execute(layer)
    assert len(sdk.calls) == 1
    if kind == "nested":
        assert_counters(layer.client.query_budget, 0, GIB)


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
def test_zero_billed_success_releases_all_reserved_bytes(kind):
    layer = layers(kind, SDK([Job(0), Job(0)]), config(maximum_total_bytes_billed=GIB))
    execute(layer)
    execute(layer)
    assert_counters(layer.query_budget, 0, 0)
    assert layer.bytes_processed == 14 and layer.query_count == 2


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
@pytest.mark.parametrize("failure", ["submission", "result", "terminal"])
def test_failures_keep_worst_case_reservation_and_mutation_outcome(kind, failure):
    exc = Forbidden("synthetic") if failure == "terminal" else RuntimeError("synthetic")
    job = Job(0, error=exc, terminal=failure == "terminal")
    sdk = SDK([job], submission_error=exc if failure == "submission" else None)
    layer = layers(kind, sdk)
    with pytest.raises(type(exc)):
        execute(layer, "UPDATE synthetic SET value=1")
    assert_counters(layer.query_budget, 0, GIB)
    assert layer.bytes_processed is None
    bounded = layer if kind == "bounded" else layer.client if kind == "nested" else None
    if bounded:
        assert bounded.mutation_outcome_unknown is (failure != "terminal")
        assert not bounded.budget_exhausted
        assert_counters(bounded.query_budget, 0, GIB)


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
def test_billing_over_ceiling_fail_closed_and_prevent_following_query(kind):
    sdk = SDK([Job(GIB + 1)])
    layer = layers(kind, sdk)
    # Nested failure is surfaced by the inner BoundedClient, whose existing
    # BadRequest contract must remain visible to transaction reconciliation.
    error = ExecutionBudgetExceeded if kind in ("bounded", "nested") else ValueError
    with pytest.raises(error):
        execute(layer)
    assert_counters(layer.query_budget, 0, GIB)
    with pytest.raises(error):
        execute(layer)
    assert len(sdk.calls) == 1
    if kind == "bounded":
        assert layer.budget_exhausted and not layer.mutation_outcome_unknown


def test_measured_result_settles_and_measures_once_even_concurrently():
    sdk = SDK([Job(10, processed=17)])
    layer = BoundedClient(sdk, config())
    job = layer.query("SELECT 1")
    assert_counters(layer.query_budget, 0, GIB)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(lambda _: job.result(), range(20))) == [[]] * 20
    assert_counters(layer.query_budget, 10, 0)
    assert layer.bytes_processed == 17 and layer.query_count == 1
    assert len(layer.measured) == 1


@pytest.mark.parametrize("unknown", [None, -1, True])
def test_repeated_result_cannot_release_previously_unknown_billing(unknown):
    sdk = SDK([Job(unknown)])
    layer = BoundedClient(sdk, config())
    job = layer.query("SELECT 1")
    job.result()
    sdk.last_job.total_bytes_billed = 0
    job.result()
    assert_counters(layer.query_budget, 0, GIB)
    assert layer.bytes_processed == 7


def test_failed_result_keeps_reservation_even_if_reconciliation_later_succeeds():
    sdk = SDK([Job(0, error=RuntimeError("synthetic"))])
    layer = BoundedClient(sdk, config())
    job = layer.query("UPDATE synthetic SET value=1")
    with pytest.raises(RuntimeError):
        job.result()
    sdk.last_job.error = None
    job.result()
    assert_counters(layer.query_budget, 0, GIB)
    assert layer.mutation_outcome_unknown and layer.bytes_processed is None


def test_get_job_does_not_own_or_settle_queried_reservation():
    sdk = SDK([Job(10, processed=17)])
    layer = BoundedClient(sdk, config())
    owned = layer.query("SELECT 1")
    recovered = layer.get_job("synthetic-1")
    recovered.result()
    recovered.result()
    assert_counters(layer.query_budget, 0, GIB)
    assert layer.query_count == 1 and layer.bytes_processed == 17
    owned.result()
    owned.result()
    assert_counters(layer.query_budget, 10, 0)
    assert layer.bytes_processed == 17


def test_get_job_alone_has_no_reservation():
    sdk = SDK([])
    sdk.last_job = Job(10)
    layer = BoundedClient(sdk, config())
    layer.get_job("existing-synthetic").result()
    assert_counters(layer.query_budget, 0, 0)
    assert layer.query_count == len(sdk.calls) == 0


def test_multiple_inflight_queries_must_fit_before_results_settle():
    sdk = SDK([Job(0), Job(0)])
    layer = BoundedClient(sdk, config(maximum_total_bytes_billed=GIB))
    first = layer.query("SELECT 1")
    with pytest.raises(ExecutionBudgetExceeded):
        layer.query("SELECT 2")
    assert len(sdk.calls) == 1
    first.result()
    layer.query("SELECT 2").result()
    assert_counters(layer.query_budget, 0, 0)


@pytest.mark.parametrize("kind", ["transport", "bounded", "nested"])
def test_synthetic_mx_shaped_150_query_workload_completes_near_three_gib(kind):
    # Shape only, no source records; includes inventory, leaves and zero-cost SQL.
    billed_mib = [9] * 56 + [55] * 28 + [16] * 4 + [180] * 2 + [20] * 30 + [0] * 30
    assert len(billed_mib) == 150 and max(billed_mib) * MIB < 0.2 * GIB
    sdk = SDK([Job(b * MIB, processed=b * MIB // 2) for b in billed_mib])
    layer = layers(kind, sdk)
    for _ in billed_mib:
        execute(layer)
    assert layer.query_count == 150
    assert 2.5 * GIB < layer.budget_accounted_bytes < 3.5 * GIB
    assert_counters(layer.query_budget, sum(billed_mib) * MIB, 0)
    if kind == "nested":
        assert layer.client.query_budget.metrics() == layer.query_budget.metrics()


def test_completed_payload_overflow_retains_actual_billing_not_artificial_ceiling():
    sdk = SDK([Job(10, rows=[{"synthetic": "large"}])])
    layer = Transport(sdk, config(maximum_payload_bytes=1))
    with pytest.raises(ValueError, match="payload_too_large_partition_required"):
        execute(layer)
    assert_counters(layer.query_budget, 10, 0)
    assert layer.bytes_processed == 7


def test_lower_sdk_query_ceiling_remains_clamped_and_accounted_conservatively():
    from google.cloud.bigquery import QueryJobConfig

    sdk = SDK([Job(0)])
    layer = BoundedClient(sdk, config())
    job = layer.query("SELECT 1", job_config=QueryJobConfig(maximum_bytes_billed=10))
    assert sdk.calls[0][1]["job_config"].maximum_bytes_billed == 10
    assert_counters(layer.query_budget, 0, GIB)
    job.result()
    assert_counters(layer.query_budget, 0, 0)
    assert issubclass(ExecutionBudgetExceeded, BadRequest)


@pytest.mark.parametrize("kind", ["transport", "bounded"])
def test_legacy_alias_can_import_unknown_read_cost_but_cannot_release_cost(kind):
    layer = layers(kind, SDK([Job(10)]))
    alias = "reserved_query_bytes" if kind == "transport" else "reserved_bytes"
    execute(layer)
    setattr(layer, alias, getattr(layer, alias) + 100)
    assert_counters(layer.query_budget, 10, 100)
    with pytest.raises(ValueError):
        setattr(layer, alias, 0)
    assert_counters(layer.query_budget, 10, 100)


def test_budget_metrics_are_allowlisted_and_contain_no_job_or_payload():
    budget = QueryBudget(GIB)
    budget.reserve(GIB)
    assert budget.metrics().keys() <= SAFE_FIELDS
    assert all(type(v) is int for v in budget.metrics().values())


def test_invalid_billing_never_settles_later_or_releases_other_inflight_reservations():
    budget = QueryBudget(100)
    bad, other = budget.reserve(20), budget.reserve(20)
    with pytest.raises(QueryBudgetExceeded):
        budget.settle(bad, 21)
    for token in (bad, other):
        with pytest.raises(QueryBudgetExceeded):
            budget.settle(token, 0)
    assert_counters(budget, 0, 40)


def test_repeated_result_after_over_ceiling_billing_still_fails_closed():
    sdk = SDK([Job(GIB + 1)])
    layer = BoundedClient(sdk, config())
    job = layer.query("SELECT 1")
    with pytest.raises(ExecutionBudgetExceeded):
        job.result()
    sdk.last_job.total_bytes_billed = 0
    with pytest.raises(ExecutionBudgetExceeded):
        job.result()
    assert_counters(layer.query_budget, 0, GIB)
    assert layer.budget_exhausted


def test_transport_without_execution_cap_keeps_existing_optional_limit_contract():
    layer = Transport(SDK([Job(10)]), config(maximum_total_bytes_billed=None))
    execute(layer)
    assert_counters(layer.query_budget, 10, 0)


@pytest.mark.parametrize("kind", ["transport", "bounded"])
def test_alias_import_enforces_budget_and_never_changes_counters_on_rejection(kind):
    layer = layers(kind, SDK([]), config(maximum_total_bytes_billed=GIB))
    alias = "reserved_query_bytes" if kind == "transport" else "reserved_bytes"
    setattr(layer, alias, GIB)
    with pytest.raises(ValueError if kind == "transport" else ExecutionBudgetExceeded):
        setattr(layer, alias, GIB + 1)
    assert_counters(layer.query_budget, 0, GIB)
    if kind == "bounded":
        assert layer.budget_exhausted and not layer.mutation_outcome_unknown
