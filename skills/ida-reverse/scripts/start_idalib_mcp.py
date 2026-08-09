"""Start or reuse the local idalib-mcp HTTP service on Windows.

This is the canonical implementation.  The neighbouring start.ps1 file remains
as a compatibility entry point for existing callers and delegates here.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def first_existing(values: list[str | None]) -> Path | None:
    for value in values:
        if value:
            path = Path(value)
            if path.exists():
                return path.resolve()
    return None


def resolve_ida(explicit: str | None) -> Path | None:
    return first_existing(
        [
            explicit,
            os.environ.get("IDA94_ROOT"),
            r"C:\Program Files\IDA Professional 9.4",
            r"C:\IDA Professional 9.4",
            r"C:\Program Files\IDA Pro 9.4",
        ]
    )


def resolve_server(explicit: str | None) -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    app_data = os.environ.get("APPDATA", "")
    candidates = [
        explicit,
        shutil.which("idalib-mcp"),
        str(Path(local_app_data) / "Programs" / "Python" / "Python313" / "Scripts" / "idalib-mcp.exe"),
    ]
    roaming_python = Path(app_data) / "Python"
    if roaming_python.exists():
        for version_dir in sorted(roaming_python.iterdir(), reverse=True):
            candidates.append(str(version_dir / "Scripts" / "idalib-mcp.exe"))
    return first_existing(candidates)


def service_online(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def listening_pids(port: int) -> list[int]:
    """Find PIDs listening on the requested TCP port."""
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].casefold() != "tcp":
            continue
        local_address = fields[1]
        state = fields[3].casefold()
        if not local_address.endswith(f":{port}") or state != "listening":
            continue
        try:
            pids.append(int(fields[4]))
        except ValueError:
            continue
    return sorted(set(pids))


def process_image_name(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) >= 1 and row[0] and row[0].casefold() != "info:":
            return row[0]
    return None


def force_stop(server_path: Path, port: int) -> bool:
    """Stop only the verified server process bound to the requested port."""
    image_names = {server_path.name.casefold(), "idalib-mcp.exe", "ida-pro-mcp.exe"}
    candidates = [pid for pid in listening_pids(port) if (process_image_name(pid) or "").casefold() in image_names]
    if not candidates:
        return False
    for pid in candidates:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    return True


def query_tools(port: int) -> int | None:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1.0) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        tools = body.get("result", {}).get("tools", [])
        return len(tools) if isinstance(tools, list) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def wait_ready(port: int, timeout_seconds: int = 15) -> int | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        count = query_tools(port)
        if count is not None and count > 0:
            return count
        time.sleep(1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Start or reuse idalib-mcp")
    parser.add_argument("--ida-dir")
    parser.add_argument("--port", type=int, default=13337)
    parser.add_argument("--server-path")
    parser.add_argument("--force-restart", action="store_true")
    args = parser.parse_args()

    ida_dir = resolve_ida(args.ida_dir)
    if not ida_dir:
        print("ERR:IDA 9.4 not found. Pass --ida-dir or set IDA94_ROOT.")
        return 1
    server_path = resolve_server(args.server_path)
    if not server_path:
        print("ERR:missing idalib-mcp. Run the capability inventory first; no auto-install is performed.")
        return 1

    already_online = service_online(args.port)
    if args.force_restart:
        if already_online and not force_stop(server_path, args.port):
            print(f"ERR:cannot safely identify idalib-mcp on port {args.port}; no process was terminated")
            return 1
        time.sleep(1)
        if service_online(args.port):
            print(f"ERR:port {args.port} is still occupied after controlled restart")
            return 1
        already_online = False

    if not already_online:
        child_env = os.environ.copy()
        child_env["IDADIR"] = str(ida_dir)
        startupinfo = None
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        try:
            subprocess.Popen(
                [str(server_path), "--host", "127.0.0.1", "--port", str(args.port)],
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
                close_fds=os.name != "nt",
            )
        except OSError as exc:
            print(f"ERR:failed to start idalib-mcp: {exc}")
            return 1
    else:
        print(f"INFO:reusing existing MCP service on port {args.port}")

    count = wait_ready(args.port)
    if count is None:
        print("ERR:timeout")
        return 1
    print(f"OK:{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
