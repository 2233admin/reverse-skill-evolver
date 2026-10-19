Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ReverseToolCatalog {
    [CmdletBinding()]
    param()

    if (Get-Variable -Name ReverseToolCatalog -Scope Script -ErrorAction SilentlyContinue) {
        return $script:ReverseToolCatalog
    }

    # Cache definitions only; resolve paths again after tools are installed.
    $script:ReverseToolCatalog = @(
        [pscustomobject]@{
            Name = 'jadx'
            Skill = 'apk-reverse'
            Purpose = 'Java 反编译'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'jadx' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\jadx\bin\jadx.bat') }
            )
        }
        [pscustomobject]@{
            Name = 'apktool'
            Skill = 'apk-reverse'
            Purpose = 'APK 解包与重建'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'apktool' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\apktool\apktool.bat') },
                [pscustomobject]@{ Type = 'java-jar'; Value = (Join-Path $env:USERPROFILE 'Tools\apktool\apktool.jar') }
            )
        }
        [pscustomobject]@{
            Name = 'adb'
            Skill = 'apk-reverse'
            Purpose = '设备连接与 logcat'
            VersionArgs = @('version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'adb' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe') }
            )
        }
        [pscustomobject]@{
            Name = 'java'
            Skill = 'apk-reverse'
            Purpose = '运行 jar 与 Java 工具链'
            VersionArgs = @('-version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'java' }
            )
        }
        [pscustomobject]@{
            Name = 'keytool'
            Skill = 'apk-reverse'
            Purpose = '生成 APK 签名密钥'
            VersionArgs = @('-help')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'keytool' }
            )
        }
        [pscustomobject]@{
            Name = 'apksigner'
            Skill = 'apk-reverse'
            Purpose = 'APK 签名'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'apksigner' },
                [pscustomobject]@{ Type = 'android-build-tool'; Value = 'apksigner.bat' }
            )
        }
        [pscustomobject]@{
            Name = 'zipalign'
            Skill = 'apk-reverse'
            Purpose = 'APK 对齐'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'zipalign' },
                [pscustomobject]@{ Type = 'android-build-tool'; Value = 'zipalign.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'frida'
            Skill = 'apk-reverse'
            Purpose = 'Frida 动态注入'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'frida' },
                [pscustomobject]@{ Type = 'python-script'; Value = 'frida.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'idalib-mcp'
            Skill = 'ida-reverse'
            Purpose = 'IDA headless MCP service'
            VersionArgs = @('--help')
            FixedVersion = 'ida-pro-mcp'
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'idalib-mcp' }
            )
        }
        [pscustomobject]@{
            Name = 'idapro'
            Skill = 'ida-reverse'
            Purpose = 'Python IDA Pro MCP CLI'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'reverse-skill' }
            )
        }
        [pscustomobject]@{
            Name = 'frida-ps'
            Skill = 'apk-reverse'
            Purpose = 'Frida 进程枚举'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'frida-ps' },
                [pscustomobject]@{ Type = 'python-script'; Value = 'frida-ps.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'frida-ls-devices'
            Skill = 'apk-reverse'
            Purpose = 'Frida 设备枚举'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'frida-ls-devices' },
                [pscustomobject]@{ Type = 'python-script'; Value = 'frida-ls-devices.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'r2'
            Skill = 'radare2'
            Purpose = 'radare2 主分析器'
            VersionArgs = @('-v')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'r2' },
                # The Windows release ships bin\r2.bat, not r2.exe; without this the
                # main analyser is reported missing while every sibling r2*.exe is found.
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\r2.bat') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\r2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\r2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Tools\radare2\bin\r2.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'rabin2'
            Skill = 'radare2'
            Purpose = '二进制侦察'
            VersionArgs = @('-v')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'rabin2' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\rabin2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\rabin2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Tools\radare2\bin\rabin2.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'rasm2'
            Skill = 'radare2'
            Purpose = '汇编/反汇编'
            VersionArgs = @('-v')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'rasm2' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\rasm2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\rasm2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Tools\radare2\bin\rasm2.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'radiff2'
            Skill = 'radare2'
            Purpose = '二进制差分'
            VersionArgs = @('-v')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'radiff2' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\radiff2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\radiff2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Tools\radare2\bin\radiff2.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'rahash2'
            Skill = 'radare2'
            Purpose = '哈希与校验'
            VersionArgs = @('-v')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'rahash2' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\rahash2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\rahash2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Tools\radare2\bin\rahash2.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'rax2'
            Skill = 'radare2'
            Purpose = '进制与位运算转换'
            VersionArgs = @('-v')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'rax2' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\bin\rax2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\radare2\rax2.exe') },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Tools\radare2\bin\rax2.exe' }
            )
        }
        [pscustomobject]@{
            Name = 'python'
            Skill = 'reverse-engineering'
            Purpose = '辅助脚本执行'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'python' },
                [pscustomobject]@{ Type = 'command'; Value = 'python3' }
            )
        }
        [pscustomobject]@{
            Name = 'pip'
            Skill = 'reverse-engineering'
            Purpose = 'Python 包管理'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'pip' },
                [pscustomobject]@{ Type = 'command'; Value = 'pip3' }
            )
        }
        [pscustomobject]@{
            Name = 'node'
            Skill = 'js-reverse'
            Purpose = '运行 Node 侧 JS 复现与 MCP 客户端'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'node' }
            )
        }
        [pscustomobject]@{
            Name = 'npx'
            Skill = 'js-reverse'
            Purpose = '运行临时 npm 包与 MCP 入口'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'npx' }
            )
        }
        [pscustomobject]@{
            Name = 'jshookmcp'
            Skill = 'js-reverse'
            Purpose = '通过 npx 启动 @jshookmcp/jshook MCP（仍需先配置并启用 MCP server）'
            FixedVersion = '@jshookmcp/jshook@latest'
            VersionArgs = @()
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'npx' }
            )
        }
        [pscustomobject]@{
            Name = 'agent-browser'
            Skill = 'browser-automation'
            Purpose = '浏览器自动化（Playwright）：打开页面、点击、填表、爬取、截图'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'agent-browser' }
            )
        }
        [pscustomobject]@{
            Name = 'analyzeHeadless'
            Skill = 'reverse-engineering'
            Purpose = 'Ghidra 无头分析（免费 IDA 替代）'
            VersionArgs = @()
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'analyzeHeadless' },
                [pscustomobject]@{ Type = 'path'; Value = '&lt;工具根目录&gt;\ghidra\support\analyzeHeadless.bat' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\ghidra\support\analyzeHeadless.bat') },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:USERPROFILE 'Tools\ghidra\ghidra_11.3_PUBLIC\support\analyzeHeadless.bat') }
            )
        }
        [pscustomobject]@{
            Name = 'playwright'
            Skill = 'browser-automation'
            Purpose = 'Playwright 浏览器引擎'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'playwright' },
                [pscustomobject]@{ Type = 'path'; Value = (Join-Path $env:APPDATA 'npm\playwright.ps1') }
            )
        }
        [pscustomobject]@{
            Name = 'proxycat'
            Skill = 'pentest-tools'
            Purpose = '代理池管理与轮换'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'proxycat' }
            )
        }
        [pscustomobject]@{
            Name = 'nmap'
            Skill = 'pentest-tools'
            Purpose = '端口扫描与服务识别'
            VersionArgs = @('--version')
            Fallbacks = @(
                [pscustomobject]@{ Type = 'command'; Value = 'nmap' },
                [pscustomobject]@{ Type = 'path'; Value = 'C:\Program Files (x86)\Nmap\nmap.exe' }
            )
        }
    )
    return $script:ReverseToolCatalog
}

