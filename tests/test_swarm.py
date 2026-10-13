from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from threading import Barrier, Event, Lock

import pytest

from reverse_skill import evolution, swarm, swarm_cli
from reverse_skill.errors import ToolOperationError


def tasks(count: int = 2) -> list[dict[str, str]]:
    return [{"id": f"task-{i}", "role": "analyst", "instruction": f"Analyze evidence track {i}"}
            for i in range(count)]


def analysis(summary: str = "Evidence remains provisional") -> dict:
    return {"summary": summary, "evidence": ["context.txt: example import"], "limitations": ["Not run on a target"]}


def agent(prompt: str, system: str, timeout: int) -> str:
    assert "untrusted data" in system
    assert timeout > 0
    if prompt.startswith("Split the goal"):
        return json.dumps({"tasks": tasks()})
    return json.dumps(analysis())


def test_agents_really_overlap_and_archive_inputs(tmp_path: Path) -> None:
    barrier = Barrier(2)
    lock = Lock()
    active = peak = 0
    calls = []

    def concurrent_agent(prompt: str, system: str, timeout: int) -> str:
        nonlocal active, peak
        with lock:
            calls.append(prompt)
        if prompt.startswith("Analyze your assigned task"):
            payload = json.loads(prompt.split("Input data:\n", 1)[1])
            assert payload["context"] == "frozen evidence"
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=5)
            with lock:
                active -= 1
        elif prompt.startswith("Summarize"):
            payload = json.loads(prompt.split("Input data:\n", 1)[1])
            assert all(row["status"] == "succeeded" for row in payload["tasks"])
        return agent(prompt, system, timeout)

    output = tmp_path / "run"
    result = swarm.run_swarm("Identify behavior", "frozen evidence", output,
                             max_calls=4, max_parallel=2, invoke=concurrent_agent)
    assert peak == 2
    assert len(calls) == result["logical_calls_consumed"] == 4
    assert result["execution_status"] == "succeeded"
    assert result["analysis_status"] == "advisory"
    assert result["context_sha256"] == hashlib.sha256(b"frozen evidence").hexdigest()
    assert json.loads((output / "run.json").read_text()) == result
    assert (output / "context.txt").read_text() == "frozen evidence"
    records = list((output / "agents").glob("*.json"))
    assert len(records) == 4
    assert all(json.loads(path.read_text())["raw_response"] for path in records)


def test_one_failed_agent_does_not_erase_other_results(tmp_path: Path) -> None:
    calls = []

    def fail_one(prompt: str, system: str, timeout: int) -> str:
        calls.append(prompt)
        payload = json.loads(prompt.split("Input data:\n", 1)[1])
        if payload.get("task", {}).get("id") == "task-0":
            raise ToolOperationError("OMP evaluation exceeded 1 second")
        if prompt.startswith("Summarize"):
            assert [row["status"] for row in payload["tasks"]] == ["failed", "succeeded"]
        return agent(prompt, system, timeout)

    result = swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=4, invoke=fail_one)
    assert len(calls) == 4
    assert result["execution_status"] == "partial"
    assert result["tasks"][1]["result"] == analysis()
    assert "exceeded" in result["tasks"][0]["error"]
    assert result["summary"] == analysis()


def test_evidence_snapshot_preserves_utf8_bytes_and_hash(tmp_path: Path) -> None:
    context = "line1\nline2\r\n证据\n"
    output = tmp_path / "run"
    result = swarm.run_swarm("Analyze", context, output, max_calls=4, invoke=agent)
    frozen = (output / "context.txt").read_bytes()
    assert frozen == context.encode("utf-8")
    assert hashlib.sha256(frozen).hexdigest() == result["context_sha256"]


