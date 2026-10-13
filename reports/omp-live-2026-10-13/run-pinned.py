"""Run the real CLI with an explicit OMP model and a cumulative invocation guard.

Instrumentation pins OMP's model/key at runtime and counts calls; it never
replaces model responses. REVERSE_TEST_API_KEY is supplied by the operator.
"""
import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from reverse_skill import cli, evolution
from reverse_skill.errors import ToolOperationError

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--name", required=True)
options = parser.parse_args()
evidence = Path(__file__).resolve().parent
root = evidence.parents[1]
ledger_path = evidence / "budget.json"
if not ledger_path.exists():
    previous = json.loads((evidence / "run-metadata.json").read_text(encoding="utf-8"))
    ledger_path.write_text(json.dumps({"limit": 37, "forwarded_calls": previous["logical_calls_started"], "blocked_calls": 0}, indent=2), encoding="utf-8")
ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
api_key = os.environ["REVERSE_TEST_API_KEY"]
original_args, original_omp = evolution._omp_args, evolution._omp
overlay = evidence / "retry.yml"
overlay.write_text("retry:\n  maxRetries: 0\n  fallbackChains: {}\n", encoding="utf-8")

def pinned_args(*args):
    return original_args(*args) + ["--model", options.model, "--api-key", api_key, "--config", str(overlay)]

def counted_omp(*args):
    if ledger["forwarded_calls"] >= ledger["limit"]:
        ledger["blocked_calls"] += 1
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        raise ToolOperationError("Operator's cumulative 37 logical OMP invocation limit reached; no call forwarded")
    ledger["forwarded_calls"] += 1
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return original_omp(*args)

evolution._omp_args, evolution._omp = pinned_args, counted_omp
argv = [
    "--json", "evolve", "--candidate", str(root / "skills/routing.md"),
    "--catalog", str(root / "skills/routing.json"), "--fixtures", str(root / "skills/evolution/fixtures/route-selection.json"),
    "--output", str(evidence / options.name), "--max-evaluations", "3", "--max-reflections", "1", "--model-timeout", "60",
]
metadata = {"argv": argv, "entrypoint": "reverse_skill.cli.main (same public CLI)",
    "instrumentation": "pin OMP model/key and guard cumulative logical calls; no response substitution",
    "model": options.model, "budget_before": dict(ledger), "physical_requests": None, "tokens": None, "cost": None,
    "config_sha256": hashlib.sha256((Path.home() / ".omp/agent/config.yml").read_bytes()).hexdigest(),
    "omp_version": subprocess.check_output(["omp", "--version"], text=True).strip(),
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "started_at": datetime.now(timezone.utc).isoformat()}

class Tee:
    def __init__(self, output, stream):
        self.output, self.stream = output, stream
    def write(self, value):
        self.output.write(value)
        self.stream.write(value)
        return len(value)
    def flush(self):
        self.output.flush()
        self.stream.flush()

started = time.monotonic()
with (evidence / f"{options.name}.stdout.json").open("w", encoding="utf-8") as stdout, (evidence / f"{options.name}.stderr.log").open("w", encoding="utf-8") as stderr:
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(Tee(stderr, sys.stderr)):
        code = cli.main(argv)
metadata.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 3), budget_after=dict(ledger), ended_at=datetime.now(timezone.utc).isoformat())
(evidence / f"{options.name}.metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
print(f"Real CLI finished: {options.model}, exit={code}, cumulative calls={ledger['forwarded_calls']}/37, elapsed={metadata['elapsed_seconds']}s", flush=True)
sys.exit(code)
