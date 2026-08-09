# Reverse Engineering Skills Master Control

本目录收录了一系列逆向工程相关的技能模块，每个子目录是一个独立模块，内含 `SKILL.md` 描述其适用场景、工具链和工作流程。

## CRITICAL: 路由执行契约（必须立即执行）

0. `NOW`：先读仓库根 `.aigx/protocol.aigx`。凡传入 `--project-path`，目标项目必须先通过官方 AIGX lint；凡明确将编辑的文件，必须同时用 `--aigx-target` 解析其 `files.aigx` 边界。缺 genome、lint 失败或边界缺失都必须阻塞。

读完本文件后，不允许只回复“已读/已理解”。必须按顺序执行：

1. `NOW`：先调用确定性路由器，得到机器可读的分流、前置检查、fallback 和成功 oracle：
   `python "<skill-root>\scripts\route_task.py" --task "<任务描述>" --input-path "<目标路径>" --pretty`
   源码或应用项目任务额外传入 `--project-path "<项目根目录>"`：它只读并返回该项目的 Code Intel 产物状态及 Sentrux 观测，供后续工具选择和结构性风险判断。
2. `NOW`：读取 `evolution/SKILL.md`，为当前任务建立最小 GOAL（目标、范围、成功 oracle、停止条件）。
3. `NOW`：读取路由器返回的目标子模块 `SKILL.md`，提取第一步可执行动作。
4. `NEXT`：按路由器返回的 `tool_plan.stages` 分阶段使用本机工具；每阶段必须先看 `status`，不能把 `installed_unverified` 插件当成已加载工具。需要刷新事实时，优先读取 `capability-graph.json`、`tool-index.md`；IDA/插件任务先运行只读的 `scripts/refresh_ida_capabilities.py --ida-dir "C:\Program Files\IDA Professional 9.4"`，再读取 `generated/ida-capability-graph.json`。
5. `THEN`：只在路由器返回 `status=ready` 且 `preflight.status=pass` 时执行；`blocked` 必须先处理缺口或授权门槛，禁止绕过。区分 `installed`、`hcli-managed`、`installed_unmanaged`、`legacy`、`installed_unverified` 和 `service_online`。
6. `ACT`：先执行返回的 `dispatch.command`（若存在），再按活动 `tool_plan` 的 phase 顺序使用工具；没有受控入口时按返回的 `skill_file` 工作流执行。完成后逐项验证 `success_oracles` 并记录 TraceCard，不要停留在“等待用户下一条确认”状态。

### 自动路由器状态语义

`route_task.py` 是确定性 preflight 和 dispatch 入口，不会静默安装工具，也不会在没有授权范围时执行安全动作：

| 状态 | 含义 | 动作 |
|---|---|---|
| `ready` | 路由已命中、能力检查通过 | 执行 `dispatch.command` 或目标 skill 第一动作 |
| `blocked` | 工具/MCP/授权/入口缺失 | 先处理 `preflight.missing_capabilities` 或 `block_reasons` |
| `no_route` | 目标类型和意图都未命中 | 提议新增 skill，不得硬塞现有模块 |
| `invalid` | 任务契约或路由数据错误 | 修复输入/路由数据后重跑 |

只有明确传入 `--execute` 才会运行已有的受控脚本入口；普通路由调用只产生计划，不产生外部副作用。

`tool_plan` 的阶段状态：`ready` 可用；`needs_smoke` 为已安装但尚未验证加载的 IDA 插件；`degraded` 为存在但尚未接通的服务；`blocked` 为工具缺失；`deferred` 为当前任务未触发的条件阶段。

`project_intelligence` 的边界：只有同名项目的已发布 Code Intel run 才是 `authoritative`；原生 Sentrux CLI 的 `check` 和 `gate` 分别给出规则与 baseline 观测；同项目旧快照仅作候选，跨项目经验只能提炼为待验证的通用模式，绝不能作为当前项目的结构事实或放行依据。需要架构治理时，路由到 `architecture-governance`：它要求 `--project-path` 与 `sentrux`，但绝不自动执行会写入 baseline 的 `sentrux gate --save`。

如果路由无法命中，必须先联网补充方法论并提议新增 skill，禁止硬塞到不匹配模块。

