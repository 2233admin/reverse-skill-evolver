from pathlib import Path
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import socket
import time
from types import SimpleNamespace

import pytest

from reverse_skill import ida, mcp
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
    assert "ExecutablePath" in command[-1] and "$listener.Process.Kill()" in command[-1]
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


def _inert_console_launcher(directory, interpreter=sys.executable):
    from pip._vendor.distlib.scripts import ScriptMaker

    directory.mkdir()
    maker = ScriptMaker(None, str(directory))
    maker.executable = interpreter
    filenames = []
    source = b"""import json, os, socket, sys
from pathlib import Path
s = socket.socket()
s.bind(('127.0.0.1', int(os.environ['OWNED_LISTEN_PORT'])))
s.listen()
Path(os.environ['OWNED_READY_FILE']).write_text(json.dumps({
    'pid': os.getpid(), 'parent_pid': os.getppid(), 'port': s.getsockname()[1]
}))
sys.stdin.read()
s.close()
"""
    maker._write_script({'idalib-mcp'}, maker._get_shebang('utf-8'), source, filenames, 'py')
    return Path(filenames[0])


@contextmanager
def _owned_launcher_listener(tmp_path, launcher, *, direct_python=False, host='127.0.0.1', wrong_port=False):
    import _winapi

    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    marker = tmp_path / 'listener-ready.json'
    env = dict(os.environ, OWNED_LISTEN_PORT=str(port), OWNED_READY_FILE=str(marker))
    command = ([sys.executable] if direct_python else []) + [
        str(launcher), '--host', host, '--port', str(port + 1 if wrong_port else port)
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, env=env)
    listener_handle = None
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), 'owned inert launcher did not become ready'
        info = json.loads(marker.read_text())
        listener_handle = _winapi.OpenProcess(_winapi.PROCESS_ALL_ACCESS, False, info['pid'])
        yield process, info
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if listener_handle is not None:
                _winapi.TerminateProcess(listener_handle, 1)
            process.terminate()
            process.wait(timeout=3)
        if listener_handle is not None:
            _winapi.CloseHandle(listener_handle)
        process.stderr.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows console-script launcher ownership')
@pytest.mark.parametrize('interpreter_kind', ['current', 'venv'])
def test_replace_real_distlib_launcher_preserves_other_launcher(tmp_path, interpreter_kind):
    interpreter = sys.executable
    if interpreter_kind == 'venv':
        import venv
        venv.EnvBuilder(with_pip=False).create(tmp_path / 'owned venv')
        interpreter = str(tmp_path / 'owned venv/Scripts/python.exe')
    selected = _inert_console_launcher(tmp_path / 'selected scripts', interpreter)
    companion = _inert_console_launcher(tmp_path / 'other scripts')
    primary_dir, companion_dir = tmp_path / 'primary', tmp_path / 'companion'
    primary_dir.mkdir()
    companion_dir.mkdir()
    with _owned_launcher_listener(primary_dir, selected) as (primary, info):
        with _owned_launcher_listener(companion_dir, companion) as (other, other_info):
            assert primary.pid != info['pid']
            if interpreter_kind == 'current':
                assert info['parent_pid'] == primary.pid
            assert other.pid != other_info['pid'] and info['port'] != other_info['port']
            ida._terminate_stale_server(info['port'], str(selected))
            primary.wait(timeout=5)
            assert other.poll() is None
            with socket.create_connection(('127.0.0.1', other_info['port']), timeout=1):
                pass


@pytest.mark.skipif(os.name != 'nt', reason='Windows console-script launcher ownership')
@pytest.mark.parametrize('mismatch', ['launcher', 'port', 'host', 'parent'])
def test_replace_distlib_listener_rejects_unrelated_identity(tmp_path, mismatch):
    selected = _inert_console_launcher(tmp_path / 'selected scripts')
    running = _inert_console_launcher(tmp_path / 'other scripts') if mismatch == 'launcher' else selected
    with _owned_launcher_listener(tmp_path, running, direct_python=mismatch == 'parent',
                                 host='0.0.0.0' if mismatch == 'host' else '127.0.0.1',
                                 wrong_port=mismatch == 'port') as (process, info):
        with pytest.raises(EnvironmentUnavailable, match='no process was stopped'):
            ida._terminate_stale_server(info['port'], str(selected))
        assert process.poll() is None
        with socket.create_connection(('127.0.0.1', info['port']), timeout=1):
            pass


