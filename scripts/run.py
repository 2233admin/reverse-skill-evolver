"""Run the bundled CLI from an installer-managed skill directory."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path


def runtime_python(package: Path, runtime: Path) -> Path:
    marker = runtime / "reverse-skill-runtime.json"
    source = str(package.resolve())
    signature = hashlib.sha256(
        (package / "pyproject.toml").read_bytes() + sys.version.encode("utf-8")
    ).hexdigest()
    if marker.is_file():
        state = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("source") != source:
            raise RuntimeError(f"Runtime directory belongs to another package: {runtime}")
    else:
        if runtime.exists() and (not runtime.is_dir() or any(runtime.iterdir())):
            raise RuntimeError(f"Runtime directory is not an owned, empty directory: {runtime}")
        runtime.mkdir(parents=True, exist_ok=True)
        state = {"source": source, "signature": None}
        marker.write_text(json.dumps(state), encoding="utf-8")

    interpreter = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.is_file():
        venv.EnvBuilder(with_pip=True).create(runtime)
    ready = subprocess.run(
        [str(interpreter), "-I", "-X", "utf8", "-c", "import click, httpx, reverse_skill"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if state.get("signature") != signature or ready.returncode:
        print("Preparing reverse-skill's private Python runtime...", file=sys.stderr)
        completed = subprocess.run(
            [str(interpreter), "-I", "-X", "utf8", "-m", "pip", "install", "--disable-pip-version-check", "--quiet",
             "--editable", source], stdout=sys.stderr, check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"Runtime dependency installation failed (exit {completed.returncode}).")
        state["signature"] = signature
        marker.write_text(json.dumps(state), encoding="utf-8")
    return interpreter


def runtime_directory(package: Path) -> Path:
    override = os.environ.get("REVERSE_SKILL_RUNTIME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        cache = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    identity = hashlib.sha256(str(package.resolve()).encode("utf-8")).hexdigest()[:16]
    return cache / "reverse-skill-evolver" / f"py{sys.version_info.major}{sys.version_info.minor}-{identity}"


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    package = Path(__file__).resolve().parents[1]
    try:
        if sys.version_info < (3, 10):
            raise RuntimeError("Reverse Skill Evolver requires Python 3.10 or newer.")
        if not (package / "pyproject.toml").is_file() or not (package / "reverse_skill").is_dir():
            raise RuntimeError("Install the complete reverse-skill-evolver skill, including its Python source.")
        interpreter = runtime_python(package, runtime_directory(package))
        return subprocess.run(
            [str(interpreter), "-I", "-X", "utf8", "-m", "reverse_skill", *arguments], check=False,
        ).returncode
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        if "--json" in arguments:
            print(json.dumps({
                "schemaVersion": "1", "ok": False, "command": "runtime", "data": None,
                "error": {"code": "EnvironmentUnavailable", "message": str(exc)},
            }))
        else:
            print(f"Cannot prepare reverse-skill: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
