"""Failure recovery and bounded local work for issue #56; no live targets."""

import importlib.util
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

from reverse_skill import gates, routing
from reverse_skill.case import FINDING_HEADING, report_sections


ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
git_bash = Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe"
if sys.platform == "win32" and git_bash.is_file():
    BASH = str(git_bash)


def bash_run(script, cwd=ROOT):
    if not BASH:
        pytest.skip("Bash is unavailable")
    return subprocess.run([BASH, "-s"], input=script, text=True, encoding="utf-8",
                          capture_output=True, cwd=cwd, timeout=30)


def bootstrap_functions():
    source = (ROOT / "kali/scripts/bootstrap-reverse.sh").read_text(encoding="utf-8")
    return source[source.index("log_info()") : source.index("# ─── 主流程")]


@pytest.mark.parametrize("failure", ["install", "chmod", "health"])
def test_jadx_failure_is_not_ready(failure):
    script = "set -euo pipefail\n" + bootstrap_functions().replace("$HOME/tools/jadx", "$TEST_JADX_DIR") + f'''
command() {{ return 1; }}
install_github_release() {{ {'return 22' if failure == 'install' else 'return 0'}; }}
chmod() {{ {'return 23' if failure == 'chmod' else 'return 0'}; }}
TEST_JADX_DIR=/unused-test-jadx
if ensure_capability jadx; then echo ready; else echo failed; fi
'''
    result = bash_run(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "failed"


def test_plan_prepares_task_text_once(monkeypatch):
    text = "unmatched arbitrary text " * 100
    original = routing.normalize
    calls = []

    def counted(value):
        if str(value).startswith(text):
            calls.append(value)
        return original(value)

    monkeypatch.setattr(routing, "normalize", counted)
    assert routing.build_plan({"task": text})["status"] == "no_route"
    assert len(calls) == 1


@pytest.mark.parametrize("module,args", [
    ("reverse_skill.cli", ["--help"]),
    ("reverse_skill.cli", ["asr", "--help"]),
    ("reverse_skill.cli", ["--json", "route", "Analyze APK"]),
    ("reverse_skill.swarm_cli", ["--help"]),
])
def test_local_entrypoints_do_not_import_httpx(module, args):
    code = '''
import importlib, importlib.abc, sys
class NoNetworkImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'httpx' or fullname.startswith('httpx.'):
            raise AssertionError('local CLI imported HTTPX')
sys.meta_path.insert(0, NoNetworkImports())
module = importlib.import_module(sys.argv[1])
raise SystemExit(module.main(sys.argv[2:]))
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, module, *args], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr


def test_email_detection_matches_original_boundaries():
    original = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    rng = random.Random(56)
    samples = [
        "someone@example.com another@private.dev", "汉a+b@private.dev", "_a@private.dev_",
        ".a@private.dev", "a@b.dev+x@z.dev", "a..+b@sub.private.dev.",
        "a" * 32000, "a" * 32000 + "@-", "a@" + "-" * 32000,
        "-@" * 16000,
    ]
    samples.extend("".join(rng.choices("abAB09._%+-@ 汉", k=60)) for _ in range(3000))
    for line in samples:
        expected = [(m.span(), m.group()) for m in original.finditer(line)]
        actual = [(m.span(), m.group()) for m in gates._email_matches(line)]
        assert actual == expected, repr(line[:100])


def test_report_sections_keep_intervening_and_final_headings():
    text = "### F-001 First\nbody\n#### retained\nmore\n### unrelated\nstop\n### F-002 Last\ntail"
    assert report_sections(text, FINDING_HEADING) == [
        ("F-001", "### F-001 First\nbody\n#### retained\nmore\n"),
        ("F-002", "### F-002 Last\ntail"),
    ]


def test_report_sections_keep_immediate_suffix_boundary():
    text = "### F-1# rest\nbody\n### F-2 title\nlast"
    assert report_sections(text, FINDING_HEADING) == [
        ("F-1", "### F-1"), ("F-2", "### F-2 title\nlast"),
    ]


def load_launcher():
    spec = importlib.util.spec_from_file_location("optimizer_launcher", ROOT / "scripts/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepared_launcher_uses_one_child_process(tmp_path, monkeypatch):
    launcher = load_launcher()
    runtime = tmp_path / "owned runtime"
    runtime.mkdir()
    signature = launcher.hashlib.sha256(
        (ROOT / "pyproject.toml").read_bytes() + sys.version.encode("utf-8")
    ).hexdigest()
    (runtime / "reverse-skill-runtime.json").write_text(json.dumps({
        "source": str(ROOT.resolve()), "signature": signature,
    }))
    interpreter = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    interpreter.parent.mkdir()
    interpreter.touch()
    monkeypatch.setenv("REVERSE_SKILL_RUNTIME", str(runtime))
    calls = []

    def run(argv, **options):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main(["--help"]) == 0
    assert len(calls) == 1
    assert calls[0][1:4] == ["-I", "-X", "utf8"]


@pytest.fixture(params=["powershell", "pwsh"])
def ps_engine(request):
    executable = shutil.which(request.param)
    if not executable:
        pytest.skip(f"{request.param} is unavailable")
    return executable


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def ps_run(engine, tmp_path, body):
    script = tmp_path / "probe.ps1"
    script.write_text("$ErrorActionPreference = 'Stop'\n" + body, encoding="utf-8-sig")
    result = subprocess.run([engine, "-NoProfile", "-NonInteractive", "-File", str(script)],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


PS_IMPORT_FUNCTION = '''
function Import-Function($Path, $Name) {
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    $fn = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $Name }, $true)
    if ($null -eq $fn) { throw "Missing function $Name" }
    Set-Item -Path ("Function:global:" + $Name) -Value $fn.Body.GetScriptBlock()
}
'''


@pytest.fixture(scope="module")
def executable_jars(tmp_path_factory):
    javac = shutil.which("javac")
    if not javac or not shutil.which("java"):
        pytest.skip("Java compiler/runtime are unavailable for synthetic executable JARs")
    directory = tmp_path_factory.mktemp("synthetic-apktool")
    jars = {}
    for name, status in (("good", 0), ("badhealth", 17)):
        source = directory / "Main.java"
        source.write_text('public class Main { public static void main(String[] args) {'
                          f'System.out.println("synthetic version"); System.exit({status});' + '}}')
        result = subprocess.run([javac, str(source)], capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        jar = directory / f"{name}.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\r\nMain-Class: Main\r\n\r\n")
            archive.write(directory / "Main.class", "Main.class")
        jars[name] = jar
    return jars


@pytest.mark.parametrize("failure", ["interrupted", "invalid", "badhealth"])
def test_apktool_stages_failure_and_repairs_poisoned_install(ps_engine, tmp_path, executable_jars, failure):
    install = tmp_path / "install with spaces"
    install.mkdir()
    (install / "keep.tmp").write_text("another owner's file")
    # Include the old wrapper: it must not hide a poisoned JAR during discovery.
    (install / "apktool.jar").write_text("old partial jar")
    (install / "apktool.bat").write_text("@exit /b 17\n")
    body = PS_IMPORT_FUNCTION + f'''
