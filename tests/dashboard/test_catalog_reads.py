"""Current labels require a complete membership-certified snapshot; no live IO."""

import json
from copy import deepcopy
from decimal import Decimal

import pytest

from src.dashboard.catalog import CatalogReader
from src.dashboard.contracts import ReadError
from src.dashboard.queries import Query
from src.utils.data import digest

STORE = "synthetic-store"
CONNECTION = "synthetic-connection"
CUTOFF = "2026-10-05T03:00:00Z"


def evidence():
    rows = []
    for resource in ("products", "variants", "attributes", "inventory"):
        filters = {"catalog_as_of": CUTOFF}
        key = digest([STORE, CONNECTION, resource, filters, "incremental"])
        cp = {
            "store_id": STORE,
            "connection_id": CONNECTION,
            "resource": resource,
            "filters": filters,
            "mode": "incremental",
            "plan_key": key,
            "run_id": resource + "-run",
            "status": "complete",
            "pending_raw_id": None,
        }
        run = {
            "store_id": STORE,
            "source": "upzero",
            "resource": resource,
            "mode": "incremental",
            "plan_key": key,
            "run_id": cp["run_id"],
            "status": "completed",
            "core_records_failed": 0,
            "source_records_read": 1,
            "finished_at": "2026-10-05T03:10:00Z",
        }
        rows.append(
            {
                "catalog_as_of": CUTOFF,
                "checkpoint": json.dumps(cp),
                "run": json.dumps(run),
                "observations": 1,
                "distinct_entities": 1,
                "valid_version_links": 1,
            }
        )
    return rows


class FakeReader:
    def __init__(self):
        self.calls: list[Query] = []
        self.proofs = evidence()
        self.variants = [
            {
                "store_id": STORE,
                "variant_id": "variant-explicit",
                "product_id": "product-explicit",
                "name": "Fonte",
                "sku": "SKU",
                "reference": "REF",
                "color": "Azul",
                "size": "M",
                "color_code": "blue",
                "color_terms": [[{"code": "blue", "rgb": "123abc"}]],
                "stock": Decimal("12.25"),
                "price": Decimal("42.10"),
                "active": True,
            }
        ]

    def query(self, query: Query, **kwargs):
        self.calls.append(query)
        assert kwargs["store_id"] == STORE
        assert kwargs["generation"] is None  # This current snapshot is separate from Analytics.
        if query.name == "catalog_source":
            return [{"store_id": STORE, "connection_id": CONNECTION}]
        if query.name == "catalog_snapshot_proof":
            return self.proofs
        if query.name == "catalog_variant_projection":
            return self.variants
        raise AssertionError(query.name)


def reader(fake):
    return CatalogReader("synthetic-project", fake, STORE, None, "request")


def test_explicit_identity_membership_money_and_current_basis():
    fake = FakeReader()
    projected = reader(fake).variants(["variant-explicit"])["variant-explicit"]
    assert projected["stock"] == "12.25" and projected["sale_price"] == "42.10"
    assert projected["product_id"] == "product-explicit" and projected["color_hex"] == "#123abc"
    assert projected["catalog"]["basis"] == "current_source_snapshot"
    assert projected["catalog"]["snapshot_as_of"] == "2026-10-05T03:00:00+00:00"
    for call in fake.calls:
        assert STORE not in call.sql and "variant-explicit" not in call.sql
        assert call.parameters["store"] == ("STRING", STORE)
    sql = fake.calls[-1].sql
    assert "v.variant_id IN" in sql and "p.product_id=v.product_id" in sql
    assert "LIKE" not in sql and "LOWER" not in sql


def test_missing_snapshot_returns_unknown_without_guessing_sku():
    fake = FakeReader()
    fake.proofs = []
    assert reader(fake).variants(["variant-explicit"]) == {}
    assert [q.name for q in fake.calls] == ["catalog_source", "catalog_snapshot_proof"]


@pytest.mark.parametrize(
    "case",
    [
        "missing-resource",
        "duplicate",
        "foreign",
        "raw",
        "run",
        "failed",
        "membership",
        "link",
        "cutoff",
    ],
)
def test_partial_or_ambiguous_catalog_fails_closed(case):
    fake = FakeReader()
    row = fake.proofs[0]
    cp, run = json.loads(row["checkpoint"]), json.loads(row["run"])
    if case == "missing-resource":
        fake.proofs.pop()
    if case == "duplicate":
        fake.proofs[1] = deepcopy(row)
    if case == "foreign":
        cp["store_id"] = "foreign"
    if case == "raw":
        cp["pending_raw_id"] = "raw"
    if case == "run":
        run["run_id"] = "foreign"
    if case == "failed":
        run["core_records_failed"] = 1
    if case == "membership":
        row["distinct_entities"] = 0
    if case == "link":
        row["valid_version_links"] = 0
    if case == "cutoff":
        row["catalog_as_of"] = "2026-10-04T03:00:00Z"
    row.update(checkpoint=json.dumps(cp), run=json.dumps(run))
    with pytest.raises(ReadError):
        reader(fake).variants(["variant-explicit"])
    assert not any(q.name == "catalog_variant_projection" for q in fake.calls)


