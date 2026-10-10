import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from jsonschema import Draft202012Validator

from reverse_skill import evolution
from reverse_skill.errors import ToolOperationError


ROOT = Path(__file__).resolve().parents[1]
TRACE_SCHEMA = ROOT / "skills" / "evolution" / "schemas" / "trace-card.schema.json"
GOAL_SCHEMA = ROOT / "skills" / "evolution" / "schemas" / "goal-contract.schema.json"


@pytest.fixture
def trace_card() -> dict:
    return {
        "schema_version": 2,
        "trace_id": "goal-1-trace",
        "goal_id": "goal-1",
        "route": {"macro_route": "reverse-engineering"},
        "steps": [
            {
                "step_id": 1,
                "prefix_summary": "input received",
                "decision": "inspect metadata",
                "outcome": "progress",
                "evidence_refs": [
                    {
                        "id": "ev-1",
                        "source": "tool@1.2.3",
                        "input_id": "artifact-1",
                        "coverage": "headers and first 64 KiB",
                        "limitations": ["not a full-file scan"],
                    }
                ],
            }
        ],
        "oracle_results": [],
        "unknowns": [
            {
                "question": "Does the payload execute at runtime?",
                "status": "open",
                "requires": "controlled runtime observation",
                "affects_outcome": True,
                "supporting_evidence": [],
                "contradicting_evidence": [],
            }
        ],
        "memory_tier": "candidate",
    }

