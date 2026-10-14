import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "skills/scripts/lib/ToolDiscovery.ps1"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell entrypoints")


def quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture(params=["powershell", "pwsh"])
def engine(request: pytest.FixtureRequest) -> str:
    executable = shutil.which(request.param)
    if executable is None:
        pytest.skip(f"{request.param} is unavailable")
    return executable


def run_ps(engine: str, tmp_path: Path, body: str, bin_dir: Path | None = None, expected_exit: int = 0) -> str:
    script = tmp_path / "test.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
        + body,
        encoding="utf-8-sig",
    )
    env = dict(os.environ)
    env.update(
        USERPROFILE=str(tmp_path),
        LOCALAPPDATA=str(tmp_path),
        APPDATA=str(tmp_path),
        UV_TOOL_BIN_DIR="",
        ANDROID_HOME="",
        ANDROID_SDK_ROOT="",
        PATH=str(bin_dir) if bin_dir else "",
    )
    result = subprocess.run(
        [engine, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr
    return result.stdout if expected_exit == 0 else result.stdout + result.stderr


def fake_tools(tmp_path: Path, names: list[str]) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    trace = tmp_path / "calls.jsonl"
    stub = tmp_path / "tool.py"
    stub.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"trace = Path({str(trace)!r})\n"
        "tool, *args = sys.argv[1:]\n"
        "with trace.open('a', encoding='utf-8') as out:\n"
        "    out.write(json.dumps([tool, args]) + '\\n')\n"
        "if tool == os.environ.get('REVERSE_TEST_FAIL_TOOL'):\n"
        "    sys.exit(17)\n"
        "if tool in ('apktool', 'java'):\n"
        "    Path(args[args.index('-o') + 1]).write_text('unsigned')\n"
        "elif tool == 'zipalign':\n"
        "    Path(args[-1]).write_text('aligned')\n"
        "elif tool == 'apksigner' and args[0] == 'sign':\n"
        "    Path(args[args.index('--out') + 1]).write_text('signed')\n"
        "print(tool)\n",
        encoding="utf-8",
    )
    for name in names:
        if os.name == "nt":
            (bin_dir / f"{name}.cmd").write_text(
                f'@"{sys.executable}" "{stub}" "{name}" %*\n', encoding="utf-8"
            )
        else:
            executable = bin_dir / name
            executable.write_text(
                f"#!{sys.executable}\n"
                "import runpy, sys\n"
                f"sys.argv = [{str(stub)!r}, {name!r}, *sys.argv[1:]]\n"
                f"runpy.run_path({str(stub)!r}, run_name='__main__')\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
    return bin_dir, trace


def test_jar_is_unavailable_without_java(engine: str, tmp_path: Path) -> None:
    jar = tmp_path / "Tools/apktool/apktool.jar"
    jar.parent.mkdir(parents=True)
    jar.touch()
    output = run_ps(
        engine, tmp_path,
        f". {quote(LIBRARY)}\nResolve-ReverseToolSpec -Name apktool | ConvertTo-Json -Compress",
    )
    spec = json.loads(output)
    assert spec["Available"] is False
    assert spec["Command"] == ""


def test_fallbacks_find_new_installs_and_newest_sdk(engine: str, tmp_path: Path) -> None:
    sdk = tmp_path / "Android/Sdk/build-tools"
    for version in ("9.0.0", "35.0.0"):
        directory = sdk / version
        directory.mkdir(parents=True)
        (directory / "zipalign.exe").touch()
    python_bin = tmp_path / "Python/Python313/Scripts"
    python_bin.mkdir(parents=True)
    (python_bin / "frida-ps.exe").touch()
    uv_bin = tmp_path / ".local/bin"
    uv_bin.mkdir(parents=True)
    output = run_ps(engine, tmp_path, f"""
. {quote(LIBRARY)}
$before = Resolve-ReverseToolSpec -Name frida
New-Item -ItemType File -Path {quote(uv_bin / 'frida.exe')} | Out-Null
$after = Resolve-ReverseToolSpec -Name frida
@{{ before = $before.Available; after = $after.ResolvedPath;
    sdk = (Resolve-ReverseToolSpec -Name zipalign).ResolvedPath;
    python = (Resolve-ReverseToolSpec -Name frida-ps).ResolvedPath }} | ConvertTo-Json -Compress
""")
    result = json.loads(output)
    assert result["before"] is False
    assert Path(result["after"]) == uv_bin / "frida.exe"
    assert Path(result["sdk"]) == sdk / "35.0.0/zipalign.exe"
    assert Path(result["python"]) == python_bin / "frida-ps.exe"


def test_mcp_config_roundtrip_preserves_other_servers(engine: str, tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    original = {"other": [1, True], "mcpServers": {"existing": {"args": ["a", "b"]}}}
    config.write_text(json.dumps(original), encoding="utf-8")
    bootstrap = ROOT / "skills/scripts/bootstrap-reverse.ps1"
    run_ps(engine, tmp_path, f"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({quote(bootstrap)}, [ref]$tokens, [ref]$errors)
$names = @('Get-McpConfig', 'Save-McpConfig', 'Ensure-McpServer')
$functions = $ast.FindAll({{ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names
}}, $false)
foreach ($node in $functions) {{ Invoke-Expression $node.Extent.Text }}
function Get-ClaudeMcpConfigPath {{ return {quote(config)} }}
Ensure-McpServer -ServerName new-server -ServerDefinition @{{ command = 'npx'; args = @('package'); env = @{{ MODE = 'test' }} }}
""")
    actual = json.loads(config.read_text(encoding="utf-8-sig"))
    assert actual["other"] == original["other"]
    assert actual["mcpServers"]["existing"] == original["mcpServers"]["existing"]
    assert actual["mcpServers"]["new-server"]["env"] == {"MODE": "test"}


@pytest.mark.parametrize("listing", ["devices", "processes"])
def test_frida_listing_uses_only_requested_cli(engine: str, tmp_path: Path, listing: str) -> None:
    name = "frida-ls-devices" if listing == "devices" else "frida-ps"
    bin_dir, trace = fake_tools(tmp_path, [name])
    switch = "-ListDevices" if listing == "devices" else "-Usb -ListProcesses"
    run_ps(engine, tmp_path,
           f"& {quote(ROOT / 'skills/apk-reverse/scripts/frida-run.ps1')} {switch}", bin_dir)
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert calls == [[name, [] if listing == "devices" else ["-U"]]]


@pytest.mark.parametrize("pause", [False, True])
def test_frida_spawn_arguments(engine: str, tmp_path: Path, pause: bool) -> None:
    bin_dir, trace = fake_tools(tmp_path, ["frida", "frida-ps", "frida-ls-devices"])
    hook = tmp_path / "hook with space.js"
    hook.touch()
    run_ps(engine, tmp_path,
           f"& {quote(ROOT / 'skills/apk-reverse/scripts/frida-run.ps1')} -Usb -Spawn "
           f"-Package com.example.app -ScriptPath {quote(hook)} {'-Pause' if pause else ''}", bin_dir)
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert calls == [["frida", ["-U", "-f", "com.example.app", "-l", str(hook)] + (["--pause"] if pause else [])]]


@pytest.mark.parametrize("jar_only", [False, True])
def test_apk_build_needs_adb_only_when_installing(engine: str, tmp_path: Path, jar_only: bool) -> None:
    bin_dir, trace = fake_tools(tmp_path, ["java" if jar_only else "apktool", "zipalign", "apksigner", "keytool"])
    if jar_only:
        jar = tmp_path / "Tools/apktool/apktool.jar"
        jar.parent.mkdir(parents=True)
        # Java execution is stubbed; discovery still checks the real ZIP structure.
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\r\nMain-Class: Main\r\n\r\n")
            archive.writestr("Main.class", b"synthetic class for the inert Java stub")
    project = tmp_path / "sample project"
    project.mkdir()
    keystore = tmp_path / "debug.keystore"
    keystore.touch()
    run_ps(engine, tmp_path,
           f"& {quote(ROOT / 'skills/apk-reverse/scripts/rebuild-sign-install.ps1')} "
           f"-ProjectDir {quote(project)} -OutDir {quote(tmp_path)} -KeystorePath {quote(keystore)}", bin_dir)
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [name for name, _ in calls] == ["java" if jar_only else "apktool", "zipalign", "apksigner", "apksigner"]
    assert (tmp_path / "sample project-signed.apk").read_text() == "signed"
    if jar_only:
        assert calls[0][1][:3] == ["-jar", str(jar), "b"]


def test_all_powershell_scripts_parse(engine: str, tmp_path: Path) -> None:
    run_ps(engine, tmp_path, f"""
Get-ChildItem -LiteralPath {quote(ROOT / 'skills')} -Recurse -Filter *.ps1 | ForEach-Object {{
    $tokens = $null; $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) {{ throw ($_.FullName + ': ' + ($errors.Message -join '; ')) }}
}}
""")


@pytest.mark.parametrize("failed_tool", ["ssh", "scp"])
def test_fleet_sync_stops_on_transport_errors(engine: str, tmp_path: Path, failed_tool: str) -> None:
    bin_dir, _ = fake_tools(tmp_path, ["ssh", "scp"])
    output = run_ps(engine, tmp_path,
                    f"$env:REVERSE_TEST_FAIL_TOOL = {quote(failed_tool)}\n"
                    f"& {quote(ROOT / 'skills/scripts/fleet-sync.ps1')} "
                    "-RemoteHost example.invalid -RemotePath 'D:\\test project' -Direction Push",
                    bin_dir, expected_exit=1)
    assert f"{failed_tool.upper()} failed (17)" in output
    assert "=== Copied" not in output


def test_required_tool_bootstraps_the_owning_package(engine: str, tmp_path: Path) -> None:
    executable = tmp_path / "Tools/radare2/bin/rabin2.exe"
    executable.parent.mkdir(parents=True)
    output = run_ps(engine, tmp_path, f"""
. {quote(LIBRARY)}
function powershell.exe {{
    $script:bootstrapArgs = $args
    New-Item -ItemType File -Path {quote(executable)} | Out-Null
    $global:LASTEXITCODE = 0
    '{{"status":"ready"}}'
}}
$specs = @(Get-RequiredReverseToolSpec -Name rabin2)
@{{ count = $specs.Count; name = $specs[0].Name;
    capability = $script:bootstrapArgs[$script:bootstrapArgs.IndexOf('-Capability') + 1] }} | ConvertTo-Json -Compress
""")
    assert json.loads(output.splitlines()[-1]) == {"count": 1, "name": "rabin2", "capability": "r2"}


def test_bootstrap_unknown_capability_exits_nonzero(engine: str, tmp_path: Path) -> None:
    output = run_ps(engine, tmp_path,
                    f"& {quote(ROOT / 'skills/scripts/bootstrap-reverse.ps1')} "
                    "-Capability nonexistent-test-tool -SkipRefresh\nexit $LASTEXITCODE", expected_exit=1)
    assert json.loads(output)["status"] == "missing-definition"


def test_tool_alias_reports_inherit_owner_state_without_changing_tool_identity(
    engine: str, tmp_path: Path,
) -> None:
    manifest = tmp_path / "bootstrap-manifest.json"
    manifest.write_text(json.dumps({"capabilities": [
        {"name": "frida", "bootstrapKind": "uv-tool", "canAutoInstall": True,
         "docsUrl": "https://example.invalid/frida"},
        {"name": "r2", "bootstrapKind": "github-release-zip", "canAutoInstall": True,
         "docsUrl": "https://example.invalid/r2", "mcpNames": ["fixture-r2"], "servicePort": 17401},
        {"name": "java", "bootstrapKind": "manual", "canAutoInstall": False,
         "docsUrl": "https://example.invalid/java"},
    ]}), encoding="utf-8")
    config = tmp_path / ".claude/mcp.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"mcpServers": {
        "fixture-r2": {"command": "fixture-only"},
        "unrelated": {"args": ["keep", "these"]},
    }}), encoding="utf-8")
    original_config = config.read_bytes()
    tool_dir = tmp_path / "fixture-tools"
    tool_dir.mkdir()
    for name in ("frida-ls-devices", "r2"):
        (tool_dir / f"{name}.exe").touch()
    owners = {
        "frida": "frida", "frida-ps": "frida", "frida-ls-devices": "frida",
        "r2": "r2", "rabin2": "r2", "rasm2": "r2", "radiff2": "r2",
        "rahash2": "r2", "rax2": "r2", "java": "java",
    }
    output = run_ps(engine, tmp_path, f"""
. {quote(LIBRARY)}
function Get-ReverseBootstrapManifestPath {{ return {quote(manifest)} }}
function Test-ReverseTcpPort {{ param([int]$Port) return ($Port -eq 17401) }}
function Get-ReverseToolVersion {{ param($Spec) return '' }}
foreach ($tool in Get-ReverseToolCatalog) {{
    $tool.Fallbacks = @([pscustomobject]@{{ Type = 'path'; Value = (Join-Path {quote(tool_dir)} ($tool.Name + '.exe')) }})
}}
$names = @({', '.join(quote(name) for name in owners)})
@{{ reports = @(Get-ReverseToolReport -Names $names);
    states = @($names | ForEach-Object {{ Get-ReverseCapabilityState -Name $_ }});
    unknown = Get-ReverseCapabilityState -Name fixture-unknown }} | ConvertTo-Json -Depth 6 -Compress
""")
    result = json.loads(output)
    assert config.read_bytes() == original_config
    assert result["unknown"] is None
    assert all(row is not None for row in result["states"]), "Every tool alias needs its owner's state"
    reports = {row["Name"]: row for row in result["reports"]}
    states = {row["Name"]: row for row in result["states"]}
    assert reports.keys() == states.keys() == owners.keys()
    kinds = {"frida": "uv-tool", "r2": "github-release-zip", "java": "manual"}
    for name, owner in owners.items():
        report, state = reports[name], states[name]
        assert report["BootstrapKind"] == state["BootstrapKind"] == kinds[owner]
        assert report["CanAutoInstall"] is state["CanAutoInstall"] is (owner != "java")
        assert report["DocsUrl"] == state["DocsUrl"] == f"https://example.invalid/{owner}"
        assert report["McpRegistered"] is state["Registered"] is (owner == "r2")
        assert report["ServiceOnline"] is state["ServiceOnline"] is (owner == "r2")
        installed = name in {"frida-ls-devices", "r2"}
        assert report["Available"] is installed
        assert report["ResolvedPath"] == (str(tool_dir / f"{name}.exe") if installed else "")
        assert report["Source"] == ("FallbackPath" if installed else "Missing")


def test_refresh_entry_writes_consistent_indexes(engine: str, tmp_path: Path) -> None:
    scripts = tmp_path / "skills/scripts"
    (scripts / "lib").mkdir(parents=True)
    shutil.copy2(ROOT / "skills/scripts/refresh-tool-index.ps1", scripts)
    shutil.copy2(LIBRARY, scripts / "lib")
    (scripts / "bootstrap-manifest.json").write_text(json.dumps({"capabilities": [
        {"name": "frida", "bootstrapKind": "uv-tool", "canAutoInstall": True,
         "docsUrl": "https://example.invalid/frida"},
        {"name": "r2", "bootstrapKind": "github-release-zip", "canAutoInstall": True,
         "docsUrl": "https://example.invalid/r2"},
        {"name": "idalib-mcp", "bootstrapKind": "local-http-mcp", "canAutoInstall": False,
         "docsUrl": "https://example.invalid/idalib", "mcpNames": ["fixture-ida"]},
    ]}), encoding="utf-8")
    config = tmp_path / ".claude/mcp.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"mcpServers": {"fixture-ida": {"command": "fixture-only"}}}),
                      encoding="utf-8")
    original_config = config.read_bytes()
    bin_dir, _ = fake_tools(tmp_path, ["reverse-skill"])
    markdown = tmp_path / "tools.md"
    index = tmp_path / "tools.json"
    graph = tmp_path / "graph.json"
    run_ps(engine, tmp_path,
           f"& {quote(scripts / 'refresh-tool-index.ps1')} "
           f"-OutputMarkdown {quote(markdown)} -OutputJson {quote(index)} -OutputCapabilityGraph {quote(graph)}",
           bin_dir)
    payload = json.loads(index.read_text(encoding="utf-8-sig"))
    nodes = json.loads(graph.read_text(encoding="utf-8-sig"))["nodes"]
    tools = {tool["name"]: tool for tool in payload["tools"]}
    assert {"keytool", "frida-ls-devices"} <= tools.keys()
    for capability in payload["capabilities"]:
        if capability["name"] in tools:
            assert capability["tool_available"] == tools[capability["name"]]["available"]
    assert {node["id"] for node in nodes if node["kind"] == "tool"} == tools.keys()
    tool_nodes = {node["id"]: node for node in nodes if node["kind"] == "tool"}
    for name in ("frida-ps", "frida-ls-devices", "rabin2", "rasm2", "radiff2", "rahash2", "rax2"):
        owner = "frida" if name.startswith("frida-") else "r2"
        node = tool_nodes[name]
        assert node["can_auto_install"] is True
        assert node["bootstrap_kind"] == tool_nodes[owner]["bootstrap_kind"]
        assert node["available"] == tools[name]["available"]
        assert node["resolved_path"] == tools[name]["resolved_path"]
    capabilities = {row["name"]: row for row in payload["capabilities"]}
    capability_nodes = {node["id"]: node for node in nodes if node["kind"] == "capability"}
    assert capabilities.keys() == capability_nodes.keys() == {"frida", "r2", "idalib-mcp"}
    for name, capability in capabilities.items():
        for field in ("tool_available", "mcp_registered", "service_online", "can_auto_install", "bootstrap_kind"):
            assert capability_nodes[name][field] == capability[field]
    assert capabilities["idalib-mcp"]["mcp_registered"] is True
    assert tools["idapro"]["available"] is tool_nodes["idapro"]["available"] is True
    assert tools["idapro"]["resolved_path"] == tool_nodes["idapro"]["resolved_path"] == str(bin_dir / "reverse-skill.cmd")
    tool_table, capability_table = markdown.read_text(encoding="utf-8-sig").split("## 能力状态视图", 1)
    assert "| idapro |" in tool_table
    assert "| idapro |" not in capability_table
    assert "| idalib-mcp |" in capability_table
    assert config.read_bytes() == original_config
