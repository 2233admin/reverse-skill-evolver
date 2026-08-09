<p align="center">
  <img src="assets/reverse-skill-evolver-cover.png" alt="Reverse Skill Evolver tactical cover" width="100%" />
</p>

AI社区：https://linux.do

 # Cybersecurity Skills Router / 逆向技能路由包

> 本包放在哪个目录都行。以下用 `<REPO_ROOT>` 代指包含本 README 的仓库根目录，用 `<SKILL_ROOT>` 代指 `<REPO_ROOT>\skills`。

---

## 0. 给 AI 的第一条指令

> **路由或编辑前先使用仓库 AIGX genome。读取本包不得顺带写入客户端全局配置。**

### 启动流程

```text
1. 从本 README 确定 `<REPO_ROOT>`，并令 `<SKILL_ROOT>` 为 `<REPO_ROOT>\skills`。
2. 读取 `.aigx\protocol.aigx`、任务相关 concern genome 和仅作兼容启动页的 `RULES.md`。
3. 项目型任务先验证目标项目 AIGX genome，并解析每个已知编辑文件的边界。
4. 运行 `python "<SKILL_ROOT>\scripts\route_task.py" ...`；只有返回 `ready` 才继续。
```

`RULES.md` 只把客户端引向权威 AIGX 上下文和确定性路由器；它不会注入全局规则、安装工具或取代 route preflight。

### 报告格式示例

```markdown
✅ **逆向任务路由预检完成**

**仓库根目录**：<REPO_ROOT>
**路由状态**：ready | blocked | no_route | invalid
**选中工作流**：<skill path>
**必需输入/能力**：<requirements>
**下一步**：<受控 dispatch 或 blocker 处理>
```

---

这不是一个“单工具安装包”，而是一套给 Claude Code / Codex CLI / Cursor / Cline / Windsurf / 其他支持规则、提示词注入、MCP 或外部工具调用的代码 AI 客户端使用的**逆向技能路由包**。

它解决的是两件事：

1. 让 AI 在遇到 APK / 二进制 / 前端 JS / 抓包 / CTF 任务时，先走对的方法论和子技能，而不是直接乱猜。
2. 把本机工具、MCP、脚本入口、工作流收敛成一套可复用目录，便于迁移到新机器。

---

## 1. 这份包里有什么

当前建议把整个包理解成两层：

```text
<REPO_ROOT>\
├── Readme.md                     # 你现在看到的安装/分发说明
├── CTF-Sandbox-Orchestrator\     # CTF 竞赛全栈（40+ 子技能）
└── skills\            # 主技能目录
    ├── SKILL.md                  # 总控入口
    ├── evolution\                # GOAL 契约、能力图谱、TraceCard、晋级门禁
    ├── routing.md                # 场景 → 技能分流（路由矩阵）
    ├── routing.json              # 机读路由镜像
    ├── CONTRIBUTING.md           # 新增 skill 指南
    ├── tool-index.md             # 工具索引（自动生成）
    ├── capability-graph.json     # 会话级工具/MCP/服务健康图谱（自动生成）
    ├── scripts\                 # 工具索引刷新与共享脚本
    ├── field-journal\           # 通用先例与已晋级模式
    ├── api-security\            # API 安全测试（REST/GraphQL/WebSocket/SOAP）
    ├── apk-reverse\             # APK 逆向
    ├── attack-chain\            # 多阶段攻击链编排
    ├── binary-diff\             # 跨版本符号迁移
    ├── browser-automation\      # 浏览器+桌面自动化（Playwright+OpenReverse）
    ├── diagram-generator\       # 图表生成（Mermaid/Graphviz/PlantUML）
    ├── docs-generator\          # 技术文档/报告生成
    ├── edr-bypass-re\           # EDR 绕过逆向（红队投递）
    ├── firmware-pentest\        # 固件渗透链（OWASP FSTM）
    ├── ghidra-reverse\          # Ghidra 逆向（GhydraMCP，免费 IDA 替代，本仓库尚未实战验证）
    ├── ida-reverse\             # IDA Pro 逆向
    ├── js-reverse\              # 前端 JS / 浏览器链路逆向
    ├── llm-security\            # LLM/AI 安全测试（OWASP LLM Top 10 + Agentic AI Top 10）
    ├── malware-analysis\        # 恶意软件分析（YARA/Sigma/沙箱/IOC 提取）
    ├── mobile-reverse\          # 移动端逆向（Android+iOS，Frida/Objection/MSTG）
    ├── patch-diff-exploit\      # N-day 补丁差分→利用
    ├── pentest-tools\           # 渗透测试工具链
    ├── pwn-chain\               # RE→可用 exploit（栈/堆/内核）
    ├── radare2\                 # radare2 CLI 逆向
    ├── reverse-engineering\     # 通用逆向方法论
    └── supply-chain-security\   # 软件供应链安全（SBOM/SCA/CI-CD）
```

如果你同时使用 CTF 资料库，建议把它放在本包根目录下（当前默认结构）：

```text
<REPO_ROOT>\
├── skills\                       # 主技能目录
├── CTF-Sandbox-Orchestrator\     # CTF 竞赛子技能（40+）
└── Readme.md
```

这样 `routing.md` 里的 `../CTF-Sandbox-Orchestrator/...` 相对路径（从 `skills/` 出发）可以正确解析。

