import hashlib
import json
from pathlib import Path

import pytest

from reverse_skill import evolution
from reverse_skill.errors import ToolOperationError
from reverse_skill.evolution import CandidateScore, pareto_frontier


def test_pareto_frontier_keeps_tradeoffs_and_drops_dominated_candidates() -> None:
    east = CandidateScore("east", {"apk": 1.0, "native": 0.25}, {"apk": 0, "native": 0})
    west = CandidateScore("west", {"apk": 0.25, "native": 1.0}, {"apk": 0, "native": 0})
    worse = CandidateScore("worse", {"apk": 0.25, "native": 0.25}, {"apk": 1, "native": 1})

    assert {score.id for score in pareto_frontier([east, west, worse])} == {"east", "west"}


@pytest.fixture
def optimizer_inputs(tmp_path: Path) -> dict:
    catalog = {
        "macro_routes": [
            {"id": "east", "trigger": "Eastern work", "fallback": "west"},
            {"id": "west", "trigger": "Western work", "fallback": None},
        ],
        "priority": ["east", "west"],
    }
    cases = [
        {"id": "east-case", "track": "east-track", "task": "  Exact frozen 东方 task.\nKeep trailing spaces.  ", "expected_route": "east"},
        {"id": "west-case", "track": "west-track", "task": "Exact frozen west task.", "expected_route": "west"},
        {"id": "unmatched-case", "track": "west-track", "task": "Exact frozen unrelated task.", "expected_route": None},
    ]
    paths = {name: tmp_path / f"{name}.json" for name in ("catalog", "fixtures")}
    paths["candidate"] = tmp_path / "curated.md"
    paths["output"] = tmp_path / "run"
    paths["catalog"].write_bytes(json.dumps(catalog, ensure_ascii=False, indent=2).encode("utf-8"))
    paths["fixtures"].write_bytes(json.dumps({"fixtures": cases}, ensure_ascii=False, indent=2).encode("utf-8"))
    paths["candidate"].write_text("Curated instructions.\nWorking...\nPreserve this literal line.", encoding="utf-8")
    return {"paths": paths, "catalog": catalog, "cases": cases}


