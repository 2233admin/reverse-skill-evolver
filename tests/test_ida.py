from pathlib import Path
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from reverse_skill import ida
from reverse_skill.errors import EnvironmentUnavailable, McpTransportError
from reverse_skill.ida import find_latest_ida, format_version, parse_version


def _fake_ida(parent: Path, name: str) -> Path:
    install = parent / name
    install.mkdir()
    (install / "ida.exe").touch()
    (install / "idalib.dll").touch()
    return install


def test_parse_and_format_version() -> None:
    assert parse_version("IDA Professional 9.4.260714.951") == (9, 4, 260714, 951)
    assert parse_version("not a version") == (0, 0, 0, 0)
    assert format_version((9, 4, 0, 0)) == "9.4"


def test_find_latest_ida_uses_highest_valid_candidate(tmp_path: Path) -> None:
    ida_92 = _fake_ida(tmp_path, "IDA Professional 9.2")
    ida_94 = _fake_ida(tmp_path, "IDA Professional 9.4")
    invalid = tmp_path / "IDA Professional 9.9"
    invalid.mkdir()
    (invalid / "ida.exe").touch()

    latest = find_latest_ida([ida_92, invalid, ida_94], only_candidates=True)

    assert latest is not None
    assert Path(latest.install_dir) == ida_94.resolve()
    assert latest.version == "9.4"
    assert latest.public()["installDir"] == str(ida_94.resolve())
    assert "version_key" not in latest.public()


def test_find_latest_ida_returns_none_without_idalib(tmp_path: Path) -> None:
    invalid = tmp_path / "IDA Professional 10.0"
    invalid.mkdir()
    (invalid / "ida.exe").touch()

    assert find_latest_ida([invalid], only_candidates=True) is None


def _start_options(tmp_path, monkeypatch):
    install = _fake_ida(tmp_path, "IDA Professional 9.4")
    server = tmp_path / "idalib-mcp.exe"
    server.touch()
    original_log = ida.tempfile.NamedTemporaryFile
    monkeypatch.setattr(ida.tempfile, "NamedTemporaryFile", lambda **kw: original_log(dir=tmp_path, **kw))
    return {"ida_dir": str(install), "server_path": str(server), "port": 14441}


def test_start_reuses_healthy_service_even_with_replace(tmp_path, monkeypatch):
    options = _start_options(tmp_path, monkeypatch)
    monkeypatch.setattr(ida.subprocess, "run", lambda *a, **kw: pytest.fail("must not clean up"))
    monkeypatch.setattr(ida.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not launch"))
    result = ida.start_server(probe=lambda *a: 8, replace_stale=True, **options)
    assert result["server"]["reused"] is True


def test_replace_checks_only_target_port_and_preserves_unknown_owner(tmp_path, monkeypatch):
    options = _start_options(tmp_path, monkeypatch)
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1, stderr="port owner PID 77 does not match", stdout="")
    monkeypatch.setattr(ida.subprocess, "run", run)
    monkeypatch.setattr(ida.subprocess, "Popen", lambda *a, **kw: pytest.fail("must preserve unknown owner"))
    if os.name != "nt":
        pytest.skip("Windows ownership inspection")
    with pytest.raises(EnvironmentUnavailable, match="OwningProcess"):
        ida.start_server(probe=lambda *a: 0, replace_stale=True, **options)
    command, kwargs = calls[0]
    assert kwargs["env"]["REVERSE_SKILL_PORT"] == "14441"
    assert kwargs["env"]["REVERSE_SKILL_SERVER"] == options["server_path"]
    assert "ExecutablePath" in command[-1] and "$process.Kill()" in command[-1]
    assert "taskkill" not in command[-1] and "/IM" not in command[-1]
    assert kwargs["timeout"] == 10


@pytest.mark.parametrize("failure", [OSError("PowerShell unavailable"), subprocess.TimeoutExpired("powershell", 10)])
def test_replace_inspection_failure_is_bounded_and_actionable(monkeypatch, failure):
    if os.name != "nt":
        pytest.skip("Windows ownership inspection")
    def fail(*a, **kw):
        raise failure
    monkeypatch.setattr(ida.subprocess, "run", fail)
    with pytest.raises(EnvironmentUnavailable, match="port 14441.*preserved"):
        ida._terminate_stale_server(14441, sys.executable)


def test_start_reports_real_child_exit_and_stderr(tmp_path, monkeypatch):
    options = _start_options(tmp_path, monkeypatch)
    original_popen = subprocess.Popen
    def launch(command, **kwargs):
        return original_popen([sys.executable, "-c", "import sys; print('startup broken', file=sys.stderr); sys.exit(17)"], **kwargs)
    monkeypatch.setattr(ida.subprocess, "Popen", launch)
    with pytest.raises(McpTransportError, match="exited before becoming ready.*exitCode=17.*startup broken"):
        ida.start_server(probe=lambda *a: 0, wait_seconds=3, **options)
    assert "startup broken" in next(tmp_path.glob("*.log")).read_text()


def test_start_timeout_retains_log_and_pid_with_wall_clock_bound(tmp_path, monkeypatch):
    options = _start_options(tmp_path, monkeypatch)
    original_popen = subprocess.Popen
    children = []
    def launch(command, **kwargs):
        child = original_popen([sys.executable, "-u", "-c", "import time; print('waiting'); time.sleep(30)"], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(ida.subprocess, "Popen", launch)
    started = time.monotonic()
    try:
        with pytest.raises(McpTransportError, match=r"within 0.5 seconds; PID=\d+, exitCode=None, log="):
            ida.start_server(probe=lambda *a: 0, wait_seconds=0.5, **options)
        assert time.monotonic() - started < 2
        assert children[0].poll() is None
        assert "waiting" in next(tmp_path.glob("*.log")).read_text()
    finally:
        for child in children:
            child.terminate()
            child.wait(timeout=3)


def test_start_success_returns_log_and_pid(tmp_path, monkeypatch):
    options = _start_options(tmp_path, monkeypatch)
    monkeypatch.setattr(ida.subprocess, "Popen", lambda *a, **kw: SimpleNamespace(pid=123, poll=lambda: None))
    counts = iter([0, 4])
    result = ida.start_server(probe=lambda *a: next(counts), **options)
    assert result["server"]["pid"] == 123
    assert Path(result["server"]["logPath"]).is_file()


@pytest.mark.skipif(os.name != "nt", reason="Windows ownership inspection")
def test_replace_real_isolated_listeners_preserves_other_port_and_unknown_owner(tmp_path):
    code = "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(60)"
    children = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(2)]
    try:
        ports = [int(child.stdout.readline()) for child in children]
        with pytest.raises(EnvironmentUnavailable, match="does not match"):
            ida._terminate_stale_server(ports[0], str(tmp_path / "unknown.exe"))
        assert all(child.poll() is None for child in children)
        ida._terminate_stale_server(ports[0], sys.executable)
        children[0].wait(timeout=3)
        assert children[1].poll() is None
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
