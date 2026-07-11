<#
.SYNOPSIS
    Fleet sync for reverse-skill-evolver: pulls or pushes field-journal candidate/validated
    entries, capability-graph.json, and tool-index.md between this machine and a paired
    machine over SSH/SCP.

.DESCRIPTION
    Collision-safe, additive merge only. Never deletes, never overwrites an existing file on
    the destination. If a filename already exists on the destination side, it is reported as
    a collision and skipped -- resolve it by hand and re-run. Missing directories are created
    on demand (not a failure).

    Assumes both machines are Windows, reachable via the `ssh -F none -p22 <user>@<host>`
    pattern already used for this fleet, and that `ssh`/`scp` (OpenSSH client) are on PATH on
    this machine. This is a manual convenience script, not a daemon -- run it by hand when you
    want to sync.

.PARAMETER RemoteHost
    NetBird/LAN address of the remote machine. Defaults to the "5080" box.

.PARAMETER RemoteUser
    SSH user on the remote machine. Defaults to Administrator.

.PARAMETER RemotePath
    Absolute path to the reverse-skill-evolver repo root ON THE REMOTE MACHINE. Required --
    not guessable, no default.

.PARAMETER Direction
    'Pull' to bring the remote's candidate/validated/capability-graph/tool-index copies into
    this local repo. 'Push' to send this local repo's copies to the remote. Required.

.EXAMPLE
    powershell -File skills\scripts\fleet-sync.ps1 -RemotePath 'D:\projects\reverse-skill-evolver' -Direction Pull

.EXAMPLE
    powershell -File skills\scripts\fleet-sync.ps1 -RemoteHost 100.80.248.248 -RemoteUser Administrator -RemotePath 'D:\projects\reverse-skill-evolver' -Direction Push
#>

[CmdletBinding()]
param(
    [string]$RemoteHost = '100.80.248.248',

    [string]$RemoteUser = 'Administrator',

    [Parameter(Mandatory = $true)]
    [string]$RemotePath,

    [Parameter(Mandatory = $true)]
    [ValidateSet('Push', 'Pull')]
    [string]$Direction
)

$ErrorActionPreference = 'Stop'

