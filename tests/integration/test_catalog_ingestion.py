import httpx
import pytest

from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.ingestion.engine import Engine
from src.normalization.catalog import normalize_catalog

STAMP = "2026-10-05T03:00:00Z"
PRODUCT = {
    "id": "p1",
    "product_id": "p1",
    "name": "Produto sintético",
    "code": "REF-1",
    "status": "active",
    "created_at": STAMP,
    "updated_at": STAMP,
}
VARIANT = {
    "id": "v1",
    "product_id": "p1",
    "sku": "SKU-1",
    "price": "19.90",
    "active": True,
    "created_at": STAMP,
    "updated_at": STAMP,
    "attributes": [
        {"attribute": {"id": "a1", "code": "color"}, "term": {"name": "Azul", "code": "AZ"}},
        {"attribute": {"id": "a2", "code": "size"}, "term": {"name": "M", "code": "M"}},
    ],
}
IMAGE = {
    "id": "image-1",
    "product_id": "p1",
    "image_url": "https://images.example.test/p1.jpg",
    "display_order": 0,
    "is_primary": True,
    "variant_ids": ["v1"],
    "created_at": STAMP,
    "updated_at": STAMP,
}


def test_official_images_resume_between_products_and_certify_exact_relationships(tmp_path):
    from src.ingestion.catalog import CatalogSnapshot

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/products"):
            return httpx.Response(
                200, json={"data": [PRODUCT, {**PRODUCT, "id": "p2", "product_id": "p2"}]}
            )
        if request.url.path.endswith("/variants"):
            return httpx.Response(200, json={"data": [VARIANT]})
        if request.url.path.endswith("/attributes"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/images"):
            assert not request.url.params
            return httpx.Response(200, json=[IMAGE] if "/p1/" in request.url.path else [])
        return httpx.Response(
            200,
            json={
                "variant_id": "v1",
                "totals": {"qty_total": 1, "qty_reserved": 0, "qty_available": 1},
            },
        )

    engine, repo = setup(tmp_path, handler)
    snapshot = CatalogSnapshot(engine)
    first = snapshot.advance(STAMP, page_budget=5, include_images=True)
    assert first["yielded"] and not first["complete"] and len(calls) == 5
    cp = next(c for c in repo.read("sync_checkpoints", "synthetic-a") if c["resource"] == "images")
    assert cp["position"] == {"index": 1} and cp["pending_raw_id"] is None
    before = cp["run_id"]
    last = snapshot.advance(STAMP, page_budget=5, include_images=True)
    assert last["complete"] and len(calls) == 6
    image_cp = next(
        c for c in repo.read("sync_checkpoints", "synthetic-a") if c["resource"] == "images"
    )
    assert image_cp["run_id"] == before and image_cp["status"] == "complete"
    assert image_cp["filters"]["product_ids"] == ["p1", "p2"]
    assert len(repo.read("upzero_images", "synthetic-a")) == 2  # Empty gallery is still observed.
    assert len(repo.read("catalog_images", "synthetic-a")) == 1
    assert last["snapshots"][-1]["observed_count"] == 1
    assert all("images" not in r["resource"] for r in repo.read("sync_runs", "synthetic-b"))


def test_image_endpoint_rejects_product_mismatch_and_invalid_position_before_fetch(tmp_path):
    engine, _ = setup(
        tmp_path, lambda _: httpx.Response(200, json=[{**IMAGE, "product_id": "other"}])
    )
    with pytest.raises(Exception, match="catalog_image_product_mismatch"):
        next(engine.connector.pages("images", {"product_ids": ["p1"], "catalog_as_of": STAMP}))
    with pytest.raises(Exception, match="catalog_images_position_invalid"):
        next(
            engine.connector.pages(
                "images", {"product_ids": ["p1"], "catalog_as_of": STAMP}, {"index": 1}
            )
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"image_url": "http://images.example.test/a"},
        {"image_url": "https://user:password@images.example.test/a"},
        {"is_primary": "true"},
        {"variant_ids": ["v1", "v1"]},
        {"display_order": -1},
    ],
)
def test_image_contract_rejects_unsafe_or_ambiguous_fields(mutation):
    with pytest.raises(ValueError):
        normalize_catalog("images", {**IMAGE, **mutation})


def setup(tmp_path, handler, store="synthetic-a"):
    settings = Settings(store, "Synthetic", store, "America/Sao_Paulo", "conn-" + store, STAMP)
    repo = SQLiteRepository(str(tmp_path / "catalog.sqlite"))
    client = UpZeroConnector("synthetic-secret", httpx.MockTransport(handler))
    return Engine(settings, repo, client), repo