> 如果你把 CTF-Sandbox-Orchestrator 放在了本包外部（如 `F:\CTF-Sandbox-Orchestrator\`），需要手动调整 `routing.md` 中的相对路径。

---

## 2. 推荐安装思路

### 2.1 推荐目录布局

建议用户下载后按下面的方式放置：

```text
<REPO_ROOT>\             # 本包根目录（可改盘符）
<REPO_ROOT>\skills\      # <SKILL_ROOT>
C:\Users\<你的用户名>\Tools\jadx\
C:\Users\<你的用户名>\Tools\apktool\
C:\Users\<你的用户名>\AppData\Local\Android\Sdk\platform-tools\
C:\Users\<你的用户名>\AppData\Local\Programs\Python\Python3xx\
C:\Program Files\nodejs\
D:\APP\IDA\                            # 示例，实际可自定
C:\Tools\radare2\                      # 可选
```

### 2.2 不要把这些值当成硬要求

本包里很多脚本、文档、工具索引都带有**样例路径**。这些路径只代表某一台机器上的落点，不代表你必须照抄。

尤其是以下路径在迁移到新机器后通常都要检查：

- `D:\APP\IDA`
- `<用户目录>\...`
- `<用户目录>\...`
- `<REPO_ROOT>\...`

如果你换了盘符、用户名或工具安装目录，请按本文档的“迁移后必改项”章节调整。

---

## 3. 快速上手

### 3.1 只想先把技能包放好

1. 把整个目录放到你喜欢的位置，例如：`<REPO_ROOT>\`
2. 进入 `skills\SKILL.md`
3. 遇到任务时按以下顺序读：
   1. `SKILL.md`
   2. `evolution\SKILL.md`
   3. `routing.json` + `routing.md`
   4. 对应子目录的 `SKILL.md`
   5. 需要确认本机工具时再看 `capability-graph.json` / `tool-index.md`

### 3.2 想让任意代码 CLI 自动走这套路由

你至少需要：

- 一个支持自定义规则 / system prompt / 项目指令 / hook 之一的代码 CLI
- 一种把“逆向任务先读路由文件”注入模型上下文的方式
- 如需直接调用外部能力，再配好 MCP 或等价工具桥接
- 本包的 `SKILL.md / evolution\SKILL.md / routing.json / routing.md / capability-graph.json / tool-index.md`

如果你已经有自己的 Claude hook、Codex CLI 项目指令、Cursor Rules、Cline 自定义指令或 Windsurf Rules，把里面指向旧路径的部分改成你当前安装位置即可。

---

## 4. 依赖总表：装什么、去哪里下、装到哪里

下表按“必需 / 常用 / 可选增强”分组。

### 4.1 核心客户端与运行时

| 组件 | 是否必需 | 项目地址 | 作用 | 推荐安装位置 | 安装/启动方式 |
|---|---|---|---|---|---|
| Claude Code | 建议 | https://github.com/anthropics/claude-code | 作为主 AI 客户端，最适合本包 | 用户自己的 Claude 环境 | 按官方说明安装；后续把本包路径和 MCP/Hook 接进去 |
| Node.js 22.12+ | JS/MCP 必需 | https://nodejs.org/ | 运行 `npx`、`jshookmcp`、本地 JS 复现 | `C:\Program Files\nodejs\` | 安装后确认 `node -v`、`npx -v` |
| Python 3.x | 常用 | https://www.python.org/ | 运行 Frida、部分辅助脚本、`ida-mcp` 常见分发形态 | `C:\Users\<用户>\AppData\Local\Programs\Python\Python3xx\` | 安装后确认 `python --version`、`pip --version` |
| Java / JDK | APK 必需 | https://adoptium.net/ 或 https://www.oracle.com/java/ | 运行 `jadx`、`apktool` 等 Java 工具链 | 系统默认 JDK 路径即可 | 安装后确认 `java -version` |

### 4.2 APK / Android 逆向工具

| 组件 | 是否必需 | 项目地址 | 作用 | 推荐安装位置 | 安装方式 |
|---|---|---|---|---|---|
| jadx | APK 常用 | https://github.com/skylot/jadx | Java 反编译 | `C:\Users\<用户>\Tools\jadx\` | 下载 release 压缩包解压；确保 `bin\jadx.bat` 存在 |
| apktool | APK 常用 | https://apktool.org/ | APK 解包 / 重建 | `C:\Users\<用户>\Tools\apktool\` | 下载 Windows 包；建议把 `apktool.bat` 与 `apktool.jar` 放同目录 |
| Android platform-tools | 动态调试常用 | https://developer.android.com/tools/releases/platform-tools | 提供 `adb` | `C:\Users\<用户>\AppData\Local\Android\Sdk\platform-tools\` | 下载解压后确认 `adb.exe` 可用 |
| Android Build-Tools | 重签名常用 | https://developer.android.com/tools/releases/build-tools | 提供 `apksigner`、`zipalign` | Android SDK 的 `build-tools\<version>\` | 用 Android SDK Manager 安装；没有它就无法完整跑重签名链路 |

### 4.3 动态分析与浏览器侧工具

| 组件 | 是否必需 | 项目地址 | 作用 | 推荐安装位置 | 安装方式 |
|---|---|---|---|---|---|
| Frida / frida-tools | 动态 Hook 常用 | https://frida.re/ | Java / native 动态注入 | Python Scripts 目录 | 一般用 `pip install frida-tools`；确认 `frida`、`frida-ps` 可用 |
| anything-analyzer | Web/抓包增强 | https://github.com/Mouseww/anything-analyzer | 浏览器自动化、HTTP 捕获、AI 分析 | 任意代码目录，例如 `C:\work\anything-analyzer-main\` | 当前本机包信息显示使用 `pnpm`，常见流程：`pnpm install` → `pnpm dev` |
| jshookmcp | JS 逆向增强 | https://github.com/vmoranv/jshookmcp | 浏览器/CDP/Hook/Network/SourceMap/AST 执行面 | 无固定目录；通过 `npx` 启动 | 不是裸工具；要先在 MCP 客户端里注册并启用 |

### 4.4 二进制逆向工具

| 组件 | 是否必需 | 项目地址 | 作用 | 推荐安装位置 | 安装方式 |
|---|---|---|---|---|---|
| IDA Pro | 二进制深度逆向常用 | https://hex-rays.com/ida-pro/ | 反编译、xref、数据流、重命名、类型恢复 | 例如 `D:\APP\IDA\` | 安装 IDA 本体后，把 `IDADIR` 指向其根目录 |
| idalib-mcp | 使用 ida-reverse 必需 | https://github.com/mrexodia/ida-pro-mcp | 暴露 `idapro_*` MCP 工具或本地 HTTP 服务 | 常见落点为 Python Scripts 目录 | `pip install git+https://github.com/mrexodia/ida-pro-mcp.git`，然后 `ida-pro-mcp --install` 安装 IDA 插件 |
| radare2 | 可选 | https://github.com/radareorg/radare2 | CLI 侦察、反汇编、差分、patch | `C:\Tools\radare2\` | 安装后确认 `r2`、`rabin2`、`rasm2`、`radiff2` 等可用 |