def test_trace_card_v2_tracks_evidence_coverage_and_unknown_resolution(trace_card: dict) -> None:
    schema = json.loads(TRACE_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    trace = trace_card
    validator.validate(trace)

    missing_unknowns = copy.deepcopy(trace)
    del missing_unknowns["unknowns"]
    assert not validator.is_valid(missing_unknowns)

    empty_evidence = copy.deepcopy(trace)
    empty_evidence["steps"][0]["evidence_refs"] = []
    validator.validate(empty_evidence)

    missing_coverage = copy.deepcopy(trace)
    del missing_coverage["steps"][0]["evidence_refs"][0]["coverage"]
    assert not validator.is_valid(missing_coverage)

    unresolved_without_evidence = copy.deepcopy(trace)
    unresolved_without_evidence["unknowns"][0]["status"] = "resolved"
    assert not validator.is_valid(unresolved_without_evidence)

    trace["unknowns"][0]["status"] = "resolved"
    trace["unknowns"][0]["supporting_evidence"] = ["ev-1"]
    validator.validate(trace)


def test_goal_evaluation_budget_is_nonnegative() -> None:
    schema = json.loads(GOAL_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    goal = {
        "schema_version": 1,
        "goal_id": "evolve-1",
        "task_summary": "Compare skill candidates",
        "authorization_scope": {"kind": "lab_fixture", "boundary": "local benchmark"},
        "inputs": [{"id": "bench", "kind": "fixture", "path_or_ref": "bench.json"}],
        "desired_outputs": [{"kind": "report", "required": True, "acceptance": "per-track scores"}],
        "success_oracles": [{"id": "oracle", "kind": "fixture_verifier", "expected": "all applicable tracks"}],
        "budgets": {"max_evaluations": 2},
    }
    assert validator.is_valid(goal)
    goal["budgets"]["max_evaluations"] = -1
    assert not validator.is_valid(goal)


@pytest.fixture
def evolution_inputs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "candidate": tmp_path / "candidate.md",
        "catalog": tmp_path / "catalog.json",
        "fixtures": tmp_path / "fixtures.json",
        "output": tmp_path / "output",
    }
    paths["candidate"].write_text("Route the task.", encoding="utf-8")
    paths["catalog"].write_text(
        json.dumps({"macro_routes": [{"id": "reverse-engineering"}]}), encoding="utf-8"
    )
    paths["fixtures"].write_text(
        json.dumps({"fixtures": [{
            "id": "case-1",
            "track": "routing",
            "task": "Inspect this binary.",
            "expected_route": "reverse-engineering",
        }]}),
        encoding="utf-8",
    )
    return paths


def _evolve_inputs(paths: dict[str, Path]) -> dict:
    return evolution.evolve(
        paths["candidate"], paths["catalog"], paths["fixtures"], paths["output"], 3, 1, 1
    )


def test_evolution_serializes_unchanged_catalog_once(
    evolution_inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    original_dumps = evolution.json.dumps
    catalog = json.loads(evolution_inputs["catalog"].read_text(encoding="utf-8"))
    catalog_serializations = 0

    def counting_dumps(value: object, *args: object, **kwargs: object) -> str:
        nonlocal catalog_serializations
        if value == catalog:
            catalog_serializations += 1
        return original_dumps(value, *args, **kwargs)

    monkeypatch.setattr(evolution.json, "dumps", counting_dumps)
    monkeypatch.setattr(evolution, "_omp", lambda *_: '{"route_id":"reverse-engineering"}')

    _evolve_inputs(evolution_inputs)

    assert catalog_serializations == 1


@pytest.mark.parametrize(
    ("input_name", "limit", "error_prefix"),
    [
        ("candidate", evolution.MAX_CANDIDATE_BYTES, "candidate exceeds"),
        ("fixtures", evolution.MAX_FIXTURE_BYTES, "Fixture file exceeds"),
        ("catalog", evolution.MAX_FIXTURE_BYTES, "Routing catalog exceeds"),
    ],
)
def test_evolution_rejects_oversized_inputs_after_bounded_read(
    evolution_inputs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    input_name: str,
    limit: int,
    error_prefix: str,
) -> None:
    class TrackedInput(io.BytesIO):
        bytes_read = 0

        def read(self, size: int = -1) -> bytes:
            data = super().read(size)
            self.bytes_read += len(data)
            return data

    # Invalid UTF-8 also proves the size rejection precedes decoding.
    stream = TrackedInput(b"\xff" * (limit + 100))
    original_open = Path.open

    def open_input(path: Path, *args, **kwargs):
        if path == evolution_inputs[input_name]:
            return stream
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_input)
    with pytest.raises(ToolOperationError, match=f"^{error_prefix} {limit} bytes"):
        _evolve_inputs(evolution_inputs)
    assert 0 < stream.bytes_read <= limit + 1
    assert stream.closed
    assert not evolution_inputs["output"].exists()


@pytest.mark.parametrize(
    ("input_name", "payload", "error_prefix", "cause_type"),
    [
        ("candidate", b"\xff", "candidate must be UTF-8:", UnicodeDecodeError),
        ("fixtures", b"\xff", "Cannot load fixture JSON", UnicodeDecodeError),
        ("catalog", b"\xff", "Cannot load routing catalog", UnicodeDecodeError),
        ("fixtures", b"{", "Cannot load fixture JSON", json.JSONDecodeError),
        ("catalog", b"{", "Cannot load routing catalog", json.JSONDecodeError),
    ],
)
def test_evolution_preserves_input_decoding_errors(
    evolution_inputs: dict[str, Path],
    input_name: str,
    payload: bytes,
    error_prefix: str,
    cause_type: type[Exception],
) -> None:
    evolution_inputs[input_name].write_bytes(payload)
    with pytest.raises(ToolOperationError, match=f"^{error_prefix}") as caught:
        _evolve_inputs(evolution_inputs)
    assert isinstance(caught.value.__cause__, cause_type)


@pytest.mark.parametrize(
    ("input_name", "error_prefix"),
    [
        ("candidate", "Cannot read candidate"),
        ("fixtures", "Cannot load fixture JSON"),
        ("catalog", "Cannot load routing catalog"),
    ],
)
def test_evolution_preserves_input_filesystem_errors(
    evolution_inputs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    input_name: str,
    error_prefix: str,
) -> None:
    original_open = Path.open
    denied = PermissionError("controlled read denial")

    def open_input(path: Path, *args, **kwargs):
        if path == evolution_inputs[input_name]:
            raise denied
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_input)
    with pytest.raises(ToolOperationError, match=f"^{error_prefix}") as caught:
        _evolve_inputs(evolution_inputs)
    assert caught.value.__cause__ is denied


def test_trace_semantics_accept_observed_and_unobserved_cards(trace_card: dict) -> None:
    assert evolution.validate_trace_card(trace_card) is None
    trace_card["unknowns"][0]["status"] = "resolved"
    trace_card["unknowns"][0]["supporting_evidence"] = ["ev-1"]
    trace_card["oracle_results"] = [{"oracle_id": "oracle-1", "status": "pass", "evidence_refs": ["ev-1"]}]
    trace_card["memory_tier"] = "validated"
    trace_card["promotion_candidate"] = True
    assert evolution.validate_trace_card(trace_card) is None
    assert Draft202012Validator(json.loads(TRACE_SCHEMA.read_text(encoding="utf-8"))).is_valid(trace_card)


