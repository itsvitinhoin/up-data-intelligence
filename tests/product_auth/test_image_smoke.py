"""Run the same credential-free composition check used inside the built image."""

import subprocess
import sys


def test_product_image_composes_both_services_without_credentials() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from src.product_auth.image_smoke import check; check()"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