### 4.5 配套资料库

| 组件 | 是否必需 | 项目地址 | 作用 | 推荐位置 |
|---|---|---|---|---|
| CTF-Sandbox-Orchestrator | CTF 场景强烈建议 | 以你的本地仓库/私有分发地址为准 | CTF 总控与 40+ competition-* 子技能 | 建议与本包同级，如 `F:\CTF-Sandbox-Orchestrator\` |

---

## 5. 本包默认支持哪些场景

### 5.1 `skills\` 下的主模块

| 模块 | 目录 | 主要解决什么 |
|---|---|---|
| 总控入口 | `SKILL.md` | 先看全局地图，再决定进哪个子 skill |
| 自进化路由内核 | `evolution\` | GOAL 契约、能力图谱、步骤级 TraceCard、晋级门禁 |
| 路由表 | `routing.md` | 按目标类型、用户意图、工具链做分流 |
| 机读路由镜像 | `routing.json` | 结构化路由、fallback edge、能力依赖、成功 oracle |
| 工具索引 | `tool-index.md` | 看本机工具有没有、路径在哪、哪个脚本会调用 |
| 能力图谱 | `capability-graph.json` | 会话级工具路径、版本、MCP 注册、服务健康、smoke 状态 |
| APK 逆向 | `apk-reverse\` | 解包、jadx、smali、重打包、Frida、native 分流 |
| IDA Pro | `ida-reverse\` | 深度二进制逆向、`idapro_*` 工作流 |
| JS / Web | `js-reverse\` | 前端签名、请求链路、补环境、SourceMap / AST / Hook |
| radare2 | `radare2\` | CLI 侦察、字符串、导入导出、patch |
| 通用方法论 | `reverse-engineering\` | 跨语言、跨平台、反分析、模式库 |
| 浏览器与桌面自动化 | `browser-automation\` | Playwright 浏览器操作 + OpenReverse 桌面应用自动化 |
| 跨版本符号迁移 | `binary-diff\` | 旧版符号迁移新版、缺 PDB 推导、LLM 批量迁移 |
| N-day 补丁差分→利用 | `patch-diff-exploit\` | 从厂商补丁定位漏洞点、写 PoC、N-day 武器化 |
| RE→利用链 | `pwn-chain\` | 从逆向走到可用 exploit：栈/堆/内核 pwn、pwntools、libc-database |
| 固件渗透链 | `firmware-pentest\` | OWASP FSTM 全链路：提取→EMBA→Firmadyne 仿真→AFL++ fuzz→打实机 |
| EDR 绕过逆向 | `edr-bypass-re\` | 逆向 EDR hook 表/ETW/AMSI → 直接 syscall / Hell's Gate / call stack spoof |
| 渗透测试工具链 | `pentest-tools\` | Nmap/Nuclei/SQLMap/FFUF/Hashcat 等 20+ 工具 MCP |
| 图表生成 | `diagram-generator\` | Mermaid/Graphviz/PlantUML 图表（攻击路径/架构/数据流） |
| 技术文档 | `docs-generator\` | 任务完成后自动生成逆向/渗透/CTF 报告 |
| LLM/AI 安全 | `llm-security\` | OWASP LLM + ASI Top 10：Prompt 注入、Agent 安全、**Agent 服从性工程** |
| 操作先例库 | `field-journal\precedent-*.md` | 通用、脱敏的方法论；不能作为某个具体目标已授权的证据 |

### 5.2 当前推荐入口

遇到任务时优先这样走：

- APK / Android → `apk-reverse\SKILL.md`
- exe / dll / so / elf → `ida-reverse\SKILL.md` 或 `radare2\SKILL.md`
- 找前端签名 / 加密参数 → `js-reverse\SKILL.md`
- HTTP 抓包 / 浏览器采样 / 请求回放 → anything-analyzer + `js-reverse`
- 渗透测试 / 端口扫描 / 漏洞扫描 → `pentest-tools\SKILL.md`
- 固件 / IoT / 路由器渗透 → `firmware-pentest\SKILL.md`
- N-day / 补丁差分 / 写 CVE PoC → `patch-diff-exploit\SKILL.md`
- 写 exploit / pwn / 栈堆内核利用 → `pwn-chain\SKILL.md`
- EDR / AV 绕过 / 红队投递 → `edr-bypass-re\SKILL.md`
- 浏览器/桌面自动化 → `browser-automation\SKILL.md`
- 符号迁移 / 跨版本对比 → `binary-diff\SKILL.md`
- 画图 / 架构图 / 攻击路径图 → `diagram-generator\SKILL.md`
- CTF 题 → `CTF-Sandbox-Orchestrator` 总控先分流

---

## 6. 启动方式与验证方式

## 6.1 刷新工具索引

这个文件不要长期信任别人的扫描结果。迁移到新机器后先刷新一遍：

```powershell
powershell -File "<SKILL_ROOT>\scripts\refresh-tool-index.ps1"
```

成功后检查：

- `skills\tool-index.md`
- `skills\tool-index.json`
- `skills\capability-graph.json`

> 重要：`tool-index.md` 里的 `yes/no` 只代表**当前扫描机器**的结果，不代表你的机器一定一样。
> `capability-graph.json` 用于当前会话事实：MCP 注册、服务端口、smoke 状态和晋级门禁策略。

### 自动任务路由

任务进入后先调用确定性路由器，不再依赖模型凭印象选择 skill：

```powershell
python "<SKILL_ROOT>\scripts\route_task.py" `
  --task "分析这个 EXE，先做静态反编译" `
  --input-path "C:\path\to\sample.exe" `
  --pretty
```