@contextmanager
def _delayed_mcp_server(delay, *, legacy=False):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    methods = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            method = message['method']
            methods.append(method)
            time.sleep(delay)
            response = {'jsonrpc': '2.0', 'id': message.get('id')}
            if method == 'server/discover':
                if legacy:
                    response['error'] = {'code': -32601, 'message': 'legacy only'}
                else:
                    response['result'] = {'resultType': 'complete', 'supportedVersions': [mcp.MODERN_VERSION],
                                          'capabilities': {}}
            elif method == 'initialize':
                response['result'] = {'protocolVersion': '2025-11-25', 'capabilities': {}}
            elif method == 'tools/list':
                response['result'] = {'tools': [{'name': 'owned-tool', 'inputSchema': {'type': 'object'}}]}
            else:
                response['result'] = {}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            if method == 'initialize':
                self.send_header('Mcp-Session-Id', 'owned-session')
            self.end_headers()
            try:
                self.wfile.write(json.dumps(response).encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_DELETE(self):
            methods.append('DELETE')
            time.sleep(delay)
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield server.server_port, methods
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize('legacy', [False, True])
def test_real_multirequest_probe_shares_deadline(monkeypatch, legacy):
    # Prepare the real HTTP client before timing to isolate the serial request budget.
    http = mcp.httpx.Client(timeout=0.4, trust_env=False)
    monkeypatch.setattr(mcp.httpx, 'Client', lambda **_: http)
    with _delayed_mcp_server(0.15 if legacy else 0.3, legacy=legacy) as (port, methods):
        started = time.monotonic()
        assert mcp.probe_tool_count(port, 0.4) == -1
        assert time.monotonic() - started < 0.6
        assert methods[:2] == ['server/discover', 'initialize' if legacy else 'tools/list']
        assert 'DELETE' not in methods
    assert http.is_closed


@pytest.mark.parametrize('expires', [False, True])
def test_start_real_multirequest_probe_checks_deadline(tmp_path, monkeypatch, expires):
    options = _start_options(tmp_path, monkeypatch)
    process = SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(ida.subprocess, 'Popen', lambda *a, **kw: process)
    http = mcp.httpx.Client(timeout=0.4, trust_env=False)
    monkeypatch.setattr(mcp.httpx, 'Client', lambda **_: http)
    calls = 0

    def probe(port, timeout):
        nonlocal calls
        calls += 1
        return 0 if calls == 1 else mcp.probe_tool_count(port, timeout)

    with _delayed_mcp_server(0.3 if expires else 0.025) as (port, methods):
        options['port'] = port
        started = time.monotonic()
        if expires:
            with pytest.raises(McpTransportError, match='did not become ready within 0.4 seconds.*PID=123'):
                ida.start_server(probe=probe, wait_seconds=0.4, **options)
            assert time.monotonic() - started < 0.6
        else:
            result = ida.start_server(probe=probe, wait_seconds=0.4, **options)
            assert result['server']['toolCount'] == 1 and result['server']['pid'] == 123
        assert methods == ['server/discover', 'tools/list']
    assert http.is_closed


def test_start_does_not_accept_probe_success_after_deadline(tmp_path, monkeypatch):
    options = _start_options(tmp_path, monkeypatch)
    monkeypatch.setattr(ida.subprocess, 'Popen', lambda *a, **kw: SimpleNamespace(pid=123, poll=lambda: None))
    calls = 0

    def late_probe(*_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 0
        time.sleep(0.2)
        return 1

    with pytest.raises(McpTransportError, match='did not become ready within 0.1 seconds'):
        ida.start_server(probe=late_probe, wait_seconds=0.1, **options)