@pytest.mark.parametrize("plan,error", [
    ({"tasks": tasks(3)}, "1..2"),
    ({"tasks": [tasks(1)[0]] * 2}, "unique"),
    ({"tasks": [{**tasks(1)[0], "id": "../escape"}]}, "identifiers"),
    ({"tasks": [{**tasks(1)[0], "role": ""}]}, "nonempty"),
    ({"tasks": [{**tasks(1)[0], "extra": True}]}, "exactly"),
    ({"tasks": []}, "1..2"),
])
def test_bad_plan_stops_before_workers_and_preserves_response(tmp_path: Path, plan: dict, error: str) -> None:
    calls = []

    def bad_plan(*args) -> str:
        calls.append(args)
        return json.dumps(plan)

    result = swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=4, invoke=bad_plan)
    assert len(calls) == 1
    assert result["execution_status"] == "failed"
    assert error in result["errors"][0]
    record = json.loads((tmp_path / "run/agents/coordinator.json").read_text())
    assert json.loads(record["raw_response"]) == plan
    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize("response", [
    'explanation {"tasks": []}',
    '{"tasks": [], "tasks": []}',
    '```json\n{"tasks": []}\n```',
    '[]',
])
def test_planner_rejects_non_json_answers(tmp_path: Path, response: str) -> None:
    result = swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=4,
                             invoke=lambda *_: response)
    assert result["execution_status"] == "failed"
    assert result["logical_calls_consumed"] == 1
    assert result["tasks"] == []


def test_invalid_model_unicode_cannot_corrupt_the_run_record(tmp_path: Path) -> None:
    bad_role = {"tasks": [{**tasks(1)[0], "role": "\ud800"}]}
    result = swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=4,
                             invoke=lambda *_: json.dumps(bad_role))
    assert result["execution_status"] == "failed"
    assert "invalid Unicode" in result["errors"][0]
    assert json.loads((tmp_path / "run/run.json").read_text()) == result


@pytest.mark.parametrize("kwargs", [
    {"max_calls": 2}, {"max_calls": True}, {"max_parallel": 0}, {"max_tasks": 33}, {"timeout": 0},
])
def test_invalid_limits_do_not_call_agents(tmp_path: Path, kwargs: dict) -> None:
    options = {"max_calls": 4, **kwargs}
    with pytest.raises(ToolOperationError):
        swarm.run_swarm("Analyze", "evidence", tmp_path / "run", **options,
                         invoke=lambda *_: pytest.fail("Invalid limits must reject before model use"))
    assert not (tmp_path / "run").exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("existing result")
    with pytest.raises(ToolOperationError, match="fresh"):
        swarm.run_swarm("Analyze", "evidence", output, max_calls=4,
                         invoke=lambda *_: pytest.fail("Existing output must reject before model use"))
    assert marker.read_text() == "existing result"


def test_budget_reserves_coordinator_and_summary(tmp_path: Path) -> None:
    calls = []

    def one_task(prompt: str, system: str, timeout: int) -> str:
        calls.append(prompt)
        if prompt.startswith("Split"):
            assert "Return 1..1 tasks" in prompt
            return json.dumps({"tasks": tasks(1)})
        return json.dumps(analysis())

    result = swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=3, invoke=one_task)
    assert result["execution_status"] == "succeeded"
    assert len(calls) == result["logical_calls_consumed"] == 3


def test_invalid_summary_keeps_completed_worker_evidence(tmp_path: Path) -> None:
    def bad_summary(prompt: str, system: str, timeout: int) -> str:
        return '{}' if prompt.startswith("Summarize") else agent(prompt, system, timeout)

    result = swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=4, invoke=bad_summary)
    assert result["execution_status"] == "partial"
    assert all(row["status"] == "succeeded" for row in result["tasks"])
    assert result["summary"] is None
    assert result["errors"]


def test_interruption_retains_run_record(tmp_path: Path) -> None:
    def interrupt(*_) -> str:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        swarm.run_swarm("Analyze", "evidence", tmp_path / "run", max_calls=4, invoke=interrupt)
    result = json.loads((tmp_path / "run/run.json").read_text())
    assert result["execution_status"] == "interrupted"
    assert result["logical_calls_consumed"] == 1


