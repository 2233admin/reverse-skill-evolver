from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
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


def _terminate_stale_servers() -> None:
    if os.name != "nt":
        return
    for image in ("idalib-mcp.exe", "ida-pro-mcp.exe"):
        subprocess.run(
            ["taskkill", "/F", "/T", "/IM", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def start_server(
    *,
    probe,
    ida_dir: str | None = None,
    port: int = 13337,
    server_path: str | None = None,
    replace_stale: bool = False,
    wait_seconds: int = 15,
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
        _terminate_stale_servers()
        time.sleep(1)

    env = os.environ.copy()
    env["IDADIR"] = installation.install_dir
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [executable, "--host", "127.0.0.1", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        close_fds=True,
        creationflags=creationflags,
    )

    for _ in range(wait_seconds):
        time.sleep(1)
        tool_count = probe(port, 3.0)
        if tool_count > 0:
            return {
                "ida": installation.public(),
                "server": {"url": f"http://127.0.0.1:{port}/mcp", "toolCount": tool_count, "reused": False},
            }
    raise McpTransportError(f"idalib-mcp did not become ready within {wait_seconds} seconds")
