import copy
import json

import pytest

from test_omp_analysis import analysis, load_script, namespace


hooks = load_script("hook_plan")


@pytest.fixture
def artifact(namespace):
    return analysis.collect_snapshot(namespace, "owned-fixture")


def test_generated_plan_preserves_source_and_unverified_status(artifact):
    frozen = copy.deepcopy(artifact)
    report = hooks.generate_hook_plan(artifact, "owned.exe", ["0x1000"], max_events=2, arg_count=1)
    assert report["status"] == "planned_not_run" and report["observations"] == []
    assert report["source"] == artifact["source"] and report["runtime"]["pointer_size"] == 8
    assert report["runtime"]["targets"][0]["rva"] == "0x1000"
    assert all(row["status"] == "unverified" for row in report["preconditions"])
    assert artifact == frozen
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("module", ["", " owned.exe", "../owned.exe", "owned\n.exe", "owned\x7f.exe"])
def test_module_basename_cannot_contain_controls_or_paths(artifact, module):
    with pytest.raises(ValueError):
        hooks.generate_hook_plan(artifact, module)


@pytest.mark.parametrize("budget,value", [("arg_count", True), ("arg_count", 9), ("max_events", 0), ("duration_seconds", 3601), ("max_targets", 0)])
def test_bad_output_budgets_fail(artifact, budget, value):
    with pytest.raises(ValueError):
        hooks.generate_hook_plan(artifact, "owned.exe", **{budget: value})


@pytest.mark.parametrize("requested", [["0x1000", "0x1000"], ["0xdead"], [], ["-1"]])
def test_target_selection_is_known_unique_and_hex(artifact, requested):
    with pytest.raises(ValueError):
        hooks.generate_hook_plan(artifact, "owned.exe", requested)


def test_duplicate_targets_mismatched_ea_unknown_isa_and_source_fail(artifact):
    for mutate in (
        lambda value: value["functions"].append(value["functions"][0]),
        lambda value: value["functions"][0].update(ea="0x140001001"),
        lambda value: value["source"].update(architecture="unknown"),
        lambda value: value["source"].update(sha256="missing"),
    ):
        value = copy.deepcopy(artifact)
        mutate(value)
        with pytest.raises(ValueError):
            hooks.generate_hook_plan(value, "owned.exe")
