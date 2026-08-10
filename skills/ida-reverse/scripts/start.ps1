<#
.SYNOPSIS
Start IDA Pro MCP HTTP server (background, non-blocking)

.DESCRIPTION
1. Kill old process
2. Start idalib-mcp HTTP server in hidden window mode
3. Wait for service ready (max 15 seconds)
4. Output result

Usage: run without parameters
#>

param(
    [string]$IdaDir,
    [int]$Port = 13337,
    [string]$ServerPath
)

$toolDiscovery = Join-Path $PSScriptRoot '..\..\scripts\lib\ToolDiscovery.ps1'
$mcpClientScript = Join-Path $PSScriptRoot '..\..\scripts\lib\McpHttpClient.ps1'
. $toolDiscovery
. $mcpClientScript

function Get-OnlineMcpToolCount {
    param([int]$RequestPort)

    $client = $null
    try {
        $client = New-McpHttpClient -Url "http://127.0.0.1:$RequestPort/mcp" -TimeoutSeconds 3
        $result = Invoke-McpRequest -Client $client -Method 'tools/list' -TimeoutSeconds 3
        return @($result.tools).Count
    }
    catch {
        return -1
    }
    finally {
        if ($null -ne $client) {
            Close-McpHttpClient -Client $client
        }
    }
}

$ida = if ([string]::IsNullOrWhiteSpace($IdaDir)) {
    Get-LatestIdaInstallation
}
else {
    Get-LatestIdaInstallation -CandidatePaths @($IdaDir) -OnlyCandidatePaths
}
if ($null -eq $ida) {
    Write-Output 'ERR:No usable IDA installation found (requires ida.exe/idat.exe and idalib.dll).'
    exit 1
}
$IdaDir = $ida.InstallDir
$env:IDADIR = $IdaDir
Write-Output "INFO:IDA:$($ida.Version):$IdaDir"

$existingToolCount = Get-OnlineMcpToolCount -RequestPort $Port
if ($existingToolCount -gt 0) {
    Write-Output "OK:${existingToolCount}:existing"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ServerPath)) {
    # Try both possible executable names (idalib-mcp is the HTTP server, ida-pro-mcp is the installer CLI)
    $resolved = Get-Command idalib-mcp -ErrorAction SilentlyContinue
    if (-not $resolved) {
        $resolved = Get-Command ida-pro-mcp -ErrorAction SilentlyContinue
    }
    if ($resolved) {
        $ServerPath = $resolved.Source
    }
    else {
        $roamingPython = Join-Path $env:APPDATA 'Python'
        if (Test-Path -LiteralPath $roamingPython) {
            $candidate = Get-ChildItem -LiteralPath $roamingPython -Directory -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $scripts = Join-Path $_.FullName 'Scripts'
                    @('idalib-mcp.exe', 'ida-pro-mcp.exe') | ForEach-Object { Join-Path $scripts $_ }
                } |
                Where-Object { Test-Path -LiteralPath $_ } |
                Select-Object -First 1
            if ($candidate) {
                $ServerPath = $candidate
            }
        }
    }
}

# Auto-bootstrap if still not found
if ([string]::IsNullOrWhiteSpace($ServerPath)) {
    $bootstrapScript = Join-Path $PSScriptRoot '..\..\scripts\bootstrap-reverse.ps1'
    if (Test-Path -LiteralPath $bootstrapScript) {
        Write-Output "INFO: ida-pro-mcp not found, attempting auto-bootstrap (pip install ida-mcp)..."
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrapScript -Capability @('idalib-mcp') -SkipRefresh
        $resolved = Get-Command ida-pro-mcp -ErrorAction SilentlyContinue
        if (-not $resolved) {
            $resolved = Get-Command idalib-mcp -ErrorAction SilentlyContinue
        }
        if ($resolved) {
            $ServerPath = $resolved.Source
        }
        else {
            $roamingPython = Join-Path $env:APPDATA 'Python'
            if (Test-Path -LiteralPath $roamingPython) {
                $candidate = Get-ChildItem -LiteralPath $roamingPython -Directory -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        $scripts = Join-Path $_.FullName 'Scripts'
                        @('ida-pro-mcp.exe', 'idalib-mcp.exe') | ForEach-Object { Join-Path $scripts $_ }
                    } |
                    Where-Object { Test-Path -LiteralPath $_ } |
                    Select-Object -First 1
                if ($candidate) {
                    $ServerPath = $candidate
                }
            }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($ServerPath)) {
    throw 'Missing required CLI tool: ida-pro-mcp — auto-bootstrap failed. Install manually: pip install git+https://github.com/mrexodia/ida-pro-mcp.git && ida-pro-mcp --install'
}

# 清理旧进程（杀进程树，包括 worker 子进程）
$old = Get-Process -Name "ida-pro-mcp" -ErrorAction SilentlyContinue
if (-not $old) { $old = Get-Process -Name "idalib-mcp" -ErrorAction SilentlyContinue }
if ($old) { taskkill /F /T /PID $old.Id 2>$null | Out-Null; Start-Sleep 2 }

# 后台启动
Start-Process -WindowStyle Hidden -FilePath $ServerPath -ArgumentList "--host 127.0.0.1 --port $Port"

# 等待就绪
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    $toolCount = Get-OnlineMcpToolCount -RequestPort $Port
    if ($toolCount -gt 0) {
        Write-Output "OK:$toolCount"
        $ready = $true
        break
    }
}
if (-not $ready) {
    Write-Output "ERR:timeout"
}
