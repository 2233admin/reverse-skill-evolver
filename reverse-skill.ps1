<#
.SYNOPSIS
Register, start, inspect, and call the IDA Pro Streamable HTTP MCP service.

.EXAMPLE
.\reverse-skill.ps1 register

.EXAMPLE
.\reverse-skill.ps1 open -Path C:\path\to\sample.exe -TimeoutSeconds 600

.EXAMPLE
.\reverse-skill.ps1 call -Tool decompile -Database session-id -ArgumentsJson '{"addr":"0x140001000"}'
#>
#requires -Version 5

[CmdletBinding(PositionalBinding = $true)]
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'doctor', 'register', 'start', 'tools', 'open', 'sessions', 'call', 'close', 'refresh')]
    [string]$Command = 'status',

    [string]$Url = 'http://127.0.0.1:13337/mcp',
    [string]$Name = 'idapro',
    [string]$Path,
    [string]$Tool,
    [string]$ArgumentsJson = '{}',
    [string]$Database,
    [string]$PreferredSessionId,
    [ValidateSet('prefer_headless', 'force_headless', 'prefer_gui', 'force_gui')]
    [string]$Mode = 'prefer_headless',
    [switch]$NoAutoAnalysis,
    [switch]$NoBuildCaches,
    [switch]$NoSave,
    [switch]$Json,
    [int]$TimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$mcpClientScript = Join-Path $PSScriptRoot 'skills\scripts\lib\McpHttpClient.ps1'
$toolDiscoveryScript = Join-Path $PSScriptRoot 'skills\scripts\lib\ToolDiscovery.ps1'
. $mcpClientScript
. $toolDiscoveryScript

function Write-ReverseResult {
    param($Value)

    if ($Json) {
        $Value | ConvertTo-Json -Depth 50
    }
    else {
        $Value
    }
}

function Get-ReverseToolOutput {
    param($ToolResult)

    $structured = Get-McpPropertyValue -InputObject $ToolResult -Name 'structuredContent'
    if ($null -ne $structured) {
        return $structured
    }
    return $ToolResult
}

function Assert-ReverseOperationSuccess {
    param(
        [Parameter(Mandatory = $true)]$Output,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    if ((Get-McpPropertyValue -InputObject $Output -Name 'success') -eq $true) {
        return
    }
    $detail = Get-McpPropertyValue -InputObject $Output -Name 'error'
    if ([string]::IsNullOrWhiteSpace([string]$detail)) {
        $detail = Get-McpPropertyValue -InputObject $Output -Name 'message'
    }
    if ([string]::IsNullOrWhiteSpace([string]$detail)) {
        $detail = 'server did not confirm success'
    }
    throw "$Operation failed: $detail"
}

function Get-CodexMcpRegistration {
    param([string]$ServerName)

    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) {
        return $null
    }

    $output = & $codex.Source mcp get $ServerName --json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        $global:LASTEXITCODE = 0
        return $null
    }
    $global:LASTEXITCODE = 0
    return ($output -join [Environment]::NewLine) | ConvertFrom-Json
}

function Register-CodexMcp {
    param(
        [string]$ServerName,
        [string]$ServerUrl
    )

    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) {
        throw 'codex CLI is not installed or is not on PATH.'
    }

    $existing = Get-CodexMcpRegistration -ServerName $ServerName
    $transport = if ($null -ne $existing) { Get-McpPropertyValue -InputObject $existing -Name 'transport' } else { $null }
    $transportType = if ($null -ne $transport) { Get-McpPropertyValue -InputObject $transport -Name 'type' } else { $null }
    $transportUrl = if ($null -ne $transport) { Get-McpPropertyValue -InputObject $transport -Name 'url' } else { $null }
    $enabled = if ($null -ne $existing) { Get-McpPropertyValue -InputObject $existing -Name 'enabled' } else { $false }
    if ($null -ne $existing -and $transportType -eq 'streamable_http' -and
        $transportUrl -eq $ServerUrl -and $enabled -eq $true) {
        return [pscustomobject]@{ name = $ServerName; url = $ServerUrl; changed = $false; status = 'already_registered' }
    }

    if ($null -ne $existing) {
        & $codex.Source mcp remove $ServerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove existing Codex MCP registration: $ServerName"
        }
    }

    & $codex.Source mcp add $ServerName --url $ServerUrl | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register Codex MCP server: $ServerName"
    }

    [pscustomobject]@{ name = $ServerName; url = $ServerUrl; changed = $true; status = 'registered' }
}

function Add-DatabaseArgument {
    param(
        [Parameter(Mandatory = $true)]$Arguments,
        [string]$SessionId
    )

    if ([string]::IsNullOrWhiteSpace($SessionId)) {
        return $Arguments
    }
    if ($null -ne $Arguments.PSObject.Properties['database']) {
        $Arguments.database = $SessionId
    }
    else {
        $Arguments | Add-Member -NotePropertyName database -NotePropertyValue $SessionId
    }
    return $Arguments
}

if ($Command -eq 'doctor') {
    $Command = 'status'
}

