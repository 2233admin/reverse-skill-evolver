import json
import subprocess
import sys
from pathlib import Path

import pytest

from reverse_skill import cli as cli_module


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reverse_skill", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_and_version_are_available() -> None:
    help_result = run_cli("--help")
    version_result = run_cli("--version")

    assert help_result.returncode == 0
    assert "Commands:" in help_result.stdout
    assert version_result.returncode == 0
    assert "1.1.2" in version_result.stdout


def test_help_describes_ida_operations_and_bounded_route_evolution_search() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    help_text = " ".join(result.stdout.lower().split())
    assert "ida pro mcp" in help_text
    assert "bounded" in help_text
    assert "route" in help_text
    assert "evolution" in help_text
    assert "search" in help_text


def test_integrations_has_a_stable_json_shape() -> None:
    result = run_cli("--json", "integrations")

    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["command"] == "integrations"
    integrations = {item["name"]: item for item in value["data"]["integrations"]}
    assert integrations["yara"]["support"] == "ready"
    assert integrations["capa"]["support"] == "discovery_only"


def test_yara_annotation_requires_database() -> None:
    result = run_cli("--json", "yara-scan", __file__, "--rules", __file__, "--annotate")

    assert result.returncode == 2
    value = json.loads(result.stdout)
    assert value["command"] == "yara-scan"
    assert "--database" in value["error"]["message"]


def test_unknown_command_is_usage_error() -> None:
    result = run_cli("unknown")

    assert result.returncode == 2
    assert "No such command" in result.stderr


def test_json_usage_error_is_one_machine_readable_envelope() -> None:
    result = run_cli("--json", "call", "tool", "--arguments-json", "{")

    assert result.returncode == 2
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["command"] == "call"
    assert value["error"]["code"] == "usage"
    assert result.stderr == ""


def test_json_mode_rejects_interactive_install_without_starting_it() -> None:
    result = run_cli("--json", "install")

    assert result.returncode == 2
    value = json.loads(result.stdout)
    assert value["command"] == "install"
    assert value["error"]["code"] == "usage"
    assert "interactive" in value["error"]["message"]


def test_transport_failure_has_stable_exit_code_and_command_name() -> None:
    result = run_cli(
        "--json",
        "--url",
        "http://127.0.0.1:1/mcp",
        "--timeout",
        "5",
        "status",
    )

    assert result.returncode == 4
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["command"] == "status"
    assert value["error"]["code"] == "McpTransportError"


@pytest.fixture
def evolve_args(tmp_path: Path) -> list[str]:
    input_path = tmp_path / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    return [
        "evolve",
        "--candidate", str(input_path),
        "--catalog", str(input_path),
        "--fixtures", str(input_path),
        "--output", str(tmp_path / "run"),
    ]


@pytest.mark.parametrize("max_evaluations,max_reflections", [(3, 2), (4, 3), (2, 1), (3, 0)])
def test_evolve_invalid_budgets_return_usage_envelope_without_running(
    evolve_args: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    max_evaluations: int,
    max_reflections: int,
) -> None:
    calls = []

    def runner(*args):
        calls.append(args)
        return {}

    monkeypatch.setattr(cli_module, "run_evolution", runner)
    exit_code = cli_module.main([
        "--json", *evolve_args,
        "--max-evaluations", str(max_evaluations),
        "--max-reflections", str(max_reflections),
    ])
    captured = capsys.readouterr()
    value = json.loads(captured.out)

    assert exit_code == 2
    assert calls == []
    assert not (tmp_path / "run").exists()
    assert captured.err == ""
    assert isinstance(value["error"]["message"], str) and value["error"]["message"]
    assert value == {
        "schemaVersion": "1",
        "ok": False,
        "command": "evolve",
        "data": None,
        "error": {"code": "usage", "message": value["error"]["message"]},
    }