function Get-ReverseSkillRoot {
    [CmdletBinding()]
    param()

    return [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
}

function Resolve-ReversePathTemplate {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Value
    }

    $resolved = $Value
    $replacements = @{
        '%USERPROFILE%' = $env:USERPROFILE
        '%LOCALAPPDATA%' = $env:LOCALAPPDATA
        '%APPDATA%' = $env:APPDATA
        '%TEMP%' = $env:TEMP
        '%SKILL_ROOT%' = Get-ReverseSkillRoot
    }

    foreach ($key in $replacements.Keys) {
        $resolved = $resolved.Replace($key, $replacements[$key])
    }

    return $resolved
}

function Get-ReverseBootstrapManifestPath {
    [CmdletBinding()]
    param()

    return Join-Path (Get-ReverseSkillRoot) 'scripts\bootstrap-manifest.json'
}

function Get-ReverseBootstrapCatalog {
    [CmdletBinding()]
    param()

    if ((Get-Variable -Name 'ReverseBootstrapCatalog' -Scope Script -ErrorAction SilentlyContinue) -and $script:ReverseBootstrapCatalog) {
        return $script:ReverseBootstrapCatalog
    }

    $path = Get-ReverseBootstrapManifestPath
    if (-not (Test-Path -LiteralPath $path)) {
        $script:ReverseBootstrapCatalog = @()
        return $script:ReverseBootstrapCatalog
    }

    $json = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $catalog = @()
    foreach ($capability in @($json.capabilities)) {
        $clone = [pscustomobject]@{}
        foreach ($property in $capability.PSObject.Properties) {
            $value = $property.Value
            if ($value -is [string]) {
                $value = Resolve-ReversePathTemplate -Value $value
            }
            elseif ($value -is [System.Collections.IEnumerable] -and -not ($value -is [string])) {
                $items = @()
                foreach ($item in $value) {
                    if ($item -is [string]) {
                        $items += Resolve-ReversePathTemplate -Value $item
                    }
                    else {
                        $items += $item
                    }
                }
                $value = $items
            }
            elseif ($null -ne $value -and $value -is [System.Management.Automation.PSCustomObject]) {
                $propCount = @($value.PSObject.Properties).Count
                if ($propCount -gt 0) {
                    $map = [ordered]@{}
                    foreach ($subProperty in $value.PSObject.Properties) {
                        $subValue = $subProperty.Value
                        if ($subValue -is [string]) {
                            $subValue = Resolve-ReversePathTemplate -Value $subValue
                        }
                        $map[$subProperty.Name] = $subValue
                    }
                    $value = [pscustomobject]$map
                }
            }
            Add-Member -InputObject $clone -NotePropertyName $property.Name -NotePropertyValue $value
        }
        $catalog += $clone
    }

    $script:ReverseBootstrapCatalog = $catalog
    return $script:ReverseBootstrapCatalog
}

