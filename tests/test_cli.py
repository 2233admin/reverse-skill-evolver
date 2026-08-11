import json
import os
import subprocess
import sys


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reverse_skill", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, **(env or {})},
        check=False,
    )


def test_help_and_version_are_available() -> None:
    help_result = run_cli("--help")
    version_result = run_cli("--version")

    assert help_result.returncode == 0
    assert "Commands:" in help_result.stdout
    assert version_result.returncode == 0
    assert "2.0.0b3" in version_result.stdout


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
        "0.1",
        "status",
    )

    assert result.returncode == 4
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["command"] == "status"
    assert value["error"]["code"] == "McpTransportError"


def test_route_does_not_treat_so_as_a_substring_of_source() -> None:
    result = run_cli(
        "--json",
        "route",
        "audit this Python source project",
        "--target-kind",
        "source_tree",
    )

    assert result.returncode in {0, 5}
    value = json.loads(result.stdout)
    assert value["command"] == "route"
    assert value["data"]["route"]["base_id"] != "native-binary"


def test_json_output_is_utf8_under_a_legacy_process_encoding() -> None:
    result = run_cli(
        "--json",
        "route",
        "audit this Python source project",
        "--target-kind",
        "source_tree",
        env={"PYTHONIOENCODING": "cp1252"},
    )

    assert result.returncode in {0, 5}
    value = json.loads(result.stdout)
    assert value["command"] == "route"
    assert value["data"]["route"]["base_id"] != "native-binary"
