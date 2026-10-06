import json
from copy import deepcopy

import pytest

from src.dashboard.catalog import CatalogReader
from src.dashboard.contracts import ReadError
from src.utils.data import digest
from tests.dashboard.test_catalog_reads import CONNECTION, STORE, FakeReader


class ImageReader(FakeReader):
    def __init__(self):
        super().__init__()
        cutoff = "2026-10-05T03:00:00+00:00"
        filters = {"catalog_as_of": cutoff, "product_ids": ["product-explicit"]}
        key = digest([STORE, CONNECTION, "images", filters, "incremental"])
        cp = {
            "store_id": STORE,
            "connection_id": CONNECTION,
            "resource": "images",
            "filters": filters,
            "mode": "incremental",
            "plan_key": key,
            "run_id": "images-run",
            "status": "complete",
            "pending_raw_id": None,
        }
        run = {
            "store_id": STORE,
            "source": "upzero",
            "resource": "images",
            "mode": "incremental",
            "plan_key": key,
            "run_id": "images-run",
            "status": "completed",
            "core_records_failed": 0,
            "source_records_read": 1,
            "finished_at": cutoff,
        }
        self.image_proofs = [
            {
                "checkpoint": json.dumps(cp),
                "run": json.dumps(run),
                "observations": 1,
                "distinct_entities": 1,
                "valid_version_links": 1,
                "product_ids": ["product-explicit"],
                "invalid_relationships": 0,
            }
        ]
        self.images = [
            {
                "store_id": STORE,
                "image_id": "image",
                "product_id": "product-explicit",
                "image_url": "https://images.example.test/official.jpg",
                "variant_ids": ["variant-explicit"],
                "is_primary": True,
                "display_order": 0,
            }
        ]

    def query(self, query, **kwargs):
        if query.name.startswith("catalog_images"):
            self.calls.append(query)
            assert query.parameters["store"] == ("STRING", STORE)
            assert STORE not in query.sql and "product-explicit" not in query.sql
            return self.image_proofs if query.name == "catalog_images_proof" else self.images
        return super().query(query, **kwargs)


def project(fake):
    return CatalogReader(
        "synthetic-project", fake, STORE, None, "request", images_enabled=True
    ).variants(["variant-explicit"])


def test_images_require_complete_official_membership_and_exact_variant_assignment():
    fake = ImageReader()
    row = project(fake)["variant-explicit"]
    assert row["image"] == fake.images[0]["image_url"]
    assert row["image_basis"] == "official_current_catalog_snapshot"
    assert "FOR SYSTEM_TIME" not in fake.calls[-1].sql  # Current catalog, explicitly separate.
    fake.images[0]["variant_ids"] = ["another-variant"]
    assert "image" not in project(fake)["variant-explicit"]


def test_absent_or_running_image_scan_never_becomes_certified_image():
    fake = ImageReader()
    fake.image_proofs = []
    assert "image" not in project(fake)["variant-explicit"]
    fake = ImageReader()
    cp = json.loads(fake.image_proofs[0]["checkpoint"])
    cp["status"] = "running"
    fake.image_proofs[0]["checkpoint"] = json.dumps(cp)
    assert "image" not in project(fake)["variant-explicit"]
    assert not any(q.name == "catalog_images_projection" for q in fake.calls)


@pytest.mark.parametrize(
    "case", ["relationship", "membership", "duplicate", "foreign", "http", "credentials"]
)
def test_invalid_image_evidence_fails_closed(case):
    fake = ImageReader()
    if case == "relationship":
        fake.image_proofs[0]["invalid_relationships"] = 1
    if case == "membership":
        fake.image_proofs[0]["product_ids"] = ["other"]
    if case == "duplicate":
        fake.image_proofs.append(deepcopy(fake.image_proofs[0]))
    if case == "foreign":
        fake.images[0]["store_id"] = "other"
    if case == "http":
        fake.images[0]["image_url"] = "http://images.example.test/a"
    if case == "credentials":
        fake.images[0]["image_url"] = "https://user:secret@images.example.test/a"
    with pytest.raises(ReadError):
        project(fake)