## 指令语义级别（RFC 2119）

- `MUST`：必须执行，违背即任务失败。
- `MUST NOT`：禁止执行，违背即安全违规。
- `SHOULD`：原则上要做，不做必须说明原因。
- `MAY`：可选动作。
## 当前模块

| 模块 | 目录 | 适用场景 |
|------|------|---------|
| **自进化路由内核** | `evolution/` | GOAL 契约、Capability Graph、步骤级 TraceCard、候选经验晋级门禁 |
| **无人值守过夜运行** | `overnight-run/` | 无人值守跑到绝对 DEADLINE：slot 填表 → validate 冒烟 → 脚手架（.night/ + night 分支 + pre-commit 红线）→ 增量报告 → 经验回流（OVERNIGHT.md v2 契约） |
| **通用逆向** | `reverse-engineering/` | GDB / Frida / angr / Unicorn / Qiling / 反分析对抗 / 全语言平台逆向 / CTF 模式库 |
| **APK 逆向** | `apk-reverse/` | Android APK 解包、jadx 反编译、smali 修改、Frida Hook、重打包签名安装 |
| **IDA Pro 逆向** | `ida-reverse/` | IDA Pro MCP HTTP 服务器：反编译、反汇编、数据流追踪、交叉引用；工具数以服务探测为准 |
| **前端 JS 逆向** | `js-reverse/` | 浏览器端签名定位、加密参数分析、运行时采样、Node 补环境复现；优先用现有 `js-reverse_*`，需要更强的浏览器/CDP/Hook 面时接入 jshookmcp，但前提是先把该 MCP server 下载/注册并启用 |
| **radare2 分析** | `radare2/` | CLI 二进制侦察、反汇编、patch：r2 / rabin2 / rasm2 / radiff2 |
| **CTF 竞赛全栈** | `../CTF-Sandbox-Orchestrator/` | 40+ 子技能：Web/逆向/Pwn/云/容器/AD/取证/隐写/移动端/密码学，由总控统一编排 |
| **技术文档编写** | `docs-generator/` | 任务完成后自动生成逆向报告、渗透报告、CTF writeup、签名逆向报告 |
| **浏览器与桌面自动化** | `browser-automation/` | 浏览器操作（Playwright）+ Windows 桌面应用操作（OpenReverse UIA/CUA）+ 网络观察 |
| **跨版本符号迁移** | `binary-diff/` | 有旧版符号迁移到新版、缺 PDB 推导、程序更新后批量迁移函数名 |
| **N-day 补丁差分→利用** | `patch-diff-exploit/` | 从厂商补丁定位漏洞点、写 PoC、N-day 武器化（与 binary-diff 分工：本 skill 偏攻击侧） |
| **RE→利用链** | `pwn-chain/` | 从逆向走到可用 exploit：栈/堆/内核 pwn、pwntools、libc-database、CTF 到真实远程的稳定化 |
| **固件渗透链** | `firmware-pentest/` | OWASP FSTM 九阶段：提取→EMBA 自动化→Firmadyne/QEMU 仿真→AFL++ fuzz→实机利用 |
| **EDR 绕过逆向** | `edr-bypass-re/` | 红队场景：逆向 EDR 的 hook 表/ETW/AMSI → 直接 syscall / Hell's Gate / 硬件断点 / call stack spoof |
| **渗透测试工具链** | `pentest-tools/` | Nmap/Nuclei/SQLMap/FFUF/Hashcat 等 20+ 渗透工具，通过 MCP 暴露给 AI |
| **图表生成** | `diagram-generator/` | 从自然语言生成 Mermaid/Graphviz/PlantUML 图表（攻击路径图、数据流图、架构图、状态机） |
| **攻击链编排** | `attack-chain/` | 多阶段攻击路径规划与执行的总指挥；完整渗透、HW 演练、从外网打到域控等跨阶段任务从这里开始 |
| **LLM/AI 安全测试** | `llm-security/` | OWASP LLM + ASI Top 10：Prompt 注入、工具滥用、记忆投毒、Agent 劫持、系统提示词提取、**Agent 服从性工程** |
| **API 安全测试** | `api-security/` | REST/GraphQL/WebSocket 全协议：BOLA/IDOR、JWT/OAuth 攻击、10 阶段方法论 |
| **供应链安全** | `supply-chain-security/` | SBOM/SCA/CI-CD 管道：依赖扫描、容器安全、构建完整性、漏洞可达性验证 |
| **移动逆向工程** | `mobile-reverse/` | Android + iOS：Frida/Objection 动态插桩、SSL Pinning/Root/越狱检测绕过、OWASP MASTG |
| **恶意软件分析** | `malware-analysis/` | YARA/Sigma 规则、CAPE/Azul 沙箱编排、IOC 提取、94 种反分析技术、多 Agent 自动化 |

