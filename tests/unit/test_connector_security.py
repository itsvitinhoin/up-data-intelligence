import json

import httpx
import pytest

from src.connectors.upzero.client import UpZeroConnector
from src.domain.models import SafeError
from src.security.sanitization import REDACTED, sanitize


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "password_hash",
        "api_key",
        "X-API-Key",
        "secret",
        "access_token",
        "refreshToken",
        "recovery_token",
        "authorization",
        "client_secret",
        "private_key",
    ],
)
def test_recursive_secrets(key):
    clean = sanitize(
        {"nested": [{key: "DO_NOT_KEEP", "cnpj": "00000000000100", "fbp": "tracking"}]}
    )
    assert "DO_NOT_KEEP" not in json.dumps(clean)
    assert clean["nested"][0]["cnpj"] == "00000000000100"
    assert clean["nested"][0]["fbp"] == "tracking"


def test_urls_and_known_secret():
    assert (
        sanitize("https://shop.test/?campaign_id=00001&fbclid=x")
        == "https://shop.test/?campaign_id=00001&fbclid=x"
    )
    assert "leak" not in sanitize("https://u:leak@shop.test/?access_token=leak&campaign_id=001")
    assert sanitize({"x": "key-value"}, ("key-value",))["x"] == REDACTED


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retries_auth_and_redaction(status, caplog):
    calls, sleeps = [], []

    def handler(req):
        calls.append(req)
        assert req.method == "GET"
        assert req.headers["X-API-Key"] == "SYNTHETIC_SECRET"
        return httpx.Response(
            status if len(calls) == 1 else 200, headers={"Retry-After": "2"}, json={"data": []}
        )

    c = UpZeroConnector("SYNTHETIC_SECRET", httpx.MockTransport(handler), sleep=sleeps.append)
    with caplog.at_level("INFO"):
        assert len(list(c.pages("customers", {}))) == 1
    assert c.retries == 1 and sleeps[0] >= 2
    assert "SYNTHETIC_SECRET" not in caplog.text


def test_timeout_safe_error():
    def handler(req):
        raise httpx.ReadTimeout("SECRET and PII", request=req)

    c = UpZeroConnector("fake", httpx.MockTransport(handler), attempts=2, sleep=lambda _: None)
    with pytest.raises(SafeError, match="retry_exhausted") as e:
        list(c.pages("customers", {}))
    assert "SECRET" not in str(e.value)


def test_customer_descending_and_empty_end():
    seen = []

    def handler(req):
        seen.append(req.url.params.get("after_id"))
        return httpx.Response(
            200, json={"data": [{"id": "9"}, {"id": "8"}] if len(seen) == 1 else []}
        )

    c = UpZeroConnector("fake", httpx.MockTransport(handler))
    assert len(list(c.pages("customers", {}))) == 2
    assert seen == [None, "8"]


def test_orders_pagination():
    def handler(req):
        page = int(req.url.params["page"])
        return httpx.Response(200, json={"data": [{"id": page}], "page": page, "total_pages": 2})

    c = UpZeroConnector("fake", httpx.MockTransport(handler))
    assert len(list(c.pages("orders", {}))) == 2


def test_cursor_loop_preserves_page_before_error():
    c = UpZeroConnector(
        "fake",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [], "next_cursor": "same"})
        ),
    )
    pages = c.pages("analytics_facts", {"from": "a", "to": "b"})
    assert next(pages).pagination_error is None
    assert next(pages).pagination_error == "cursor_repeated"
    with pytest.raises(SafeError, match="cursor_repeated"):
        next(pages)


def test_after_id_no_progress():
    c = UpZeroConnector(
        "fake", httpx.MockTransport(lambda _: httpx.Response(200, json={"data": [{"id": "5"}]}))
    )
    pages = c.pages("customers", {}, {"after_id": 5})
    assert next(pages).pagination_error == "after_id_no_progress"


@pytest.mark.parametrize("status", [301, 400, 401, 403])
def test_no_retry_rejected(status):
    c = UpZeroConnector(
        "fake",
        httpx.MockTransport(lambda _: httpx.Response(status, text="SECRET")),
        sleep=lambda _: pytest.fail(),
    )
    with pytest.raises(SafeError, match="http_rejected"):
        list(c.pages("customers", {}))


@pytest.mark.parametrize(
    "body",
    [
        b'{"data":[],"data":[]}',
        b'{"data":NaN}',
        b'{"secret":"DO_NOT_LEAK"}',
        b"not json DO_NOT_LEAK",
    ],
)
def test_invalid_response_never_leaks(body):
    c = UpZeroConnector("fake", httpx.MockTransport(lambda _: httpx.Response(200, content=body)))
    with pytest.raises(SafeError, match="invalid_response") as e:
        list(c.pages("customers", {}))
    assert "DO_NOT_LEAK" not in str(e.value)


def test_long_retry_after_defers_instead_of_early_retry():
    c = UpZeroConnector(
        "fake",
        httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "3600"})),
        sleep=lambda _: pytest.fail(),
    )
    with pytest.raises(SafeError, match="retry_after_deferred"):
        list(c.pages("customers", {}))


def test_http_date_retry_after():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    attempts = []
    delays = []

    def handler(_):
        attempts.append(1)
        return httpx.Response(
            429 if len(attempts) == 1 else 200,
            headers={"Retry-After": format_datetime(datetime.now(UTC) + timedelta(seconds=5))},
            json={"data": []},
        )

    c = UpZeroConnector("fake", httpx.MockTransport(handler), sleep=delays.append)
    list(c.pages("customers", {}))
    assert delays[0] >= 3


@pytest.mark.parametrize(
    "resource,filters",
    [
        ("unsupported_catalog", {}),
        ("orders", {"authorization": "SECRET"}),
        ("analytics_facts", {"from": "a"}),
        ("customers", {"limit": 201}),
    ],
)
def test_connector_rejects_out_of_scope(resource, filters):
    c = UpZeroConnector("fake", httpx.MockTransport(lambda _: pytest.fail()))
    with pytest.raises(SafeError):
        list(c.pages(resource, filters))


def test_embedded_json_sanitized():
    v = sanitize({"meta": '{"password_hash":"DO_NOT_LEAK","cnpj":"00000000000100"}'})
    assert "DO_NOT_LEAK" not in v["meta"] and "00000000000100" in v["meta"]
