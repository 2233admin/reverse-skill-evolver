import ast
import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".omp" / "skills" / "omp-ida-native"


def test_omp_skill_metadata_and_references_are_portable() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: omp-ida-native\ndescription:")
    assert "## ACTION REQUIRED" in text
    assert "## 任务完成自检" in text
    for document in SKILL.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith("https://"):
                continue
            path = (document.parent / target).resolve()
            assert path.is_relative_to(SKILL.resolve()), (document, target)
            assert path.is_file(), (document, target)


@pytest.mark.parametrize("available,expected", [
    ({"omp_ida_native"}, True),
    ({"idapro"}, True),
    ({"omp_ida_native", "idapro"}, True),
    (set(), False),
])
def test_native_binary_route_backend_alternatives(available: set[str], expected: bool) -> None:
    routes = json.loads((ROOT / "skills" / "routing.json").read_text(encoding="utf-8"))["macro_routes"]
    route = next(route for route in routes if route["id"] == "native-binary")
    assert route["primary_skill"] == "ida-reverse/SKILL.md"
    assert route["requires_capabilities"] == []
    assert set(route["requires_any_capabilities"]) == {"omp_ida_native", "idapro"}
    assert any(capability in available for capability in route["requires_any_capabilities"]) is expected
    assert route["fallback_edges"][0]["when"] == "all_supported_ida_backends_unavailable"


def test_native_backend_is_selected_before_mcp_instructions() -> None:
    text = (ROOT / "skills" / "ida-reverse" / "SKILL.md").read_text(encoding="utf-8")
    assert text.index("../../.omp/skills/omp-ida-native/SKILL.md") < text.index("## idapro HTTP MCP")
    for name in ("routing.md", "routing_zh.md"):
        routing = (ROOT / "skills" / name).read_text(encoding="utf-8")
        assert "requires_any_capabilities" in routing
        assert "omp_ida_native" in routing
        assert "all_supported_ida_backends_unavailable" in routing


def test_batch_example_is_valid_python() -> None:
    text = (SKILL / "references" / "native-ida.md").read_text(encoding="utf-8")
    examples = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)
    assert len(examples) == 1
    ast.parse(examples[0])


def test_shared_entry_accepts_native_evidence_without_external_index() -> None:
    evolution = (ROOT / "skills" / "evolution" / "SKILL.md").read_text(encoding="utf-8")
    assert "OMP native IDA schema and operation evidence were recorded" in evolution
    rules = (ROOT / "RULES.md").read_text(encoding="utf-8")
    compact = rules.split("### Post-Trigger Execution", 1)[1].split("### Core Rules", 1)[0]
    assert "OMP native IDA → record live schema and operation evidence" in compact
