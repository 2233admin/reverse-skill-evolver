<#!
.SYNOPSIS
  Compatibility entry point for the canonical Python idalib-open client.

.DESCRIPTION
  Keeps the existing PowerShell command and parameter names stable while delegating
  file staging, database-lock fallback, HTTP calls, polling, and timeout handling to Python.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$Path,
    [string]$SessionId = '',
    [switch]$NoAutoAnalysis = $false,
    [int]$TimeoutSeconds = 120,
    [int]$Port = 13337
)

$ErrorActionPreference = 'Stop'
$pythonScript = Join-Path $PSScriptRoot 'open_idalib.py'
$python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
$pythonPath = if ($python) { $python.Source } else { $null }
if (-not $python) {
    $knownPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path -LiteralPath $knownPython) { $pythonPath = $knownPython }
}
if (-not $pythonPath) { throw 'Python runtime not found. Install or expose Python before opening a binary.' }

$arguments = @($pythonScript, '--path', $Path, '--port', "$Port", '--timeout-seconds', "$TimeoutSeconds")
if ($SessionId) { $arguments += @('--session-id', $SessionId) }
if ($NoAutoAnalysis) { $arguments += '--no-auto-analysis' }

& $pythonPath @arguments
exit $LASTEXITCODE
