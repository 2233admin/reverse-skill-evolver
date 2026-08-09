<#!
.SYNOPSIS
  Compatibility entry point for the canonical Python capability inventory.

.DESCRIPTION
  Keeps the existing PowerShell command stable while delegating all discovery and report
  generation to refresh_ida_capabilities.py. It does not install or modify anything.
#>

[CmdletBinding()]
param(
    [string]$IdaDir,
    [string]$OutputDir,
    [switch]$SkipUpgradeCheck
)

$ErrorActionPreference = 'Stop'
$pythonScript = Join-Path $PSScriptRoot 'refresh_ida_capabilities.py'
$python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
$pythonPath = if ($python) { $python.Source } else { $null }
if (-not $python) {
    $knownPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path -LiteralPath $knownPython) { $pythonPath = $knownPython }
}
if (-not $pythonPath) { throw 'Python runtime not found. Install or expose Python before running the capability inventory.' }

$arguments = @($pythonScript)
if ($IdaDir) { $arguments += @('--ida-dir', $IdaDir) }
if ($OutputDir) { $arguments += @('--output-dir', $OutputDir) }
if ($SkipUpgradeCheck) { $arguments += '--skip-upgrade-check' }

& $pythonPath @arguments
exit $LASTEXITCODE