function Get-ReverseBootstrapDefinition {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    return Get-ReverseBootstrapCatalog | Where-Object { $_.name -eq $Name } | Select-Object -First 1
}

function Get-ClaudeMcpConfigPath {
    [CmdletBinding()]
    param()

    return Join-Path $env:USERPROFILE '.claude\mcp.json'
}

function Get-ClaudeMcpServerNames {
    [CmdletBinding()]
    param()

    $configPath = Get-ClaudeMcpConfigPath
    if (-not (Test-Path -LiteralPath $configPath)) {
        return @()
    }

    try {
        $json = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -eq $json.mcpServers) {
            return @()
        }
        return @($json.mcpServers.PSObject.Properties.Name)
    }
    catch {
        return @()
    }
}

function Get-CodexMcpServerNames {
    [CmdletBinding()]
    param()

    if (Get-Variable -Name 'CodexMcpServerNamesCached' -Scope Script -ErrorAction SilentlyContinue) {
        return @($script:CodexMcpServerNamesCached)
    }

    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) {
        $script:CodexMcpServerNamesCached = @()
        return $script:CodexMcpServerNamesCached
    }

    try {
        $output = & $codex.Source mcp list --json 2>$null
        $nativeExitCode = $LASTEXITCODE
        $global:LASTEXITCODE = 0
        if ($nativeExitCode -ne 0 -or -not $output) {
            $script:CodexMcpServerNamesCached = @()
            return $script:CodexMcpServerNamesCached
        }

        $servers = ($output -join [Environment]::NewLine) | ConvertFrom-Json
        $script:CodexMcpServerNamesCached = @($servers | ForEach-Object { [string]$_.name } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        return $script:CodexMcpServerNamesCached
    }
    catch {
        $global:LASTEXITCODE = 0
        $script:CodexMcpServerNamesCached = @()
        return $script:CodexMcpServerNamesCached
    }
}

