import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_cli_tools_use_isolated_uv_environments() -> None:
    manifest = json.loads(
        (ROOT / "skills" / "scripts" / "bootstrap-manifest.json").read_text(encoding="utf-8")
    )
    definitions = {item["name"]: item for item in manifest["capabilities"]}

    for name in ("frida", "frida-ps"):
        assert definitions[name]["bootstrapKind"] == "uv-tool"
        assert definitions[name]["uvPackage"] == "frida-tools"

    assert definitions["aigx"]["bootstrapKind"] == "uv-tool"
    assert definitions["aigx"]["uvPackage"] == "aigx==1.2.0"

    assert all(item["bootstrapKind"] != "pip-package" for item in definitions.values())
