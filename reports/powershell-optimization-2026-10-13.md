# PowerShell 脚本优化与验证

本次修改 8 个脚本，运行脚本净减少 77 行；保留原有命令参数和索引字段。本报告记录实现与验证证据，代码交付进度见关联 Issue。

跟踪 Issue：[GitHub #41 — 优化 PowerShell 工具发现与调用，修复兼容和失败处理](https://github.com/2233admin/reverse-skill-evolver/issues/41)。

## 改动

- `skills/scripts/lib/ToolDiscovery.ps1`：缓存工具定义，仍实时查找可执行文件，安装后重新查询不会使用旧的可用性结果；统一必需工具的安装与查找入口，Frida 子命令和 radare2 辅助工具映射到所属安装包。补全 uv/Python Scripts 和 Android Build-Tools 查找，按数字版本选择 SDK 工具。JAR 工具要求 Java 可用；TCP 探测在成功、失败和超时时都释放资源。
- `skills/apk-reverse/scripts/decode.ps1`：使用共用工具入口；通过一次目录遍历统计 SO/XML 文件。
- `skills/apk-reverse/scripts/frida-run.ps1`：仅查找当前操作需要的 CLI；设备/进程枚举直接调用 `frida-ls-devices` / `frida-ps`，消除对系统 Python 中 Frida 模块的依赖。默认恢复进程，`-Pause` 传入 `--pause`。枚举输出采用 Frida CLI 的原生表格格式。
- `skills/apk-reverse/scripts/rebuild-sign-install.ps1`：使用共用工具入口，支持 Java + JAR 形式的 apktool。仅 `-Install` 时要求 adb，仅生成新密钥时要求 keytool；删除签名前的多余复制。
- `skills/radare2/scripts/recon.ps1`：使用共用工具入口，避免安装状态文本混入工具对象；增加 UTF-8 BOM，解决 Windows PowerShell 5.1 对中文脚本的解析问题。
- `skills/scripts/bootstrap-reverse.ps1`：移除 5.1 不支持的 `ConvertFrom-Json -AsHashtable`，保留已有配置字段与其他 MCP 服务；一次写入 npm MCP 环境配置，安装后更新当前进程 PATH，失败或缺少定义时返回非零退出码。
- `skills/scripts/refresh-tool-index.ps1`：能力表复用工具报告中的探测结果，Markdown 合并为一次写入；增加 keytool 和设备枚举的引用，删除 Frida 对系统 Python 的旧引用。
- `skills/scripts/fleet-sync.ps1`：统一 SCP 调用，SSH/SCP 失败立即终止，成功后才记录复制；远端命令使用 UTF-16 编码传输，转义路径中的单引号。

## 验证

| 结论 | 验证方式与记录 | 结果与局限 |
|---|---|---|
| 提交前完整 Python 检查通过 | 在最新 `origin/main`（`53010b3`）建立的 Issue #41 专用工作区执行 `python -m pytest -q --tb=short`；输出在本次会话工具记录 | 退出码 0，256 passed、5 skipped，88.46 秒。跳过项未计为通过；实际设备与远端集成仍未验证。 |
| 相关测试通过 | `python -m pytest tests/test_powershell_scripts.py tests/test_bootstrap_contract.py tests/test_routing_contract.py -q --tb=short`；完整输出在本次会话的工具执行记录 | 退出码 0，39 passed，57.19 秒。包含 30 个 PowerShell 用例及 9 个原有合同用例。PowerShell 5.1.28000.2952 与 7.6.6 均执行，无跳过。 |
| 所有 13 个 PowerShell 文件可解析 | `test_all_powershell_scripts_parse` 在两个引擎中调用原生 AST 解析器 | 两个引擎均通过。解析不代替所有脚本的功能测试。 |
| 核心入口与失败处理符合预期 | 用例直接调用 Frida、APK 打包、索引刷新、同步及引导脚本；MCP 配置在临时文件中读写 | 覆盖仅有目标 CLI、带空格参数、暂停、缺 Java、SDK 版本排序、安装后重新查找、无 adb 打包、JAR 打包、配置保留、索引字段一致性、运输失败及非零退出码。Frida/Android/SSH/SCP 使用替身；未进行实际安装、注入、设备安装或远端同步。 |
| 工具定义查询减少开销 | 同一 PowerShell 7.6.6 进程，改前源码取自 Git HEAD `c4d8856`，两组各预热一次，随后各执行 5 轮，每轮 200 次 `Get-ReverseToolDefinition -Name java`；原始数据见 [benchmark JSON](powershell-optimization-benchmark-2026-10-13.json) | 中位数 233.85 ms → 82.78 ms，降低约 64.6%。只测元数据查询，不能推算整个索引刷新或逆向任务的速度。 |
| diff 格式检查通过 | `git diff --check -- skills/scripts skills/apk-reverse/scripts skills/radare2/scripts`；输出在本次会话工具记录 | 退出码 0。 |
| Code Intel 管线未运行成功 | `code-intel 'F:\projects\reverse-skill-evolver' --mode normal` | 退出码 1：`read DAG capability registry: 系统找不到指定的路径。 (os error 3)`。本次使用源码检查、双引擎测试和 diff 检查；未修复主机 Code Intel 安装。 |

新增测试位于 [test_powershell_scripts.py](../tests/test_powershell_scripts.py)。Windows 专用入口测试在其他操作系统上跳过。

## API 依据

Frida 的默认恢复与 `--pause` 行为核对了[官方 CLI 实现](https://github.com/frida/frida-tools/blob/main/frida_tools/repl.py)。隔离工具安装方式核对了 [uv 工具文档](https://docs.astral.sh/uv/concepts/tools/)。

## 未验证范围

没有执行真实工具下载或安装，没有连接 Android 设备或远端机器，没有启动 Frida 注入会话。现有报告与其他工作区改动保留。

## PR #44：辅助 CLI 能力元数据

[Codex P2 审查意见](https://github.com/2233admin/reverse-skill-evolver/pull/44#discussion_r4260361401) 已核实：工具报告按辅助 CLI 原名查 manifest，缺少该名称的定义时，错误输出不可自动安装及空安装元数据。`Get-ReverseCapabilityName` 统一安装入口和能力状态中的所属包解析；报告继续保留各 CLI 自己的名称、路径和可用性，不借用所属包的安装状态。

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| 新回归能检出缺失 alias 状态 | 改前执行 `python -m pytest tests/test_powershell_scripts.py -q -p no:cacheprovider -k 'tool_alias_reports' --tb=short` | 退出码 1，2 failed、30 deselected，4.60 秒；两个引擎均在预期的 alias 状态断言失败。 |
| 所属包元数据、CLI 身份及索引输出符合预期 | 改后执行同文件测试，筛选 `tool_alias_reports or refresh_entry or required_tool_bootstraps` | 退出码 0，6 passed、26 deselected，21.61 秒；PowerShell 5.1 和 7 均运行。使用自有临时 manifest、已有 MCP 配置和 CLI 替身；检查所有辅助 CLI、非 alias、未知名称、注册/服务状态、原配置字节不变及实际索引入口输出。 |

原始输出位于本次修复会话的工具记录。未进行实际安装、设备操作或 SSH/SCP 同步。

## PR #44：capability 行的定义边界

[CodeRabbit 审查意见](https://github.com/2233admin/reverse-skill-evolver/pull/44#discussion_r4260385172) 已核实：索引在复用工具报告前没有校验 capability 定义，因而为 `idapro` 等只有 CLI 的工具生成了虚假的 capability 行。现在先检查缓存中的 manifest 定义，存在定义才复用报告或查询能力状态；不会为已有工具报告重复探测注册或服务。`idapro` 保留原 CLI 工具行，不映射到 `idalib-mcp`。

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| 新回归能检出无定义的 capability 行 | 改前筛选 `test_refresh_entry_writes_consistent_indexes` | 退出码 1，2 failed、30 deselected，6.95 秒；两个引擎均在 capability 名称集合断言失败。 |
| 定义边界、三种索引输出及共用入口符合预期 | 改后执行 `python -m pytest tests/test_powershell_scripts.py -q -p no:cacheprovider -k 'tool_alias_reports or refresh_entry or required_tool_bootstraps or all_powershell_scripts_parse' --tb=short` | 退出码 0，8 passed、24 deselected，17.72 秒；PowerShell 5.1 和 7 均运行，无跳过。索引测试执行真实脚本的临时副本，使用自有 manifest、已有 MCP 配置及 `reverse-skill` 替身；JSON/graph capability 集合与字段一致，Markdown 没有虚假 `idapro` capability 行，CLI 路径和可用性保留，独立 `idalib-mcp` 注册状态保留，配置字节不变。 |

原始输出位于本次修复会话的工具记录。未运行真实 IDA/模型、工具安装、设备操作或 SSH/SCP 同步；原 30 个双引擎用例的既有结果保留，本轮只重跑受影响入口和解析检查。