switch ($Command) {
    'register' {
        Write-ReverseResult (Register-CodexMcp -ServerName $Name -ServerUrl $Url)
        break
    }
    'start' {
        $startScript = Join-Path $PSScriptRoot 'skills\ida-reverse\scripts\start.ps1'
        & $startScript -Port ([uri]$Url).Port
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        break
    }
    'refresh' {
        & (Join-Path $PSScriptRoot 'skills\scripts\refresh-tool-index.ps1')
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        break
    }
    'status' {
        $ida = Get-LatestIdaInstallation
        $registration = Get-CodexMcpRegistration -ServerName $Name
        $registeredTransport = if ($null -ne $registration) { Get-McpPropertyValue -InputObject $registration -Name 'transport' } else { $null }
        $registeredUrl = if ($null -ne $registeredTransport) { Get-McpPropertyValue -InputObject $registeredTransport -Name 'url' } else { $null }
        $registrationEnabled = if ($null -ne $registration) { Get-McpPropertyValue -InputObject $registration -Name 'enabled' } else { $false }
        $client = $null
        try {
            $client = New-McpHttpClient -Url $Url -TimeoutSeconds ([Math]::Min($TimeoutSeconds, 30))
            $toolList = Invoke-McpRequest -Client $client -Method 'tools/list' -TimeoutSeconds ([Math]::Min($TimeoutSeconds, 30))
            Write-ReverseResult ([pscustomobject]@{
                ida = if ($null -eq $ida) { $null } else { [pscustomobject]@{
                    version = $ida.Version
                    path    = $ida.InstallDir
                } }
                mcp = [pscustomobject]@{
                    url              = $Url
                    online           = $true
                    protocol_version = $client.ProtocolVersion
                    server           = $client.ServerInfo
                    session_mode     = -not [string]::IsNullOrWhiteSpace($client.SessionId)
                    tool_count       = @($toolList.tools).Count
                }
                codex = [pscustomobject]@{
                    registered = $null -ne $registration
                    name       = $Name
                    url        = $registeredUrl
                    enabled    = $registrationEnabled
                }
            })
        }
        catch {
            Write-ReverseResult ([pscustomobject]@{
                ida  = if ($null -eq $ida) { $null } else { [pscustomobject]@{ version = $ida.Version; path = $ida.InstallDir } }
                mcp  = [pscustomobject]@{ url = $Url; online = $false; error = $_.Exception.Message }
                codex = [pscustomobject]@{
                    registered = $null -ne $registration
                    name       = $Name
                    url        = $registeredUrl
                    enabled    = $registrationEnabled
                }
            })
            exit 1
        }
        finally {
            if ($null -ne $client) {
                Close-McpHttpClient -Client $client
            }
        }
        break
    }
    default {
        $client = New-McpHttpClient -Url $Url -TimeoutSeconds ([Math]::Min($TimeoutSeconds, 30))
        try {
            switch ($Command) {
                'tools' {
                    $result = Invoke-McpRequest -Client $client -Method 'tools/list' -TimeoutSeconds $TimeoutSeconds
                    if ($Json) {
                        Write-ReverseResult $result
                    }
                    else {
                        $result.tools | Select-Object name, description
                    }
                }
                'sessions' {
                    $result = Get-ReverseToolOutput (Invoke-McpTool -Client $client -Name 'idb_list' -TimeoutSeconds $TimeoutSeconds)
                    $listError = Get-McpPropertyValue -InputObject $result -Name 'error'
                    if (-not [string]::IsNullOrWhiteSpace([string]$listError)) {
                        throw "idb_list failed: $listError"
                    }
                    if ($Json) {
                        Write-ReverseResult $result
                    }
                    else {
                        $result.sessions | Select-Object session_id, filename, backend, is_analyzing, input_path
                    }
                }
                'open' {
                    if ([string]::IsNullOrWhiteSpace($Path)) {
                        throw 'open requires -Path.'
                    }
                    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
                    $openArguments = [pscustomobject]@{
                        input_path       = $resolvedPath
                        mode             = $Mode
                        run_auto_analysis = -not $NoAutoAnalysis
                        build_caches      = -not $NoBuildCaches
                        init_hexrays      = $true
                    }
                    if (-not [string]::IsNullOrWhiteSpace($PreferredSessionId)) {
                        $openArguments | Add-Member -NotePropertyName preferred_session_id -NotePropertyValue $PreferredSessionId
                    }
                    $result = Invoke-McpTool -Client $client -Name 'idb_open' -Arguments $openArguments -TimeoutSeconds $TimeoutSeconds
                    $output = Get-ReverseToolOutput $result
                    Assert-ReverseOperationSuccess -Output $output -Operation 'idb_open'
                    Write-ReverseResult $output
                }
                'call' {
                    if ([string]::IsNullOrWhiteSpace($Tool)) {
                        throw 'call requires -Tool.'
                    }
                    $arguments = $ArgumentsJson | ConvertFrom-Json
                    $arguments = Add-DatabaseArgument -Arguments $arguments -SessionId $Database
                    $result = Invoke-McpTool -Client $client -Name $Tool -Arguments $arguments -TimeoutSeconds $TimeoutSeconds
                    Write-ReverseResult (Get-ReverseToolOutput $result)
                }
                'close' {
                    if ([string]::IsNullOrWhiteSpace($Database)) {
                        throw 'close requires -Database.'
                    }
                    $result = Invoke-McpTool -Client $client -Name 'idb_close' -Arguments ([pscustomobject]@{
                        database = $Database
                        save     = -not $NoSave
                    }) -TimeoutSeconds $TimeoutSeconds
                    $output = Get-ReverseToolOutput $result
                    Assert-ReverseOperationSuccess -Output $output -Operation 'idb_close'
                    Write-ReverseResult $output
                }
            }
        }
        finally {
            Close-McpHttpClient -Client $client
        }
    }
}
