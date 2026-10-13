param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath,

    [int]$StringsLimit = 40,

    [int]$ImportsLimit = 80,

    [switch]$RunAnalysis
)

# 强制当前脚本使用 UTF-8 输出，尽量减少中文标题乱码。
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '..\..\scripts\lib\ToolDiscovery.ps1')

function Write-Section {
    param(
        [Parameter(Mandatory = $true)]
    [string]$Title
    )

    # 用固定分段标题，方便人看，也方便后续 grep。
    ""
    "=== $Title ==="
}

$rabin2 = Get-RequiredReverseToolSpec -Name 'rabin2'
$r2 = $null
if ($RunAnalysis) {
    $r2 = Get-RequiredReverseToolSpec -Name 'r2'
}

# 将输入路径规范化成绝对路径，避免 r2/rabin2 在相对路径下歧义解析。
$resolvedPath = Resolve-Path -LiteralPath $TargetPath
$target = $resolvedPath.Path

"目标文件: $target"

Write-Section -Title '基本信息'
& $rabin2.Command @($rabin2.PrefixArgs + @('-I', '--', $target))

Write-Section -Title '节区'
& $rabin2.Command @($rabin2.PrefixArgs + @('-S', '--', $target))

Write-Section -Title '导入'
& $rabin2.Command @($rabin2.PrefixArgs + @('-i', '--', $target)) | Select-Object -First $ImportsLimit

Write-Section -Title '导出'
& $rabin2.Command @($rabin2.PrefixArgs + @('-E', '--', $target))

Write-Section -Title '字符串'
& $rabin2.Command @($rabin2.PrefixArgs + @('-zz', '--', $target)) | Select-Object -First $StringsLimit

if ($RunAnalysis) {
    Write-Section -Title '函数与入口分析'
    & $r2.Command @($r2.PrefixArgs + @('-A', '-q', '-c', 's entry0;afl;iz;ii;q', '--', $target))
}
