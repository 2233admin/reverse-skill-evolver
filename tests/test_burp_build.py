import os
import shutil
import subprocess
from pathlib import Path

import pytest


BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "burp-mcp-full" / "build.sh"
BASH = shutil.which("bash")
if os.name == "nt":
    git = shutil.which("git")
    git_bash = Path(git).parent.parent / "bin/bash.exe" if git else None
    BASH = str(git_bash) if git_bash and git_bash.is_file() else None
pytestmark = pytest.mark.skipif(BASH is None, reason="POSIX build entrypoint requires Bash")


def test_build_script_is_valid_shell_with_an_intact_shebang():
    assert BUILD_SCRIPT.read_bytes().startswith(b"#!/bin/sh\n")
    if os.name != "nt":
        assert os.access(BUILD_SCRIPT, os.X_OK)
    result = subprocess.run([BASH, "-n", BUILD_SCRIPT.as_posix()], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("elsewhere", [False, True], ids=["own-directory", "other-directory"])
@pytest.mark.parametrize("wrapper_exit", [0, 37], ids=["success", "failure"])
def test_build_script_delegates_from_any_directory_and_preserves_exit(tmp_path, elsewhere, wrapper_exit):
    project = tmp_path / "burp project"
    project.mkdir()
    script = project / "build.sh"
    shutil.copyfile(BUILD_SCRIPT, script)
    wrapper = project / "gradlew"
    wrapper.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$PWD" > wrapper-cwd.txt\n'
        'printf "%s\\0" "$@" > wrapper-args.bin\nexit "$WRAPPER_EXIT"\n',
        encoding="utf-8",
        newline="\n",
    )
    assert b"\r" not in wrapper.read_bytes()
    wrapper.chmod(0o755)
    caller = tmp_path / "caller"
    caller.mkdir()

    result = subprocess.run(
        [BASH, script.as_posix(), "--offline", "--no-daemon"],
        cwd=caller if elsewhere else project,
        env={**os.environ, "WRAPPER_EXIT": str(wrapper_exit)},
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=10,
    )

    assert result.returncode == wrapper_exit, result.stdout + result.stderr
    assert (project / "wrapper-args.bin").read_bytes().split(b"\0")[:-1] == [b"jar", b"--offline", b"--no-daemon"]
    recorded_directory = (project / "wrapper-cwd.txt").read_text().strip()
    expected_directory = subprocess.run(
        [BASH, "-c", "pwd"], cwd=project, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert recorded_directory == expected_directory