function Test-ReverseTcpPort {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [string]$TargetHost = '127.0.0.1'
    )

    $client = New-Object System.Net.Sockets.TcpClient
    $waitHandle = $null
    try {
        $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
        $waitHandle = $async.AsyncWaitHandle
        $connected = $waitHandle.WaitOne(1000, $false)
        if (-not $connected) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
        if ($null -ne $waitHandle) { $waitHandle.Close() }
    }
}

function Get-ReverseCapabilityName {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Name)

    switch ($Name) {
        { $_ -in @('frida-ps', 'frida-ls-devices') } { return 'frida' }
        { $_ -in @('rabin2', 'rasm2', 'radiff2', 'rahash2', 'rax2') } { return 'r2' }
        default { return $Name }
    }
}

function Get-ReverseCapabilityState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $capability = Get-ReverseCapabilityName -Name $Name
    $definition = Get-ReverseBootstrapDefinition -Name $capability
    if ($null -eq $definition) {
        return $null
    }

    $registered = $false
    if ($definition.PSObject.Properties['mcpNames']) {
        $registeredNames = @(
            Get-ClaudeMcpServerNames
            Get-CodexMcpServerNames
        ) | Select-Object -Unique
        foreach ($candidate in @($definition.mcpNames)) {
            if ($registeredNames -contains $candidate) {
                $registered = $true
                break
            }
        }
    }

    $serviceOnline = $false
    if ($definition.PSObject.Properties['servicePort'] -and $definition.servicePort) {
        $serviceOnline = Test-ReverseTcpPort -Port ([int]$definition.servicePort)
    }

    return [pscustomobject]@{
        Name = $Name
        BootstrapKind = $definition.bootstrapKind
        CanAutoInstall = [bool]$definition.canAutoInstall
        DocsUrl = [string]$definition.docsUrl
        Registered = $registered
        ServiceOnline = $serviceOnline
    }
}

function Get-ReverseToolDefinition {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $definition = Get-ReverseToolCatalog | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($null -eq $definition) {
        throw "Unknown reverse tool: $Name"
    }

    $bootstrap = Get-ReverseBootstrapDefinition -Name $Name
    if ($null -ne $bootstrap) {
        foreach ($property in $bootstrap.PSObject.Properties) {
            if (-not $definition.PSObject.Properties[$property.Name]) {
                Add-Member -InputObject $definition -NotePropertyName $property.Name -NotePropertyValue $property.Value
            }
        }
    }

    return $definition
}

