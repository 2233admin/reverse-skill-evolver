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


@pytest.mark.parametrize("operation,helper,invalid", [
    ("snapshot", "callees", "missing"), ("snapshot", "callees", "not_callable"),
    ("snapshot", "ida_bytes", "missing"), ("snapshot", "ida_bytes", "not_callable"),
    ("pseudocode", "pseudocode", "missing"), ("pseudocode", "pseudocode", "not_callable"),
    ("triage", "xrefs_to", "missing"), ("triage", "xrefs_to", "not_callable"),
])
def test_operation_helpers_are_checked_before_enumeration(namespace, operation, helper, invalid):
    scans = []
    original = namespace["functions"]
    def functions():
        scans.append("functions")
        return original()
    namespace["functions"] = functions
    if invalid == "missing":
        namespace.pop(helper)
    else:
        namespace[helper] = SimpleNamespace(get_bytes=None) if helper == "ida_bytes" else None
    method = analysis.triage if operation == "triage" else analysis.collect_snapshot
    options = {"collect_pseudocode": True} if operation == "pseudocode" else {}
    with pytest.raises(RuntimeError, match=rf"{helper}.*open an owned native database"):
        method(namespace, "owned-native", **options)
    assert scans == []


def test_operations_do_not_require_unused_helpers(namespace):
    snapshot_namespace = {key: value for key, value in namespace.items() if key not in ("xrefs_to", "pseudocode", "ida_bytes")}
    snapshot = analysis.collect_snapshot(snapshot_namespace, "owned-native", max_bytes_per_function=0)
    assert len(snapshot["functions"]) == 2
    assert all(row["bytes_hashed"] == 0 for row in snapshot["functions"])
    triage_namespace = {key: value for key, value in namespace.items() if key not in ("callees", "ida_bytes", "pseudocode")}
    assert analysis.triage(triage_namespace, "owned-native")["candidates"]


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


def test_custom_batch_matches_default_scan_semantics_and_native_ownership(namespace):
    import os
    import threading
    import re
    scans = []
    owner = (os.getpid(), threading.get_ident())
    for helper in ("functions", "strings", "imports", "xrefs_to", "func"):
        original = namespace[helper]
        def owned(*args, original=original, helper=helper):
            assert (os.getpid(), threading.get_ident()) == owner
            scans.append(helper)
            return original(*args)
        namespace[helper] = owned
    local = analysis.triage(namespace, "owned-native", max_subject_chars=12)
    # A semantically identical custom pattern must produce exactly the same rows/coverage.
    custom_pattern = "(?:" + analysis._DEFAULT_PATTERNS[0] + ")"
    custom = analysis.triage(namespace, "owned-native", function_pattern=custom_pattern, max_subject_chars=12)
    custom["coverage"]["patterns"]["functions"] = analysis._DEFAULT_PATTERNS[0]
    assert custom == local
    assert set(scans) == {"functions", "strings", "imports", "xrefs_to", "func"}
    # Backreferences, lookarounds and named groups remain Python regexes.
    namespace["strings"] = lambda: [(0x140002000, "TOKEN token password")]
    result = analysis.triage(namespace, "owned-native", string_pattern=r"(?P<word>token)\s+(?P=word)(?= password)")
    assert result["coverage"]["source_scans"]["strings"]["matches"] == 1
    for matches, scan in analysis._custom_matches(
        [([(1, "TOKEN token password"), (2, "x" * 30)], lambda row: row[1])],
        [re.compile("token", re.IGNORECASE)], 1, 2, 12,
    ):
        assert matches == [(1, "TOKEN token password")]
        assert scan == {"total": 2, "scanned": 1, "scan_truncated": True, "matches": 1, "text_truncated": True}


def test_pathological_custom_batch_fails_and_reaps_child_then_recovers(namespace, monkeypatch):
    import subprocess
    children = []
    popen = subprocess.Popen
    def tracked(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(analysis.subprocess, "Popen", tracked)
    namespace["strings"] = lambda: [(0x140002000, "a" * 100 + "!")]
    try:
        with pytest.raises(RuntimeError, match="Custom triage regex batch exceeded 2 seconds"):
            analysis.triage(namespace, "owned-native", string_pattern=r"^(a+)+$")
        assert children and all(child.poll() is not None for child in children)
        assert namespace["queries"] == []
        failed_children = len(children)
        assert analysis.triage(namespace, "owned-native", string_pattern=r"a+")["coverage"]["source_scans"]["strings"]["matches"] == 1
        assert len(children) > failed_children and all(child.poll() is not None for child in children)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()


def test_custom_batch_loads_helper_from_compile_filename(namespace, monkeypatch, tmp_path):
    isolated = {}
    script = SCRIPTS / "ida_analysis.py"
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), isolated)
    assert "__file__" not in isolated
    monkeypatch.chdir(tmp_path)
    report = isolated["triage"](namespace, "owned-native", string_pattern=r"password(?= invalid)")
    assert report["coverage"]["source_scans"]["strings"]["matches"] == 1


