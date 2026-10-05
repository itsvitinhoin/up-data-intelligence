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