如果目标是源码或应用项目，增加 `--project-path "<项目根目录>"`，并把每个已知编辑文件作为 `--aigx-target "<仓库相对路径>"` 传入。目标项目的 AIGX genome 和编辑边界是强制门槛；Code Intel/Sentrux 证据仅对同一个项目具有权威性。

路由器会自动完成：目标类型识别、意图匹配、能力 preflight、MCP 在线检查、fallback 选择、授权门槛和成功 oracle 输出。

- `status=ready`：允许执行返回的 `dispatch.command` 或目标 skill 第一动作。
- `status=blocked`：先处理缺失工具、未注册 MCP 或授权范围，禁止绕过。
- `status=no_route`：提议新增 skill，不把任务硬塞到相近模块。
- `status=invalid`：修正任务合同。

只有明确加 `--execute` 才会运行已有的受控脚本入口；普通调用只生成机器可读计划。

## 6.2 IDA Pro 链路

### 启动 IDA MCP HTTP 服务

当前包内脚本入口：

```powershell
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\start.ps1"
```

当前脚本默认复用健康服务。只有显式传 `-ForceRestart` 时，才终止请求端口上已核验的进程树、后台启动服务、等待就绪，并输出 `OK:<工具数量>` 或 `ERR:timeout`。

### 打开样本

```powershell
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\open.ps1" -Path "C:\path\to\sample.exe" -TimeoutSeconds 600
```

特点：

- 自动识别并绕过新版 `idb_open` / 旧版 `idalib_open` 的 schema 问题
- System32 文件会自动复制到临时目录
- 旧数据库文件被锁时会降级到临时副本
- 长分析会输出 `INFO:opening:...`

### 你必须改的地方

默认脚本里仍然存在机器相关值，例如：

- `ida-reverse\scripts\start.ps1`
  - `IDADIR`
  - `ServerPath`
- `ida-reverse\scripts\open.ps1`
  - `IDADIR`
  - `TempDir`

迁移后必须按你的机器改成真实值。

## 6.3 anything-analyzer

当前本机项目元信息显示：

- 项目名：`anything-analyzer`
- 包管理器：`pnpm@10.24.0`
- 常见脚本：`dev` / `build` / `preview`

常见开发启动方式：

```powershell
pnpm install
pnpm dev
```

本包只约定它最终对外提供一个 MCP 入口，例如：

```text
http://localhost:23816/mcp
```

如果地址、端口或认证头不同，请同步改你的 MCP 客户端配置。

## 6.4 jshookmcp

`jshookmcp` 在本包里的定位不是独立总入口，而是 `js-reverse` 的增强执行面。

它适合：

- 浏览器自动化
- CDP 调试
- JS Hook
- 网络拦截
- SourceMap / AST 辅助理解

### 注册方式示例

```json
{
  "mcpServers": {
    "jshook": {
      "command": "npx",
      "args": ["-y", "@jshookmcp/jshook@latest"],
      "env": {
        "JSHOOK_BASE_PROFILE": "search"
      }
    }
  }
}
```

注意：

- `tool-index.md` 里 `jshookmcp = yes` 只表示本机具备 `node/npx` 条件
- 不表示它已经被 Claude / Cursor / Cline 注册并启用
- 如果没在 MCP 客户端里启用，它对 AI 是不可调用的

