#requires -Version 5

[CmdletBinding()]
param(
    [string]$Package,

    [string]$Process,

    [string]$RemoteHost = '127.0.0.1:27042',

    [string]$ScriptPath,

    [switch]$Usb,

    [switch]$Spawn,

    [switch]$Pause,

    [switch]$ListDevices,

    [switch]$ListProcesses
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

. (Join-Path $PSScriptRoot '..\..\scripts\lib\ToolDiscovery.ps1')

if ($ListDevices) {
    $devices = Get-RequiredReverseToolSpec -Name 'frida-ls-devices'
    & $devices.Command @($devices.PrefixArgs)
    exit $LASTEXITCODE
}

$target = if ($Package) { $Package } elseif ($Process) { $Process } else { '' }
if ([string]::IsNullOrWhiteSpace($target) -and -not $ListProcesses) {
    throw 'Provide -Package or -Process, or use -ListProcesses.'
}

$deviceFlag = if ($Usb) { '-U' } else { '-H' }

if ($ListProcesses) {
    $processes = Get-RequiredReverseToolSpec -Name 'frida-ps'
    $processArgs = if ($Usb) { @('-U') } else { @('-H', $RemoteHost) }
    & $processes.Command @($processes.PrefixArgs + $processArgs)
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($ScriptPath) -or -not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
    throw "Frida script not found: $ScriptPath"
}

$fridaArgs = @($deviceFlag)
if (-not $Usb) {
    $fridaArgs += $RemoteHost
}
if ($Spawn) {
    $fridaArgs += '-f'
} else {
    $fridaArgs += '-n'
}
$fridaArgs += $target
$fridaArgs += '-l'
$fridaArgs += $ScriptPath
if ($Pause) {
    $fridaArgs += '--pause'
}

$frida = Get-RequiredReverseToolSpec -Name 'frida'
& $frida.Command @($frida.PrefixArgs + $fridaArgs)
exit $LASTEXITCODE
