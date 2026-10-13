"""Record one real, bounded public CLI run without reading credentials or changing config."""
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


root = Path(__file__).resolve().parents[2]
evidence = Path(__file__).resolve().parent
output = evidence / "full-suite"
command = [
    sys.executable, "-m", "reverse_skill", "--json", "evolve",
    "--candidate", str(root / "skills/routing.md"),
    "--catalog", str(root / "skills/routing.json"),
    "--fixtures", str(root / "skills/evolution/fixtures/route-selection.json"),
    "--output", str(output), "--max-evaluations", "3", "--max-reflections", "1",
    "--model-timeout", "60",
]
config = Path.home() / ".omp/agent/config.yml"
metadata = {
    "budget_receipt": "https://github.com/2233admin/reverse-skill-evolver/issues/21#issuecomment-6144393049",
    "logical_call_limit": 37, "per_call_seconds": 60,
    "physical_request_count": None, "token_usage": None, "cost": None,
    "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
    "omp_version": subprocess.check_output(["omp", "--version"], text=True).strip(),
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "command": command, "started_at": datetime.now(timezone.utc).isoformat(),
    "model_selection": "existing OMP default; not overridden by this CLI",
}
(evidence / "run-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
started = time.monotonic()
with (evidence / "cli.stdout.json").open("w", encoding="utf-8") as stdout:
    process = subprocess.Popen(command, cwd=root, stdout=stdout, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    with (evidence / "cli.stderr.log").open("w", encoding="utf-8") as stderr:
        for line in process.stderr:
            stderr.write(line)
            stderr.flush()
            print(line, end="", flush=True)
    code = process.wait()
metadata.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 3), ended_at=datetime.now(timezone.utc).isoformat())
if (output / "results.json").is_file():
    report = json.loads((output / "results.json").read_text(encoding="utf-8"))
    metadata.update(logical_calls_started=report["logical_calls_started"], archive_status=report["status"])
    assert metadata["logical_calls_started"] <= 37
(evidence / "run-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
print(f"Real CLI finished: exit={code}, elapsed={metadata['elapsed_seconds']}s; archive={output}", flush=True)
sys.exit(code)