. {ps_quote(ROOT / 'skills/scripts/lib/ToolDiscovery.ps1')}
Import-Function {ps_quote(ROOT / 'skills/scripts/bootstrap-reverse.ps1')} Ensure-ApktoolInstall
Import-Function {ps_quote(ROOT / 'skills/scripts/bootstrap-reverse.ps1')} Ensure-DownloadDirectory
$script:install = {ps_quote(install)}
function Get-ReverseToolDefinition($Name) {{
    $fallbacks = if ($Name -eq 'java') {{ @([pscustomobject]@{{ Type='path'; Value={ps_quote(shutil.which('java'))} }}) }}
        else {{ @([pscustomobject]@{{ Type='path'; Value=(Join-Path $script:install 'apktool.bat') }},
                  [pscustomobject]@{{ Type='java-jar'; Value=(Join-Path $script:install 'apktool.jar') }}) }}
    return [pscustomobject]@{{ Name=$Name; Skill='test'; Purpose='synthetic'; VersionArgs=@('--version'); Fallbacks=$fallbacks }}
}}
function Ensure-JavaRuntime {{}}
function Get-GitHubLatestReleaseAsset {{ return [pscustomobject]@{{ name='apktool.jar'; browser_download_url='https://mock.invalid/test' }} }}
$script:failure = {ps_quote(failure)}
$script:downloads = 0
function Invoke-WebRequest($Uri, $OutFile, $Headers) {{
    $script:downloads++
    if ($script:downloads -eq 1) {{
        if ($script:failure -eq 'badhealth') {{ Copy-Item -LiteralPath {ps_quote(executable_jars['badhealth'])} -Destination $OutFile }}
        else {{ [IO.File]::WriteAllText($OutFile, 'new partial jar') }}
        if ($script:failure -eq 'interrupted') {{ throw 'interrupted transfer' }}
    }}
    else {{ Copy-Item -LiteralPath {ps_quote(executable_jars['good'])} -Destination $OutFile }}
}}
$definition = [pscustomobject]@{{ repo='mock'; assetRegex='mock'; installDir=$script:install; wrapperName='apktool.bat' }}
if ((Resolve-ReverseToolSpec apktool).Available) {{ throw 'Poisoned JAR reported available' }}
$failed = $false
try {{ Ensure-ApktoolInstall $definition | Out-Null }} catch {{ $failed = $true }}
if (-not $failed) {{ throw 'Failed installation reported success' }}
if ([IO.File]::ReadAllText((Join-Path $script:install 'apktool.jar')) -ne 'old partial jar') {{ throw 'Existing artifact changed on failure' }}
if (@(Get-ChildItem -LiteralPath $script:install -Filter '.apktool-*').Count) {{ throw 'Staged artifact leaked' }}
if ((Resolve-ReverseToolSpec apktool).Available) {{ throw 'Failure became available' }}
$repaired = Ensure-ApktoolInstall $definition
if (-not $repaired.Available -or $script:downloads -ne 2) {{ throw 'Retry failed to repair' }}
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $script:install 'apktool.jar')))
Ensure-ApktoolInstall $definition | Out-Null
if ($script:downloads -ne 2 -or [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $script:install 'apktool.jar'))) -ne $before) {{ throw 'Healthy installation replaced' }}
if ([IO.File]::ReadAllText((Join-Path $script:install 'keep.tmp')) -ne "another owner's file") {{ throw 'Foreign file removed' }}
@{{ failed=$failed; repaired=$repaired.Available; downloads=$script:downloads }} | ConvertTo-Json -Compress
'''
    result = json.loads(ps_run(ps_engine, tmp_path, body))
    assert result == {"failed": True, "repaired": True, "downloads": 2}


@pytest.mark.parametrize("direction", ["Pull", "Push"])
def test_fleet_collisions_keep_case_and_order(ps_engine, tmp_path, direction):
    directory = tmp_path / "journal"
    directory.mkdir()
    for name in ("A.md", "b.md", "local-only.md"):
        (directory / name).touch()
    body = PS_IMPORT_FUNCTION + f'''
