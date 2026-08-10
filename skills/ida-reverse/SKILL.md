---
name: ida-reverse
description: |
  IDA Pro 逆向分析辅助技能。当用户提到逆向、反编译、分析二进制/PE/ELF/APK/DLL/SO、破解、找密码、漏洞分析、病毒分析、firmware 固件分析，或需要分析 exe/dll/so/elf/macho/sys 等文件时，务必使用此技能。

  Ensure to use this skill when the user wants to analyze any binary file, regardless of whether they explicitly mention "IDA" or "reverse engineering". This includes requests like "看看这个exe", "分析这个dll", "帮我破解", "找一下密码", "这个软件怎么注册", etc.

  Prefer native idapro MCP tools for agent calls and the Python reverse-skill CLI for installation, registration, diagnostics, and manual use. The IDA execution path does not use PowerShell.
---

# IDA Pro 逆向分析技能

## 当前调用边界（必读）

### 踩过的坑

1. **原生 MCP 与 CLI 使用同一条真实链路**
   - Codex 注册名为 `idapro`，地址默认是 `http://127.0.0.1:13337/mcp`
   - 原生 MCP 适合代理直接调工具；Python 命令 `reverse-skill` 适合登录安装、诊断和人工操作
   - CLI 先按 `2026-07-28` 调用 `server/discover`；现代服务使用逐请求元数据，旧服务才降级到 `initialize` / `notifications/initialized` 和 `Mcp-Session-Id`