@pytest.mark.parametrize("budget_args,expected_budgets", [
    ((), (3, 1)),
    (("--max-evaluations", "3", "--max-reflections", "1"), (3, 1)),
    (("--max-evaluations", "4", "--max-reflections", "1"), (4, 1)),
    (("--max-evaluations", "4", "--max-reflections", "2"), (4, 2)),
])
def test_evolve_valid_budgets_reach_runner_and_emit_success_envelope(
    evolve_args: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_args: tuple[str, ...],
    expected_budgets: tuple[int, int],
) -> None:
    calls = []
    report = {
        "evaluations_consumed": expected_budgets[0],
        "reflections_consumed": expected_budgets[1],
    }

    def runner(*args):
        calls.append(args)
        return report

    monkeypatch.setattr(cli_module, "run_evolution", runner)
    exit_code = cli_module.main(["--json", *evolve_args, *budget_args])
    captured = capsys.readouterr()
    input_path = (tmp_path / "input.json").resolve()

    assert exit_code == 0
    assert calls == [(input_path, input_path, input_path, tmp_path / "run", *expected_budgets, 120)]
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "schemaVersion": "1",
        "ok": True,
        "command": "evolve",
        "data": report,
        "error": None,
    }


@pytest.fixture
def valid_tracecard() -> dict:
    return {
        "schema_version": 2,
        "trace_id": "cli-trace",
        "goal_id": "cli-goal",
        "route": {"macro_route": "reverse-engineering"},
        "steps": [{
            "step_id": 1,
            "prefix_summary": "fixture inspected",
            "decision": "check fixture oracle",
            "outcome": "oracle_passed",
            "evidence_refs": [{
                "id": "fixture-evidence",
                "source": "synthetic CLI fixture",
                "input_id": "fixture-input",
                "coverage": "fixture assertions",
                "limitations": ["synthetic evidence is not external evidence verification"],
            }],
        }],
        "oracle_results": [{
            "oracle_id": "fixture-oracle",
            "status": "pass",
            "evidence_refs": ["fixture-evidence"],
        }],
        "unknowns": [],
        "memory_tier": "validated",
        "promotion_candidate": False,
    }


