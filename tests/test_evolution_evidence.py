import json
from pathlib import Path

import pytest

from reverse_skill import evolution


def test_evolve_report_retains_exact_task_with_failed_fixture_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = "  Inspect APK comet-739: 核对 native bridge.\nKeep this wording unchanged.  "
    candidate_path = tmp_path / "candidate.md"
    catalog_path = tmp_path / "catalog.json"
    fixtures_path = tmp_path / "fixtures.json"
    output_path = tmp_path / "run"
    candidate_path.write_text("Select the applicable macro route.", encoding="utf-8")
    catalog_path.write_text(
        json.dumps({"macro_routes": [{"id": "reverse-engineering"}]}),
        encoding="utf-8",
    )
    fixtures_path.write_text(
        json.dumps({"fixtures": [{
            "id": "comet-739",
            "track": "routing",
            "task": task,
            "expected_route": "reverse-engineering",
        }]}),
        encoding="utf-8",
    )
    # Valid abstentions fail the fixture; reflection returns replacement instructions.
    responses = iter([
        '{"route_id":null}',
        '{"route_id":null}',
        "Route APK tasks to the reverse-engineering macro route.",
        '{"route_id":null}',
    ])
    monkeypatch.setattr(evolution, "_omp", lambda *_: next(responses))

    evolution.evolve(
        candidate_path, catalog_path, fixtures_path, output_path,
        max_evaluations=3, max_reflections=1, timeout=1,
    )

    report = json.loads((output_path / "results.json").read_text(encoding="utf-8"))
    assert report["candidates"]
    for evaluation in [report["baseline"], *report["candidates"]]:
        assert len(evaluation["outcomes"]) == 1
        outcome = evaluation["outcomes"][0]
        assert outcome["fixture_id"] == "comet-739"
        assert outcome["expected_route"] == "reverse-engineering"
        assert outcome["route_id"] is None
        assert outcome["passed"] is False
        assert outcome["invalid"] is None
        assert outcome.get("task") == task