function Get-ReverseFallbackPaths {
    param([string]$Type, [string]$FileName)

    if ($Type -eq 'python-script') {
        $binDir = if ($env:UV_TOOL_BIN_DIR) { $env:UV_TOOL_BIN_DIR } else { Join-Path $env:USERPROFILE '.local\bin' }
        Join-Path $binDir $FileName
        foreach ($root in @((Join-Path $env:APPDATA 'Python'), (Join-Path $env:LOCALAPPDATA 'Programs\Python'))) {
            if (Test-Path -LiteralPath $root -PathType Container) {
                Get-ChildItem -LiteralPath $root -Directory | ForEach-Object {
                    Join-Path $_.FullName "Scripts\$FileName"
                }
            }
        }
    }
    elseif ($Type -eq 'android-build-tool') {
        $roots = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA 'Android\Sdk')) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
        foreach ($root in $roots) {
            $buildTools = Join-Path $root 'build-tools'
            if (Test-Path -LiteralPath $buildTools -PathType Container) {
                Get-ChildItem -LiteralPath $buildTools -Directory |
                    Sort-Object -Property { try { [version]$_.Name } catch { [version]'0.0' } } -Descending |
                    ForEach-Object { Join-Path $_.FullName $FileName }
            }
        }
    }
}

function Test-ReverseApktoolJar {
    param([Parameter(Mandatory = $true)][string]$Path)

    $archive = $null
    $reader = $null
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
        $manifest = $archive.GetEntry('META-INF/MANIFEST.MF')
        if ($null -eq $manifest) { return $false }
        $reader = [System.IO.StreamReader]::new($manifest.Open())
        $content = $reader.ReadToEnd()
        if ($content -notmatch '(?m)^Main-Class: ([A-Za-z0-9_.$]+)\r?$') { return $false }
        return ($null -ne $archive.GetEntry(($Matches[1].Replace('.', '/') + '.class')))
    }
    catch { return $false }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $archive) { $archive.Dispose() }
    }
}

function Resolve-ReverseToolSpec {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $definition = Get-ReverseToolDefinition -Name $Name
    $spec = [pscustomobject]@{
        Name = $definition.Name
        Skill = $definition.Skill
        Purpose = $definition.Purpose
        Available = $false
        Source = 'Missing'
        ResolvedPath = ''
        Command = ''
        PrefixArgs = @()
        VersionArgs = $definition.VersionArgs
        FixedVersion = if ($definition.PSObject.Properties['FixedVersion']) { [string]$definition.FixedVersion } else { '' }
    }

    foreach ($candidate in $definition.Fallbacks) {
        switch ($candidate.Type) {
            'command' {
                $cmd = Get-Command -Name $candidate.Value -ErrorAction SilentlyContinue
                if ($null -ne $cmd) {
                    if ($Name -eq 'apktool' -and -not [string]::IsNullOrWhiteSpace($cmd.Source)) {
                        $jar = Join-Path (Split-Path -Parent $cmd.Source) 'apktool.jar'
                        if ((Test-Path -LiteralPath $jar) -and -not (Test-ReverseApktoolJar -Path $jar)) { continue }
                    }
                    $spec.Available = $true
                    $spec.Source = 'Get-Command'
                    $spec.ResolvedPath = $cmd.Source
                    $spec.Command = $cmd.Source
                    return $spec
                }
            }
            'path' {
                if (Test-Path -LiteralPath $candidate.Value -PathType Leaf) {
                    if ($Name -eq 'apktool' -and -not (Test-ReverseApktoolJar -Path (Join-Path (Split-Path -Parent $candidate.Value) 'apktool.jar'))) { continue }
                    $spec.Available = $true
                    $spec.Source = 'FallbackPath'
                    $spec.ResolvedPath = $candidate.Value
                    $spec.Command = $candidate.Value
                    return $spec
                }
            }
            'java-jar' {
                if ((Test-Path -LiteralPath $candidate.Value -PathType Leaf) -and (Test-ReverseApktoolJar -Path $candidate.Value)) {
                    $java = Resolve-ReverseToolSpec -Name 'java'
                    if ($java.Available) {
                        $spec.Available = $true
                        $spec.Source = 'FallbackJavaJar'
                        $spec.ResolvedPath = $candidate.Value
                        $spec.Command = $java.Command
                        $spec.PrefixArgs = @('-jar', $candidate.Value)
                        $spec.VersionArgs = @('-jar', $candidate.Value) + $definition.VersionArgs
                        return $spec
                    }
                }
            }
            { $_ -in @('python-script', 'android-build-tool') } {
                foreach ($path in Get-ReverseFallbackPaths -Type $candidate.Type -FileName $candidate.Value) {
                    if (Test-Path -LiteralPath $path -PathType Leaf) {
                        $spec.Available = $true
                        $spec.Source = 'FallbackPath'
                        $spec.ResolvedPath = $path
                        $spec.Command = $path
                        return $spec
                    }
                }
            }
        }
    }

    return $spec
}

