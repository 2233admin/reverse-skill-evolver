"""Exercise the collector in the pinned production OMP worker on owned DLLs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TEMP = ROOT / ".verification"
PYTHON = TEMP / "ida-runtime/Scripts/python.exe"
WORKER = TEMP / "omp-worker-fa5ff4a3.py"
LLVM = Path(shutil.which("clang")).parent
KERNEL = Path("C:/Program Files (x86)/Windows Kits/10/Lib/10.0.26100.0/um/x64/kernel32.Lib")
COLLECTOR = ROOT / ".omp/skills/omp-ida-native/scripts/ida_analysis.py"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "fresh"

for version in ("v1", "v2"):
    source = HERE / f"toy-{version}.c"
    obj, binary = TEMP / f"toy-{version}.obj", TEMP / f"toy-{version}.dll"
    subprocess.run([str(LLVM / "clang.exe"), "--target=x86_64-windows-msvc", "-O0", "-c", str(source), "-o", str(obj)], check=True)
    subprocess.run([str(LLVM / "lld-link.exe"), "/dll", "/noentry", "/nodefaultlib", str(obj), str(KERNEL), f"/out:{binary}"], check=True)
    shutil.copyfile(binary, HERE / binary.name)
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    database = f"owned-native-{version}-{sha[:12]}"
    code = f"""
import json
task_namespace = dict(globals())
task_script = {str(COLLECTOR)!r}
exec(compile(open(task_script, encoding='utf-8').read(), task_script, 'exec'), task_namespace)
task_snapshot = task_namespace['collect_snapshot'](globals(), {database!r}, max_functions=20, max_strings=20, max_imports=20)
task_triage = task_namespace['triage'](globals(), {database!r})
task_no_matches = task_namespace['triage'](globals(), {database!r}, function_pattern='^NO_MATCH$', string_pattern='^NO_MATCH$', import_pattern='^NO_MATCH$')
task_limited = task_namespace['collect_snapshot'](globals(), {database!r}, max_functions=1, max_strings=1, max_imports=1, max_bytes_per_function=1, collect_pseudocode=True, max_pseudocode_functions=1, max_pseudocode_chars=30)
task_xref_limited = task_namespace['triage'](globals(), {database!r}, max_candidates=1, max_xref_queries=1, max_xrefs_per_source=1, max_evidence_per_candidate=1)
with open({str(HERE / f'native-data-{LABEL}-{version}.json')!r}, 'x', encoding='utf-8') as task_file:
    json.dump({{'snapshot':task_snapshot,'triage':task_triage,'no_matches':task_no_matches,'limited':task_limited,'xref_limited':task_xref_limited}}, task_file, ensure_ascii=False)
print('complete artifact saved')
"""
    frames = [
        {"id": 1, "method": "open", "params": {"path": str(binary), "new": True}},
        {"id": 2, "method": "exec", "params": {"code": code}},
    ]
    env = dict(os.environ, IDADIR="C:/Program Files/IDA Professional 9.4")
    result = subprocess.run([str(PYTHON), str(WORKER)], input="\n".join(json.dumps(row) for row in frames)+"\n", capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    (HERE / f"native-{version}.stdout.jsonl").write_bytes(result.stdout.encode("utf-8"))
    (HERE / f"native-{version}.stderr.txt").write_bytes(result.stderr.encode("utf-8"))
    responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert result.returncode == 0, result.stderr[-2000:]
    assert len(responses) == 2 and all(row["ok"] for row in responses), responses
    response = responses[1]["result"]
    assert response["error"] is None, response["error"]
    data = json.loads((HERE / f"native-data-{LABEL}-{version}.json").read_text(encoding="utf-8"))
    assert data["snapshot"]["source"]["sha256"] == sha
    assert any("license-invalid" in row["value"] for row in data["snapshot"]["strings"])
    assert any("GetCurrentProcessId" in row["name"] for row in data["snapshot"]["imports"])
    assert any(row["name"] == ("verify_license" if version=="v1" else "check_license") for row in data["triage"]["candidates"])
    assert data["triage"]["coverage"]["non_function_xrefs_skipped"] >= 1
    assert data["no_matches"]["candidates"] == []
    assert data["limited"]["coverage"]["functions_truncated"] and data["limited"]["coverage"]["bytes_truncated"]
    assert data["limited"]["coverage"]["pseudocode_text_truncated"]
    assert data["xref_limited"]["coverage"]["xref_queries"] <= 1
    for name, value in data.items():
        (HERE / f"{name}-{version}.json").write_bytes((json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode("utf-8"))
    print(f"native {version}: real strings/imports/function leads, non-function xrefs, no-match and limits PASS; sha={sha}", flush=True)
