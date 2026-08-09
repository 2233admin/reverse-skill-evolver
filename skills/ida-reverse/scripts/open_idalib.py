"""Open a binary through the local idalib-mcp HTTP API.

The legacy open.ps1 entry point delegates here.  This module deliberately uses
only the standard library so the skill can run with the machine's existing
Python installation and does not install or modify IDA components.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def rpc_call(port: int, method: str, params: dict[str, Any], timeout: float = 10.0) -> tuple[dict[str, Any] | None, str | None]:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace")), None
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return None, str(exc)


def detect_api_mode(port: int) -> tuple[str | None, str | None]:
    """Detect the current idalib-mcp tool contract instead of assuming its age."""
    response, error = rpc_call(port, "tools/list", {}, timeout=5.0)
    if error:
        return None, error
    tools = response.get("result", {}).get("tools", []) if response else []
    names = {str(item.get("name")) for item in tools if isinstance(item, dict) and item.get("name")}
    if {"idb_open", "idb_list"}.issubset(names):
        return "idb", None
    if {"idalib_open", "idalib_list"}.issubset(names):
        return "idalib", None
    return None, "unsupported_idalib_mcp_api"


def ready_session(
    port: int,
    expected_session_id: str,
    expected_path: Path,
    api_mode: str,
) -> tuple[dict[str, Any] | None, str | None]:
    list_tool = "idb_list" if api_mode == "idb" else "idalib_list"
    response, error = rpc_call(port, "tools/call", {"name": list_tool, "arguments": {}}, timeout=10.0)
    if error:
        return None, error
    if not response:
        return None, "empty_session_list_response"
    structured = response.get("result", {}).get("structuredContent", {})
    sessions = structured.get("sessions", []) if isinstance(structured, dict) else []
    expected_text = str(expected_path)
    expected_name = expected_path.name.casefold()
    for candidate in sessions if isinstance(sessions, list) else []:
        if not isinstance(candidate, dict) or candidate.get("is_analyzing") is not False:
            continue
        candidate_path = str(candidate.get("input_path", ""))
        candidate_name = Path(candidate_path).name.casefold()
        same_session = candidate.get("session_id") == expected_session_id
        same_path = candidate_path == expected_text
        same_file = candidate_name == expected_name
        if same_session or same_path or same_file:
            return candidate, None
    return None, None


def rpc_success(response: dict[str, Any] | None) -> bool:
    structured = response.get("result", {}).get("structuredContent", {}) if response else {}
    return isinstance(structured, dict) and structured.get("success") is True


def rpc_error(response: dict[str, Any] | None, error: str | None) -> str:
    if error:
        return error
    if not response:
        return "empty_response"
    structured = response.get("result", {}).get("structuredContent", {})
    if isinstance(structured, dict) and structured.get("error"):
        return str(structured["error"])
    if response.get("error"):
        return str(response["error"])
    return "idalib_open_failed"


def is_under(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([str(path), str(parent)]).casefold() == str(parent).casefold()
    except ValueError:
        return False


def stage_if_needed(path: Path, temp_dir: Path) -> tuple[Path, bool]:
    """Copy protected or locked inputs to a unique temp path, matching open.ps1."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = path.resolve()
    if is_under(resolved_path, temp_dir.resolve()):
        return resolved_path, True

    system32 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
    if is_under(resolved_path, system32.resolve()):
        target = temp_dir / resolved_path.name
        shutil.copy2(resolved_path, target)
        return target.resolve(), True

    locked = False
    for extension in (".id0", ".id1", ".id2", ".nam", ".til", ".i64"):
        database = resolved_path.with_suffix(extension)
        if not database.exists():
            continue
        try:
            database.unlink()
        except OSError:
            locked = True
        if database.exists():
            locked = True

    if locked:
        target = temp_dir / f"{uuid.uuid4().hex[:8]}-{resolved_path.name}"
        shutil.copy2(resolved_path, target)
        return target.resolve(), True
    return resolved_path, False