## 6.5 APK 脚本链路

常用脚本：

- `apk-reverse\scripts\decode.ps1`
- `apk-reverse\scripts\frida-run.ps1`
- `apk-reverse\scripts\rebuild-sign-install.ps1`
- `apk-reverse\scripts\manifest-summary.ps1`

迁移后先验证：

```powershell
jadx --version
apktool --version
adb version
frida-ps -U
```

如果 `apksigner` / `zipalign` 在 `tool-index.md` 里仍然是 `no`，说明 Android Build-Tools 还没补齐。

---

## 7. Claude Code / Codex CLI / 其他 AI 客户端如何接入

## 7.1 通用接入原则

不管你用的是 Claude Code、Codex CLI、Cursor、Cline、Windsurf，还是别的代码 AI 客户端，真正要接入的是这四件事：

1. 本包目录
2. MCP 或等价外部工具入口
3. 一种稳定的提示注入方式
4. “先路由后执行”的工作原则

### MCP 示例

```json
{
  "mcpServers": {
    "anything-analyzer": {
      "url": "http://localhost:23816/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_TOKEN>"
      }
    },
    "idapro": {
      "url": "http://127.0.0.1:13337/mcp"
    },
    "jshook": {
      "command": "npx",
      "args": ["-y", "@jshookmcp/jshook@latest"],
      "env": {
        "JSHOOK_BASE_PROFILE": "search"
      }
    },
    "burpsuite": {
      "command": "node",
      "args": ["<REPO_ROOT>/burp-mcp-full/mcp-bridge.js"]
    }
  }
}
```

### 最低提示要求

所有客户端必须暴露同一条三步入口链：

1. `<REPO_ROOT>\.aigx\protocol.aigx` — 权威上下文与编辑边界合同。
2. `<REPO_ROOT>\RULES.md` — 薄兼容启动页。
3. `<SKILL_ROOT>\scripts\route_task.py` — 确定性、fail-closed 计划器。

返回的计划按需选择能力证据和子 skill。不得预载或用 `routing.json`、过期能力图、模型直觉替代这条链。

## 7.2 Claude Code

Claude Code 最适合直接接这套包，因为它同时支持：

- MCP
- 本地 hook
- 项目级说明
- 本地脚本

如果你已经有 `.claude\settings.local.json`、`.claude\mcp.json` 或项目说明，只更新它们指向三步入口链的非破坏性指针；不要把完整 genome 复制进全局配置。

## 7.3 Codex CLI

Codex CLI 也可以复用这套包，但建议把 README 理解成“接入原则”而不是“只认某一种配置格式”。

对 Codex CLI，至少确保：

- 把 AIGX protocol、RULES bootstrap 和确定性路由器暴露给模型
- 逆向/CTF/抓包任务先运行路由器
- 如果要调 anything-analyzer / jshook / idapro，则客户端侧要有对应 MCP 或外部工具接入能力
- 如果没有 hook 机制，就用项目级 instructions / system prompt 兜底

换句话说，Codex CLI 需要复用的是这套**路由方法论和工具入口**，不一定要复刻 Claude 的 hook 实现。

## 7.4 Cursor / Cline / Windsurf / 其他代码 CLI

这些工具只要满足两件事，也可以复用本包：

1. 支持 MCP 或等价外部工具接入
2. 支持 Rules / 自定义指令 / 项目级说明文件

在项目说明中增加指向 `<REPO_ROOT>\.aigx\protocol.aigx`、`<REPO_ROOT>\RULES.md` 和 `<SKILL_ROOT>\scripts\route_task.py` 的非破坏性指针。MCP 地址单独配置；不要向全局配置注入重复规则正文。

---

## 8. 迁移后必改项

这是最容易漏掉的部分。

### 8.1 绝对路径

你只要换了电脑、用户名、盘符，以下内容都应检查：