Import-Function {ps_quote(ROOT / 'skills/scripts/fleet-sync.ps1')} Sync-Directory
$LocalRepoRoot = {ps_quote(tmp_path)}
$RemotePath = 'synthetic-remote'; $SshTarget = 'mock'
$script:Collisions = [System.Collections.Generic.List[string]]::new()
$script:Copied = [System.Collections.Generic.List[string]]::new()
function Get-RemoteFileNames {{ @('b.MD', 'remote-only.md', 'a.MD') }}
function Invoke-FleetCopy {{}}
Sync-Directory journal {direction}
@{{ collisions=@($script:Collisions); copied=@($script:Copied) }} | ConvertTo-Json -Compress
'''
    result = json.loads(ps_run(ps_engine, tmp_path, body))
    names = [item.split(" ", 1)[0].split("\\")[-1] for item in result["collisions"]]
    assert names == (["b.MD", "a.MD"] if direction == "Pull" else ["A.md", "b.md"])
    assert len(result["copied"]) == 1


@pytest.mark.parametrize("stage", ["pre-import", "still-broken", "dispatch-exit", "dispatch-import"])
def test_launcher_only_repairs_before_dispatch(tmp_path, monkeypatch, capfd, stage):
    launcher = load_launcher()
    package = tmp_path / "synthetic pack"
    (package / "scripts").mkdir(parents=True)
    (package / "reverse_skill").mkdir()
    (package / "pyproject.toml").write_text("synthetic manifest")
    (package / "reverse_skill/__init__.py").touch()
    flag = package / "repaired"
    events = package / "dispatches"
    cli = "from pathlib import Path\n"
    if stage in {"pre-import", "still-broken"}:
        cli += f"if not Path({str(flag)!r}).exists(): raise ModuleNotFoundError('synthetic missing dependency')\n"
    cli += f"def main():\n    with Path({str(events)!r}).open('a') as stream: stream.write('dispatched\\n')\n"
    cli += ("    raise ImportError('failure inside command')\n" if stage == "dispatch-import"
            else "    return 86\n" if stage == "dispatch-exit" else "    return 0\n")
    (package / "reverse_skill/cli.py").write_text(cli)
    runtime = tmp_path / "runtime"
    venv.EnvBuilder(system_site_packages=True, with_pip=False).create(runtime)
    interpreter = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    purelib = subprocess.check_output([str(interpreter), "-I", "-c",
                                      "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
    (Path(purelib) / "package.pth").write_text(str(package), encoding="utf-8")
    signature = launcher.hashlib.sha256(
        (package / "pyproject.toml").read_bytes() + sys.version.encode("utf-8")
    ).hexdigest()
    (runtime / "reverse-skill-runtime.json").write_text(json.dumps({
        "source": str(package.resolve()), "signature": signature,
    }))
    monkeypatch.setattr(launcher, "__file__", str(package / "scripts/run.py"))
    monkeypatch.setenv("REVERSE_SKILL_RUNTIME", str(runtime))
    real_run = launcher.subprocess.run
    repairs = []

    def run(argv, **options):
        if "pip" in argv:
            repairs.append(argv)
            if stage == "pre-import":
                flag.touch()
            return subprocess.CompletedProcess(argv, 0)
        return real_run(argv, **options)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    result = launcher.main(["--json", "synthetic-command"])
    captured = capfd.readouterr()
    if stage == "still-broken":
        assert result == 3 and not events.exists()
        value = json.loads(captured.out)
        assert value["command"] == "runtime" and value["error"]["code"] == "EnvironmentUnavailable"
    else:
        assert result == {"pre-import": 0, "dispatch-exit": 86, "dispatch-import": 1}[stage]
        assert events.read_text().splitlines() == ["dispatched"]
    assert len(repairs) == (1 if stage in {"pre-import", "still-broken"} else 0)


def test_refresh_shares_one_fresh_version_snapshot(tmp_path):
    if not BASH or not shutil.which("jq"):
        pytest.skip("Bash and jq are required")
    scripts = tmp_path / "kali/scripts"
    (scripts / "lib").mkdir(parents=True)
    shutil.copy2(ROOT / "kali/scripts/refresh-tool-index.sh", scripts)
    tool = tmp_path / "mock-tool.sh"
    trace = tmp_path / "versions.txt"
    tool.write_text("#!/usr/bin/env bash\n"
                    f"echo called >> {shlex.quote(trace.as_posix())}\n"
                    'echo "$REVERSE_TEST_VERSION"\n', encoding="utf-8")
    tool.chmod(0o755)
    library = (ROOT / "kali/scripts/lib/tool-discovery.sh").read_text(encoding="utf-8")
    library += f'''
