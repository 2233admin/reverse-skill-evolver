<#
.SYNOPSIS
Compatibility entry point for opening a target through reverse-skill.ps1.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$SessionId = '',
    [switch]$NoAutoAnalysis = $false,
    [int]$TimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($TimeoutSeconds -le 0) {
    Write-Output 'ERR:invalid_timeout'
    exit 1
}
if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    Write-Output 'ERR:file_not_found'
    exit 1
}

$resolvedPath = (Resolve-Path -LiteralPath $Path).Path
$isTempCopy = $false
$system32 = Join-Path $env:WINDIR 'System32'
if ($resolvedPath.StartsWith($system32, [StringComparison]::OrdinalIgnoreCase)) {
    $tempDir = Join-Path $env:TEMP 'reverse-skill'
    if (-not (Test-Path -LiteralPath $tempDir)) {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    }
    $tempName = "{0}-{1}" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)), ([IO.Path]::GetFileName($resolvedPath))
    $tempPath = Join-Path $tempDir $tempName
    Copy-Item -LiteralPath $resolvedPath -Destination $tempPath
    $resolvedPath = $tempPath
    $isTempCopy = $true
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$cli = Join-Path $repoRoot 'reverse-skill.ps1'
$cliArguments = @(
    'open',
    '-Path', $resolvedPath,
    '-Mode', 'prefer_headless',
    '-TimeoutSeconds', [string]$TimeoutSeconds,
    '-Json'
)
if ($NoAutoAnalysis) {
    $cliArguments += '-NoAutoAnalysis'
}
if (-not [string]::IsNullOrWhiteSpace($SessionId)) {
    $cliArguments += @('-PreferredSessionId', $SessionId)
}

try {
    $result = ((& $cli @cliArguments) -join [Environment]::NewLine) | ConvertFrom-Json
    if ($result.success -ne $true) {
        Write-Output "ERR:$($result.error)"
        exit 1
    }

    $tag = if ($isTempCopy) { ' (temp copy)' } else { '' }
    Write-Output "OK:$($result.session.filename):$($result.session.session_id)$tag"
}
catch {
    Write-Output "ERR:$($_.Exception.Message)"
    exit 1
}