- `<REPO_ROOT>\...`
- `<用户目录>\...`
- `<用户目录>\...`
- `D:\APP\IDA\`

### 8.2 IDA 脚本

重点检查：

- `skills\ida-reverse\scripts\start.ps1`
- `skills\ida-reverse\scripts\open.ps1`

至少要确认：

- `IDADIR`
- `idalib-mcp.exe` / `ida-pro-mcp.exe` 实际路径
- 临时目录是否存在且可写
- 端口 `13337` 是否冲突

### 8.3 Claude 本地 hook

如果你已经为 Claude 配了：

- `.claude\settings.local.json`
- `.claude\scripts\route-reverse.ps1`

那么迁移本包后，要把脚本里所有旧的：

- `SKILL.md`
- `evolution\SKILL.md`
- `routing.json`
- `routing.md`
- `capability-graph.json`
- `tool-index.md`
- `refresh-tool-index.ps1`

路径改成新的安装位置。

### 8.4 工具索引

迁移后请重新执行：

```powershell
powershell -File "<SKILL_ROOT>\scripts\refresh-tool-index.ps1"
```

不要直接相信随包附带的 `tool-index.md`，因为那是上一台机器扫出来的。

---

## 9. 推荐验证清单

新机器装完后，建议按下面顺序验收。

### 9.1 基础命令

```powershell
java -version
python --version
pip --version
node -v
npx -v
jadx --version
apktool --version
adb version
frida-ps -U
```

### 9.2 IDA 链路

```powershell
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\start.ps1"
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\open.ps1" -Path "C:\path\to\sample.exe" -TimeoutSeconds 600
```

### 9.3 工具索引

```powershell
powershell -File "<SKILL_ROOT>\scripts\refresh-tool-index.ps1"
```

然后确认 `tool-index.md` 至少正确反映：

- `jadx`
- `apktool`
- `adb`
- `frida`
- `node`
- `npx`
- `jshookmcp`
- `r2` / `rabin2`（如果你装了 radare2）

### 9.4 MCP 可用性

确认你的 AI 客户端里至少能看到：

- anything-analyzer（如果已接入）
- jshook（如果已注册）
- idapro（如果已接入并已启动）

---

## 10. 常见问题

### Q1：我能把 `skills` 放到别的盘吗？

可以，但你必须同步改所有引用它的绝对路径，包括：

- Claude hook
- MCP 示例配置中的本地脚本路径
- 你自己写的 Rules / RULES.md / memory 指针
- 任何写死了旧路径的 PowerShell 脚本

### Q2：为什么文档或脚本里还会出现 `<用户目录>\...`？

这是历史机器留下的示例路径，不代表必须使用该路径。迁移时一律以你当前机器真实路径为准。

### Q3：`tool-index.md` 里显示 `yes`，为什么 Claude 还是不能调用？

因为这只说明**本机存在运行条件或可执行文件**，不代表对应工具或 MCP server 已经注册到 AI 客户端。

典型例子：

- `jshookmcp = yes` 只说明 `node/npx` 在
- 不说明你已经把 `@jshookmcp/jshook` 配进 Claude MCP

### Q4：一定要装 IDA 吗？

不是。二进制分析可以先用 `radare2`，但如果你需要更强的伪代码、xref、重命名、类型恢复，IDA 仍然是本包里的深度方案。

### Q5：anything-analyzer 和 jshookmcp 的区别？

- anything-analyzer：更偏浏览器自动化、HTTP 捕获、请求分析
- jshookmcp：更偏 JS 运行时、CDP、Hook、SourceMap、AST
- `js-reverse`：不是工具，而是方法论和工作流

正确关系是：

- `playbook` 决定怎么做
- anything-analyzer / jshookmcp 负责执行取证和采样

---

## 11. 给分发者的建议

如果你准备把这套包发给别人，建议同时附上：

1. 本 README
2. 一个已经改好路径的示例 `mcp.json`
3. 一个已经改好路径的 Claude hook 示例
4. 一份“首次安装 checklist”
5. 一次 fresh scan 生成的 `tool-index.md` 和 `capability-graph.json`

最理想的分发形态是：

- 文档里只写**结构和要求**
- 具体机型路径留给安装者自己填
- 机密信息（Token、私有 URL、内部端口）全部改成占位符

---

## 12. 当前包内最重要的文件

如果你只看核心文件，先看这些：

1. `<REPO_ROOT>\README.md`
2. `<REPO_ROOT>\.aigx\protocol.aigx` + concern genomes — 权威项目上下文
3. `<REPO_ROOT>\RULES.md` — 进入 AIGX 与路由器的兼容启动页
4. `<SKILL_ROOT>\SKILL.md` — 总控入口
5. `<SKILL_ROOT>\evolution\SKILL.md` — GOAL、能力图谱、TraceCard、晋级门禁
6. `<SKILL_ROOT>\routing.json` + `<SKILL_ROOT>\routing.md` — 场景→技能分流
7. `<SKILL_ROOT>\capability-graph.json` + `<SKILL_ROOT>\tool-index.md` — 本机能力/工具状态

安全路由若因授权阻塞，必须提供当前 session 明确的 `authorization_scope`，否则停止。随包先例只是通用方法论，不能推翻拒绝、证明目标归属或取代路由器的授权门禁。

如果要新增 skill，看这个：

9. `<SKILL_ROOT>\CONTRIBUTING.md`

---

## 13. 跨 AI 客户端的上下文启动

权威规则源是 `.aigx/`。`RULES.md` 和各客户端指令文件只是非破坏性的薄指针；不得复制整套规则，也不得静默改写客户端全局配置。

### 13.1 首次使用流程

1. 用 AI 客户端打开 `<REPO_ROOT>`。
2. 让客户端读取 `.aigx\protocol.aigx` 与 `RULES.md`。
3. 用真实任务和 artifact/project 路径运行确定性路由器。
4. 只有 `status=ready` 才继续；缺失制品、无效 AIGX、未解析编辑边界和结构门禁失败都必须阻塞。

### 13.2 验证启动链

对 artifact 路由先故意不传 `--input-path`，确认返回 `status=blocked` 和 `input_path_required`；再传入现存文件，确认计划给出选中的受控入口。该验证不会修改 artifact、IDA 配置或结构 baseline。

### 13.3 更新

相关 AIGX concern 与被索引的实现/文档必须一起更新。晋级前运行官方 AIGX lint、定向路由测试和完整脚本回归。

---

## 14. Session 上下文

机器状态、目标路径、凭据、合同、IDB 和运行产物必须保留在本仓库之外。AIGX 保存稳定的项目规则与文件边界，不是已分析目标的登记表，也不能取代每个 session 的授权范围。

---

## 15. 不持久化目标数据的自动进化

运行 trace、报告、目标身份、路径、二进制、源码事实、IDB、含目标数据的命令和分析证据必须保留在获授权的目标工作区或外部 session store。完成任务不会自动向本分发仓库写入任何内容。

### 15.1 晋级候选

只有通用模式可以提议晋级。进入本仓前必须完成脱敏、证明不依赖单一目标、提供可复现 fixture 或回归测试、绑定成功 oracle，并给出回滚证据。无法满足这些条件的候选继续留在仓外。

### 15.2 晋级门禁

使用 `evolution/trace-card.template.yaml` 与 `evolution/promotion-record.template.yaml`。状态严格区分：

- `validated`：通用 oracle 与回归通过，可影响未来路由。
- `candidate`：可能可复用但尚无回归，只能提示。
- `forensic`：失败、异常、疑似污染或目标特定证据，只能分析，禁止晋级为控制流。

只有显式、经审查的晋级才允许更新 AIGX、`routing.md`、`routing.json`、子 skill 或 `bootstrap-manifest.json`。提交前运行官方 AIGX lint、定向回归、完整脚本测试与敏感数据扫描。

### 15.3 随包 Field Journal

`field-journal/` 只保存包自身的通用先例和已晋级模式；它不是逐项目日志目录、授权数据库，也不是 session 自动回写目标。

---

## 16. 给 AI 的完整行为总结

权威顺序是：加载 AIGX → 解析任务与编辑边界 → 构建确定性路由 → 满足输入、能力、服务、授权和项目门禁 → 执行受控工作流 → 验证成功 oracle → 只晋级通用且有回归证据的经验。`RULES.md` 只是进入这条链路的兼容入口。

---

最后建议：

- 把这套包当成"技能路由 + 工具入口 + 方法论资产 + 自进化知识库"，不要当成某个单独客户端的说明书。
- 真正迁移成功的标志不是“文件拷过去了”，而是：任何受支持的代码 CLI 都遵循同一条 AIGX-first 路由，调用本机真实存在的能力，把目标证据留在仓外，并且只晋级经审查的通用经验。

---

## 17. Bootstrap 失败时的用户引导

并非所有能力都能 100% 自动安装成功。当 AI 尝试自动补齐后仍然失败时，**不要沉默或反复重试**，必须立即切换到"引导用户手动配置"模式。

### 17.1 AI 的失败处理流程

```text
1. 调用 bootstrap-reverse.ps1 尝试自动安装
2. 安装后验证是否可用
3. 如果仍不可用 → 不要再重试 → 立即输出结构化引导
```

### 17.2 结构化引导模板

当自动安装失败时，AI 必须按以下格式告知用户：

```markdown
⚠️ **[工具名] 自动安装失败，需要你手动处理**

