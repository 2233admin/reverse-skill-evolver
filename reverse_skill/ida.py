from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import EnvironmentUnavailable, McpTransportError


_VERSION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)")
_IDA_DIR_RE = re.compile(r"^IDA(?: Professional| Pro)?(?:\s+|$)", re.IGNORECASE)


def parse_version(text: str | None) -> tuple[int, int, int, int]:
    match = _VERSION_RE.search(text or "")
    if not match:
        return (0, 0, 0, 0)
    parts = [int(part) for part in match.group(1).split(".")]
    return tuple((parts + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def format_version(version: tuple[int, int, int, int]) -> str:
    parts = list(version)
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return ".".join(str(part) for part in parts)


def _windows_product_version(path: Path) -> str | None:
    if os.name != "nt":
        return None

    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None

    translation_ptr = ctypes.c_void_p()
    translation_len = ctypes.c_uint()
    if not version.VerQueryValueW(
        buffer, "\\VarFileInfo\\Translation", ctypes.byref(translation_ptr), ctypes.byref(translation_len)
    ) or translation_len.value < 4:
        return None

    language, codepage = ctypes.cast(
        translation_ptr, ctypes.POINTER(ctypes.c_ushort * 2)
    ).contents
    value_ptr = ctypes.c_void_p()
    value_len = ctypes.c_uint()
    query = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\ProductVersion"
    if not version.VerQueryValueW(
        buffer, query, ctypes.byref(value_ptr), ctypes.byref(value_len)
    ):
        return None
    return ctypes.wstring_at(value_ptr, value_len.value).rstrip("\x00")


@dataclass(frozen=True)
class IdaInstallation:
    install_dir: str
    executable: str
    idalib_path: str
    version: str
    version_key: tuple[int, int, int, int]

    def public(self) -> dict[str, str]:
        return {
            "installDir": self.install_dir,
            "executable": self.executable,
            "idalibPath": self.idalib_path,
            "version": self.version,
        }


def _default_candidates() -> list[Path]:
    candidates: list[Path] = []
    ida_dir = os.environ.get("IDADIR")
    if ida_dir:
        candidates.append(Path(ida_dir))

    appdata = os.environ.get("APPDATA")
    if appdata:
        config_path = Path(appdata) / "Hex-Rays" / "IDA Pro" / "ida-config.json"
        try:
            configured = json.loads(config_path.read_text(encoding="utf-8"))["Paths"]["ida-install-dir"]
            if configured:
                candidates.append(Path(configured))
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            pass

    parents = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path("C:/"),
        Path("D:/Program Files"),
        Path("D:/"),
    ]
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        parents.append(Path(user_profile) / "Tools")

    for parent in parents:
        if not parent.is_dir():
            continue
        try:
            candidates.extend(
                child for child in parent.glob("IDA*") if child.is_dir() and _IDA_DIR_RE.match(child.name)
            )
        except OSError:
            continue
    return candidates


def find_latest_ida(
    candidate_paths: Iterable[str | os.PathLike[str]] = (), *, only_candidates: bool = False
) -> IdaInstallation | None:
    candidates = [Path(path) for path in candidate_paths]
    if not only_candidates:
        candidates.extend(_default_candidates())

    seen: set[str] = set()
    installations: list[IdaInstallation] = []
    for candidate in candidates:
        try:
            install_dir = candidate.expanduser().resolve()
        except OSError:
            continue
        key = str(install_dir).casefold().rstrip("\\/")
        if not key or key in seen:
            continue
        seen.add(key)

        idalib_path = install_dir / "idalib.dll"
        executable = install_dir / "ida.exe"
        if not executable.is_file():
            executable = install_dir / "idat.exe"
        if not executable.is_file() or not idalib_path.is_file():
            continue

        directory_version = parse_version(install_dir.name)
        try:
            product_version = parse_version(_windows_product_version(executable))
        except (OSError, ValueError):
            product_version = (0, 0, 0, 0)
        version_key = max(directory_version, product_version)
        installations.append(
            IdaInstallation(
                install_dir=str(install_dir),
                executable=str(executable),
                idalib_path=str(idalib_path),
                version=format_version(version_key),
                version_key=version_key,
            )
        )

    if not installations:
        return None
    return max(installations, key=lambda item: (item.version_key, item.install_dir.casefold()))


def _find_python_command(names: tuple[str, ...]) -> str | None:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    candidates: list[Path] = []
    python_dir = Path(sys.executable).parent
    for scripts_dir in (python_dir, python_dir / "Scripts"):
        candidates.extend(scripts_dir / f"{name}.exe" for name in names)
    appdata = os.environ.get("APPDATA")
    if appdata:
        python_root = Path(appdata) / "Python"
        if python_root.is_dir():
            for child in python_root.iterdir():
                candidates.extend(child / "Scripts" / f"{name}.exe" for name in names)
    return next((str(path) for path in candidates if path.is_file()), None)


def find_server_executable(explicit: str | None = None) -> str | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return str(path) if path.is_file() else None
    return _find_python_command(("idalib-mcp", "ida-pro-mcp"))


def install_ida_mcp(*, upgrade: bool = False) -> dict[str, object]:
    command = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        command.append("--upgrade")
    command.append("git+https://github.com/mrexodia/ida-pro-mcp.git")
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise EnvironmentUnavailable(f"ida-pro-mcp installation failed with exit code {completed.returncode}")

    ida_installer = _find_python_command(("ida-pro-mcp",))
    if not ida_installer:
        raise EnvironmentUnavailable("ida-pro-mcp installed but its command could not be located")
    completed = subprocess.run([ida_installer, "--install"], check=False)
    if completed.returncode != 0:
        raise EnvironmentUnavailable(f"ida-pro-mcp --install failed with exit code {completed.returncode}")
    return {"installed": True, "installer": ida_installer, "server": find_server_executable()}


def _terminate_stale_server(port: int, executable: str) -> None:
    if os.name != "nt":
        raise EnvironmentUnavailable(
            "--replace-stale requires Windows ownership inspection; inspect the target port manually"
        )
    # Bind a process handle before checking ownership so a reused PID cannot select another process.
    script = r"""
$ErrorActionPreference = 'Stop'
try {
    $owners = @(Get-NetTCPConnection -State Listen | Where-Object {
        $_.LocalPort -eq [int]$env:REVERSE_SKILL_PORT
    } | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -gt 1) { throw 'multiple listener owners; no process was stopped' }
    foreach ($owner in $owners) {
        $process = Get-Process -Id $owner
        $null = $process.Handle
        $info = Get-CimInstance Win32_Process -Filter "ProcessId = $owner"
        if (!$info.ExecutablePath -or $info.ExecutablePath -ne $env:REVERSE_SKILL_SERVER) {
            throw "port owner PID $owner does not match the selected executable; no process was stopped"
        }
        if ($process.Path -ne $info.ExecutablePath -or $process.HasExited) {
            throw 'port owner changed during inspection; no process was stopped'
        }
        $process.Kill()
        if (!$process.WaitForExit(3000)) { throw "PID $owner did not stop within 3 seconds" }
    }
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
"""
    env = os.environ.copy()
    env.update(REVERSE_SKILL_PORT=str(port), REVERSE_SKILL_SERVER=str(Path(executable).resolve()))
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, check=False, timeout=10, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EnvironmentUnavailable(
            f"cannot verify ownership of port {port}; processes preserved: {exc}"
        ) from exc
    if completed.returncode:
        raise EnvironmentUnavailable(
            f"cannot replace service on port {port}: {completed.stderr.strip()}; "
            f"inspect `Get-NetTCPConnection -LocalPort {port}` and its OwningProcess before retrying"
        )


def _startup_failure(process, log_path: Path, reason: str) -> McpTransportError:
    try:
        with log_path.open("rb") as log:
            log.seek(max(0, log_path.stat().st_size - 2000))
            detail = log.read().decode("utf-8", errors="replace").strip()
    except OSError:
        detail = "log could not be read"
    return McpTransportError(
        f"{reason}; PID={process.pid}, exitCode={process.poll()}, log={log_path}; {detail}"
    )


def start_server(
    *,
    probe,
    ida_dir: str | None = None,
    port: int = 13337,
    server_path: str | None = None,
    replace_stale: bool = False,
    wait_seconds: float = 15,
) -> dict[str, object]:
    installation = find_latest_ida([ida_dir] if ida_dir else (), only_candidates=bool(ida_dir))
    if installation is None:
        raise EnvironmentUnavailable("no usable IDA installation found (requires ida.exe/idat.exe and idalib.dll)")

    existing_count = probe(port, 3.0)
    if existing_count > 0:
        return {
            "ida": installation.public(),
            "server": {"url": f"http://127.0.0.1:{port}/mcp", "toolCount": existing_count, "reused": True},
        }

    executable = find_server_executable(server_path)
    if not executable:
        raise EnvironmentUnavailable("idalib-mcp is not installed; run `reverse-skill install` first")
    if replace_stale:
        _terminate_stale_server(port, executable)

    env = os.environ.copy()
    env["IDADIR"] = installation.install_dir
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with tempfile.NamedTemporaryFile(prefix=f"reverse-skill-ida-{port}-", suffix=".log", delete=False) as log:
        log_path = Path(log.name)
        try:
            process = subprocess.Popen(
                [executable, "--host", "127.0.0.1", "--port", str(port)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                env=env, close_fds=True, creationflags=creationflags,
            )
        except OSError as exc:
            raise EnvironmentUnavailable(f"cannot start {executable}: {exc}; log={log_path}") from exc

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise _startup_failure(process, log_path, "idalib-mcp exited before becoming ready")
        tool_count = probe(port, min(3.0, max(0.1, deadline - time.monotonic())))
        if tool_count > 0:
            if process.poll() is not None:
                raise _startup_failure(process, log_path, "idalib-mcp exited during startup")
            return {
                "ida": installation.public(),
                "server": {
                    "url": f"http://127.0.0.1:{port}/mcp", "toolCount": tool_count,
                    "reused": False, "pid": process.pid, "logPath": str(log_path),
                },
            }
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    raise _startup_failure(process, log_path, f"idalib-mcp did not become ready within {wait_seconds} seconds")