def open_and_poll(
    path: Path,
    session_id: str,
    auto_analysis: bool,
    port: int,
    timeout_seconds: int,
    temp_copy: bool,
    api_mode: str,
) -> tuple[bool, str | None, bool]:
    result: dict[str, Any] = {}
    finished = threading.Event()

    def request_open() -> None:
        if api_mode == "idb":
            tool_name = "idb_open"
            arguments = {
                "input_path": str(path),
                "mode": "prefer_headless",
                "run_auto_analysis": auto_analysis,
                "build_caches": auto_analysis,
                "init_hexrays": auto_analysis,
                "preferred_session_id": session_id,
            }
        else:
            tool_name = "idalib_open"
            arguments = {
                "input_path": str(path),
                "run_auto_analysis": auto_analysis,
                "session_id": session_id,
            }
        response, error = rpc_call(
            port,
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
            timeout=max(10.0, float(timeout_seconds)),
        )
        result["response"] = response
        result["error"] = error
        finished.set()

    thread = threading.Thread(target=request_open, name="idalib-open", daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout_seconds
    progress_at = time.monotonic() - 10
    last_poll_error: str | None = None

    while time.monotonic() < deadline:
        if finished.wait(timeout=1.0):
            break
        session, poll_error = ready_session(port, session_id, path, api_mode)
        if poll_error and poll_error != last_poll_error:
            print(f"INFO:session_poll:{poll_error}", flush=True)
            last_poll_error = poll_error
        if session:
            tag = " (temp copy)" if temp_copy else ""
            print(f"OK:{session.get('filename', path.name)}:{session.get('session_id', session_id)}{tag}")
            return True, None, False
        now = time.monotonic()
        if now - progress_at >= 10:
            elapsed = int(now - (deadline - timeout_seconds))
            print(f"INFO:opening:{elapsed}/{timeout_seconds}s", flush=True)
            progress_at = now

    if not finished.is_set():
        # The worker is daemonized and may complete later; make one final session check.
        session, poll_error = ready_session(port, session_id, path, api_mode)
        if poll_error and poll_error != last_poll_error:
            print(f"INFO:session_poll:{poll_error}", flush=True)
        if session:
            tag = " (temp copy)" if temp_copy else ""
            print(f"OK:{session.get('filename', path.name)}:{session.get('session_id', session_id)}{tag}")
            return True, None, False
        print(f"ERR:open_timeout_{timeout_seconds}s")
        return False, f"open_timeout_{timeout_seconds}s", False

    response = result.get("response")
    if rpc_success(response):
        structured = response["result"]["structuredContent"]
        session = structured.get("session", {})
        tag = " (temp copy)" if temp_copy else ""
        print(f"OK:{session.get('filename', path.name)}:{session.get('session_id', session_id)}{tag}")
        return True, None, False
    return False, rpc_error(response, result.get("error")), response is not None


def open_with_fallback(path: Path, session_id: str, auto_analysis: bool, port: int, timeout_seconds: int, temp_dir: Path) -> int:
    api_mode, api_error = detect_api_mode(port)
    if not api_mode:
        print(f"ERR:{api_error or 'unsupported_idalib_mcp_api'}")
        return 1
    print(f"INFO:api_mode:{api_mode}", flush=True)
    staged_path, temp_copy = stage_if_needed(path, temp_dir)
    ok, error, retryable = open_and_poll(staged_path, session_id, auto_analysis, port, timeout_seconds, temp_copy, api_mode)
    if ok:
        return 0
    if not temp_copy and retryable:
        fallback = temp_dir / f"{uuid.uuid4().hex[:8]}-{path.name}"
        shutil.copy2(path, fallback)
        retry_ok, retry_error, _ = open_and_poll(fallback.resolve(), session_id, auto_analysis, port, timeout_seconds, True, api_mode)
        if retry_ok:
            return 0
        error = retry_error or error
    print(f"ERR:{error or 'idalib_open_failed'}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a binary through idalib-mcp")
    parser.add_argument("--path", required=True)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--no-auto-analysis", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--port", type=int, default=13337)
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists() or not path.is_file():
        print("ERR:file_not_found")
        return 1
    if args.timeout_seconds <= 0:
        print("ERR:invalid_timeout")
        return 1
    session_id = args.session_id or uuid.uuid4().hex[:8]
    temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "reverse-skill"
    return open_with_fallback(path, session_id, not args.no_auto_analysis, args.port, args.timeout_seconds, temp_dir)


if __name__ == "__main__":
    raise SystemExit(main())