**问题**：[具体错误信息]

**可能原因**：
- [原因1，如：网络不通 / GitHub API 限流]
- [原因2，如：缺少前置依赖]
- [原因3，如：端口被占用]

**手动安装步骤**：
1. [第一步，含具体命令或下载链接]
2. [第二步]
3. [第三步]

**安装完成后验证**：
```
[验证命令]
```

**验证通过后告诉我，我会继续当前任务。**
```

### 17.3 各能力的具体引导方案

#### anything-analyzer 安装失败或端口不一致

```markdown
⚠️ **anything-analyzer 服务不可用**

**问题**：端口 23816 无响应，或服务未启动

**可能原因**：
- 项目未 clone 到本地
- pnpm 未安装
- 端口被其他程序占用
- 项目依赖未安装

**手动安装步骤**：

1. 确保已安装 Node.js 和 pnpm：
   ```powershell
   node -v          # 需要 v18+
   pnpm -v          # 如果没有：npm install -g pnpm
   ```

2. Clone 项目：
   ```powershell
   git clone https://github.com/Mouseww/anything-analyzer.git C:\work\anything-analyzer
   cd C:\work\anything-analyzer
   ```

3. 安装依赖并启动：
   ```powershell
   pnpm install
   pnpm dev
   ```

4. 确认服务启动后，检查端口：
   ```powershell
   curl http://localhost:23816/mcp
   ```
   如果端口不是 23816，请告诉我实际端口号，我会帮你更新 MCP 配置。

5. 在你的 AI 客户端 MCP 配置中注册：
   ```json
   {
     "mcpServers": {
       "anything-analyzer": {
         "url": "http://localhost:23816/mcp"
       }
     }
   }
   ```
   - Claude Code：写入 `~/.claude/mcp.json`
   - Kiro：写入 `.kiro/settings/mcp.json`
   - Cursor：在 MCP 设置面板中添加

**验证通过后告诉我，我继续当前任务。**
```

#### jshookmcp 注册失败或不可调用

```markdown
⚠️ **jshookmcp MCP server 不可用**

**问题**：已注册但无法调用，或注册失败

**可能原因**：
- npx 无法拉取 @jshookmcp/jshook 包（网络问题）
- MCP 客户端未启用该 server
- Node.js 版本过低

**手动配置步骤**：

1. 确认 npx 可用：
   ```powershell
   npx -v    # 需要 9.0+
   ```

2. 测试能否拉取包：
   ```powershell
   npx -y @jshookmcp/jshook@latest --help
   ```

