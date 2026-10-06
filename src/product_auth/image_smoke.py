"""Offline image acceptance: compose both APIs without credentials or network IO."""

import io
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch


def check_unauthenticated(app: Any, path: str, kind: str) -> None:
    statuses: list[str] = []
    headers: list[tuple[str, str]] = []

    def start(status: str, values: list[tuple[str, str]]) -> None:
        statuses.append(status)
        headers.extend(values)

    body = b"".join(
        app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": path, "wsgi.input": io.BytesIO()},
            start,
        )
    )
    assert statuses == ["401 Unauthorized"], kind + "_authentication_guard_failed"
    assert json.loads(body)["error"]["code"] == "unauthenticated"
    assert ("Cache-Control", "private, no-store") in headers


def check() -> None:
    root = Path(__file__).resolve().parents[2]
    for directory in (root / "src", root / "sql"):
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sql"}:
                path.read_bytes()

    from src.product_auth.runtime import compose

    with (
        patch.dict(
            os.environ,
            {
                "UP_PRODUCT_PROJECT": "up-data-intelligence-dev",
                "UP_PRODUCT_LOCATION": "southamerica-east1",
            },
        ),
        patch("google.cloud.bigquery.Client") as client,
    ):
        for kind, route in (("read", "/v1/session"), ("admin", "/v1/admin/onboarding")):
            app = compose(kind)
            check_unauthenticated(app, route, kind)
            client.return_value.query.assert_not_called()


if __name__ == "__main__":
    assert os.getuid() == 10001 and os.getgid() == 10001, "nonroot_runtime_required"
    root = Path(__file__).resolve().parents[2]
    for directory in (root / "src", root / "sql"):
        for path in (directory, *directory.rglob("*")):
            assert path.stat().st_uid == 0, "root_owned_application_required"
            assert not os.access(path, os.W_OK), "runtime_application_write_forbidden"
    check()
    print("PRODUCT_IMAGE_SMOKE_PASS read=401 admin=401 network=disabled nonroot=10001")
