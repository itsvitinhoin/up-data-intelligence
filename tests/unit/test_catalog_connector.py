import httpx
import pytest

from src.connectors.upzero.client import UpZeroConnector
from src.domain.models import SafeError


def test_catalog_cursor_and_decimal_transport():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.params.get("cursor"):
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(
            200, content=b'{"data":[{"id":"v-1","price":123.45}],"next_cursor":"opaque"}'
        )

    with_connector = UpZeroConnector("synthetic", httpx.MockTransport(handler))
    pages = list(with_connector.pages("variants", {"limit": 1}))
    assert pages[0].payload["data"][0]["price"] == "123.45"
    assert len(calls) == 2
    assert calls[1].url.params["cursor"] == "opaque"
    assert all(c.url.path == "/external/v1/variants" for c in calls)
    assert all(c.headers["X-API-Key"] == "synthetic" for c in calls)


def test_attributes_array_is_captured_as_raw_envelope():
    def handler(request):
        assert request.url.path == "/external/v1/attributes"
        assert not request.url.params
        return httpx.Response(200, json=[{"id": "color", "code": "color", "terms": []}])

    c = UpZeroConnector("synthetic", httpx.MockTransport(handler))
    pages = list(c.pages("attributes", {}))
    assert len(pages) == 1 and pages[0].next_position is None
    assert pages[0].payload["data"][0]["code"] == "color"


def test_inventory_single_variant_decimal_and_identity():
    def handler(request):
        assert dict(request.url.params) == {"variant_id": "v-1"}
        return httpx.Response(200, content=b'{"variant_id":"v-1","totals":{"qty_available":12.25}}')

    c = UpZeroConnector("synthetic", httpx.MockTransport(handler))
    page = next(c.pages("inventory", {"variant_id": "v-1"}))
    assert page.next_position is None
    assert page.payload["data"][0]["id"] == "v-1"
    assert page.payload["data"][0]["totals"]["qty_available"] == "12.25"
    with pytest.raises(SafeError, match="inventory_variant_required"):
        next(c.pages("inventory", {}))
    c = UpZeroConnector(
        "synthetic",
        httpx.MockTransport(lambda _: httpx.Response(200, json={"variant_id": "other"})),
    )
    with pytest.raises(SafeError, match="inventory_variant_mismatch"):
        next(c.pages("inventory", {"variant_id": "v-1"}))


def test_catalog_duplicate_keys_and_repeated_cursor_fail_closed():
    c = UpZeroConnector(
        "synthetic",
        httpx.MockTransport(lambda _: httpx.Response(200, content=b'{"data":[],"data":[]}')),
    )
    with pytest.raises(SafeError, match="invalid_response"):
        next(c.pages("products", {}))
    c = UpZeroConnector(
        "synthetic",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [], "next_cursor": "same"})
        ),
    )
    it = c.pages("products", {})
    assert next(it).next_position == {"cursor": "same"}
    assert next(it).pagination_error == "cursor_repeated"
    with pytest.raises(SafeError, match="cursor_repeated"):
        next(it)