## 统一入口

遇到逆向、CTF、抓包、前端签名、APK 改包、二进制分析类任务时，先按这个顺序进入：

1. 先读 `evolution/SKILL.md`，建立 GOAL 与成功 oracle
2. 再读 `routing.json`，用它做结构化候选路由
3. 同步读取 `routing.md`，确认人读上下文和跨模块路径
4. 再进入对应子模块的 `SKILL.md`
5. 需要确认本机工具路径时，先读 `capability-graph.json`，再读 `tool-index.md`；IDA 相关任务还要读取 `generated/ida-capability-graph.json` 和 `ida-reverse/references/ida-plugin-capabilities.json`。

## 工作思路

这些模块可以按需组合使用：

1. **拿到一个目标** → 先看文件类型，选对应的分析工具
2. **快速捡漏** → strings / rabin2 -z / ltrace 看看有没有直接线索
3. **深入分析** → 如果需要反编译→IDA；需要动态 Hook→Frida；需要符号执行→angr
4. **一条路走不通就换一条** → 静态分析不行就动态，Java 层不行就看 so，页面观察不够就断点

## 目录是动态扩充的

本目录会持续增长。发现新的子目录时，读它的 `SKILL.md` 就能快速了解用途。

新增 skill 时，按 `CONTRIBUTING.md` 的标准流程操作，确保：
- 路由矩阵能正确分流
- bootstrap 系统能自动补齐依赖
- tool-index 能反映新工具状态

## 关联资源

- 本机还有 **anything-analyzer**（端口 23816）MCP 服务器，提供浏览器自动化、HTTP 捕获和 AI 分析能力
- `tool-index.md` 记录本机逆向工具是否可用、实际路径、版本和脚本引用
- 包根目录下的 `Readme.md` 提供面向 Claude Code、Codex CLI 与其他代码 AI 客户端的通用安装与接入说明

## 按需自举

当 workflow 发现缺少工具时，不要直接报错。先盘点并报告缺口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-root>\scripts\bootstrap-reverse.ps1" -Capability @('工具名') -StartServices
```

`scripts/bootstrap-reverse.ps1` 仍可用于明确允许自动安装的非 IDA 工具；IDA 插件优先通过 HCLI。IDA/`idalib-mcp` 不得因为一次探测失败就自动 pip 覆盖现有版本。

任何安装或服务变更后必须重新运行对应盘点；IDA 使用 `refresh-ida-capabilities.ps1`，不要把旧缓存当成当前能力。

## 操作先例库（Precedent Files）

`field-journal/precedent-*.md` 只提供通用、脱敏的方法论。按任务需要读取；它们不能替代当前 session 的用户授权，也不能把某一目标默认为已授权。

## 自动进化

运行 trace、目标身份/路径、二进制、源码事实、IDB 和分析证据必须留在目标工作区或外部 session store，禁止自动回写本仓。只有已脱敏、目标无关且有回归证据的通用模式，才能由 `evolution/` 生成 TraceCard 和 promotion record 并提议晋级：

- `validated/`：oracle 通过、可复用、可参与未来路由。
- `candidate/`：有潜力但未回归，只能提示，不能支配控制流。
- `forensic/`：失败、异常、疑似污染或证据不足，只能用于分析。

只有通过 `evolution/promotion-record.template.yaml` 所列门禁后，才允许更新 `routing.md`、`routing.json`、子 skill 或 bootstrap manifest。

- TraceCard：`evolution/trace-card.template.yaml`
- 晋级记录：`evolution/promotion-record.template.yaml`
- 随包先例：`field-journal/precedent-*.md`（通用参考，不是目标授权）
