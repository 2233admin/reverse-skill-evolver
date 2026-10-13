import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / ".omp/skills/omp-ida-native/scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analysis = load_script("ida_analysis")


@pytest.fixture
def namespace():
    base = 0x140000000
    queries = []
    def xrefs(ea):
        queries.append(ea)
        return [{"from": base + 0x1002, "func": "verify_password", "type": "DATA_READ"},
                {"from": base + 0x2008, "func": None, "type": "DATA_READ"}]
    return {
        "db": SimpleNamespace(sha256="a" * 64, module="owned.exe", format="PE", architecture="metapc", bitness=64, base_address=base),
        "functions": lambda: [(base + 0x1000, "verify_password"), (base + 0x1200, "sub_140001200")],
        "strings": lambda: [(base + 0x2000, "password invalid")],
        "imports": lambda: [(base + 0x3000, "KERNEL32", "ReadFile")],
        "func": lambda ea: SimpleNamespace(size=lambda: 8, start_ea=base + 0x1000),
        "callees": lambda ea: ["ReadFile", "other"],
        "ida_bytes": SimpleNamespace(get_bytes=lambda ea, count: bytes(range(count))),
        "pseudocode": lambda ea: "// function header\n// decompilation failed: fixture; showing disassembly\nret",
        "xrefs_to": xrefs,
        "queries": queries,
    }


def test_collected_contract_preserves_bytes_and_fallback_kind(namespace):
    snapshot = analysis.collect_snapshot(namespace, "owned-native", max_functions=1, max_bytes_per_function=2, max_callees=1, collect_pseudocode=True)
    row = snapshot["functions"][0]
    assert row["rva"] == "0x1000" and row["ea"] == "0x140001000"
    assert row["bytes_sha256"] == hashlib.sha256(b"\x00\x01").hexdigest()
    assert row["bytes_truncated"] and snapshot["coverage"]["functions_truncated"]
    assert row["callees_truncated"] and row["pseudocode_kind"] == "assembly_fallback"
    json.dumps(snapshot, allow_nan=False)


def test_triage_uses_function_owner_skips_data_xrefs_and_limits_queries(namespace):
    report = analysis.triage(namespace, "owned-native", max_xref_queries=1, max_evidence_per_candidate=1)
    assert report["candidates"][0]["ea"] == "0x140001000"
    assert report["coverage"]["non_function_xrefs_skipped"] == 1
    assert report["coverage"]["xref_queries"] == len(namespace["queries"]) == 1
    assert report["coverage"]["xref_queries_truncated"] and report["coverage"]["evidence_truncated"]
    assert len(report["candidates"][0]["evidence"]) == 1
    no_match = analysis.triage(namespace, "owned-native", function_pattern="^NONE$", string_pattern="^NONE$", import_pattern="^NONE$")
    assert no_match["candidates"] == []


@pytest.mark.parametrize("method", [analysis.collect_snapshot, analysis.triage])
def test_missing_native_environment_is_actionable(method):
    with pytest.raises(RuntimeError, match="OMP native IDA exec namespace.*open an owned"):
        method({}, "owned-native")


@pytest.mark.parametrize("field,value", [("sha256", "unknown"), ("bitness", True), ("base_address", -1), ("module", None), ("architecture", "")])
def test_invalid_source_cannot_be_exported_as_traceable(namespace, field, value):
    setattr(namespace["db"], field, value)
    with pytest.raises(ValueError):
        analysis.collect_snapshot(namespace, "owned-native")


@pytest.mark.parametrize("budget,value", [("max_functions", True), ("max_functions", 5001), ("max_text_chars", 0), ("max_bytes_per_function", -1)])
def test_snapshot_rejects_invalid_budgets(namespace, budget, value):
    with pytest.raises(ValueError):
        analysis.collect_snapshot(namespace, "owned-native", **{budget: value})


def test_zero_capture_budget_keeps_unknown_coverage(namespace):
    report = analysis.collect_snapshot(namespace, "owned-native", max_functions=0, max_strings=0, max_imports=0)
    assert report["functions"] == report["strings"] == report["imports"] == []
    assert report["coverage"]["functions_total"] == 2 and report["coverage"]["functions_truncated"]