def test_catalog_snapshots_raw_core_versions_and_store_isolation(tmp_path):
    def handler(request):
        if request.url.path.endswith("/products"):
            return httpx.Response(200, json={"data": [PRODUCT], "next_cursor": None})
        if request.url.path.endswith("/variants"):
            return httpx.Response(200, json={"data": [VARIANT], "next_cursor": None})
        if request.url.path.endswith("/attributes"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "code": "color",
                        "name": "Cor",
                        "terms": [{"id": "t1", "code": "AZ", "rgb": "#0000ff"}],
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "variant_id": "v1",
                "totals": {"qty_total": 10, "qty_reserved": 2, "qty_available": 8},
            },
        )

    engine, repo = setup(tmp_path, handler)
    for resource, filters in [
        ("products", {}),
        ("variants", {}),
        ("attributes", {}),
        ("inventory", {"variant_id": "v1"}),
    ]:
        run = engine.run(resource, filters, mode="incremental")
        assert run["status"] == "completed" and run["core_records_failed"] == 0
        assert len(repo.read("upzero_" + resource, "synthetic-a")) == 1
        assert engine.run(resource, filters, mode="incremental")["run_id"] == run["run_id"]
    assert repo.read("catalog_products", "synthetic-a")[0]["name"] == "Produto sintético"
    variant = repo.read("catalog_variants", "synthetic-a")[0]
    assert (variant["product_id"], variant["color"], variant["size"], variant["price"]) == (
        "p1",
        "Azul",
        "M",
        "19.90",
    )
    assert repo.read("catalog_inventory", "synthetic-a")[0]["qty_available"] == "8"
    other, _ = setup(tmp_path, handler, "synthetic-b")
    other.run("variants", {})
    assert (
        repo.read("catalog_variants", "synthetic-a")[0]["row_key"]
        != repo.read("catalog_variants", "synthetic-b")[0]["row_key"]
    )
    assert len(repo.read("catalog_variants_versions", "synthetic-a")) == 1


def test_catalog_yield_preserves_checkpoint_and_resumes_without_reset(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.params.get("cursor"))
        if request.url.params.get("cursor"):
            return httpx.Response(
                200, json={"data": [{**VARIANT, "id": "v2"}], "next_cursor": None}
            )
        return httpx.Response(200, json={"data": [VARIANT], "next_cursor": "next"})

    engine, repo = setup(tmp_path, handler)
    first = engine.advance("variants", {}, mode="incremental", page_budget=1)
    assert first["yielded"] and not first["complete"]
    cp = repo.read("sync_checkpoints", "synthetic-a")[0]
    assert cp["pending_raw_id"] is None and cp["position"] == {"cursor": "next"}
    last = engine.advance("variants", {}, mode="incremental", page_budget=1)
    assert last["complete"] and last["run_id"] == first["run_id"]
    assert last["pages"] == 2 and calls == [None, "next"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"active": "true"},
        {
            "attributes": [
                {"attribute": {"code": "color"}, "term": {"name": "a"}},
                {"attribute": {"code": "color"}, "term": {"name": "b"}},
            ]
        },
        {"product_id": None},
        {"updated_at": None},
    ],
)
def test_variant_invalid_identity_or_attributes_rejected(mutation):
    with pytest.raises((ValueError, TypeError)):
        normalize_catalog("variants", {**VARIANT, **mutation})


def test_sku_does_not_create_color_or_size():
    row = normalize_catalog("variants", {**VARIANT, "sku": "RED-XL", "attributes": []})[1]
    assert row["color"] is None and row["size"] is None
    with pytest.raises(ValueError, match="identity_mismatch"):
        normalize_catalog("products", {**PRODUCT, "product_id": "other"})


def test_variant_accepts_exact_portuguese_codes_and_rejects_cross_alias_duplicates():
    attributes = [
        {"attribute": {"code": "cor"}, "term": {"name": "Azul", "code": "AZ"}},
        {"attribute": {"code": "tamanho"}, "term": {"name": "M", "code": "M"}},
    ]
    row = normalize_catalog("variants", {**VARIANT, "attributes": attributes})[1]
    assert (row["color"], row["color_code"], row["size"], row["size_code"]) == (
        "Azul",
        "AZ",
        "M",
        "M",
    )
    attributes.append({"attribute": {"code": "color"}, "term": {"name": "Azul"}})
    with pytest.raises(ValueError, match="catalog_attribute_ambiguous"):
        normalize_catalog("variants", {**VARIANT, "attributes": attributes})


def test_unchanged_products_have_new_snapshot_membership_without_fake_versions(tmp_path):
    engine, repo = setup(tmp_path, lambda request: httpx.Response(200, json={"data": [PRODUCT]}))
    first = engine.run("products", {}, mode="incremental")
    second = engine.run("products", {}, mode="incremental", refresh=True)
    assert first["run_id"] != second["run_id"]
    assert len(repo.read("catalog_products_versions", "synthetic-a")) == 1
    observations = repo.read("catalog_observations", "synthetic-a")
    assert {r["run_id"] for r in observations} == {first["run_id"], second["run_id"]}
    assert len({r["entity_version_id"] for r in observations}) == 1
    assert len({r["raw_record_id"] for r in observations}) == 2
    assert second["core_records_failed"] == 0


