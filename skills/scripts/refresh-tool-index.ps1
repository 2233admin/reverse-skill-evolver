[CmdletBinding()]
param(
    [string]$OutputMarkdown,
    [string]$OutputJson,
    [string]$OutputCapabilityGraph
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if ([string]::IsNullOrWhiteSpace($OutputMarkdown)) {
    $OutputMarkdown = Join-Path $PSScriptRoot '..\tool-index.md'
}
if ([string]::IsNullOrWhiteSpace($OutputJson)) {
    $OutputJson = Join-Path $PSScriptRoot '..\tool-index.json'
}
if ([string]::IsNullOrWhiteSpace($OutputCapabilityGraph)) {
    $OutputCapabilityGraph = Join-Path $PSScriptRoot '..\capability-graph.json'
}

. (Join-Path $PSScriptRoot 'lib\ToolDiscovery.ps1')

$scriptRefs = @{
    'jadx' = @('apk-reverse/scripts/decode.ps1')
    'apktool' = @('apk-reverse/scripts/decode.ps1', 'apk-reverse/scripts/rebuild-sign-install.ps1')
    'adb' = @('apk-reverse/scripts/rebuild-sign-install.ps1')
    'java' = @('apk-reverse/scripts/decode.ps1')
    'apksigner' = @('apk-reverse/scripts/rebuild-sign-install.ps1')
    'zipalign' = @('apk-reverse/scripts/rebuild-sign-install.ps1')
    'frida' = @('apk-reverse/scripts/frida-run.ps1')
    'frida-ps' = @('apk-reverse/scripts/frida-run.ps1')
    'r2' = @('radare2/scripts/recon.ps1')
    'rabin2' = @('radare2/scripts/recon.ps1')
    'rasm2' = @('radare2/SKILL.md')
    'radiff2' = @('radare2/SKILL.md')
    'rahash2' = @('radare2/SKILL.md')
    'rax2' = @('radare2/SKILL.md')
    'python' = @('apk-reverse/scripts/frida-run.ps1')
    'pip' = @()
    'node' = @('js-reverse/SKILL.md')
    'npx' = @('js-reverse/SKILL.md')
    'jshookmcp' = @('js-reverse/SKILL.md')
    'agent-browser' = @('browser-automation/SKILL.md')
    'playwright' = @('browser-automation/SKILL.md', 'browser-automation/scripts/setup.ps1')
    'analyzeHeadless' = @('reverse-engineering/SKILL.md')
    'proxycat' = @('pentest-tools/SKILL.md')
    'nmap' = @('pentest-tools/SKILL.md')
}

$reports = @(Get-ReverseToolReport)
$generatedAt = Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'

$markdownLines = @(
    '# 逆向工具索引',
    '',
    "- 扫描时间: $generatedAt",
    '- 路由入口: `SKILL.md` → `routing.md` → 对应子 skill',
    '- 说明: 本表由 `scripts/refresh-tool-index.ps1` 自动生成，优先用于 Claude 路由和工具路径确认。',
    '- 注意: 对于 jshookmcp 这类 MCP server，`yes` 只表示本机具备通过 node/npx 拉起它的条件，不表示它已经在 Claude MCP 配置里注册并启用。',
    '',
    '| 工具 | 归属 skill | 作用 | 可用 | 路径 | 版本 | 来源 | 脚本引用 |',
    '|---|---|---|---|---|---|---|---|'
)

foreach ($report in $reports) {
    $pathText = if ($report.ResolvedPath) { $report.ResolvedPath } else { '—' }
    $versionText = if ($report.Version) { $report.Version } else { '—' }
    $refs = $scriptRefs[$report.Name]
    $refsText = if ($refs -and $refs.Count -gt 0) { ($refs -join '<br>') } else { '—' }
    $availableText = if ($report.Available) { 'yes' } else { 'no' }
    $escapedPath = $pathText.Replace('|', '\|')
    $escapedVersion = $versionText.Replace('|', '\|')
    $escapedRefs = $refsText.Replace('|', '\|')
    $markdownLines += "| $($report.Name) | $($report.Skill) | $($report.Purpose) | $availableText | $escapedPath | $escapedVersion | $($report.Source) | $escapedRefs |"
}

$markdownContent = ($markdownLines -join [Environment]::NewLine) + [Environment]::NewLine
$markdownContent | Set-Content -LiteralPath $OutputMarkdown -Encoding utf8

# --- Capability status view ---
$capabilityNames = @('jadx', 'apktool', 'frida', 'idalib-mcp', 'jshookmcp', 'anything-analyzer', 'idapro', 'r2', 'adb', 'agent-browser', 'ghidra-mcp', 'seclists', 'proxycat', 'burpsuite-mcp', 'nmap')
$capabilityRows = @()
foreach ($capName in $capabilityNames) {
    $state = Get-ReverseCapabilityState -Name $capName
    if ($null -eq $state) { continue }
    $toolAvailable = $false
    try {
        $toolSpec = Resolve-ReverseToolSpec -Name $capName
        $toolAvailable = $toolSpec.Available
    }
    catch {
        # Capability exists in bootstrap manifest but not in tool catalog (e.g. MCP-only capabilities)
        $toolAvailable = $false
    }
    $capabilityRows += [pscustomobject]@{
        name = $capName
        tool_available = $toolAvailable
        mcp_registered = $state.Registered
        service_online = $state.ServiceOnline
        can_auto_install = $state.CanAutoInstall
        bootstrap_kind = $state.BootstrapKind
    }
}

# Append capability view to markdown
$markdownCapLines = @(
    '',
    '---',
    '',
    '## 能力状态视图 (Capability Status)',
    '',
    '| 能力 | 工具可用 | MCP 已注册 | 服务在线 | 可自动安装 | 安装方式 |',
    '|------|---------|-----------|---------|-----------|---------|'
)
foreach ($cap in $capabilityRows) {
    $toolText = if ($cap.tool_available) { '✓' } else { '✗' }
    $mcpText = if ($cap.mcp_registered) { '✓' } else { '—' }
    $svcText = if ($cap.service_online) { '✓' } else { '—' }
    $autoText = if ($cap.can_auto_install) { '✓' } else { '✗' }
    $kindText = if ($cap.bootstrap_kind) { $cap.bootstrap_kind } else { '—' }
    $markdownCapLines += "| $($cap.name) | $toolText | $mcpText | $svcText | $autoText | $kindText |"
}
$markdownCapLines += ''
$markdownCapLines += '> ✓ = 是 | ✗ = 否 | — = 不适用或未检测'
$markdownCapLines += ''

$capContent = ($markdownCapLines -join [Environment]::NewLine)
Add-Content -LiteralPath $OutputMarkdown -Value $capContent -Encoding utf8

$jsonRows = foreach ($report in $reports) {
    [pscustomobject]@{
        name = $report.Name
        skill = $report.Skill
        purpose = $report.Purpose
        available = $report.Available
        resolved_path = $report.ResolvedPath
        version = $report.Version
        source = $report.Source
        script_refs = @($scriptRefs[$report.Name])
    }
}

$jsonPayload = [pscustomobject]@{
    generated_at = $generatedAt
    routing_entry = @('SKILL.md', 'routing.md')
    tools = $jsonRows
    capabilities = $capabilityRows
}

$jsonPayload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputJson -Encoding utf8

# --- Capability graph ---
$toolNodes = foreach ($report in $reports) {
    $smokeStatus = 'missing'
    if ($report.Available -and -not [string]::IsNullOrWhiteSpace([string]$report.Version)) {
        $smokeStatus = 'pass'
    }
    elseif ($report.Available) {
        $smokeStatus = 'available_no_version'
    }

    [pscustomobject]@{
        id = $report.Name
        kind = 'tool'
        owning_skill = $report.Skill
        purpose = $report.Purpose
        available = [bool]$report.Available
        resolved_path = $report.ResolvedPath
        version = $report.Version
        source = $report.Source
        bootstrap_kind = $report.BootstrapKind
        can_auto_install = [bool]$report.CanAutoInstall
        mcp_registered = [bool]$report.McpRegistered
        service_online = [bool]$report.ServiceOnline
        smoke_status = $smokeStatus
        script_refs = @($scriptRefs[$report.Name])
    }
}

$serviceNodes = foreach ($cap in $capabilityRows) {
    $serviceStatus = 'not_applicable'
    if ($cap.mcp_registered -or $cap.service_online) {
        $serviceStatus = 'pass'
    }
    elseif ($cap.bootstrap_kind -eq 'local-http-mcp' -or $cap.bootstrap_kind -eq 'npm-mcp') {
        $serviceStatus = 'not_online'
    }

    [pscustomobject]@{
        id = $cap.name
        kind = 'capability'
        tool_available = [bool]$cap.tool_available
        mcp_registered = [bool]$cap.mcp_registered
        service_online = [bool]$cap.service_online
        can_auto_install = [bool]$cap.can_auto_install
        bootstrap_kind = $cap.bootstrap_kind
        smoke_status = $serviceStatus
    }
}

$capabilityGraph = [pscustomobject]@{
    schema_version = 1
    generated_at = $generatedAt
    platform = [pscustomobject]@{
        os = [System.Environment]::OSVersion.Platform.ToString()
        version = [System.Environment]::OSVersion.VersionString
    }
    routing_entry = @('SKILL.md', 'routing.json', 'routing.md')
    nodes = @($toolNodes) + @($serviceNodes)
    memory_policy = [pscustomobject]@{
        validated = 'may influence future routing'
        candidate = 'advisory only'
        forensic = 'analysis only'
    }
    promotion_gate = [pscustomobject]@{
        requires_oracle_pass = $true
        requires_regression_check = $true
        requires_sensitive_data_scan = $true
        requires_rollback = $true
    }
}

$capabilityGraph | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputCapabilityGraph -Encoding utf8

"markdown=$OutputMarkdown"
"json=$OutputJson"
"capability_graph=$OutputCapabilityGraph"
"tools=$($reports.Count)"

