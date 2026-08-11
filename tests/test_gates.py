"""Tests for the Python repository gates (leak-scan, doc-facts, version, routing-coherence)."""

import json
from pathlib import Path

import pytest

from reverse_skill.gates import (
    LEAK_PATTERNS,
    doc_facts,
    leak_scan,
    routing_coherence,
    version_consistency,
)

ROOT = Path(__file__).resolve().parents[1]


def test_leak_scan_finds_credentials_and_ignores_allowed_examples(tmp_path: Path) -> None:
    (tmp_path / "clean.md").write_text(
        "Contact alice@example.com or admin@localhost; IP 10.0.0.5 is private.\n",
        encoding="utf-8",
    )
    (tmp_path / "leaky.md").write_text(
        "token: ghp_abcdefghijklmnopqrstuvwxyz1234567890\nkey: AKIA0123456789ABCDEF\nmobile: 13800138000\n",
        encoding="utf-8",
    )
    (tmp_path / "notes.json").write_text(
        '{"jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz123456"}',
        encoding="utf-8",
    )

    result = leak_scan(str(tmp_path))
    assert result["status"] == "findings"
    kinds = {item["kind"] for item in result["findings"]}
    assert kinds >= {"GitHub token", "AWS Access Key", "CN mobile", "JWT"}
    assert not any(item["kind"] == "Email" for item in result["findings"]), "allowed example emails must be ignored"
    assert result["scanned_files"] == 3

    reported = leak_scan(str(tmp_path), report_only=True)
    assert reported["status"] == "reported"


def test_leak_scan_missing_path_is_invalid(tmp_path: Path) -> None:
    result = leak_scan(str(tmp_path / "missing"))
    assert result["status"] == "invalid"
    assert result["reason"] == "path_not_found"


def test_leak_scan_clean_directory(tmp_path: Path) -> None:
    (tmp_path / "ok.md").write_text("generic reverse-engineering notes, no secrets.\n", encoding="utf-8")
    result = leak_scan(str(tmp_path))
    assert result["status"] == "clean"
    assert result["findings"] == []


def test_field_journal_is_clean_by_default() -> None:
    result = leak_scan(str(ROOT / "skills" / "field-journal"))
    assert result["status"] == "clean", result["findings"][:3]


def test_version_consistency_reports_drift(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('version = "2.0.0b3"\n', encoding="utf-8")
    (tmp_path / "reverse_skill").mkdir()
    (tmp_path / "reverse_skill" / "__init__.py").write_text('__version__ = "2.0.0b3"\n', encoding="utf-8")
    (tmp_path / "reverse-skill.opencli.json").write_text(
        json.dumps({"info": {"version": "2.0.0-beta.4"}}),
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n\n- nothing\n", encoding="utf-8")
    result = version_consistency(tmp_path)
    assert result["status"] == "findings"
    names = {check["name"] for check in result["failures"]}
    assert "opencli" in names


def test_version_consistency_clean_with_beta_normalization(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('version = "2.0.0b3"\n', encoding="utf-8")
    (tmp_path / "reverse_skill").mkdir()
    (tmp_path / "reverse_skill" / "__init__.py").write_text('__version__ = "2.0.0b3"\n', encoding="utf-8")
    (tmp_path / "reverse-skill.opencli.json").write_text(
        json.dumps({"info": {"version": "2.0.0-beta.3"}}),
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n\n- nothing\n", encoding="utf-8")
    result = version_consistency(tmp_path)
    assert result["status"] == "clean", result["failures"]


def test_routing_coherence_on_repo_is_clean() -> None:
    result = routing_coherence(ROOT)
    assert result["status"] == "clean", result["failures"]


def test_routing_coherence_detects_missing_skill(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "routing.json").write_text(
        json.dumps(
            {
                "macro_routes": [
                    {
                        "id": "ghost",
                        "primary_skill": "ghost/SKILL.md",
                        "requires_capabilities": [],
                        "fallback_edges": [],
                        "success_oracles": [],
                    }
                ],
                "tool_stages": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "reverse_skill" / "data").mkdir(parents=True)
    (tmp_path / "reverse_skill" / "data" / "routing.json").write_text(
        (tmp_path / "skills" / "routing.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = routing_coherence(tmp_path)
    assert result["status"] == "findings"
    assert any("ghost" in check["detail"] for check in result["failures"])


def test_doc_facts_detects_missing_opencli_command(tmp_path: Path) -> None:
    (tmp_path / "reverse_skill").mkdir()
    (tmp_path / "reverse_skill" / "cli.py").write_text(
        'COMMAND_NAMES = {"route", "case"}\n',
        encoding="utf-8",
    )
    (tmp_path / "reverse-skill.opencli.json").write_text(
        json.dumps({"command": {"commands": [{"name": "route"}]}}),
        encoding="utf-8",
    )
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "routing.json").write_text('{"macro_routes": []}\n', encoding="utf-8")
    (tmp_path / "skills" / "ida-reverse" / "references").mkdir(parents=True)
    (tmp_path / "skills" / "ida-reverse" / "references" / "ida-plugin-capabilities.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "reverse_skill" / "data").mkdir(parents=True)
    (tmp_path / "reverse_skill" / "data" / "routing.json").write_text(
        '{"macro_routes": []}\n', encoding="utf-8"
    )
    (tmp_path / "reverse_skill" / "data" / "ida-plugin-capabilities.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("install via reverse-skill route\n", encoding="utf-8")
    (tmp_path / "README_zh.md").write_text("install via reverse-skill route\n", encoding="utf-8")

    result = doc_facts(tmp_path)
    assert result["status"] == "findings"
    names = {check["name"] for check in result["failures"]}
    assert "cli_commands_exist_in_opencli" in names
