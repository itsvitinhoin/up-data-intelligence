from copy import deepcopy

import pytest

from src.domain.models import SafeError
from src.quality.catalog import catalog_freshness, certify_catalog_snapshot
from src.utils.data import digest

CUTOFF = "2026-10-05T03:00:00Z"


@pytest.mark.parametrize("assigned", [["unknown"], ["v-other-product"]])
def test_images_cannot_cross_products_or_guess_variant_identity(assigned):
    from src.quality.catalog import certify_image_relationships

    variants = [
        {"store_id": "store", "variant_id": "v", "product_id": "p"},
        {"store_id": "store", "variant_id": "v-other-product", "product_id": "other"},
    ]
    image = {"store_id": "store", "image_id": "i", "product_id": "p", "variant_ids": assigned}
    with pytest.raises(SafeError, match="catalog_image_variant_relationship_invalid"):
        certify_image_relationships("store", {"p", "other"}, variants, [image])
    certify_image_relationships("store", {"p", "other"}, variants, [])
    certify_image_relationships(
        "store", {"p", "other"}, variants, [{**image, "variant_ids": ["v"]}]
    )


def evidence():
    filters = {"catalog_as_of": CUTOFF}
    key = digest(["store", "conn", "variants", filters, "incremental"])
    checkpoint = {
        "store_id": "store",
        "connection_id": "conn",
        "resource": "variants",
        "plan_key": key,
        "run_id": "run",
        "status": "complete",
        "pending_raw_id": None,
        "mode": "incremental",
        "filters": filters,
    }
    run = {
        "store_id": "store",
        "source": "upzero",
        "mode": "incremental",
        "resource": "variants",
        "plan_key": key,
        "run_id": "run",
        "status": "completed",
        "core_records_failed": 0,
        "source_records_read": 1,
        "finished_at": "2026-10-05T03:10:00Z",
    }
    observations = [
        {
            "store_id": "store",
            "resource": "variants",
            "run_id": "run",
            "entity_id": "variant",
            "entity_version_id": "version",
            "raw_record_id": "raw",
            "observed_at": "2026-10-05T03:05:00Z",
        }
    ]
    return checkpoint, run, observations


def certify(cp, run, rows):
    return certify_catalog_snapshot("store", "conn", "variants", CUTOFF, cp, run, rows)


def test_exact_membership_proves_snapshot_not_lifetime_and_freshness_is_separate():
    proof = certify(*evidence())
    assert proof["observed_count"] == 1 and proof["history_complete"] is False
    assert catalog_freshness(proof, "2026-10-05T03:10:00Z") == "HEALTHY"
    assert catalog_freshness(proof, "2026-10-07T03:10:00Z") == "STALE"
    assert catalog_freshness(None, CUTOFF) == "NOT_CONFIGURED"


@pytest.mark.parametrize(
    "case",
    ["pending", "recovered", "raw", "foreign", "failed", "duplicate", "missing", "run", "cutoff"],
)
def test_partial_or_conflicting_evidence_never_becomes_certified(case):
    cp, run, rows = deepcopy(evidence())
    if case == "pending":
        cp["status"] = "running"
    if case == "recovered":
        cp["status"] = "recovered"
    if case == "raw":
        cp["pending_raw_id"] = "raw"
    if case == "foreign":
        rows[0]["store_id"] = "foreign"
    if case == "failed":
        run["core_records_failed"] = 1
    if case == "duplicate":
        rows *= 2
        run["source_records_read"] = 2
    if case == "missing":
        rows.clear()
    if case == "run":
        cp["run_id"] = "other"
    if case == "cutoff":
        cp["filters"]["catalog_as_of"] = "2026-10-04T03:00:00Z"
    with pytest.raises(SafeError):
        certify(cp, run, rows)


def test_empty_complete_catalog_is_zero_only_with_source_exhaustion_proof():
    cp, run, rows = evidence()
    run["source_records_read"] = 0
    assert certify(cp, run, [])["observed_count"] == 0
    cp["status"] = "running"
    with pytest.raises(SafeError):
        certify(cp, run, [])


def test_catalog_is_never_historical_coverage_or_customer_freshness():
    from src.control_plane.model import StoreConfig
    from src.installation.adoption import inspect

    cfg = StoreConfig(
        "synthetic-catalog", upzero_connection_id="up-catalog", timezone="America/Sao_Paulo"
    )
    filters = {"catalog_as_of": "2026-10-05T03:00:00Z", "limit": 200}
    cp = {
        "store_id": cfg.store_id,
        "connection_id": cfg.upzero_connection_id,
        "resource": "products",
        "mode": "incremental",
        "filters": filters,
        "plan_key": digest(
            [cfg.store_id, cfg.upzero_connection_id, "products", filters, "incremental"]
        ),
        "run_id": "catalog-run",
        "status": "complete",
        "pending_raw_id": None,
    }
    run = {
        "store_id": cfg.store_id,
        "resource": "products",
        "source": "upzero",
        "run_id": "catalog-run",
        "plan_key": cp["plan_key"],
        "status": "completed",
        "core_records_failed": 0,
    }
    result = inspect(cfg, [cp], [run], "2026-10-05T03:00:00Z")
    assert result == {
        "coverage": {"orders": [], "analytics_facts": []},
        "pending": [],
        "customers_fresh": False,
    }
    run["run_id"] = "different-run"
    with pytest.raises(SafeError, match="work_checkpoint_mismatch"):
        inspect(cfg, [cp], [run], "2026-10-05T03:00:00Z")
