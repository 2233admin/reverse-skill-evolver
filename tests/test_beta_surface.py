import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reverse_skill", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_packaged_beta_data_matches_canonical_skill_contracts() -> None:
    pairs = [
        (ROOT / "skills" / "routing.json", ROOT / "reverse_skill" / "data" / "routing.json"),
        (
            ROOT / "skills" / "ida-reverse" / "references" / "ida-plugin-capabilities.json",
            ROOT / "reverse_skill" / "data" / "ida-plugin-capabilities.json",
        ),
    ]
    for canonical, packaged in pairs:
        assert json.loads(canonical.read_text(encoding="utf-8")) == json.loads(
            packaged.read_text(encoding="utf-8")
        )


def test_context_command_fails_closed_without_a_genome(tmp_path: Path) -> None:
    result = run_cli("--json", "context", str(tmp_path))
    assert result.returncode == 5
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["command"] == "context"
    assert value["data"]["reason"] == "aigx_genome_missing"
    assert value["error"]["code"] == "context_blocked"


def test_search_command_uses_machine_readable_python_surface(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    result = run_cli("--json", "search", str(tmp_path), "beta", "--engine", "rg")
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["command"] == "search"
    assert value["data"]["status"] == "observed"
    assert value["data"]["writes_performed"] is False


def test_nested_beta_commands_are_exposed() -> None:
    for command in (("plugins", "--help"), ("teams", "--help")):
        result = run_cli(*command)
        assert result.returncode == 0
        assert "Commands:" in result.stdout