2. **`C:\Windows\System32\` 文件无权限打开**
   - idalib 无法直接读取 System32 目录下的文件
   - **解决办法**：`reverse-skill open` 自动检测并复制到临时目录后再打开

3. **启动服务器命令阻塞对话**
   - `idalib-mcp` 启动后会持续输出 INFO 日志到控制台
   - **解决办法**：使用 `reverse-skill start`；Python 用无窗口后台进程启动服务
   - 命令会等待服务就绪后自动退出，不阻塞对话

4. **MCP 注册名固定为 `idapro`**
   - 服务器自身名称可以是 `ida-pro-mcp`；Codex 侧统一使用短注册名 `idapro`
   - 运行 `reverse-skill register`，不要手工漂移配置文件

5. **传输固定为 Streamable HTTP**
   - 当前方案不使用 stdio，IDA CLI 也不经过 PowerShell
   - 真正链路是 `reverse-skill → HTTP MCP → idalib-mcp.exe → IDA`

6. **协议版本必须协商，不能写死服务端版本**
   - 客户端优先使用已发布版 `2026-07-28` 的逐请求 `_meta`，并镜像 `MCP-Protocol-Version` / `Mcp-Method` / `Mcp-Name` / `Mcp-Param-*` 头
   - 遇到非现代响应才进入 legacy 初始化，接受 `2025-11-25`、`2025-06-18` 或 `2025-03-26`；`status` 必须明确显示 `era`
   - 现代协议没有协议会话；IDA database ID 是应用层显式句柄，不等同于 `Mcp-Session-Id`
   - MRTR 的 `requestState` 必须原样回传且重试使用新的 JSON-RPC id；CLI 用 `--input-responses-json` / `--request-state` 显式完成该步骤
   - 规范映射、双时代流程和本机验证见 [`references/mcp-2026-07-28-dual-era.md`](references/mcp-2026-07-28-dual-era.md)

7. **健康服务不能为了“重启”被误杀**
   - `reverse-skill start` 先完成 MCP 初始化和 `tools/list` 健康检查
   - 服务健康时原样复用；只有显式传入 `--replace-stale` 时，才清理陈旧 `idalib-mcp` 进程树后启动新服务

8. **打开和分析可能是长请求**
   - `idb_open(run_auto_analysis=true)` 会等待 IDA 分析，应按样本规模设置根选项 `--timeout`
   - 超时是明确失败，不用吞错、盲重试或伪造成功会话

### 工作流程原则

| 步骤 | 做什么 | 用什么 |
|------|--------|--------|
| 1 | 注册并检查 Codex MCP | `reverse-skill register`、`status` |
| 2 | 确保 HTTP 服务在运行 | `reverse-skill start` |
| 3 | 打开目标二进制文件 | `reverse-skill open "xxx.exe"` |
| 4 | 调用动态发现的工具 | 原生 `idapro` MCP，或 `reverse-skill call` |
| 5 | 分析完毕 | `reverse-skill close <session-id>` |

## Python CLI

安装入口：`<repo-root>\pyproject.toml`；源码入口：`python -m reverse_skill`。

```console
python -m pip install -e .
reverse-skill register
reverse-skill start
reverse-skill status
reverse-skill tools
reverse-skill --timeout 600 open "C:\path\to\file.exe"
reverse-skill sessions
reverse-skill call decompile --database "<session-id>" --arguments-json '{"addr":"0x140001000"}'
reverse-skill close "<session-id>"
```

`start` 自动选择本机最高版本的有效 IDA；`--ida-dir` 只用于明确固定版本。`open` 支持 `--preferred-session-id`、`--no-auto-analysis`、`--no-build-caches`，并自动处理 System32 输入。复杂样本使用 `reverse-skill --timeout 600 open ...`；这只扩大等待上限，不改变服务端分析行为。

机器调用使用 `--json`；输出 schema、稳定退出码和 OpenCLI 0.1 描述见 [`references/cli-contract.md`](references/cli-contract.md)。

## v2 beta：插件与 Teams

统一使用 Python CLI，不再维护第二套脚本协议：

```console
reverse-skill plugins inventory
reverse-skill plugins check --plugin-root "<IDA user plugins>"
reverse-skill teams preflight "<IDB Git repository>"
reverse-skill teams plan "<private collaboration contract.json>"
reverse-skill teams lab "<private worktree contract.json>"
```

- `plugins inventory` 自动选择本机最新版有效 IDA；`--ida-dir` 只用于明确固定安装。
- 插件状态严格区分已发现、静态兼容、运行时加载和动作验证；静态检查不能冒充 GUI smoke。
- Teams 默认只读。创建隔离 lab 必须显式增加 `--apply`，并且合同中的 lab 目录必须位于脏源仓之外。
- 登录、授权或 Teams entitlement 需要时由用户交互完成，不进入许可证漂移或猜测逻辑。
- 原 `skills/**/scripts/*.py` 路径只保留兼容入口，实际实现统一位于 `reverse_skill` 包。

## 核心工具列表

`tools/list` 的实时结果是唯一真相；先执行 `reverse-skill tools`，不要依赖固定数量或历史快照。当前主要分组如下：

- 会话：`idb_open`、`idb_list`、`idb_close`、`idb_save`、`server_health`
- 概览：`survey_binary`、`list_funcs`、`list_globals`、`entity_query`、`imports_query`
- 反编译：`decompile`、`disasm`、`analyze_function`、`analyze_batch`、`func_profile`
- 引用与数据流：`xrefs_to`、`xref_query`、`callees`、`callgraph`、`trace_data_flow`
- 搜索与读取：`find_regex`、`search_text`、`find_bytes`、`get_bytes`、`get_string`、`get_int`
- 类型与结构：`declare_type`、`set_type`、`infer_types`、`type_query`、`read_struct`
- 注释与修改：`set_comments`、`append_comments`、`rename`、`patch`、`patch_asm`、`define_func`
- 签名：`make_signature`、`make_signature_for_function`、`make_signature_for_range`、`find_xref_signatures`

Codex 原生工具会由客户端加上 `idapro` 注册命名空间；CLI 的 `call TOOL` 参数使用上面这些服务端原名。每个分析工具都必须携带 `database=<session-id>`。

## 逆向分析完整工作流

### Step 1: 启动服务器
确保 HTTP 服务在后台运行。
```console
reverse-skill register
reverse-skill start
reverse-skill status
```
`status` 中 `mcp.online=true` 且 `toolCount>0` 表示就绪。

### Step 2: 打开文件
```console
reverse-skill --timeout 600 open "C:\目标.exe"
```
命令返回真实 session；带自动分析的复杂样本需要更长超时。

### Step 3: 全局概览
```
survey_binary(detail_level="minimal", database="<session-id>")
```
关注：
- 架构（x86/x64/ARM）
- 入口点（main/WinMain/DllMain）
- 有趣的字符串（URL、路径、错误消息）
- 导入分类（加密函数？网络 API？文件操作？）
- 热门函数（高 xref 计数的函数通常是关键逻辑）

### Step 4: 深入关键函数
```
analyze_function(addr="关键函数名", database="<session-id>")
```
或：
```
decompile(addr="函数名", database="<session-id>")
disasm(addr="函数名", max_instructions=50, database="<session-id>")
```

### Step 5: 数据流和交叉引用
```
xrefs_to(addrs="关键地址/字符串", database="<session-id>")
callgraph(roots=["关键函数"], max_depth=3, database="<session-id>")
trace_data_flow(addr="关键地址", direction="backward", max_depth=5, database="<session-id>")
```

### Step 6: 记录和优化
```
set_comments(items=[{"addr": "0x140001000", "comment": "你的理解"}], database="<session-id>")
rename(batch={"func": [{"addr": "函数地址", "name": "有意义的名字"}]}, database="<session-id>")
```

### Step 7: 输出报告
分析完成后，生成 `report.md` 记录发现和步骤。

## Prompt 工程准则

1. **不要手动算进制** — 任何时候需要转换数字，用 `int_convert`
2. **先 survey 后深入** — 先看概况再针对性分析
3. **持续加注释和重命名** — 分析过程中不断更新函数名和变量名，提升后续分析的准确性
4. **跟踪交叉引用** — 发现有趣的数据/字符串，用 `xrefs_to` 看谁引用了它
5. **遇到混淆代码** — 先做字符串解密、导入哈希去除、控制流平坦化去除等预处理
6. **C++ STL 代码** — 用 FLIRT/Lumina 识别库函数后，再分析业务逻辑
7. **不要暴力破解** — 分析应从反汇编中推导解决方案，用简单 Python 辅助计算
8. **遇到 "No database bound"** — 先执行 `reverse-skill open`，再把返回的 session 作为 `database`
9. **遇到 worker 不可达** — 该 session 已陈旧；不要伪造结果，关闭或重新打开真实目标
10. **带自动分析打开 GUI/复杂样本时** — 显式加根选项 `--timeout 600`，超时后按失败处理

---

## 路由上下文

**上游入口**: `skills/SKILL.md`（总控）、`routing.md`
**上游备选**: `radare2/`（如果不想开 IDA，可以先 r2 快速侦察）
**下游出口**:
- 需 Frida 动态验证 → `reverse-engineering/tools-dynamic.md`
- 需符号执行/angr → `reverse-engineering/tools-dynamic.md`
- 需通用逆向方法论 → `reverse-engineering/SKILL.md`

**同级关联模块**: `radare2/`（IDA 不可用时替代方案）

---

## 按需自举（On-Demand Bootstrap）

本 skill 的 Python CLI 已接入统一自举系统。

### 自动化能力边界

| 工具 | 可自动安装 | 安装方式 | 说明 |
|------|-----------|---------|------|
| idalib-mcp | ✓ | `reverse-skill install` | 从 GitHub 安装并进入上游交互安装器 |
| IDA Pro 本体 | ✗ | 需手动安装/登录 | 默认选择本机可用安装中的最高版本；显式 `--ida-dir` 才固定目录 |

### 安装步骤（已验证）

```console
# 1. 安装本仓库 Python CLI
python -m pip install -e .

# 2. 从 GitHub 安装 ida-pro-mcp 并进入交互安装（选择 Streamable HTTP）
reverse-skill install

# 3. 重启 IDA Pro，打开目标文件
# 插件自动监听 127.0.0.1:13337

# 4. 验证
ida-pro-mcp --config
```

> ⚠️ **注意**：PyPI 上的 `ida-mcp` 包（作者 jtsylve）是另一个项目，不是我们需要的。
> 必须从 GitHub 安装 `mrexodia/ida-pro-mcp`。

### 自举触发点

- CLI 安装：`reverse-skill install`
- MCP 注册：对 Codex 执行 `reverse-skill register`；其他客户端按各自的原生注册命令配置同一 URL

### 前置条件

- IDA Pro 已安装；Python CLI 按版本选择本机最高的有效安装，旧 `IDADIR` 只作为候选，不再覆盖新版
- Python 已安装（idalib-mcp 依赖 Python）