@pytest.mark.parametrize("mutation", [
    lambda trace: trace.update(trace_id=" "),
    lambda trace: trace["steps"][0]["evidence_refs"][0].update(id=""),
    lambda trace: trace["steps"][0]["evidence_refs"][0].update(coverage=" "),
    lambda trace: trace["steps"].append(copy.deepcopy(trace["steps"][0])),
    lambda trace: trace["steps"][0]["evidence_refs"].append(copy.deepcopy(trace["steps"][0]["evidence_refs"][0])),
    lambda trace: trace["unknowns"][0].update(supporting_evidence=[""]),
    lambda trace: trace["unknowns"][0].update(contradicting_evidence=["missing"]),
    lambda trace: trace["unknowns"][0].update(supporting_evidence=["ev-1", "ev-1"]),
    lambda trace: trace["unknowns"][0].update(status="resolved"),
    lambda trace: trace["unknowns"][0].pop("affects_outcome"),
    lambda trace: trace.update(oracle_results=[{}]),
    lambda trace: trace.update(oracle_results=[{"oracle_id": "o", "status": "pass", "evidence_refs": []}]),
    lambda trace: trace.update(started_at=42),
    lambda trace: trace["steps"][0].update(cost=[]),
    lambda trace: trace.update(learning=[]),
    lambda trace: trace.update(oracle_results=[{"oracle_id": "o", "status": "pass", "evidence_refs": ["missing"]}]),
    lambda trace: trace.update(memory_tier="validated"),
    lambda trace: trace.update(promotion_candidate=True),
    lambda trace: trace.update(promotion_candidate="true"),
])
def test_trace_semantics_reject_unsupported_claims(trace_card: dict, mutation) -> None:
    mutation(trace_card)
    with pytest.raises(ToolOperationError, match="Invalid TraceCard"):
        evolution.validate_trace_card(trace_card)


@pytest.mark.parametrize("status", ["pass", "fail", "not_run"])
def test_trace_validated_requires_all_oracles_passed_and_no_relevant_unknowns(trace_card: dict, status: str) -> None:
    trace_card["memory_tier"] = "validated"
    trace_card["oracle_results"] = [{"oracle_id": "o", "status": status, "evidence_refs": ["ev-1"]}]
    validator = Draft202012Validator(json.loads(TRACE_SCHEMA.read_text(encoding="utf-8")))
    # Even a passed oracle cannot erase an outcome-affecting open unknown.
    assert not validator.is_valid(trace_card)
    with pytest.raises(ToolOperationError):
        evolution.validate_trace_card(trace_card)
    trace_card["unknowns"][0]["affects_outcome"] = False
    if status == "pass":
        validator.validate(trace_card)
        evolution.validate_trace_card(trace_card)
    else:
        assert not validator.is_valid(trace_card)
        with pytest.raises(ToolOperationError):
            evolution.validate_trace_card(trace_card)


@pytest.mark.parametrize("trace", [None, [], {}, {"schema_version": 1}])
def test_trace_semantics_reject_non_cards(trace: object) -> None:
    with pytest.raises(ToolOperationError):
        evolution.validate_trace_card(trace)


@pytest.mark.parametrize("output", [
    "",
    'Here is the answer:\n{"route_id":"reverse-engineering"}',
    '{"route_id":null}\n{"route_id":"reverse-engineering"}',
    '{"route_id":"reverse-engineering"}\ntrailing prose',
    '{"route_id":"reverse-engineering"}\nWorking...',
    'Working...\nWorking...\n{"route_id":"reverse-engineering"}',
    '```json\n{"route_id":"reverse-engineering"}\n```',
    '{"route_id":"missing"}',
    '{"route_id":42}',
    '{"route_id":true}',
    '{"route_id":[]}',
    '{"route_id":null,"extra":1}',
    '{"route_id":"missing","route_id":"reverse-engineering"}',
    '{"route_id":{"nested":1,"nested":2}}',
    '["reverse-engineering"]',
])
def test_route_response_rejects_invalid_complete_answers(output: str) -> None:
    route, error = evolution._parse_response(output, {"reverse-engineering"})
    assert route is None
    assert error is not None


@pytest.mark.parametrize("prefix", ["", "Working...\n", "Working...\r\n"])
def test_route_response_accepts_whole_json_and_only_leading_print_framing(prefix: str) -> None:
    assert evolution._parse_response(prefix + '{\n "route_id": "reverse-engineering"\n}', {"reverse-engineering"}) == ("reverse-engineering", None)
    assert evolution._parse_response(prefix + '{"route_id":null}', {"reverse-engineering"}) == (None, None)


def test_omp_subprocess_uses_stdin_and_isolated_bounded_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(evolution.shutil, "which", lambda _: "C:/Program Files/OMP/omp.exe")

    def run(args: list[str], **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="Working...\nexact output\n", stderr="")

    monkeypatch.setattr(evolution.subprocess, "run", run)
    assert evolution._omp("large task\n" * 10_000, 'system "quoted" 中文', 7) == "Working...\nexact output\n"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "C:/Program Files/OMP/omp.exe"
    for flag in ("--no-session", "--no-tools", "--no-skills", "--no-rules", "--no-extensions", "--print"):
        assert flag in args
    assert args[args.index("--max-time") + 1] == "7"
    assert args[args.index("--append-system-prompt") + 1] == 'system "quoted" 中文'
    assert not Path(args[args.index("--cwd") + 1]).exists()
    assert kwargs == {
        "input": "large task\n" * 10_000, "capture_output": True,
        "encoding": "utf-8", "errors": "replace", "timeout": 17, "check": False,
    }


