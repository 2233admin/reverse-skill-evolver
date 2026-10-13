#requires -Version 5

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [string]$OutDir,

    [string]$BaseName,

    [string]$KeystorePath,

    [string]$KeyAlias = 'androiddebugkey',

    [string]$StorePass = 'android',

    [string]$KeyPass = 'android',

    [string]$DeviceSerial,

    [switch]$Install,

    [switch]$Reinstall,

    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

. (Join-Path $PSScriptRoot '..\..\scripts\lib\ToolDiscovery.ps1')

if ([string]::IsNullOrWhiteSpace($KeystorePath)) {
    $KeystorePath = Join-Path $PSScriptRoot '..\debug.keystore'
}

function Ensure-DebugKeystore {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Keytool,
        [Parameter(Mandatory = $true)][string]$Alias,
        [Parameter(Mandatory = $true)][string]$StorePassword,
        [Parameter(Mandatory = $true)][string]$KeyPassword
    )

    if (Test-Path -LiteralPath $Path) {
        return
    }

    $parent = Split-Path -Path $Path -Parent
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    & $Keytool -genkeypair -v -keystore $Path -storepass $StorePassword -keypass $KeyPassword -alias $Alias -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Android Debug,O=ReverseSkill,C=CN'
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to generate debug keystore.'
    }
}

if (-not (Test-Path -LiteralPath $ProjectDir)) {
    throw "Project directory not found: $ProjectDir"
}

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $projectParent = Split-Path -Path $ProjectDir -Parent
    if ([string]::IsNullOrWhiteSpace($projectParent)) {
        $projectParent = [System.IO.Directory]::GetCurrentDirectory()
    }
    $OutDir = $projectParent
}

$apktool = Get-RequiredReverseToolSpec -Name 'apktool'
$zipalign = Get-RequiredReverseToolSpec -Name 'zipalign'
$apksigner = Get-RequiredReverseToolSpec -Name 'apksigner'
$adb = if ($Install) { Get-RequiredReverseToolSpec -Name 'adb' } else { $null }

if (-not (Test-Path -LiteralPath $KeystorePath -PathType Leaf)) {
    $keytool = Get-RequiredReverseToolSpec -Name 'keytool'
    Ensure-DebugKeystore -Path $KeystorePath -Keytool $keytool.Command -Alias $KeyAlias -StorePassword $StorePass -KeyPassword $KeyPass
}

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$name = if ($BaseName) { $BaseName } else { Split-Path -Path $ProjectDir -Leaf }
$unsignedApk = Join-Path $OutDir ($name + '-unsigned.apk')
$alignedApk = Join-Path $OutDir ($name + '-aligned.apk')
$signedApk = Join-Path $OutDir ($name + '-signed.apk')

if ($Clean) {
    foreach ($path in @($unsignedApk, $alignedApk, $signedApk)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

& $apktool.Command @($apktool.PrefixArgs + @('b', $ProjectDir, '-o', $unsignedApk))
if ($LASTEXITCODE -ne 0) {
    throw 'apktool build failed.'
}

& $zipalign.Command @($zipalign.PrefixArgs + @('-f', '-p', '4', $unsignedApk, $alignedApk))
if ($LASTEXITCODE -ne 0) {
    throw 'zipalign failed.'
}

& $apksigner.Command @($apksigner.PrefixArgs + @('sign', '--ks', $KeystorePath, '--ks-key-alias', $KeyAlias, '--ks-pass', "pass:$StorePass", '--key-pass', "pass:$KeyPass", '--out', $signedApk, $alignedApk))
if ($LASTEXITCODE -ne 0) {
    throw 'apksigner sign failed.'
}

& $apksigner.Command @($apksigner.PrefixArgs + @('verify', '--print-certs', $signedApk))
if ($LASTEXITCODE -ne 0) {
    throw 'apksigner verify failed.'
}

"unsigned_apk=$unsignedApk"
"aligned_apk=$alignedApk"
"signed_apk=$signedApk"
"keystore=$KeystorePath"

if ($Install) {
    $installArgs = @()
    if ($DeviceSerial) {
        $installArgs += '-s'
        $installArgs += $DeviceSerial
    }
    $installArgs += 'install'
    if ($Reinstall) {
        $installArgs += '-r'
    }
    $installArgs += $signedApk

    & $adb.Command @($adb.PrefixArgs + $installArgs)
    if ($LASTEXITCODE -ne 0) {
        throw 'adb install failed.'
    }

    "install_device=$DeviceSerial"
}
