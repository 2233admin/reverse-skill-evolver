import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, validate


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
        "install",
        "register",
        "start",
        "status",
        "doctor",
        "tools",
        "open",
        "sessions",
        "call",
        "close",
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
