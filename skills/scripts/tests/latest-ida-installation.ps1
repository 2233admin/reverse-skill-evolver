[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$discoveryScript = Join-Path $PSScriptRoot '..\lib\ToolDiscovery.ps1'
. $discoveryScript

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("reverse-skill-ida-test-{0}" -f [guid]::NewGuid().ToString('N'))
$oldIdaDir = $env:IDADIR

try {
    $ida92 = Join-Path $testRoot 'IDA Professional 9.2'
    $ida94 = Join-Path $testRoot 'IDA Professional 9.4'
    foreach ($dir in @($ida92, $ida94)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $dir 'ida.exe') -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $dir 'idalib.dll') -Force | Out-Null
    }

    $env:IDADIR = $ida92
    $latest = Get-LatestIdaInstallation -CandidatePaths @($env:IDADIR, $ida94) -OnlyCandidatePaths
    if ($null -eq $latest -or $latest.InstallDir -ne $ida94 -or $latest.Version -ne '9.4') {
        throw "Expected IDA 9.4, got: $($latest | ConvertTo-Json -Compress)"
    }

    $explicit = Get-LatestIdaInstallation -CandidatePaths @($ida92) -OnlyCandidatePaths
    if ($null -eq $explicit -or $explicit.InstallDir -ne $ida92 -or $explicit.Version -ne '9.2') {
        throw "Explicit path did not stay on IDA 9.2: $($explicit | ConvertTo-Json -Compress)"
    }

    Write-Output 'PASS: latest IDA wins; explicit single-directory selection is preserved.'
}
finally {
    $env:IDADIR = $oldIdaDir
    $resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
    if ($resolvedTestRoot.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTestRoot) -like 'reverse-skill-ida-test-*' -and
        (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