def test_inventory_snapshot_yields_between_variants_not_during_promotion(tmp_path):
    calls = []

    def handler(request):
        assert set(request.url.params) == {"variant_id"}
        identity = request.url.params["variant_id"]
        calls.append(identity)
        return httpx.Response(
            200,
            json={
                "variant_id": identity,
                "totals": {
                    "qty_total": 4,
                    "qty_reserved": 1,
                    "qty_available": 3,
                },
            },
        )

    engine, repo = setup(tmp_path, handler)
    filters = {"variant_ids": ["v1", "v2", "v3"], "catalog_as_of": STAMP}
    first = engine.advance("inventory", filters, mode="incremental", page_budget=2)
    assert first["yielded"] and not first["complete"]
    checkpoint = repo.read("sync_checkpoints", "synthetic-a")[0]
    assert checkpoint["position"] == {"index": 2}
    assert checkpoint["pending_raw_id"] is None
    assert len(repo.read("catalog_inventory", "synthetic-a")) == 2
    last = engine.advance("inventory", filters, mode="incremental", page_budget=2)
    assert last["complete"] and last["run_id"] == first["run_id"]
    assert last["pages"] == 3 and calls == ["v1", "v2", "v3"]
    assert len(repo.read("catalog_observations", "synthetic-a")) == 3


@pytest.mark.parametrize(
    "filters",
    [
        {"variant_ids": ["v1", "v1"], "catalog_as_of": STAMP},
        {"variant_ids": ["v2", "v1"], "catalog_as_of": STAMP},
        {"variant_ids": ["v1"]},
        {"variant_ids": ["v1"], "variant_id": "v1", "catalog_as_of": STAMP},
    ],
)
def test_invalid_inventory_snapshot_fails_before_api(tmp_path, filters):
    def handler(request):
        raise AssertionError("source API must not run")

    engine, _ = setup(tmp_path, handler)
    with pytest.raises(Exception, match="inventory_snapshot_invalid"):
        engine.advance("inventory", filters, mode="incremental")


def test_logical_catalog_snapshot_uses_one_shared_budget_and_certified_variant_membership(tmp_path):
    from src.ingestion.catalog import CatalogSnapshot

    calls = []

    def handler(request):
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/products"):
            return httpx.Response(200, json={"data": [PRODUCT]})
        if request.url.path.endswith("/variants"):
            return httpx.Response(200, json={"data": [VARIANT, {**VARIANT, "id": "v2"}]})
        if request.url.path.endswith("/attributes"):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "variant_id": request.url.params["variant_id"],
                "totals": {
                    "qty_total": 4,
                    "qty_reserved": 0,
                    "qty_available": 4,
                },
            },
        )

    engine, repo = setup(tmp_path, handler)
    snapshot = CatalogSnapshot(engine)
    first = snapshot.advance(STAMP, page_budget=4)
    assert first["yielded"] and not first["complete"]
    assert len(calls) == 4
    assert repo.read("sync_checkpoints", "synthetic-a")[-1]["pending_raw_id"] is None
    last = snapshot.advance(STAMP, page_budget=4)
    assert last["complete"] and last["pages_processed"] == 5
    assert len(calls) == 5
    assert {p["resource"] for p in last["snapshots"]} == {
        "products",
        "variants",
        "attributes",
        "inventory",
    }
    assert snapshot.advance(STAMP, page_budget=4)["complete"]
    assert len(calls) == 5  # Same-cutoff rerun does not refresh completed checkpoints.


def test_images_only_requires_existing_certified_base_before_any_source_request(tmp_path):
    from src.ingestion.catalog import CatalogSnapshot

    def forbidden(request):
        raise AssertionError("Images extension must not create a second base snapshot")

    engine, _ = setup(tmp_path, forbidden)
    with pytest.raises(Exception, match="catalog_images_base_not_certified"):
        CatalogSnapshot(engine).advance(STAMP, include_images=True, images_only=True)


def test_images_only_reuses_all_completed_child_runs_and_fetches_only_images(tmp_path):
    from src.ingestion.catalog import CatalogSnapshot

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/products"):
            return httpx.Response(200, json={"data": [PRODUCT]})
        if request.url.path.endswith("/variants"):
            return httpx.Response(200, json={"data": [VARIANT]})
        if request.url.path.endswith("/attributes"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/images"):
            return httpx.Response(200, json=[IMAGE])
        return httpx.Response(
            200,
            json={
                "variant_id": "v1",
                "totals": {"qty_total": 1, "qty_reserved": 0, "qty_available": 1},
            },
        )

    engine, repo = setup(tmp_path, handler)
    snapshot = CatalogSnapshot(engine)
    assert snapshot.advance(STAMP)["complete"]
    before = repo.read("sync_checkpoints", "synthetic-a")
    calls.clear()
    assert snapshot.advance(STAMP, include_images=True, images_only=True)["complete"]
    assert len(calls) == 1 and calls[0].endswith("/images")
    after = [c for c in repo.read("sync_checkpoints", "synthetic-a") if c["resource"] != "images"]
    assert after == before