@pytest.mark.parametrize("worker_fails", [False, True])
def test_interrupt_cancels_queued_calls_and_records_running_result(
    tmp_path: Path, monkeypatch, worker_fails: bool,
) -> None:
    started = Event()
    calls = []

    def blocked_agent(prompt: str, system: str, timeout: int) -> str:
        calls.append(prompt)
        if prompt.startswith("Split"):
            return json.dumps({"tasks": tasks(3)})
        if prompt.startswith("Analyze"):
            started.set()
            Event().wait(timeout=1)
            if worker_fails:
                raise ToolOperationError("Running call failed during interruption")
        return json.dumps(analysis())

    def interrupt_wait(_):
        assert started.wait(timeout=5)
        raise KeyboardInterrupt

    monkeypatch.setattr(swarm, "as_completed", interrupt_wait)
    output = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        swarm.run_swarm("Analyze", "evidence", output, max_calls=5,
                        max_parallel=1, invoke=blocked_agent)
    result = json.loads((output / "run.json").read_text())
    assert len(calls) == result["logical_calls_consumed"] == 2
    assert result["execution_status"] == "interrupted"
    assert result["summary"] is None
    assert [row["status"] for row in result["tasks"]] == [
        "failed" if worker_fails else "succeeded", "cancelled", "cancelled",
    ]
    if worker_fails:
        assert "Running call failed" in result["tasks"][0]["error"]
    else:
        assert result["tasks"][0]["result"] == analysis()
    assert {path.name for path in (output / "agents").glob("*.json")} == {
        "coordinator.json", "worker-task-0.json",
    }


@pytest.mark.parametrize("after_enqueue", [False, True])
def test_interrupt_during_submission_preserves_started_work(
    tmp_path: Path, monkeypatch, after_enqueue: bool,
) -> None:
    started = Event()
    calls = []
    executor_type = swarm.ThreadPoolExecutor

    class InterruptingExecutor(executor_type):
        def submit(self, fn, /, *args, **kwargs):
            index = args[0]
            if index == 2 and not after_enqueue:
                assert started.wait(timeout=5)
                raise KeyboardInterrupt
            future = super().submit(fn, *args, **kwargs)
            if index == 0 and after_enqueue:
                assert started.wait(timeout=5)
                raise KeyboardInterrupt
            return future

    def blocked_agent(prompt: str, system: str, timeout: int) -> str:
        calls.append(prompt)
        if prompt.startswith("Split"):
            return json.dumps({"tasks": tasks(4)})
        started.set()
        Event().wait(timeout=1)
        return json.dumps(analysis())

    monkeypatch.setattr(swarm, "ThreadPoolExecutor", InterruptingExecutor)
    output = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        swarm.run_swarm("Analyze", "evidence", output, max_calls=6,
                        max_parallel=1, invoke=blocked_agent)
    result = json.loads((output / "run.json").read_text())
    assert len(calls) == result["logical_calls_consumed"] == 2
    assert result["execution_status"] == "interrupted"
    assert [row["status"] for row in result["tasks"]] == [
        "succeeded", "cancelled", "cancelled", "cancelled",
    ]
    assert result["tasks"][0]["result"] == analysis()
    assert len(list((output / "agents").glob("*.json"))) == 2


def test_cli_uses_real_subprocess_stdin_without_model_use(tmp_path: Path, monkeypatch, capsys) -> None:
    worker = tmp_path / "fixture_agent.py"
    worker.write_text(
        'import json, sys\n'
        'prompt = sys.stdin.read()\n'
        f'plan = {json.dumps({"tasks": tasks()})!r}\n'
        f'result = {json.dumps(analysis())!r}\n'
        'print("Working...")\n'
        'print(plan if prompt.startswith("Split the goal") else result)\n'
    )
    monkeypatch.setattr(evolution.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(evolution, "_omp_args", lambda *_: [sys.executable, str(worker)])
    context = tmp_path / "context.txt"
    context.write_text("evidence")
    exit_code = swarm_cli.main(["--json", "--goal", "Analyze", "--context", str(context),
                                "--output", str(tmp_path / "run"), "--max-calls", "4"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["command"] == "swarm"
    assert payload["data"]["logical_calls_consumed"] == 4
    assert payload["data"]["summary"] == analysis()


def test_cli_failure_has_nonzero_exit_and_report_location(tmp_path: Path, monkeypatch, capsys) -> None:
    context = tmp_path / "context.txt"
    context.write_text("evidence")
    monkeypatch.setattr(evolution, "_omp", lambda *_: 'not JSON')
    exit_code = swarm_cli.main(["--json", "--goal", "Analyze", "--context", str(context),
                                "--output", str(tmp_path / "run"), "--max-calls", "4"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 5
    assert payload["ok"] is False
    assert "run.json" in payload["error"]["message"]
    assert json.loads((tmp_path / "run/run.json").read_text())["execution_status"] == "failed"
