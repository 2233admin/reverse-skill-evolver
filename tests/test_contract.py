import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, validate

from reverse_skill.cli import cli


ROOT = Path(__file__).resolve().parents[1]


def test_output_schema_is_valid_and_accepts_real_error_envelope() -> None:
    schema = json.loads((ROOT / "reverse-skill-output.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    result = subprocess.run(
        [sys.executable, "-m", "reverse_skill", "--json", "call", "x", "--arguments-json", "{"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    validate(json.loads(result.stdout), schema)


def test_opencli_description_matches_click_command_surface() -> None:
    description = json.loads((ROOT / "reverse-skill.opencli.json").read_text(encoding="utf-8"))
    assert description["opencli"] == "0.1"
    assert description["command"]["name"] == "reverse-skill"
    described = {command["name"] for command in description["command"]["commands"]}
    result = subprocess.run(
        [sys.executable, "-m", "reverse_skill", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for option in description["command"]["options"]:
        assert option["name"] in result.stdout
    for command in described:
        assert f"  {command}" in result.stdout
    assert described == {
        "asr",
        "install",
        "register",
        "start",
        "status",
        "doctor",
        "tools",
        "integrations",
        "yara-scan",
        "open",
        "sessions",
        "call",
        "close",
        "evolve",
        "tracecard-validate",
    }

    for command in description["command"]["commands"]:
        command_help = subprocess.run(
            [sys.executable, "-m", "reverse_skill", command["name"], "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for option in command.get("options", []):
            assert option["name"] in command_help
        for argument in command.get("arguments", []):
            assert argument["name"] in command_help


def test_opencli_evolve_required_options_match_click() -> None:
    description = json.loads((ROOT / "reverse-skill.opencli.json").read_text(encoding="utf-8"))
    evolve = next(command for command in description["command"]["commands"] if command["name"] == "evolve")
    options = {option["name"]: option for option in evolve["options"]}
    required_options = {"--candidate", "--catalog", "--fixtures", "--output"}

    assert {name for name, option in options.items() if option.get("required", False)} == required_options
    for parameter in cli.commands["evolve"].params:
        name = parameter.opts[0]
        assert options[name].get("required", False) == parameter.required
    for name in required_options:
        assert options[name]["arguments"][0]["required"] is True


def test_opencli_tracecard_validate_requires_input() -> None:
    description = json.loads((ROOT / "reverse-skill.opencli.json").read_text(encoding="utf-8"))
    command = next(item for item in description["command"]["commands"] if item["name"] == "tracecard-validate")

    assert command["options"] == [
        {"name": "--input", "required": True, "arguments": [{"name": "FILE", "required": True}]},
    ]
    assert cli.commands["tracecard-validate"].params[0].opts == ["--input"]
    assert cli.commands["tracecard-validate"].params[0].required is True


def test_opencli_asr_commands_match_nested_click_surface() -> None:
    description = json.loads((ROOT / "reverse-skill.opencli.json").read_text(encoding="utf-8"))
    group = next(command for command in description["command"]["commands"] if command["name"] == "asr")
    assert {command["name"] for command in group["commands"]} == {
        "list", "show", "install", "install-script", "authors", "author", "plugin", "scans",
        "scan", "scan-result", "import-repo", "create-goal", "record-download",
    }
    assert {command["name"] for command in group["commands"]} == set(cli.commands["asr"].commands)
    for command in group["commands"]:
        help_text = subprocess.run(
            [sys.executable, "-m", "reverse_skill", "asr", command["name"], "--help"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        for option in command.get("options", []):
            assert option["name"] in help_text
        for argument in command.get("arguments", []):
            assert argument["name"] in help_text
