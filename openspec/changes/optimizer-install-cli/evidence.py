"""Run local baseline/implementation comparisons; no targets or installations.

Run from the checkout: python openspec/changes/optimizer-install-cli/evidence.py
Raw samples are written next to this script. Baseline files and test runtimes
stay in ignored, task-owned .verification storage.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
from statistics import median
import subprocess
import sys
from time import perf_counter
import venv


ROOT = Path(__file__).resolve().parents[3]
BASE = "d6d085364508215d0019b83f32dc58dd8f170c9e"
WORK = ROOT / ".verification/optimizer-install-cli"
BEFORE = WORK / "baseline"
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def samples(before, after, rounds=3, iterations=1):
    result = {"before_ms": [], "after_ms": []}
    for _ in range(rounds):
        for key, function in (("before_ms", before), ("after_ms", after)):
            start = perf_counter()
            for _ in range(iterations):
                function()
            result[key].append((perf_counter() - start) * 1000 / iterations)
    result["before_median_ms"] = median(result["before_ms"])
    result["after_median_ms"] = median(result["after_ms"])
    return result


def snapshot():
    paths = subprocess.check_output([
        "git", "ls-tree", "-r", "--name-only", BASE, "--", "reverse_skill", "scripts/run.py",
        "pyproject.toml", "skills/scripts/fleet-sync.ps1", "kali/scripts/bootstrap-reverse.sh",
        "kali/scripts/refresh-tool-index.sh", "kali/scripts/lib/tool-discovery.sh",
        "skills/scripts/bootstrap-reverse.ps1", "skills/scripts/lib/ToolDiscovery.ps1",
    ], cwd=ROOT, text=True).splitlines()
    for name in paths:
        target = BEFORE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", f"{BASE}:{name}"], cwd=ROOT))


def route_evidence():
    from reverse_skill import routing
    old = load("baseline_routing", BEFORE / "reverse_skill/routing.py")
    cases = [{"task": row["hint"]} for row in json.loads(
        (ROOT / "tests/data/routing-benchmark.json").read_text(encoding="utf-8"))["cases"]]
    hint = "List ASR items for an APK task: jadx apktool smali decompile repack frida ssl pinning signature bypass root detection"
    cases += [{"task": text} for text in (
        "Forefy audited skills exclude MCP servers", "List Forefy ASR items for IDA binary analysis",
        "List ASR items for an APK task, audited only", "OMP native IDA inspect sample.exe",
        "OMP JavaScript captured signer replay", hint)]
    cases += [{"task": "example", "route_id": "asr-registry"},
              {"task": "unrelated", "route_id": "missing"}, {"task": hint, "route_id": "apk-android"},
              {"task": "Analyse\tAPK\nFrida", "target_kind": "APK"},
              {"task": "分析\n签 名\t绕过 安卓"}, {"task": "session\nxyz", "input_path": "sample.so"}]
    assert len(cases) == 175
    assert all(old.build_plan(task) == routing.build_plan(task) for task in cases)
    boundaries = [("session", "so"), ("sample.so", "so"), ("分 析", "分析"), ("", ""), ("SIGNATURE\nBYPASS", "signature bypass")]
    assert all(old.contains_keyword(*pair) == routing.contains_keyword(*pair) for pair in boundaries)
    measured = []
    for length, iterations in ((64, 20), (512, 10), (16384, 2)):
        task = {"task": ("XYZ whitespace \t123\n" * (length // 19 + 2))[:length]}
        row = {"task_chars": length}
        for label, module in (("before", old), ("after", routing)):
            original = module.normalize
            calls = []
            combined = module._task_text(task)
            def counted(value):
                if value == combined:
                    calls.append(value)
                return original(value)
            module.normalize = counted
            module.build_plan(task)
            module.normalize = original
            row[f"{label}_task_preparations"] = len(calls)
        row.update(samples(lambda: old.build_plan(task), lambda: routing.build_plan(task), iterations=iterations))
        measured.append(row)
    return {"complete_plans_equal": 175, "keyword_boundaries_equal": 5, "measurements": measured}


def scan_evidence():
    from reverse_skill import gates
    from reverse_skill import case
    old_gates = load("reverse_skill.baseline_gates", BEFORE / "reverse_skill/gates.py")
    old_case = load("reverse_skill.baseline_case", BEFORE / "reverse_skill/case.py")
    email = []
    probe = WORK / "email.txt"
    for length in (4000, 8000, 16000, 32000):
        for suffix in ("", "@-"):
            probe.write_text("a." * (length // 2) + suffix, encoding="utf-8")
            assert old_gates.leak_scan(str(probe)) == gates.leak_scan(str(probe))
            row = {"chars": length + len(suffix), "suffix": suffix, "results_equal": True}
            row.update(samples(lambda: old_gates.leak_scan(str(probe)), lambda: gates.leak_scan(str(probe))))
            email.append(row)
    class Text(str):
        copied = 0
        def __getitem__(self, key):
            value = super().__getitem__(key)
            if isinstance(key, slice):
                self.copied += len(value)
            return value
    report = "".join(f"### F-{i} Finding\n" + "x" * 220 + "\n" for i in range(8000))
    old_text, new_text = Text(report), Text(report)
    assert old_case.report_sections(old_text, old_case.FINDING_HEADING) == case.report_sections(new_text, case.FINDING_HEADING)
    sections = {"chars": len(report), "sections_equal": 8000,
                "before_copied_chars": old_text.copied, "after_copied_chars": new_text.copied}
    sections.update(samples(lambda: old_case.report_sections(report, old_case.FINDING_HEADING),
                            lambda: case.report_sections(report, case.FINDING_HEADING)))
    return email, sections


def help_evidence():
    result = {}
    for module in ("reverse_skill.cli", "reverse_skill.swarm_cli"):
        outputs, counts = {}, {}
        def invoke(root, label):
            code = f"import {module} as cli; import sys,json; status=cli.main(['--help']); print(json.dumps(sum(name.startswith('httpx') for name in sys.modules)),file=sys.stderr); raise SystemExit(status)"
            process = subprocess.run([sys.executable, "-B", "-c", code], cwd=root,
                                     capture_output=True, encoding="utf-8", timeout=30)
            assert process.returncode == 0, process.stderr
            outputs[label] = process.stdout
            counts[label] = json.loads(process.stderr)
        row = samples(lambda: invoke(BEFORE, "before"), lambda: invoke(ROOT, "after"), rounds=7)
        assert outputs["before"] == outputs["after"]
        row.update(stdout_equal=True, httpx_modules=counts)
        result[module] = row
    return result


def launcher_evidence():
    runtimes = {}
    for label, root in (("before", BEFORE), ("after", ROOT)):
        runtime = WORK / f"runtime-{label}"
        venv.EnvBuilder(system_site_packages=True, with_pip=False).create(runtime)
        interpreter = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        purelib = subprocess.check_output([str(interpreter), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
        (Path(purelib) / "package.pth").write_text(str(root), encoding="utf-8")
        signature = hashlib.sha256((root / "pyproject.toml").read_bytes() + sys.version.encode("utf-8")).hexdigest()
        (runtime / "reverse-skill-runtime.json").write_text(json.dumps({"source": str(root.resolve()), "signature": signature}))
        location = subprocess.check_output([str(interpreter), "-I", "-c", "import reverse_skill; print(reverse_skill.__file__)"], text=True).strip()
        assert Path(location).parent == root / "reverse_skill"
        runtimes[label] = runtime
    outputs = {}
    def invoke(root, label):
        process = subprocess.run([sys.executable, "-I", "-X", "utf8", str(root / "scripts/run.py"), "--help"],
                                 cwd=WORK, env={**os.environ, "REVERSE_SKILL_RUNTIME": str(runtimes[label])},
                                 capture_output=True, encoding="utf-8", timeout=30)
        assert process.returncode == 0, process.stderr
        outputs[label] = process.stdout
    result = samples(lambda: invoke(BEFORE, "before"), lambda: invoke(ROOT, "after"), rounds=12)
    assert outputs["before"] == outputs["after"]
    result.update(stdout_equal=True, before_runtime_children=2, after_runtime_children=1)
    return result


def shell_evidence(harness):
    failures = {}
    inventory = {}
    tools = {}
    for label, root in (("before", BEFORE), ("after", ROOT)):
        harness.ROOT = root
        functions = harness.bootstrap_functions().replace("$HOME/tools/jadx", "$TEST_JADX_DIR")
        process = harness.bash_run("set -euo pipefail\n" + functions + '''
command() { return 1; }
install_github_release() { return 22; }
chmod() { return 1; }
TEST_JADX_DIR=/unused-test-jadx
if ensure_capability jadx; then echo ready; else echo failed; fi
''')
        assert process.returncode == 0, process.stderr
        failures[label] = process.stdout.splitlines()[-1]
        directory = WORK / f"inventory-{label}"
        scripts = directory / "kali/scripts"
        (scripts / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / "kali/scripts/refresh-tool-index.sh", scripts)
        trace = directory / "calls.txt"
        trace.write_text("")
        tool = WORK / "version-tool.sh"
        tool.write_text(f"#!/usr/bin/env bash\necho called >> {shlex.quote(trace.as_posix())}\necho synthetic-version\n", encoding="utf-8")
        tool.chmod(0o755)
        library = (root / "kali/scripts/lib/tool-discovery.sh").read_text(encoding="utf-8")
        library += f'''
TOOL_CATALOG=()
for ((i=1;i<=32;i++)); do TOOL_CATALOG+=("tool-$i|test|synthetic|--version|mock"); done
declare -A SCRIPT_REFS=()
find_command() {{ echo {shlex.quote(tool.as_posix())}; }}
check_mcp_registered() {{ echo false; }}
test_tcp_port() {{ return 1; }}
'''
        (scripts / "lib/tool-discovery.sh").write_text(library, encoding="utf-8")
        process = subprocess.run([harness.BASH, str(scripts / "refresh-tool-index.sh"), "index.md", "index.json", "graph.json"],
                                 cwd=directory, capture_output=True, encoding="utf-8", timeout=60)
        assert process.returncode == 0, process.stderr
        inventory[label] = len(trace.read_text().splitlines())
        tools[label] = json.loads((directory / "index.json").read_text(encoding="utf-8"))["tools"]
    harness.ROOT = ROOT
    assert tools["before"] == tools["after"]
    assert failures == {"before": "ready", "after": "failed"}
    assert inventory == {"before": 64, "after": 32}
    return {"ER-02": failures, "IO-01": {"version_calls": inventory, "tool_rows_equal": 32}}


def fleet_evidence(harness):
    body = harness.PS_IMPORT_FUNCTION + f'''
Import-Function {harness.ps_quote(BEFORE / 'skills/scripts/fleet-sync.ps1')} Sync-Directory
Set-Item Function:SyncBefore (Get-Item Function:Sync-Directory).ScriptBlock
Import-Function {harness.ps_quote(ROOT / 'skills/scripts/fleet-sync.ps1')} Sync-Directory
$script:names = @(1..4000 | ForEach-Object {{ "entry-$_.md" }})
$script:files = @($script:names | ForEach-Object {{ [pscustomobject]@{{ Name=$_ }} }})
$script:Collisions = [System.Collections.Generic.List[string]]::new()
$script:Copied = [System.Collections.Generic.List[string]]::new()
$LocalRepoRoot = 'synthetic-local'; $RemotePath = 'synthetic-remote'; $SshTarget = 'mock'
function Test-Path {{ return $true }}
function Get-ChildItem {{ return $script:files }}
function Get-RemoteFileNames {{ return $script:names }}
function Invoke-FleetCopy {{ throw 'No copy expected' }}
$before = @(); $after = @(); $equal = $true
foreach ($round in 1..3) {{
    foreach ($mode in @('before', 'after')) {{
        $script:Collisions.Clear()
        $watch = [Diagnostics.Stopwatch]::StartNew()
        if ($mode -eq 'before') {{ SyncBefore journal Pull }} else {{ Sync-Directory journal Pull }}
        $watch.Stop()
        if ($mode -eq 'before') {{ $before += $watch.Elapsed.TotalMilliseconds; $expected = $script:Collisions -join '|' }}
        else {{ $after += $watch.Elapsed.TotalMilliseconds; $equal = $equal -and (($script:Collisions -join '|') -ceq $expected) }}
    }}
}}
@{{ before_ms=$before; after_ms=$after; collisions_equal=$equal; collision_count=$script:Collisions.Count }} | ConvertTo-Json -Compress
'''
    result = json.loads(harness.ps_run(shutil.which("pwsh") or shutil.which("powershell"), WORK, body))
    assert result["collisions_equal"] and result["collision_count"] == 4000
    result["before_median_ms"] = median(result["before_ms"])
    result["after_median_ms"] = median(result["after_ms"])
    return result


def apktool_evidence(harness):
    result = {}
    engine = shutil.which("pwsh") or shutil.which("powershell")
    for label, root in (("before", BEFORE), ("after", ROOT)):
        directory = WORK / f"apktool-{label}"
        directory.mkdir(exist_ok=True)
        body = harness.PS_IMPORT_FUNCTION + f'''
Import-Function {harness.ps_quote(root / 'skills/scripts/bootstrap-reverse.ps1')} Ensure-ApktoolInstall
Import-Function {harness.ps_quote(root / 'skills/scripts/lib/ToolDiscovery.ps1')} Resolve-ReverseToolSpec
'''
        if label == "after":
            body += f"Import-Function {harness.ps_quote(root / 'skills/scripts/lib/ToolDiscovery.ps1')} Test-ReverseApktoolJar\n"
        body += f'''
$script:directory = {harness.ps_quote(directory)}
$script:jar = Join-Path $script:directory 'apktool.jar'
if (Test-Path -LiteralPath $script:jar) {{ Remove-Item -LiteralPath $script:jar }}
$script:downloads = 0
function Get-ReverseToolDefinition($Name) {{
    $path = if ($Name -eq 'java') {{ {harness.ps_quote(sys.executable)} }} else {{ $script:jar }}
    $kind = if ($Name -eq 'java') {{ 'path' }} else {{ 'java-jar' }}
    [pscustomobject]@{{ Name=$Name; Skill='test'; Purpose='inert discovery'; VersionArgs=@();
        Fallbacks=@([pscustomobject]@{{ Type=$kind; Value=$path }}) }}
}}
function Ensure-JavaRuntime {{}}
function Ensure-DownloadDirectory($Path) {{ New-Item -ItemType Directory -Force -Path $Path | Out-Null }}
function Get-GitHubLatestReleaseAsset {{ [pscustomobject]@{{ name='apktool.jar'; browser_download_url='https://mock.invalid/test' }} }}
function Invoke-WebRequest($Uri, $OutFile, $Headers) {{ $script:downloads++; [IO.File]::WriteAllText($OutFile, 'partial JAR'); throw 'interrupted' }}
$definition = [pscustomobject]@{{ repo='mock'; assetRegex='mock'; installDir=$script:directory; wrapperName='apktool.bat' }}
$first_failed = $false
try {{ Ensure-ApktoolInstall $definition | Out-Null }} catch {{ $first_failed = $true }}
$partial = Test-Path -LiteralPath $script:jar
$available = (Resolve-ReverseToolSpec apktool).Available
try {{ Ensure-ApktoolInstall $definition | Out-Null }} catch {{}}
@{{ first_failed=$first_failed; partial_final_jar=$partial; available_after_failure=$available; download_attempts=$script:downloads }} | ConvertTo-Json -Compress
'''
        result[label] = json.loads(harness.ps_run(engine, WORK, body))
    assert result["before"] == {"first_failed": True, "partial_final_jar": True,
                                "available_after_failure": True, "download_attempts": 1}
    assert result["after"] == {"first_failed": True, "partial_final_jar": False,
                               "available_after_failure": False, "download_attempts": 2}
    result["successful_repair_validation"] = "test_apktool_stages_failure_and_repairs_poisoned_install (PowerShell 5.1/7; synthetic executable JAR)"
    return result


def main():
    snapshot()
    harness = load("optimizer_tests", ROOT / "tests/test_optimizer_install_cli.py")
    result = {"baseline": BASE, "python": sys.version,
              "boundary": "Local synthetic comparisons only; no real IDA/Burp/ASR/fleet or installers."}
    result["DEAD-01"] = route_evidence()
    result["SEC-01"], result["ALG-04"] = scan_evidence()
    result["BUNDLE-01"] = help_evidence()
    result["BUILD-001"] = launcher_evidence()
    result.update(shell_evidence(harness))
    result["DATA-03"] = fleet_evidence(harness)
    result["ER-03"] = apktool_evidence(harness)
    target = Path(__file__).with_name("evidence-results.json")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