@pytest.mark.parametrize("failure", ["timeout", "oserror", "exit"])
def test_omp_subprocess_failures_preserve_diagnostics(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    monkeypatch.setattr(evolution.shutil, "which", lambda _: "omp.exe")

    def run(*args, **kwargs):
        if failure == "timeout":
            raise evolution.subprocess.TimeoutExpired(args[0], kwargs["timeout"])
        if failure == "oserror":
            raise OSError("controlled start failure")
        return SimpleNamespace(returncode=9, stdout="stdout detail", stderr="stderr detail")

    monkeypatch.setattr(evolution.subprocess, "run", run)
    expected = {"timeout": "exceeded 7 seconds", "oserror": "controlled start failure", "exit": "OMP exited 9: stderr detail"}
    with pytest.raises(ToolOperationError, match=expected[failure]):
        evolution._omp("task", "system", 7)


def test_windows_limit_is_not_applied_to_non_windows_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evolution.sys, "platform", "linux")
    monkeypatch.setattr(evolution, "MAX_WINDOWS_COMMAND_UNITS", 1)
    evolution._check_windows_argv(["omp", "valid on this platform"])


def test_windows_limit_counts_serialized_quotes_utf16_and_nul(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evolution.sys, "platform", "win32")
    args = ["C:/Program Files/OMP/omp.exe", 'quotes "\\" and emoji 🦄']
    units = len(evolution.subprocess.list2cmdline(args).encode("utf-16-le")) // 2 + 1
    monkeypatch.setattr(evolution, "MAX_WINDOWS_COMMAND_UNITS", units)
    evolution._check_windows_argv(args)
    monkeypatch.setattr(evolution, "MAX_WINDOWS_COMMAND_UNITS", units - 1)
    with pytest.raises(ToolOperationError, match="UTF-16 units"):
        evolution._check_windows_argv(args)


def test_oversized_windows_candidate_rejected_before_any_model_call(evolution_inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evolution.sys, "platform", "win32")
    # Byte-size passes, but Windows doubles embedded quotes in serialized argv.
    evolution_inputs["candidate"].write_text('"' * 20_000, encoding="utf-8")
    monkeypatch.setattr(evolution, "_omp", lambda *_: pytest.fail("must reject before baseline"))
    with pytest.raises(ToolOperationError, match="serialized Windows command"):
        _evolve_inputs(evolution_inputs)
    assert not evolution_inputs["output"].exists()


def test_actual_omp_argv_is_checked_before_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evolution.sys, "platform", "win32")
    monkeypatch.setattr(evolution.shutil, "which", lambda _: "omp.exe")
    monkeypatch.setattr(evolution.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("must reject before subprocess"))
    with pytest.raises(ToolOperationError, match="serialized Windows command"):
        evolution._omp("stdin task", '"' * 20_000, 1)


def test_promotion_candidacy_requires_validated_and_unique_oracles(trace_card: dict) -> None:
    trace_card["unknowns"] = []
    oracle = {"oracle_id": "oracle", "status": "pass", "evidence_refs": ["ev-1"]}
    trace_card["oracle_results"] = [oracle]
    trace_card["promotion_candidate"] = True
    with pytest.raises(ToolOperationError, match="requires validated"):
        evolution.validate_trace_card(trace_card)
    assert not Draft202012Validator(json.loads(TRACE_SCHEMA.read_text(encoding="utf-8"))).is_valid(trace_card)
    trace_card["memory_tier"] = "validated"
    evolution.validate_trace_card(trace_card)
    trace_card["oracle_results"].append(copy.deepcopy(oracle))
    with pytest.raises(ToolOperationError, match="oracle IDs"):
        evolution.validate_trace_card(trace_card)


def test_trace_with_no_evidence_can_be_candidate_but_not_validated(trace_card: dict) -> None:
    trace_card["steps"][0]["evidence_refs"] = []
    trace_card["unknowns"] = []
    trace_card["oracle_results"] = [{"oracle_id": "oracle", "status": "not_run", "evidence_refs": []}]
    evolution.validate_trace_card(trace_card)
    trace_card["memory_tier"] = "validated"
    with pytest.raises(ToolOperationError, match="all oracles passed"):
        evolution.validate_trace_card(trace_card)
