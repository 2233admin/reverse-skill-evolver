import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_real_stdio_bridge_against_isolated_backends():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [shutil.which("node"), "--test", "burp-mcp-full/tests/mcp-bridge.test.js"],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