@pytest.mark.parametrize(("max_evaluations", "max_reflections", "stop_reason"), [
    (4, 2, "budget_reached"),
    (5, 2, "budget_reached"),
    (6, 3, "all_frontier_candidates_passed"),
])
def test_real_reflection_proposals_evaluate_full_frozen_suite_and_keep_ancestors(
    optimizer_inputs: dict, monkeypatch: pytest.MonkeyPatch,
    max_evaluations: int, max_reflections: int, stop_reason: str,
) -> None:
    paths, cases, catalog = (optimizer_inputs[name] for name in ("paths", "cases", "catalog"))
    frozen_bytes = {name: paths[name].read_bytes() for name in ("catalog", "fixtures")}
    curated_text = paths["candidate"].read_bytes().decode("utf-8")
    proposal_texts = ["Proposal one.\nWorking...\nKeep successes.", "Proposal two: route both and abstain when unrelated."]
    outputs = {
        "": ['{"route_id":null}', '{"route_id":null}', '{"route_id":null}'],
        curated_text: ['Working...\r\n{"route_id":"east"}\r\n', 'prose\n{"route_id":"west"}', '{"route_id":"east"}'],
        proposal_texts[0]: ['{"route_id":"east"}', '{"route_id":"west"}', '{"route_id":"west"}'],
        proposal_texts[1]: ['{"route_id":"east"}', '{"route_id":"west"}', '{"route_id":null}'],
    }
    calls = []
    reflections = []
    fixture_indices = {text: 0 for text in outputs}

    def omp(prompt: str, system: str, timeout: int) -> str:
        calls.append((prompt, system, timeout))
        if prompt.startswith("You are editing"):
            payload = json.loads(prompt.split("Reflection data:\n", 1)[1])
            reflections.append(payload)
            return "Working...\n" + proposal_texts[len(reflections) - 1]
        assert json.loads(prompt.split("Routing catalog:\n", 1)[1].split("\nTask:\n", 1)[0]) == catalog
        index = fixture_indices[system]
        assert prompt.split("\nTask:\n", 1)[1] == cases[index]["task"]
        fixture_indices[system] += 1
        # Prove subsequent calls and archived identities don't re-read mutable input paths.
        if len(calls) == 1:
            paths["catalog"].write_bytes(b"mutated catalog")
            paths["fixtures"].write_bytes(b"mutated fixtures")
            paths["candidate"].write_text("mutated curated text", encoding="utf-8")
        return outputs[system][index]

    monkeypatch.setattr(evolution, "_omp", omp)
    report = evolution.evolve(
        paths["candidate"], paths["catalog"], paths["fixtures"], paths["output"],
        max_evaluations, max_reflections, 7,
    )
    assert report["evaluations_consumed"] == 4
    assert report["reflections_consumed"] == 2
    assert len(calls) == 4 * len(cases) + 2
    assert all(count == len(cases) for count in fixture_indices.values())
    assert all(timeout == 7 for _, _, timeout in calls)
    assert report["termination_reason"] == stop_reason
    assert report["pareto_frontier"] == ["proposal-2"]
    assert report["promotion"].startswith("not_promoted;")
    assert paths["candidate"].read_text(encoding="utf-8") == "mutated curated text"
    assert reflections[0]["parent_candidate"] == curated_text
    assert reflections[1]["parent_candidate"] == proposal_texts[0]
    assert [row["fixture_id"] for row in reflections[0]["failed_fixtures"]] == ["west-case", "unmatched-case"]
    assert reflections[0]["failed_fixtures"][0]["raw_response"] == outputs[curated_text][1]
    assert reflections[0]["failed_fixtures"][0]["invalid"] is not None
    assert reflections[0]["successful_fixtures"][0]["raw_response"] == outputs[curated_text][0]
    for reflection in reflections:
        assert reflection["routing_catalog"] == catalog
        for row in reflection["failed_fixtures"] + reflection["successful_fixtures"]:
            assert row["task"] == next(case["task"] for case in cases if case["id"] == row["fixture_id"])
    for name, raw in frozen_bytes.items():
        identity = report["inputs"][name]
        assert (paths["output"] / identity["artifact"]).read_bytes() == raw
        assert identity["sha256"] == hashlib.sha256(raw).hexdigest()
    evaluations = [report["baseline"], *report["candidates"]]
    expected_texts = ["", curated_text, *proposal_texts]
    for row, text in zip(evaluations, expected_texts):
        assert row["candidate_text"] == text
        assert row["candidate_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert (paths["output"] / row["candidate_artifact"]).read_bytes() == text.encode("utf-8")
        assert row["input_sha256"] == {name: report["inputs"][name]["sha256"] for name in frozen_bytes}
        assert len(row["outcomes"]) == len(cases)
    curated, first, second = report["candidates"]
    assert curated["pass_rates"] == {"east-track": 1.0, "west-track": 0.0}
    assert curated["invalid_counts"] == {"east-track": 0, "west-track": 1}
    assert first["pass_rates"] == {"east-track": 1.0, "west-track": 0.5}
    assert second["pass_rates"] == {"east-track": 1.0, "west-track": 1.0}
    assert first["parent_id"] == curated["id"] and first["parent_sha256"] == curated["candidate_sha256"]
    assert second["parent_id"] == first["id"] and second["parent_sha256"] == first["candidate_sha256"]
    assert report["reflections"][0]["context"] == reflections[0]
    assert report["reflections"][0]["raw_response"] == "Working...\n" + proposal_texts[0]
    assert json.loads((paths["output"] / "results.json").read_text(encoding="utf-8")) == report


def test_all_passing_curated_stops_without_reflection(optimizer_inputs: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    paths, cases = optimizer_inputs["paths"], optimizer_inputs["cases"]
    calls = []

    def omp(prompt: str, system: str, timeout: int) -> str:
        assert not prompt.startswith("You are editing")
        case = cases[len(calls) % len(cases)]
        calls.append(prompt)
        return json.dumps({"route_id": case["expected_route"]})

    monkeypatch.setattr(evolution, "_omp", omp)
    report = evolution.evolve(paths["candidate"], paths["catalog"], paths["fixtures"], paths["output"], 3, 1, 1)
    assert len(calls) == 2 * len(cases)
    assert report["evaluations_consumed"] == 2
    assert report["reflections_consumed"] == 0
    assert report["reflections"] == []
    assert report["termination_reason"] == "all_frontier_candidates_passed"


@pytest.mark.parametrize(("evaluations", "reflections"), [(2, 1), (3, 0), (3, 2)])
def test_invalid_budgets_reject_before_model_use(optimizer_inputs: dict, monkeypatch: pytest.MonkeyPatch, evaluations: int, reflections: int) -> None:
    paths = optimizer_inputs["paths"]
    monkeypatch.setattr(evolution, "_omp", lambda *_: pytest.fail("budget must reject before model use"))
    with pytest.raises(ToolOperationError):
        evolution.evolve(paths["candidate"], paths["catalog"], paths["fixtures"], paths["output"], evaluations, reflections, 1)
    assert not paths["output"].exists()


@pytest.mark.parametrize(("response", "diagnostic"), [
    ("Working...\n", "empty candidate"),
    ('{"route_id":"east"}', "route answer"),
    ("x" * (evolution.MAX_CANDIDATE_BYTES + 1), "Reflected candidate exceeds"),
    ('"' * 20_000, "serialized Windows command"),
])
def test_invalid_reflection_never_evaluates_a_proposal(
    optimizer_inputs: dict, monkeypatch: pytest.MonkeyPatch, response: str, diagnostic: str,
) -> None:
    paths = optimizer_inputs["paths"]
    calls = []

    def omp(prompt: str, system: str, timeout: int) -> str:
        calls.append(prompt)
        if prompt.startswith("You are editing"):
            return response
        assert len(calls) <= 2 * len(optimizer_inputs["cases"])
        return '{"route_id":null}'

    monkeypatch.setattr(evolution, "_omp", omp)
    with pytest.raises(ToolOperationError, match=diagnostic):
        evolution.evolve(paths["candidate"], paths["catalog"], paths["fixtures"], paths["output"], 3, 1, 1)
    assert len(calls) == 2 * len(optimizer_inputs["cases"]) + 1
    assert not paths["output"].exists()
