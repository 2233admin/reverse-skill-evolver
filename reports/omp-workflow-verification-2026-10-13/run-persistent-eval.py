"""One bounded real OMP session validates two eval cells; credentials stay in env."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TASK = ROOT / ".verification/omp-replay-owned"
TASK.mkdir(exist_ok=True)
MODULE = ROOT / ".omp/skills/omp-js-replay/scripts/signature-replay.mjs"
OUTPUT = HERE / "omp-persistent-replay.json"
samples = [{"id": str(value), "input": {"value": value, "timestamp": 1700000000},
            "expected": hmac.new(b"fixture-only-key", json.dumps({"value": value, "timestamp": 1700000000}, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()}
           for value in (7, 8)]
ledger_path = ROOT / "reports/omp-live-2026-10-13/budget.json"
ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
assert ledger["forwarded_calls"] < ledger["limit"]
assert not OUTPUT.exists()
prompt = f"""Run one owned local JavaScript replay verification. Use ONLY the eval tool in language js. No delegation, agent(), network, installation, host settings, or unrelated files.
The actual local module is {str(MODULE)!r}. You may read/import only it and Node builtins crypto/url/fs. Write only {str(OUTPUT)!r}.
Perform TWO SEPARATE eval TOOL CALLS using the same persistent kernel and no reset:
Cell one: import the local compareSignatures module (use pathToFileURL/dynamic import or the eval interface's module-import command). Define persistent taskReplayModule, taskFixtures, taskSigner, taskCellToken. taskFixtures must be exactly {json.dumps(samples)}. taskSigner(input) is HMAC-SHA256 with fixture-only-key over JSON.stringify(input). Set taskCellToken='owned-persistent-cell-one'. Print a short initialization marker.
Cell two: reuse those previously defined variables without redefining/importing them. Assert taskCellToken is still owned-persistent-cell-one. Call compareSignatures(taskFixtures, taskSigner), then again with maxCases:1. Save a JSON object containing cellToken, fullReport, partialReport to {str(OUTPUT)!r}. Print the resulting fullReport.passed and partialReport.coverage. No actual sample code is evaluated. Expected signatures above were independently computed; do not replace them or fabricate reports.
After the two actual tool calls, briefly report the file path. If an eval call fails, diagnose within this single bounded session and preserve the error; never claim a fabricated successful result.
"""
env = dict(os.environ, PI_NATIVES_DIR=str(ROOT / ".verification/omp-natives"),
           PI_CODING_AGENT_DIR=str(ROOT / ".verification/omp-state/agent"),
           TEMP=str(ROOT / ".verification/frida-temp"), TMP=str(ROOT / ".verification/frida-temp"))
command = [shutil.which("omp"), "--cwd", str(TASK), "--model", "minimax-code-cn/MiniMax-M3.1-Flash-Preview",
           "--api-key", env["REVERSE_TEST_API_KEY"], "--tools", "eval", "--no-extensions", "--no-skills", "--no-rules",
           "--no-session", "--no-title", "--thinking", "low", "--max-time", "60", "--mode", "json", "--print"]
ledger["forwarded_calls"] += 1
ledger_path.write_bytes((json.dumps(ledger, indent=2)+"\n").encode("utf-8"))
started = time.monotonic()
try:
    result = subprocess.run(command, input=prompt, capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=70)
except subprocess.TimeoutExpired:
    print("real OMP persistent eval exceeded bounded timeout", file=sys.stderr)
    raise SystemExit(5)
(HERE / "omp-persistent-eval.stdout.jsonl").write_bytes(result.stdout.encode("utf-8"))
(HERE / "omp-persistent-eval.stderr.txt").write_bytes(result.stderr.encode("utf-8"))
metadata = {"model": "minimax-code-cn/MiniMax-M3.1-Flash-Preview", "logical_omp_invocations": 1,
            "cumulative_invocations": ledger["forwarded_calls"], "exit_code": result.returncode,
            "elapsed_seconds": round(time.monotonic()-started,3), "module_sha256": hashlib.sha256(MODULE.read_bytes()).hexdigest()}
(HERE / "omp-persistent-eval.metadata.json").write_bytes((json.dumps(metadata,indent=2)+"\n").encode("utf-8"))
assert result.returncode == 0, result.stderr[-1500:]
assert OUTPUT.is_file(), "No actual replay artifact produced; inspect retained real OMP frames"
report = json.loads(OUTPUT.read_text(encoding="utf-8"))
assert report["cellToken"] == "owned-persistent-cell-one"
assert report["fullReport"]["passed"] is True and report["fullReport"]["coverage"]["processed"] == 2
assert report["partialReport"]["passed"] is False and report["partialReport"]["coverage"]["remaining"] == 1
assert [row["actual"] for row in report["fullReport"]["cases"]] == [row["expected"] for row in samples]
events = [json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith("{")]
tool_calls = [row for row in events if row.get("type") == "tool_execution_start"]
assert len(tool_calls) >= 2 and all(row.get("toolName") == "eval" for row in tool_calls), tool_calls
print(f"real OMP persistent eval: PASS; tool calls={len(tool_calls)}, elapsed={metadata['elapsed_seconds']}s; cumulative logical calls={ledger['forwarded_calls']}/37", flush=True)
