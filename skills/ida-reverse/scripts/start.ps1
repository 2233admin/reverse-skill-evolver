<#!
.SYNOPSIS
  Compatibility entry point for the canonical Python idalib-mcp launcher.

.DESCRIPTION
  Keeps the existing PowerShell command and parameter names stable while delegating
  service discovery, reuse, controlled restart, and readiness checks to Python.
#>

[CmdletBinding()]
param(
    [string]$IdaDir,
    [int]$Port = 13337,
    [string]$ServerPath,
    [switch]$ForceRestart
)

$ErrorActionPreference = 'Stop'
$pythonScript = Join-Path $PSScriptRoot 'start_idalib_mcp.py'
$python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
$pythonPath = if ($python) { $python.Source } else { $null }
if (-not $python) {
    $knownPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path -LiteralPath $knownPython) { $pythonPath = $knownPython }
}
if (-not $pythonPath) { throw 'Python runtime not found. Install or expose Python before starting idalib-mcp.' }

$arguments = @($pythonScript, '--port', "$Port")
if ($IdaDir) { $arguments += @('--ida-dir', $IdaDir) }
if ($ServerPath) { $arguments += @('--server-path', $ServerPath) }
if ($ForceRestart) { $arguments += '--force-restart' }

& $pythonPath @arguments
exit $LASTEXITCODE
