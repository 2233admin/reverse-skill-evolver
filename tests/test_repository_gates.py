import json
import shutil
from pathlib import Path

import pytest
from jsonschema import validate

from reverse_skill.cli import main
from reverse_skill.gates import doc_facts, leak_scan, routing_coherence, version_consistency


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo(tmp_path):
    for name in ("pyproject.toml", "reverse_skill/__init__.py", "reverse-skill.opencli.json",
                 "CHANGELOG.md", "README.md", "README_zh.md", "skills/routing.json",
                 "reverse_skill/data/routing.json"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_command_and_data_checks_detect_drift(repo):
    assert doc_facts(repo)["status"] == "clean"
    path = repo / "reverse-skill.opencli.json"
    spec = json.loads(path.read_text())
    group = next(c for c in spec["command"]["commands"] if c["name"] == "case")
    group["commands"].pop()
    path.write_text(json.dumps(spec), encoding="utf-8")
    assert doc_facts(repo)["status"] == "findings"
    shutil.copyfile(ROOT / "reverse-skill.opencli.json", path)
    (repo / "reverse_skill/data/routing.json").write_text("{}")
    assert doc_facts(repo)["status"] == "findings"


def test_version_check_detects_real_mismatch(repo):
    assert version_consistency(repo)["status"] == "clean"
    (repo / "reverse_skill/__init__.py").write_text('__version__ = "99.0.0"')
    assert version_consistency(repo)["status"] == "findings"


def test_route_paths_and_ids_are_checked(repo):
    path = repo / "skills/routing.json"
    path.write_text(json.dumps({"macro_routes": [
        {"id": "test", "primary_skill": "../outside.md"},
        {"id": "test", "primary_skill": "missing.md"},
    ]}), encoding="utf-8")
    result = routing_coherence(repo)
    assert result["status"] == "findings"
    assert {c["name"] for c in result["failures"]} == {
        "unique_routes", "test:../outside.md", "test:missing.md"}


def test_leak_scan_redacts_values_and_keeps_demo_addresses(tmp_path):
    path = tmp_path / "report.md"
    token = "ghp_" + "x" * 24
    path.write_text("someone@example.com\n" + token, encoding="utf-8")
    result = leak_scan(str(path))
    assert result["status"] == "findings"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["kind"] == "GitHub token"
    assert token not in json.dumps(result)
    assert leak_scan(str(path), report_only=True)["status"] == "reported"


def test_failures_keep_output_v1_contract(tmp_path, capsys):
    assert main(["--json", "case", "review", str(tmp_path / "missing")]) == 5
    value = json.loads(capsys.readouterr().out)
    validate(value, json.loads((ROOT / "reverse-skill-output.schema.json").read_text()))
    assert value["data"] is None
    report = json.loads(value["error"]["message"].split("\nDiagnostics: ")[1])
    assert report["issues"][0]["code"] == "case.missing"
