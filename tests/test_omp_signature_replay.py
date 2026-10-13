from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_signature_replay_in_real_js_runtime():
    result = subprocess.run(
        [shutil.which("node"), "--test", "tests/omp-signature-replay.test.mjs"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