def test_missing_adjacent_worker_fails_before_xrefs_and_returns_no_partial_report(namespace, tmp_path):
    isolated = {}
    script = SCRIPTS / "ida_analysis.py"
    exec(compile(script.read_text(encoding="utf-8"), str(tmp_path / "ida_analysis.py"), "exec"), isolated)
    with pytest.raises(RuntimeError, match=r"Custom triage regex worker failed \(exit 2\)"):
        isolated["triage"](namespace, "owned-native", string_pattern="password")
    assert namespace["queries"] == []


def test_defaults_never_launch_regex_child_and_invalid_regex_fails_before_enumeration(namespace, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("must not launch a matching child")
    monkeypatch.setattr(analysis.subprocess, "run", forbidden)
    assert analysis.triage(namespace, "owned-native")["candidates"]
    namespace["functions"] = forbidden
    import re
    with pytest.raises(re.error):
        analysis.triage(namespace, "owned-native", string_pattern="[")


@pytest.mark.parametrize("max_matches,max_scan", [(0, 100), (100, 0), (1, 1)])
def test_custom_batch_preserves_zero_and_truncated_scan_coverage(namespace, max_matches, max_scan):
    local = analysis.triage(namespace, "owned-native", max_matches_per_source=max_matches, max_scan_per_source=max_scan)
    custom = analysis.triage(namespace, "owned-native", function_pattern="(?:" + analysis._DEFAULT_PATTERNS[0] + ")",
                             max_matches_per_source=max_matches, max_scan_per_source=max_scan)
    custom["coverage"]["patterns"] = local["coverage"]["patterns"]
    assert custom == local


def test_custom_batch_stops_preparing_subjects_after_first_match():
    import re
    calls = []
    rows = [(1, "match" + "\N{SNOWMAN}" * 16379)] * 100000

    def subject(row):
        calls.append(row)
        assert len(calls) == 1, "must not prepare the rest of a large scan after one match"
        return row[1]

    [(matches, scan)] = analysis._custom_matches(
        [(rows, subject)], [re.compile("match")], 1, 100000, 16384,
    )
    assert matches == [rows[0]]
    assert scan == {"total": 100000, "scanned": 1, "scan_truncated": True,
                    "matches": 1, "text_truncated": False}


def test_custom_batch_bounds_encoded_payload_and_combines_chunk_coverage(monkeypatch):
    import re
    payload_sizes = []
    run = analysis.subprocess.run

    def bounded(*args, **kwargs):
        payload_sizes.append(len(kwargs["input"].encode("ascii")))
        assert payload_sizes[-1] <= 4096
        return run(*args, **kwargs)

    monkeypatch.setattr(analysis, "_REGEX_PAYLOAD_BYTES", 4096, raising=False)
    monkeypatch.setattr(analysis, "_REGEX_BATCH_SECONDS", 10)
    monkeypatch.setattr(analysis.subprocess, "run", bounded)
    rows = [(index, "\N{SNOWMAN}" * 300 + ("match" if index == 6 else "")) for index in range(7)]
    rows[0] = (0, "\N{SNOWMAN}" * 400)
    [(matches, scan)] = analysis._custom_matches(
        [(rows, lambda row: row[1])], [re.compile("match")], 100, 7, 305,
    )
    assert len(payload_sizes) > 1
    assert matches == [rows[6]]
    assert scan == {"total": 7, "scanned": 7, "scan_truncated": False,
                    "matches": 1, "text_truncated": True}


def test_custom_chunks_share_one_deadline_including_preparation(monkeypatch):
    import json
    import re
    import subprocess
    clock, timeouts = [0.0], []

    def slow_chunk(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        request = json.loads(kwargs["input"])
        batch = request["batches"][0]
        clock[0] += 1.1
        result = [{"indices": [], "coverage": {"scanned": len(batch["subjects"]), "text_truncated": False}}]
        return subprocess.CompletedProcess(args[0], 0, stdout=json.dumps(result))

    monkeypatch.setattr(analysis.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(analysis.subprocess, "run", slow_chunk)
    with pytest.raises(RuntimeError, match="Custom triage regex batch exceeded 2 seconds"):
        analysis._custom_matches(
            [([(1, "x")] * 100, lambda row: row[1])], [re.compile("never")], 1, 100, 10,
        )
    assert timeouts == pytest.approx([2.0, 0.9])
