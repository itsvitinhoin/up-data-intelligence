"""Only numeric timing categories reach the browser; no metadata descriptions."""

from src.product_auth.http import response


def test_response_timings_allowlist_and_serialization():
    received = []
    result = response(
        lambda status, headers: received.append((status, dict(headers))),
        200,
        {"data": None},
        timings={"auth": 1, "bq": 2, "api_total": 4, "tenant": 99, "secret": 99},
    )
    assert result == [b'{"data":null}']
    headers = received[0][1]
    assert headers["Cache-Control"] == "private, no-store"
    timing = headers["Server-Timing"]
    assert "serialization;dur=" in timing and "api_total;dur=4" in timing
    assert "secret" not in timing and "tenant" not in timing
