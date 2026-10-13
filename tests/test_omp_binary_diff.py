import copy
import json
import subprocess
import sys

import pytest

from test_omp_analysis import SCRIPTS, analysis, load_script, namespace


diff = load_script("binary_diff")


@pytest.fixture
def snapshots(namespace):
    before = analysis.collect_snapshot(namespace, "owned-before")
    after = copy.deepcopy(before)
    after["source"].update(sha256="b" * 64, image_base="0x150000000", database_id="owned-after")
    for row in after["functions"]:
        row["rva"] = hex(int(row["rva"], 16) + 0x100)
        row["ea"] = hex(0x150000000 + int(row["rva"], 16))
    return before, after


def test_unique_name_maps_layout_change_without_mutating_inputs(snapshots):
    before, after = snapshots
    frozen = copy.deepcopy(snapshots)
    report = diff.compare_snapshots(before, after)
    assert len(report["matches"]) == 1
    match = report["matches"][0]
    assert match["mapping_basis"] == "unique_symbol_name" and "rva" in match["changed_fields"]
    assert report["unmatched_before"][0]["name"].startswith("sub_")
    assert snapshots == frozen


def test_explicit_mapping_handles_rename_and_takes_priority(snapshots):
    before, after = snapshots
    after["functions"][0]["name"] = "renamed_check"
    report = diff.compare_snapshots(before, after, [{"old_rva": "0x1000", "new_rva": "0x1100"}])
    assert report["matches"][0]["mapping_basis"] == "user_mapping"
    assert "name" in report["matches"][0]["changed_fields"]


def test_same_rva_and_duplicate_names_do_not_establish_identity(snapshots):
    before, after = snapshots
    for row in before["functions"] + after["functions"]:
        row["name"] = "duplicate"
    after["functions"][0].update(rva="0x1000", ea="0x150001000")
    report = diff.compare_snapshots(before, after)
    assert report["matches"] == []
    assert len(report["unmatched_before"]) == len(report["unmatched_after"]) == 2


def test_partial_hashes_and_fallback_remain_distinct(snapshots):
    before, after = snapshots
    before["coverage"].update(functions_total=3, functions_truncated=True)
    before["functions"][0].update(bytes_hashed=2, bytes_truncated=True, pseudocode="asm", pseudocode_kind="assembly_fallback")
    report = diff.compare_snapshots(before, after)
    row = report["matches"][0]
    assert report["coverage_truncated"]
    assert row["byte_comparison"] == "partial_or_missing_bytes"
    assert row["before"]["pseudocode"]["available"] is False
    assert row["after"]["pseudocode"]["kind"] == "not_collected"


@pytest.mark.parametrize("field,value", [("architecture", "arm64"), ("bitness", 32), ("format", "ELF")])
def test_incompatible_sources_fail(snapshots, field, value):
    before, after = snapshots
    after["source"][field] = value
    with pytest.raises(ValueError):
        diff.compare_snapshots(before, after)


@pytest.mark.parametrize("mapping", [
    [{"old_rva": "0x1000", "new_rva": "0x1100"}] * 2,
    [{"old_rva": "0x1000", "new_rva": "0x1100"}, {"old_rva": "0x1200", "new_rva": "0x1100"}],
    [{"old_rva": "0x9999", "new_rva": "0x1100"}],
])
def test_mapping_conflicts_fail(snapshots, mapping):
    with pytest.raises(ValueError):
        diff.compare_snapshots(*snapshots, mapping)


@pytest.mark.parametrize("mutation", [
    lambda r: r["functions"][0].update(ea="0x140001000"),
    lambda r: r["source"].update(sha256="bad"),
    lambda r: r["coverage"].update(functions_total=3, functions_truncated=False),
    lambda r: r["functions"][0].update(bytes_truncated=True),
])
def test_invalid_identity_or_false_coverage_fails(snapshots, mutation):
    before, after = snapshots
    mutation(after)
    with pytest.raises(ValueError):
        diff.compare_snapshots(before, after)


def test_cli_creates_new_file_and_refuses_overwrite_or_input_alias(snapshots, tmp_path):
    before, after = [tmp_path / name for name in ("before.json", "after.json")]
    for path, snapshot in zip((before, after), snapshots):
        path.write_text(json.dumps(snapshot), encoding="utf-8")
    output = tmp_path / "comparison.json"
    command = [sys.executable, str(SCRIPTS / "binary_diff.py"), "--before", str(before), "--after", str(after), "--output"]
    assert subprocess.run([*command, str(output)], capture_output=True).returncode == 0
    original = output.read_bytes()
    assert subprocess.run([*command, str(output)], capture_output=True).returncode == 1
    assert output.read_bytes() == original
    input_bytes = before.read_bytes()
    assert subprocess.run([*command, str(before)], capture_output=True).returncode == 1
    assert before.read_bytes() == input_bytes


@pytest.mark.parametrize("payload", ['{"field":1,"field":2}', '{"field":NaN}'])
def test_cli_json_loader_rejects_ambiguous_inputs(tmp_path, payload):
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        diff._load(path)
