import json
import subprocess
import sys


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
    assert "1.0.0" in version_result.stdout


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