@pytest.mark.parametrize("case", ["duplicate", "foreign", "unrequested"])
def test_variant_identity_fail_closed(case):
    fake = FakeReader()
    if case == "duplicate":
        fake.variants *= 2
    if case == "foreign":
        fake.variants[0]["store_id"] = "foreign"
    if case == "unrequested":
        fake.variants[0]["variant_id"] = "unrequested"
    with pytest.raises(ReadError, match="catalog_variant_identity_ambiguous"):
        reader(fake).variants(["variant-explicit"])


def test_no_ids_does_not_query_and_bounded_batch_is_enforced():
    fake = FakeReader()
    assert reader(fake).variants([]) == {} and not fake.calls
    with pytest.raises(ReadError, match="catalog_variant_limit"):
        reader(fake).variants([str(i) for i in range(1001)])
    assert not fake.calls


def test_unknown_stock_and_ambiguous_color_are_null():
    fake = FakeReader()
    fake.variants[0]["stock"] = None
    fake.variants[0]["color_terms"] *= 2
    row = reader(fake).variants(["variant-explicit"])["variant-explicit"]
    assert row["stock"] is None and row["color_hex"] is None


def test_family_uses_canonical_parent_and_reuses_pinned_membership():
    fake = FakeReader()
    catalog = reader(fake)
    first = catalog.variants(["variant-explicit"])
    family = catalog.family(first["variant-explicit"]["product_id"])
    assert set(family) == {"variant-explicit"}
    assert sum(q.name == "catalog_snapshot_proof" for q in fake.calls) == 1
    query = fake.calls[-1]
    assert query.parameters["product"] == ("STRING", "product-explicit")
    assert "product-explicit" not in query.sql
    fake.variants[0]["product_id"] = "foreign-parent"
    with pytest.raises(ReadError, match="catalog_variant_identity_ambiguous"):
        catalog.family("product-explicit")


def test_portuguese_codes_resolve_from_certified_stored_attributes_without_reingestion():
    fake = FakeReader()
    row = fake.variants[0]
    row.update(
        color=None,
        color_code=None,
        size=None,
        size_code=None,
        attributes=json.dumps(
            [
                {"attribute": {"code": "cor"}, "term": {"name": "Azul", "code": "blue"}},
                {"attribute": {"code": "tamanho"}, "term": {"name": "M", "code": "medium"}},
            ]
        ),
    )
    value = reader(fake).variants(["variant-explicit"])["variant-explicit"]
    assert value["color"] == "Azul" and value["size"] == "M"
    assert value["color_hex"] == "#123abc" and value["stock"] == "12.25"
    assert value["catalog"]["basis"] == "current_source_snapshot"
    assert "v.attributes" in fake.calls[-1].sql
    assert "a.code IN ('color','cor')" in fake.calls[-1].sql
    assert len(fake.calls) == 3  # Same read-only proof/projection calls; no source replay.


@pytest.mark.parametrize("case", ["duplicate-alias", "conflict", "malformed"])
def test_explicit_attribute_aliases_fail_closed_on_ambiguity(case):
    fake = FakeReader()
    attributes = [{"attribute": {"code": "cor"}, "term": {"name": "Azul", "code": "blue"}}]
    if case == "duplicate-alias":
        attributes.append({"attribute": {"code": "color"}, "term": {"name": "Azul"}})
    if case == "conflict":
        attributes[0]["term"]["name"] = "Vermelho"
    fake.variants[0]["attributes"] = {} if case == "malformed" else attributes
    with pytest.raises(ReadError, match="catalog_attribute_evidence_invalid"):
        reader(fake).variants(["variant-explicit"])


def test_unknown_source_attribute_code_does_not_infer_from_name_or_sku():
    fake = FakeReader()
    fake.variants[0].update(
        color=None,
        size=None,
        color_code=None,
        attributes=[{"attribute": {"code": "custom", "name": "Cor"}, "term": {"name": "Azul"}}],
        sku="AZUL-M",
    )
    row = reader(fake).variants(["variant-explicit"])["variant-explicit"]
    assert row["color"] is None and row["size"] is None and row["color_hex"] is None