TOOL_CATALOG=('first|test|synthetic|--version|mock1' 'second|test|synthetic|--version|mock2' 'third|test|synthetic|--version|mock3')
declare -A SCRIPT_REFS=()
find_command() {{ printf '%s\\n' {shlex.quote(tool.as_posix())}; }}
check_mcp_registered() {{ echo false; }}
test_tcp_port() {{ return 1; }}
'''
    (scripts / "lib/tool-discovery.sh").write_text(library, encoding="utf-8")
    for version in ("snapshot-one", "snapshot-two"):
        result = subprocess.run([BASH, str(scripts / "refresh-tool-index.sh"),
                                 "index.md", "index.json", "graph.json"], cwd=tmp_path,
                                env={**os.environ, "REVERSE_TEST_VERSION": version},
                                capture_output=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stderr
        data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert [item["name"] for item in data["tools"]] == ["first", "second", "third"]
        assert {item["version"] for item in data["tools"]} == {version}
        markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
        assert markdown.count(version) == 3
    assert trace.read_text().splitlines() == ["called"] * 6


@pytest.mark.parametrize("failure", ["api", "download", "extract", "publish"])
def test_release_installer_propagates_nested_failures(tmp_path, failure):
    # Use the real helper in the same conditional call shape as production.
    script = "set -euo pipefail\n" + bootstrap_functions() + f'''
