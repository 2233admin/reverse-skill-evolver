"""Black-box routing benchmark: 163 upstream cases frozen against our router.

Each case asserts the packaged router's selected stable route id equals the
fixture's ``expect_local``. The fixture is independent of the upstream repo
(copied data) and only the *selection* is asserted: capability/input/authorization
preflight gates are irrelevant to routing selection, so the capability probe layer
is stubbed for speed and hermeticity (same selection, 100x faster, no host probes).
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH_PATH = ROOT / "tests" / "data" / "routing-benchmark.json"
CROSSWALK_PATH = ROOT / "reverse_skill" / "data" / "upstream-route-crosswalk.json"


@pytest.fixture(autouse=True)
def _fast_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace live capability probing with a static stub.

    Route *selection* (score_route / aliases / target kinds) does not read
    capability state; only preflight gates do. Keeping the stub hermetic means
    the 163-case benchmark runs in <1s on any host without TCP/which probes.
    """
    import reverse_skill.routing as routing

    def stub() -> dict:
        return {
            "python": {
                "kind": "tool",
                "available": True,
                "resolved_path": sys.executable,
                "sources": ["benchmark-stub"],
            }
        }

    monkeypatch.setattr(routing, "load_capabilities", stub)


def load_benchmark() -> dict:
    return json.loads(BENCH_PATH.read_text(encoding="utf-8"))


def test_benchmark_matches_upstream_case_count() -> None:
    bench = load_benchmark()
    assert bench["schema_version"] == 1
    assert len(bench["cases"]) == 163
    quick = [case for case in bench["cases"] if case.get("quick")]
    assert len(quick) == 41


def test_every_upstream_r_id_has_a_crosswalk_entry() -> None:
    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    bench = load_benchmark()
    upstream_ids = {case["expect"] for case in bench["cases"]}
    missing = upstream_ids - set(crosswalk["routes"].keys())
    assert not missing, f"no crosswalk entry for {sorted(missing)}"


def test_crosswalk_statuses_are_declared() -> None:
    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    for r_id, entry in crosswalk["routes"].items():
        assert entry["status"] in {"adopted", "superseded", "rejected"}
        if entry["status"] == "adopted":
            assert entry["mapped_route"], f"{r_id} adopted but has no mapped_route"
        if entry["mapped_route"]:
            assert entry["mapped_skill"], f"{r_id} has mapped_route but no mapped_skill"


def test_rejected_domains_have_no_mapped_route() -> None:
    """Rejected domains must not have been force-wired into the router.

    A rejected domain can still be reached by a *pre-existing* alias of an adopted
    route (e.g. sigma -> malware-analysis); that divergence is documented in the
    crosswalk note, not papered over with a new keyword or fallback edge.
    """
    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    for r_id, entry in crosswalk["routes"].items():
        if entry["status"] == "rejected":
            assert entry["mapped_route"] is None, (
                f"{r_id} is rejected but crosswalk maps it to {entry['mapped_route']}"
            )


def test_router_selection_matches_frozen_expectations() -> None:
    import reverse_skill.routing as routing

    bench = load_benchmark()
    failures = []
    for case in bench["cases"]:
        plan = routing.build_plan({"task": case["hint"]})
        status = plan.get("status")
        route = plan.get("route") or {}
        base = str(route.get("base_id") or route.get("id") or "")
        selected = "no_route" if status == "no_route" or not base else base
        if selected != case["expect_local"]:
            failures.append(
                {
                    "hint": case["hint"],
                    "expect_upstream": case["expect"],
                    "expect_local": case["expect_local"],
                    "selected": selected,
                }
            )
    assert not failures, (
        f"{len(failures)} benchmark case(s) drifted from the frozen expectations. "
        "Update tests/data/routing-benchmark.json only after a human review of the router change:\n"
        + json.dumps(failures[:10], ensure_ascii=False, indent=1)
    )


def test_quick_cases_are_a_subset_and_pass() -> None:
    import reverse_skill.routing as routing

    bench = load_benchmark()
    quick = [case for case in bench["cases"] if case.get("quick")]
    for case in quick:
        plan = routing.build_plan({"task": case["hint"]})
        status = plan.get("status")
        route = plan.get("route") or {}
        base = str(route.get("base_id") or route.get("id") or "")
        selected = "no_route" if status == "no_route" or not base else base
        assert selected == case["expect_local"], case["hint"]


def _derive_expectation(crosswalk: dict, expect: str) -> str:
    """Mirror of the generator's crosswalk derivation (no router call)."""
    entry = crosswalk["routes"].get(expect, {})
    if entry.get("status") == "rejected":
        return "no_route"
    return str(entry.get("mapped_route") or "no_route")


def test_fixture_expectations_are_independent_of_implementation() -> None:
    """The frozen expectations must be reproducible from the reviewed sources.

    The generator (scripts/regenerate_routing_benchmark.py) derives expect_local
    from the crosswalk plus its OVERRIDES table; it never runs the router. This
    test re-derives the same way, so a fixture edited to match whatever the
    router currently outputs would fail here.
    """
    import importlib.util

    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    bench = load_benchmark()

    script_path = ROOT / "scripts" / "regenerate_routing_benchmark.py"
    spec = importlib.util.spec_from_file_location("regenerate_routing_benchmark", script_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    mismatches = []
    for case in bench["cases"]:
        derived = _derive_expectation(crosswalk, case["expect"])
        if (case["expect"], case["hint"]) in generator.OVERRIDES:
            derived = generator.OVERRIDES[(case["expect"], case["hint"])]
        if derived != case["expect_local"]:
            mismatches.append((case["expect"], case["hint"], derived, case["expect_local"]))
    assert not mismatches, (
        f"{len(mismatches)} fixture expectation(s) are not reproducible from the reviewed "
        "crosswalk + OVERRIDES; expectations must not be derived from the router:\n"
        + json.dumps(mismatches[:10], ensure_ascii=False, indent=1)
    )


def test_override_table_is_complete_and_consistent() -> None:
    """Every override entry must exist in the fixture and explain a real divergence."""
    import importlib.util

    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    bench = load_benchmark()
    fixture_keys = {(case["expect"], case["hint"]) for case in bench["cases"]}

    script_path = ROOT / "scripts" / "regenerate_routing_benchmark.py"
    spec = importlib.util.spec_from_file_location("regenerate_routing_benchmark", script_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    # No stale entries pointing at hints that no longer exist.
    stale = set(generator.OVERRIDES) - fixture_keys
    assert not stale, f"stale override entries: {sorted(stale)}"

    # Every override must actually change the crosswalk derivation.
    for (expect, hint), expected in generator.OVERRIDES.items():
        assert (expect, hint) in fixture_keys
        derived = _derive_expectation(crosswalk, expect)
        assert derived != expected, (
            f"override for {expect!r} {hint!r} duplicates the crosswalk derivation {derived}"
        )
