import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_launcher(path=ROOT / "scripts/run.py"):
    spec = importlib.util.spec_from_file_location("skill_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_metadata_follows_agent_skills_specification():
    entries = [ROOT / "SKILL.md", *(ROOT / "skills").rglob("SKILL.md"),
               *(ROOT / "CTF-Sandbox-Orchestrator").rglob("SKILL.md")]
    assert len(entries) > 1
    for path in entries:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
        assert match, f"{path}: missing UTF-8 YAML frontmatter"
        data = yaml.safe_load(match[1])
        assert isinstance(data, dict)
        assert set(data) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
        name = data["name"]
        assert isinstance(name, str) and 1 <= len(name) <= 64
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        assert name == ("reverse-skill-evolver" if path == ROOT / "SKILL.md" else path.parent.name)
        description = data["description"]
        assert isinstance(description, str) and 1 <= len(description.strip()) <= 1024
        if "compatibility" in data:
            assert isinstance(data["compatibility"], str) and 1 <= len(data["compatibility"]) <= 500
        if "metadata" in data:
            assert isinstance(data["metadata"], dict)
            assert all(isinstance(key, str) and isinstance(value, str) for key, value in data["metadata"].items())


@pytest.fixture
def installed_pack(tmp_path):
    destination = tmp_path / "skills/reverse-skill-evolver"
    destination.mkdir(parents=True)
    for name in ("SKILL.md", "pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, destination / name)
    for name in ("reverse_skill", "scripts", "skills", "CTF-Sandbox-Orchestrator"):
        shutil.copytree(ROOT / name, destination / name, ignore=shutil.ignore_patterns("__pycache__"))
    return destination


def test_installed_bundle_contains_every_macro_route_and_shared_runtime(installed_pack):
    mirror = json.loads((installed_pack / "skills/routing.json").read_text(encoding="utf-8"))
    for route in mirror["macro_routes"]:
        assert (installed_pack / "skills" / route["primary_skill"]).is_file()
        for edge in route["fallback_edges"]:
            if edge["goto"].endswith(".md"):
                assert (installed_pack / "skills" / edge["goto"]).is_file()
    for path in ("skills/ROUTER.md", "skills/scripts/lib/ToolDiscovery.ps1", "skills/scripts/bootstrap-reverse.ps1",
                 "skills/field-journal/_index.md", "CTF-Sandbox-Orchestrator/ctf-sandbox-orchestrator/SKILL.md",
                 "reverse_skill/asr.py", "scripts/run.py"):
        assert (installed_pack / path).is_file()


def test_launcher_preserves_working_directory_arguments_and_cli_envelope(installed_pack, tmp_path, monkeypatch, capfd):
    launcher = load_launcher(installed_pack / "scripts/run.py")
    runtime = tmp_path / "prepared test runtime"
    venv.EnvBuilder(system_site_packages=True, with_pip=False).create(runtime)
    interpreter = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    purelib = subprocess.check_output(
        [str(interpreter), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True,
    ).strip()
    (Path(purelib) / "installed-package.pth").write_text(str(installed_pack), encoding="utf-8")
    workspace = tmp_path / "unrelated workspace"
    workspace.mkdir()
    (workspace / "broken trace.json").write_text("{}", encoding="utf-8")
    shadow = workspace / "reverse_skill"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('wrong package loaded')", encoding="utf-8")
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("PYTHONPATH", str(workspace))
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setattr(launcher, "runtime_python", lambda *args: interpreter)
    assert launcher.main(["--json", "tracecard-validate", "--input", "broken trace.json"]) == 5
    captured = capfd.readouterr()
    envelope = json.loads(captured.out)
    assert envelope["command"] == "tracecard-validate"
    assert envelope["error"]["code"] == "ToolOperationError"
    assert "Invalid TraceCard" in envelope["error"]["message"]
    assert captured.err == ""
    assert launcher.main(["--json", "tracecard-validate", "--input", "不存在雪☃.json"]) == 2
    captured = capfd.readouterr()
    assert "不存在雪☃.json" in json.loads(captured.out)["error"]["message"]
    assert captured.err == ""


@pytest.mark.parametrize("marker", [None, {"source": "different-package"}, []])
def test_launcher_refuses_foreign_runtime_directories(installed_pack, tmp_path, monkeypatch, capsys, marker):
    launcher = load_launcher(installed_pack / "scripts/run.py")
    runtime = tmp_path / "foreign environment"
    runtime.mkdir()
    sentinel = runtime / "keep.txt"
    sentinel.write_text("owned by someone else")
    if marker is not None:
        (runtime / "reverse-skill-runtime.json").write_text(json.dumps(marker), encoding="utf-8")
    monkeypatch.setenv("REVERSE_SKILL_RUNTIME", str(runtime))
    assert launcher.main(["--json", "asr", "list"]) == 3
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is False and envelope["command"] == "runtime"
    assert sentinel.read_text() == "owned by someone else"


def test_incomplete_copy_reports_setup_failure_without_running_cli(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "partial pack/scripts"
    destination.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/run.py", destination / "run.py")
    launcher = load_launcher(destination / "run.py")
    monkeypatch.setattr(launcher, "runtime_python", lambda *args: pytest.fail("incomplete package was run"))
    assert launcher.main(["--json", "asr", "list"]) == 3
    envelope = json.loads(capsys.readouterr().out)
    assert "complete reverse-skill-evolver skill" in envelope["error"]["message"]


def test_runtime_cache_distinguishes_installed_packages(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.delenv("REVERSE_SKILL_RUNTIME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    first = launcher.runtime_directory(tmp_path / "first")
    second = launcher.runtime_directory(tmp_path / "second")
    assert first != second and first.is_relative_to(tmp_path) and second.is_relative_to(tmp_path)


def test_first_setup_ignores_a_caller_pip_module(installed_pack, tmp_path, monkeypatch, capfd):
    launcher = load_launcher(installed_pack / "scripts/run.py")
    workspace = tmp_path / "caller workspace"
    workspace.mkdir()
    sentinel = workspace / "unsafe-import-ran"
    (workspace / "pip.py").write_text(
        "from pathlib import Path\nPath('unsafe-import-ran').write_text('bad')\n"
        "raise RuntimeError('caller pip module was imported')\n", encoding="utf-8",
    )
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("PYTHONPATH", str(workspace))
    monkeypatch.setenv("REVERSE_SKILL_RUNTIME", str(tmp_path / "fresh runtime"))
    monkeypatch.setenv("PIP_NO_INDEX", "1")
    monkeypatch.setenv("PIP_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("PIP_CACHE_DIR", str(tmp_path / "empty pip cache"))
    monkeypatch.delenv("PIP_FIND_LINKS", raising=False)
    assert launcher.main(["--json", "asr", "list"]) == 3
    assert not sentinel.exists()
    envelope = json.loads(capfd.readouterr().out)
    assert "dependency installation failed" in envelope["error"]["message"]
