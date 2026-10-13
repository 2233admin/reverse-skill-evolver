"""Fixed upstream expectations; inference is tested without tool or model calls."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from reverse_skill.cli import cli
from reverse_skill.routing import build_plan, contains_keyword


ROOT = Path(__file__).resolve().parents[1]
BENCH = json.loads((ROOT / "tests/data/routing-benchmark.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", BENCH["cases"], ids=lambda case: case["hint"])
def test_fixed_upstream_route(case):
    plan = build_plan({"task": case["hint"]})
    assert plan.get("route", {}).get("base_id", "no_route") == case["expect_local"]
    assert plan["executed"] is False


def test_benchmark_is_complete():
    assert len(BENCH["cases"]) == 163
    assert sum(bool(case.get("quick")) for case in BENCH["cases"]) == 41


@pytest.mark.parametrize("task,expected", [
    ("Forefy audited skills exclude MCP servers", "asr-registry"),
    ("List Forefy ASR items for IDA binary analysis", "asr-registry"),
    ("List ASR items for an APK task, audited only", "asr-registry"),
    ("OMP native IDA inspect sample.exe", "native-binary"),
    ("OMP JavaScript captured signer replay", "js-browser-signature"),
])
def test_current_workflows_remain_selectable(task, expected):
    plan = build_plan({"task": task})
    assert plan["route"]["id"] == expected
    assert plan["status"] == "selected"
    assert plan["preflight"]["authorization_verified"] is False
    assert plan["preflight"]["capabilities_verified"] is False


def test_route_cli_preserves_machine_envelope():
    result = CliRunner().invoke(cli, ["--json", "route", "Analyze APK", "--input-path", "sample.apk"])
    assert result.exit_code == 0
    value = json.loads(result.output)
    assert value["ok"] is True and value["command"] == "route"
    assert value["data"]["route"]["skill"] == "apk-reverse/SKILL.md"


def test_explicit_route_and_token_boundaries():
    assert build_plan({"task": "example", "route_id": "asr-registry"})["route"]["id"] == "asr-registry"
    assert build_plan({"task": "unrelated", "route_id": "missing"})["status"] == "no_route"
    assert contains_keyword("session", "so") is False
    assert contains_keyword("sample.so", "so") is True