3. 在 MCP 配置中添加：
   ```json
   {
     "mcpServers": {
       "jshook": {
         "command": "npx",
         "args": ["-y", "@jshookmcp/jshook@latest"],
         "env": {
           "JSHOOK_BASE_PROFILE": "search"
         }
       }
     }
   }
   ```

4. 重启 AI 客户端或重新连接 MCP server

**配置完成后告诉我，我继续当前任务。**
```

#### idalib-mcp / IDA Pro 服务启动失败

```markdown
⚠️ **IDA Pro MCP 服务不可用**

**问题**：端口 13337 无响应

**可能原因**：
- IDA Pro 未安装或 IDADIR 环境变量未设置
- idalib-mcp 未安装
- IDA 许可证问题

**手动配置步骤**：

1. 确认 IDA Pro 已安装，记下安装目录

2. 设置环境变量（替换为你的实际路径）：
   ```powershell
   [Environment]::SetEnvironmentVariable('IDADIR', '<你的IDA安装目录>', 'User')
   ```
   或 CMD：
   ```cmd
   setx IDADIR "<你的IDA安装目录>"
   ```

3. 安装 ida-pro-mcp（必须从 GitHub，不是 PyPI）：
   ```powershell
   pip install git+https://github.com/mrexodia/ida-pro-mcp.git
   ```

4. 安装 IDA 插件：
   ```powershell
   ida-pro-mcp --install
   ```
   选择：Streamable HTTP → Global → 全选客户端

5. 重启 IDA Pro，打开目标文件，插件自动监听 13337

**启动成功后告诉我，我继续当前任务。**
```

#### radare2 安装失败

```markdown
⚠️ **radare2 自动安装失败**

**问题**：GitHub Release 下载失败或解压后未加入 PATH

**手动安装步骤**：

1. 从 GitHub 下载最新 Windows 版本：
   https://github.com/radareorg/radare2/releases
   选择 `radare2-*-w64.zip`

2. 解压到：`C:\Users\<你的用户名>\Tools\radare2\`

3. 把 `bin\` 目录加入系统 PATH：
   ```powershell
   $r2bin = "$env:USERPROFILE\Tools\radare2\bin"
   [Environment]::SetEnvironmentVariable('PATH', "$r2bin;$([Environment]::GetEnvironmentVariable('PATH', 'User'))", 'User')
   ```

4. 新开终端验证：
   ```powershell
   r2 -v
   rabin2 -v
   ```

**验证通过后告诉我。**
```

#### zipalign / apksigner 不可用

```markdown
⚠️ **Android Build-Tools 未安装（zipalign / apksigner 不可用）**

**说明**：这两个工具目前无法全自动安装，需要通过 Android SDK Manager 手动处理。

**手动安装步骤**：

1. 如果已有 Android Studio，打开 SDK Manager 安装 Build-Tools

2. 如果只想命令行安装：
   ```powershell
   # 先确认 sdkmanager 位置（通常在 Android SDK 的 cmdline-tools 目录下）
   sdkmanager "build-tools;35.0.0"
   ```

3. 安装后确认路径存在：
   ```powershell
   dir "$env:LOCALAPPDATA\Android\Sdk\build-tools\35.0.0\zipalign.exe"
   dir "$env:LOCALAPPDATA\Android\Sdk\build-tools\35.0.0\apksigner.bat"
   ```

4. 不需要手动加 PATH，本包脚本会自动扫描 build-tools 目录

**安装完成后运行 `refresh-tool-index.ps1` 刷新索引。**
```

### 17.4 端口冲突处理

当 MCP 服务的端口与预期不一致时，AI 应该：

1. 询问用户实际端口号
2. 帮用户更新 MCP 配置中的 URL
3. 更新 `bootstrap-manifest.json` 中对应的 `servicePort`（如果是永久变更）
4. 重新验证连通性

示例对话：

```
AI: anything-analyzer 的默认端口 23816 无响应。你的服务跑在哪个端口？
用户: 3000
AI: 好的，我帮你把 MCP 配置改成 http://localhost:3000/mcp，并验证连通性。
```

### 17.5 AI 行为规则总结

| 情况 | AI 应该做什么 |
|------|-------------|
| bootstrap 成功 | 继续执行任务，不打扰用户 |
| bootstrap 失败，原因明确 | 输出结构化引导，等用户确认后继续 |
| bootstrap 失败，原因不明 | 输出已知信息 + 建议用户检查网络/权限，等确认 |
| 服务端口不一致 | 询问实际端口，帮用户更新配置 |
| 反复失败（同一工具失败 2 次） | 明确告知"自动安装无法完成"，给出完整手动步骤，不再重试 |
| 用户确认已手动安装 | 重新运行 `refresh-tool-index.ps1` 验证，然后继续任务 |

---

## 18. 许可与免责声明

本包仅用于合法授权的安全研究、学习和 CTF 竞赛。

- 使用者需确保所有操作在法律允许范围内进行
- 未经授权对他人系统进行渗透测试属于违法行为
- 本包作者不对任何滥用行为承担责任
- 逆向工程应遵守当地法律法规及软件许可协议
- CTF 竞赛环境中的操作不应扩展到竞赛范围之外

> **强制使用 AIGX。** `.aigx/` 是项目上下文的唯一权威来源；`RULES.md` 与各客户端指令只负责启动。目标项目缺少有效 genome，或显式编辑文件没有边界条目时，项目路由必须阻塞。