# Repo root is two levels up from this script: skills\scripts\fleet-sync.ps1 -> repo root
$LocalRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RemotePath = $RemotePath.TrimEnd('\', '/')

$SshTarget = "${RemoteUser}@${RemoteHost}"
$SshBaseArgs = @('-F', 'none', '-p', '22', $SshTarget)

# Relative sync targets: two merge-directories (many files), two merge-files (single file each)
$SyncDirs = @('skills\field-journal\candidate', 'skills\field-journal\validated')
$SyncFiles = @('skills\capability-graph.json', 'skills\tool-index.md')

$script:Collisions = New-Object System.Collections.Generic.List[string]
$script:Copied = New-Object System.Collections.Generic.List[string]
$script:SkippedNoSource = New-Object System.Collections.Generic.List[string]

function Invoke-RemotePowerShell {
    param([Parameter(Mandatory = $true)][string]$Command)
    $remoteCmd = "powershell -NoProfile -NonInteractive -Command `"$Command`""
    $fullArgs = $SshBaseArgs + @($remoteCmd)
    $output = & ssh @fullArgs 2>$null
    return $output
}

function Get-RemoteFileNames {
    param([Parameter(Mandatory = $true)][string]$RelDir)
    $remoteDir = "$RemotePath\$RelDir"
    $cmd = "if (-not (Test-Path -LiteralPath '$remoteDir')) { New-Item -ItemType Directory -Force -Path '$remoteDir' | Out-Null }; Get-ChildItem -LiteralPath '$remoteDir' -File | Select-Object -ExpandProperty Name"
    $names = Invoke-RemotePowerShell -Command $cmd
    if ($null -eq $names) { return @() }
    return @($names | Where-Object { $_ -and $_.Trim() -ne '' })
}

function Test-RemoteFileExists {
    param([Parameter(Mandatory = $true)][string]$RelFile)
    $remoteFile = "$RemotePath\$RelFile"
    $cmd = "if (Test-Path -LiteralPath '$remoteFile' -PathType Leaf) { 'YES' } else { 'NO' }"
    $result = Invoke-RemotePowerShell -Command $cmd
    return (($result -join '') -match 'YES')
}

function Assert-RemoteDir {
    param([Parameter(Mandatory = $true)][string]$RelDir)
    $remoteDir = "$RemotePath\$RelDir"
    $cmd = "if (-not (Test-Path -LiteralPath '$remoteDir')) { New-Item -ItemType Directory -Force -Path '$remoteDir' | Out-Null }"
    Invoke-RemotePowerShell -Command $cmd | Out-Null
}

function Sync-Directory {
    param(
        [Parameter(Mandatory = $true)][string]$RelDir,
        [Parameter(Mandatory = $true)][string]$Direction
    )

    $localDir = Join-Path $LocalRepoRoot $RelDir
    if (-not (Test-Path -LiteralPath $localDir)) {
        New-Item -ItemType Directory -Force -Path $localDir | Out-Null
    }

    $remoteNames = Get-RemoteFileNames -RelDir $RelDir
    $localNames = @(Get-ChildItem -LiteralPath $localDir -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)

    if ($Direction -eq 'Pull') {
        foreach ($name in $remoteNames) {
            if ($localNames -contains $name) {
                $script:Collisions.Add("$RelDir\$name (local already has this file, remote copy NOT pulled)")
                continue
            }
            $remoteFile = "$RemotePath\$RelDir\$name"
            $localFile = Join-Path $localDir $name
            & scp -P 22 "${SshTarget}:${remoteFile}" "$localFile"
            $script:Copied.Add("PULL $RelDir\$name")
        }
    }
    else {
        foreach ($name in $localNames) {
            if ($remoteNames -contains $name) {
                $script:Collisions.Add("$RelDir\$name (remote already has this file, local copy NOT pushed)")
                continue
            }
            $localFile = Join-Path $localDir $name
            $remoteFile = "$RemotePath\$RelDir\$name"
            & scp -P 22 "$localFile" "${SshTarget}:${remoteFile}"
            $script:Copied.Add("PUSH $RelDir\$name")
        }
    }
}

function Sync-File {
    param(
        [Parameter(Mandatory = $true)][string]$RelFile,
        [Parameter(Mandatory = $true)][string]$Direction
    )

    $localFile = Join-Path $LocalRepoRoot $RelFile
    $localExists = Test-Path -LiteralPath $localFile -PathType Leaf
    $remoteExists = Test-RemoteFileExists -RelFile $RelFile

    if ($Direction -eq 'Pull') {
        if (-not $remoteExists) {
            $script:SkippedNoSource.Add("$RelFile (remote has no copy, nothing to pull)")
            return
        }
        if ($localExists) {
            $script:Collisions.Add("$RelFile (local already has this file, remote copy NOT pulled)")
            return
        }
        $localParent = Split-Path -Parent $localFile
        if (-not (Test-Path -LiteralPath $localParent)) {
            New-Item -ItemType Directory -Force -Path $localParent | Out-Null
        }
        $remoteFile = "$RemotePath\$RelFile"
        & scp -P 22 "${SshTarget}:${remoteFile}" "$localFile"
        $script:Copied.Add("PULL $RelFile")
    }
    else {
        if (-not $localExists) {
            $script:SkippedNoSource.Add("$RelFile (local has no copy, nothing to push)")
            return
        }
        if ($remoteExists) {
            $script:Collisions.Add("$RelFile (remote already has this file, local copy NOT pushed)")
            return
        }
        $remoteParentRel = Split-Path -Parent $RelFile
        if ($remoteParentRel) { Assert-RemoteDir -RelDir $remoteParentRel }
        $remoteFile = "$RemotePath\$RelFile"
        & scp -P 22 "$localFile" "${SshTarget}:${remoteFile}"
        $script:Copied.Add("PUSH $RelFile")
    }
}

Write-Host "Fleet sync: $Direction  local=$LocalRepoRoot  remote=${SshTarget}:$RemotePath"

foreach ($dir in $SyncDirs) { Sync-Directory -RelDir $dir -Direction $Direction }
foreach ($file in $SyncFiles) { Sync-File -RelFile $file -Direction $Direction }

Write-Host ''
Write-Host "=== Copied ($($script:Copied.Count)) ==="
$script:Copied | ForEach-Object { Write-Host "  $_" }

Write-Host ''
Write-Host "=== Skipped, no source on that side ($($script:SkippedNoSource.Count)) ==="
$script:SkippedNoSource | ForEach-Object { Write-Host "  $_" }

Write-Host ''
Write-Host "=== Collisions -- NOT overwritten, resolve manually ($($script:Collisions.Count)) ==="
if ($script:Collisions.Count -eq 0) {
    Write-Host '  (none)'
}
else {
    $script:Collisions | ForEach-Object { Write-Warning "  $_" }
}