function Get-RequiredReverseToolSpec {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Name)

    $spec = Resolve-ReverseToolSpec -Name $Name
    if ($spec.Available) { return $spec }

    $capability = Get-ReverseCapabilityName -Name $Name
    $definition = Get-ReverseBootstrapDefinition -Name $capability
    if ($definition -and $definition.canAutoInstall) {
        Write-Host "INFO: $Name not found, attempting auto-bootstrap..." -ForegroundColor Yellow
        $bootstrap = Join-Path (Get-ReverseSkillRoot) 'scripts\bootstrap-reverse.ps1'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrap -Capability $capability -SkipRefresh | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Bootstrap failed for required CLI tool: $Name" }
        $env:PATH = @($env:PATH, [Environment]::GetEnvironmentVariable('PATH', 'Machine'), [Environment]::GetEnvironmentVariable('PATH', 'User')) -join ';'
        $spec = Resolve-ReverseToolSpec -Name $Name
        if ($spec.Available) { return $spec }
    }

    $hint = if ($definition) { "See $($definition.docsUrl)" } else { "Install $Name manually (Android Build-Tools for apksigner/zipalign, JDK for keytool)." }
    throw "Missing required CLI tool: $Name. $hint"
}

function Get-ReverseToolVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Spec
    )

    if (-not $Spec.Available) {
        return ''
    }
    if ($Spec.PSObject.Properties['FixedVersion'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.FixedVersion)) {
        return [string]$Spec.FixedVersion
    }

    try {
        $rawLines = & $Spec.Command @($Spec.VersionArgs) 2>&1 | Select-Object -First 10
        foreach ($line in $rawLines) {
            $text = ([string]$line).Trim()
            if ($text -and $text -notmatch '^Module manifest file error' -and $text -notmatch '^\s*->\s*Invalid line') {
                return $text
            }
        }
        return ''
    }
    catch {
        return ''
    }
}

function Invoke-ReverseTool {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    $spec = Resolve-ReverseToolSpec -Name $Name
    if (-not $spec.Available) {
        throw "Missing required CLI tool: $Name"
    }

    & $spec.Command @($spec.PrefixArgs + $Arguments)
    return $LASTEXITCODE
}

function Get-ReverseToolReport {
    [CmdletBinding()]
    param(
        [string[]]$Names
    )

    $selectedNames = if ($null -ne $Names -and @($Names).Count -gt 0) { $Names } else { (Get-ReverseToolCatalog).Name }

    foreach ($name in $selectedNames) {
        $spec = Resolve-ReverseToolSpec -Name $name
        $capabilityState = Get-ReverseCapabilityState -Name $name
        [pscustomobject]@{
            Name = $spec.Name
            Skill = $spec.Skill
            Purpose = $spec.Purpose
            Available = $spec.Available
            ResolvedPath = $spec.ResolvedPath
            Source = $spec.Source
            Version = Get-ReverseToolVersion -Spec $spec
            BootstrapKind = if ($capabilityState) { $capabilityState.BootstrapKind } else { '' }
            CanAutoInstall = if ($capabilityState) { $capabilityState.CanAutoInstall } else { $false }
            DocsUrl = if ($capabilityState) { $capabilityState.DocsUrl } else { '' }
            McpRegistered = if ($capabilityState) { $capabilityState.Registered } else { $false }
            ServiceOnline = if ($capabilityState) { $capabilityState.ServiceOnline } else { $false }
        }
    }
}