@pytest.mark.parametrize("json_output", [True, False])
@pytest.mark.parametrize("memory_tier", ["validated", "candidate", "forensic"])
def test_tracecard_validate_accepts_valid_content_without_mutating_input(
    tmp_path: Path, valid_tracecard: dict, json_output: bool, memory_tier: str,
) -> None:
    valid_tracecard["memory_tier"] = memory_tier
    input_path = tmp_path / "tracecard.json"
    original = json.dumps(valid_tracecard)
    input_path.write_text(original, encoding="utf-8")
    result = run_cli(
        *(["--json"] if json_output else []),
        "tracecard-validate", "--input", str(input_path),
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert input_path.read_text(encoding="utf-8") == original
    value = json.loads(result.stdout)
    if json_output:
        assert value == {
            "schemaVersion": "1",
            "ok": True,
            "command": "tracecard-validate",
            "data": {"semantics_valid": True},
            "error": None,
        }
    else:
        assert value == {"semantics_valid": True}


@pytest.mark.parametrize("evidence_ref", ["", "missing-evidence"])
def test_tracecard_validate_rejects_empty_or_dangling_evidence_links(
    tmp_path: Path, valid_tracecard: dict, evidence_ref: str,
) -> None:
    valid_tracecard["oracle_results"][0]["evidence_refs"] = [evidence_ref]
    input_path = tmp_path / "tracecard.json"
    input_path.write_text(json.dumps(valid_tracecard), encoding="utf-8")
    result = run_cli("--json", "tracecard-validate", "--input", str(input_path))
    value = json.loads(result.stdout)

    assert result.returncode == 5
    assert result.stderr == ""
    assert value == {
        "schemaVersion": "1",
        "ok": False,
        "command": "tracecard-validate",
        "data": None,
        "error": {"code": "ToolOperationError", "message": value["error"]["message"]},
    }
    assert "Invalid TraceCard:" in value["error"]["message"]
    assert "evidence" in value["error"]["message"]


def test_tracecard_validate_rejects_open_outcome_affecting_unknown(
    tmp_path: Path, valid_tracecard: dict,
) -> None:
    valid_tracecard["unknowns"] = [{
        "question": "Is the fixture result representative?",
        "status": "open",
        "requires": "additional observation",
        "affects_outcome": True,
        "supporting_evidence": [],
        "contradicting_evidence": [],
    }]
    input_path = tmp_path / "tracecard.json"
    input_path.write_text(json.dumps(valid_tracecard), encoding="utf-8")
    result = run_cli("--json", "tracecard-validate", "--input", str(input_path))
    value = json.loads(result.stdout)

    assert result.returncode == 5
    assert result.stderr == ""
    assert value["ok"] is False
    assert value["command"] == "tracecard-validate"
    assert value["data"] is None
    assert value["error"]["code"] == "ToolOperationError"
    assert "open outcome-affecting unknown" in value["error"]["message"]


@pytest.mark.parametrize("content", [b"{", b"\xff", b"[]", b"{}"])
def test_tracecard_validate_invalid_content_is_operation_failure(
    tmp_path: Path, content: bytes,
) -> None:
    input_path = tmp_path / "tracecard.json"
    input_path.write_bytes(content)
    result = run_cli("--json", "tracecard-validate", "--input", str(input_path))
    value = json.loads(result.stdout)

    assert result.returncode == 5
    assert result.stderr == ""
    assert value["schemaVersion"] == "1"
    assert value["ok"] is False
    assert value["command"] == "tracecard-validate"
    assert value["data"] is None
    assert value["error"]["code"] == "ToolOperationError"
    assert value["error"]["message"]


def test_tracecard_validate_requires_input() -> None:
    result = run_cli("--json", "tracecard-validate")
    value = json.loads(result.stdout)

    assert result.returncode == 2
    assert result.stderr == ""
    assert value["command"] == "tracecard-validate"
    assert value["error"]["code"] == "usage"
    assert "--input" in value["error"]["message"]


@pytest.mark.parametrize("timeout_args,expected_timeout", [
    ((), 120.0),
    (("--timeout", "0.25"), 0.25),
])
@pytest.mark.parametrize("command,operation,existing,expected_operations,message", [
    ("register", "get", False, ["get"], "failed to inspect"),
    ("status", "get", False, ["get"], "failed to inspect"),
    ("doctor", "get", False, ["get"], "failed to inspect"),
    ("register", "remove", True, ["get", "remove"], "failed to remove"),
    ("register", "add", False, ["get", "add"], "failed to register"),
    ("register", "add", True, ["get", "remove", "add"], "failed to register"),
])
def test_codex_mcp_timeouts_fail_without_fallback_or_retry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    timeout_args: tuple[str, ...],
    expected_timeout: float,
    command: str,
    operation: str,
    existing: bool,
    expected_operations: list[str],
    message: str,
) -> None:
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[2] == operation:
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout", expected_timeout))
        if args[2] == "get":
            if not existing:
                return subprocess.CompletedProcess(args, 1, "", "not found")
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "name": "idapro",
                "enabled": True,
                "transport": {"type": "streamable_http", "url": "http://old.example/mcp"},
            }), "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "codex")
    monkeypatch.setattr(cli_module.subprocess, "run", run)
    monkeypatch.setattr(cli_module, "find_latest_ida", lambda: None)

    exit_code = cli_module.main(["--json", *timeout_args, command])
    captured = capsys.readouterr()
    value = json.loads(captured.out)

    assert exit_code == 3
    assert captured.err == ""
    assert value == {
        "schemaVersion": "1",
        "ok": False,
        "command": command,
        "data": None,
        "error": {
            "code": "EnvironmentUnavailable",
            "message": value["error"]["message"],
        },
    }
    assert message in value["error"]["message"]
    assert "idapro" in value["error"]["message"]
    assert "timed out" in value["error"]["message"]
    assert [args[2] for args, _ in calls] == expected_operations
    for args, kwargs in calls:
        assert args[:2] == ["codex", "mcp"]
        assert args[3] == "idapro"
        assert kwargs == {
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": expected_timeout,
        }