TMPDIR={shlex.quote(tmp_path.as_posix())}
curl() {{
    if [[ "$*" == *releases/latest* ]]; then
        {'return 22' if failure == 'api' else 'echo metadata; return 0'}
    fi
    {'return 22' if failure == 'download' else 'return 0'}
}}
jq() {{ echo https://mock.invalid/jadx.zip; }}
unzip() {{ {'return 9' if failure == 'extract' else 'return 0'}; }}
cp() {{ return 19; }}
if install_github_release mock mock "$TMPDIR/install"; then echo ready; else echo failed; fi
'''
    result = bash_run(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "failed"
    assert not list(tmp_path.glob("reverse-bootstrap.*"))


def test_jadx_release_extracts_and_checks_health(tmp_path):
    archive = tmp_path / "release.zip"
    trace = tmp_path / "health.txt"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("jadx-1/bin/jadx", "#!/usr/bin/env bash\n"
                         f"echo \"$*\" > {shlex.quote(trace.as_posix())}\necho synthetic-version\n")
    target = tmp_path / "installed"
    functions = bootstrap_functions().replace("$HOME/tools/jadx", "$TEST_JADX_DIR")
    script = "set -euo pipefail\n" + functions + f'''
TMPDIR={shlex.quote(tmp_path.as_posix())}
TEST_JADX_DIR={shlex.quote(target.as_posix())}
command() {{ return 1; }}
curl() {{
    if [[ "$*" == *releases/latest* ]]; then
        echo '{{"assets":[{{"name":"jadx-1.zip","browser_download_url":"https://mock.invalid/jadx-1.zip"}}]}}'
        return 0
    fi
    cp {shlex.quote(archive.as_posix())} "$3"
}}
if ensure_capability jadx; then echo ready; else echo failed; fi
'''
    result = bash_run(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "ready", result.stdout + result.stderr
    assert trace.read_text().strip() == "--version"
    assert not list(tmp_path.glob("reverse-bootstrap.*"))


def test_report_sections_do_not_copy_unread_suffixes():
    class TrackedText(str):
        copied = 0

        def __getitem__(self, key):
            value = super().__getitem__(key)
            if isinstance(key, slice):
                self.copied += len(value)
            return value

    text = TrackedText("".join(f"### F-{index} Title\nbody\n" for index in range(1000)))
    sections = report_sections(text, FINDING_HEADING)
    assert len(sections) == 1000
    assert text.copied == len(text)


def test_bootstrap_collects_failures_and_returns_nonzero():
    source = (ROOT / "kali/scripts/bootstrap-reverse.sh").read_text(encoding="utf-8")
    body = source[source.index("RESULTS=()") :]
    script = '''set -euo pipefail
CAPABILITIES=(bad good)
SKIP_REFRESH=true
ensure_capability() { [[ "$1" == good ]]; }
''' + body
    result = bash_run(script)
    assert result.returncode == 1
    assert "bad (failed)" in result.stdout
    assert "✓ good" in result.stdout


def test_complete_jar_keeps_apk_build_without_adb(ps_engine, tmp_path, executable_jars):
    # Reuse the existing inert tool harness, with a complete JAR instead of an empty file.
    spec = importlib.util.spec_from_file_location("ps_build_harness", ROOT / "tests/test_powershell_scripts.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    bin_dir, trace = harness.fake_tools(tmp_path, ["java", "zipalign", "apksigner", "keytool"])
    jar = tmp_path / "Tools/apktool/apktool.jar"
    jar.parent.mkdir(parents=True)
    shutil.copy2(executable_jars["good"], jar)
    project = tmp_path / "sample project"
    project.mkdir()
    keystore = tmp_path / "debug.keystore"
    keystore.touch()
    harness.run_ps(ps_engine, tmp_path,
                   f"& {ps_quote(ROOT / 'skills/apk-reverse/scripts/rebuild-sign-install.ps1')} "
                   f"-ProjectDir {ps_quote(project)} -OutDir {ps_quote(tmp_path)} -KeystorePath {ps_quote(keystore)}", bin_dir)
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [name for name, _ in calls] == ["java", "zipalign", "apksigner", "apksigner"]
    assert calls[0][1][:3] == ["-jar", str(jar), "b"]
    assert (tmp_path / "sample project-signed.apk").read_text() == "signed"
