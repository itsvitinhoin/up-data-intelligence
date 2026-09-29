"""Deterministic technical scenario estimator, no prices or cloud IO. 30-day month."""

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Scenario:
    stores: int = 1
    facts_per_store_month: int = 355886
    facts_payload_bytes: int = 1500  # assumption, not measured MX Fashion payload
    fast_interval_minutes: int = 15
    reconcile_frequency_per_day: int = 1
    reconcile_lookback_hours: int = 72
    raw_retention_days: int = 365
    core_retention: int = 365  # days
    quality_frequency: int = 48  # separate invocations/day
    deep_quality_frequency: int = 1  # proposed historical checks/day, not approved
    analytics_frequency: int = 0  # publications/day, illustrative only
    page_limit: int = 1000
    history_days: int = 30  # current reconcile default starts at initial_from
    core_row_bytes: int = 1000
    version_multiplier: float = 1.0
    raw_identical_fraction: float = 0.0  # hypothetical future blob reuse; default OFF
    raw_envelope_bytes: int = 1000
    ops_bytes_per_run: int = 2000
    analytics_bytes_per_publication: int = 10000
    meta_bytes_per_store_month: int = 0  # not enabled; explicit assumption
    execution_seconds: float = 30.0
    vcpus: float = 1.0
    memory_gib: float = 1.0
    scan_bytes_per_observation: int = 1000
    bq_jobs_per_page: int = 8  # sensitivity input; not measured SQL count

    def validate(self) -> None:
        if any(v < 0 for v in asdict(self).values()):
            raise ValueError("negative_scenario")
        if (
            min(self.stores, self.fast_interval_minutes, self.page_limit) <= 0
            or self.page_limit > 1000
        ):
            raise ValueError("invalid_capacity")
        if not 0 <= self.raw_identical_fraction <= 1:
            raise ValueError("invalid_reobservation_fraction")


def estimate(s: Scenario, *, current: bool = False) -> dict[str, object]:
    s.validate()
    f = s.facts_per_store_month
    runs = 30 * 1440 / s.fast_interval_minutes
    daily = f / 30
    fast_per_run = f / runs + (daily * s.reconcile_lookback_hours / 24 if current else 0)
    rec_runs = 30 if current else 30 * s.reconcile_frequency_per_day
    rec_days = s.history_days if current else s.reconcile_lookback_hours / 24
    rec_observations = rec_runs * daily * rec_days
    observations = runs * fast_per_run + rec_observations
    # Current CLI reconcile divides the horizon into <=24h requests.
    rec_pages = rec_runs * (
        math.floor(rec_days) * max(1, math.ceil(daily / s.page_limit))
        + (max(1, math.ceil(daily * (rec_days % 1) / s.page_limit)) if rec_days % 1 else 0)
    )
    pages = math.ceil(runs) * max(1, math.ceil(fast_per_run / s.page_limit)) + rec_pages
    quality_runs = 30 * (s.quality_frequency + (0 if current else s.deep_quality_frequency))
    analytics_runs = 30 * s.analytics_frequency
    executions = runs + rec_runs + quality_runs + analytics_runs
    # Current CLI runs full quality after sync/reconcile, plus dedicated quality jobs.
    deep_checks = runs + rec_runs + quality_runs if current else 30 * s.deep_quality_frequency
    # Proposal fast checks inspect affected observations; deep checks inspect history.
    scan_units = observations + deep_checks * daily * s.history_days
    if not current:
        scan_units += s.quality_frequency * f  # scoped recent checks, assumed 1-day scopes
    # Analytics scans modeled independently: full retained history per publication.
    scan_units += analytics_runs * daily * s.history_days
    queries = pages * s.bq_jobs_per_page + deep_checks + analytics_runs
    n = s.stores
    raw_month = (
        observations * s.facts_payload_bytes * (1 - s.raw_identical_fraction)
        + pages * s.raw_envelope_bytes
    ) * n
    core_rows = f * s.core_retention / 30 * n
    storage = {
        "raw": raw_month * s.raw_retention_days / 30,
        "core_facts": core_rows * s.core_row_bytes,
        "versions": core_rows * s.version_multiplier * s.core_row_bytes,
        "ops": executions * n * s.ops_bytes_per_run * s.raw_retention_days / 30,
        "analytics": analytics_runs * n * s.analytics_bytes_per_publication * s.core_retention / 30,
        "meta_future": s.meta_bytes_per_store_month * n * s.core_retention / 30,
    }
    return {
        "scenario": "current_pilot"
        if current
        else f"fast_reconcile_{s.reconcile_frequency_per_day}",
        "stores": n,
        "unique_facts_month": f * n,
        "fact_observations_month": round(observations * n),
        "observation_multiplier": round(observations / f, 6) if f else None,
        "estimated_api_pages": round(pages * n),
        "raw_observation_pages": round(pages * n),
        "raw_ingress_gb_month": round(raw_month / 1e9, 6),
        "core_retained_fact_rows": round(core_rows),
        "core_new_fact_upserts_month": f * n,  # no restatements assumed
        "raw_page_writes": round(pages * n),
        "estimated_bq_queries": round(queries * n),
        "estimated_bq_scanned_bytes": round(scan_units * s.scan_bytes_per_observation * n),
        "estimated_execution_counts": round(executions * n),
        "foundation_fact_executions": round((runs + rec_runs) * n),
        "vcpu_seconds": round(executions * n * s.execution_seconds * s.vcpus),
        "gib_seconds": round(executions * n * s.execution_seconds * s.memory_gib),
        "retained_storage_gb": {k: round(v / 1e9, 6) for k, v in storage.items()},
        "retained_storage_tb": round(sum(storage.values()) / 1e12, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset", choices=["mx-fashion", "10-stores", "100-stores"], default="mx-fashion"
    )
    parser.add_argument("--compare", action="store_true")
    for key, value in asdict(Scenario()).items():
        parser.add_argument("--" + key.replace("_", "-"), type=type(value))
    args = vars(parser.parse_args())
    preset = args.pop("preset")
    compare = args.pop("compare")
    base = Scenario(stores={"mx-fashion": 1, "10-stores": 10, "100-stores": 100}[preset])
    s = replace(base, **{k: v for k, v in args.items() if v is not None})
    cases = (
        [estimate(s, current=True)]
        + [estimate(replace(s, reconcile_frequency_per_day=r)) for r in (1, 2, 4)]
        if compare
        else [estimate(s)]
    )
    print(json.dumps({"assumptions": asdict(s), "estimates": cases}, indent=2))


if __name__ == "__main__":
    main()
