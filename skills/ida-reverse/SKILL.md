---
name: ida-reverse
description: |
  IDA Pro 逆向分析辅助技能。当用户提到逆向、反编译、分析二进制/PE/ELF/APK/DLL/SO、破解、找密码、漏洞分析、病毒分析、firmware 固件分析，或需要分析 exe/dll/so/elf/macho/sys 等文件时，务必使用此技能。

  Ensure to use this skill when the user wants to analyze any binary file, regardless of whether they explicitly mention "IDA" or "reverse engineering". This includes requests like "看看这个exe", "分析这个dll", "帮我破解", "找一下密码", "这个软件怎么注册", etc.

  Use the canonical Python clients `scripts/start_idalib_mcp.py` and `scripts/open_idalib.py` for deterministic server management and file opening. `scripts/start.ps1` and `scripts/open.ps1` remain compatibility wrappers only; new functionality must use Python, not ad-hoc PowerShell.
---

# IDA Pro 逆向分析技能

## 本机能力盘点与插件选择（必须先做）

1. 先执行只读盘点：
   `python "<skill-root>\scripts\refresh_ida_capabilities.py" --ida-dir "C:\Program Files\IDA Professional 9.4"`
   旧的 `refresh-ida-capabilities.ps1` 保留为兼容包装器，不再维护第二份发现逻辑。
2. 插件任务再执行独立的只读兼容预检：
   `python "<skill-root>\scripts\validate_ida_plugins.py" --plugin-root "<IDA user plugin root>" --ida-version 9.4 --python-exe "<IDAPython runtime>" --pretty`
   它校验 manifest、入口文件、IDA 版本声明、Python 语法与已移除 API；不导入插件、不启动 IDA、不写插件目录。
3. 读取生成的 `generated\ida-capability-graph.json`，再读取 `references\ida-plugin-capabilities.json`。
4. 将插件状态分开报告：`installed`、`compatible_preflight`、`runtime_loaded`、`action_verified`；静态预检通过仍不能称为 GUI 已加载或功能已验证。
5. 根据 workflow readiness 选择插件：版本差异优先 BinDiff + BinExport 或 Diaphora；YARA/加密优先 FindYaraX、Yarka、IDASignsrch；AI 解释在 AIDA/Gepetto 中选一个；结构化 Agent 数据用 DeepExtract；Rust 用 HappyIDA/EmuIt + Rust 工具链。
6. HCLI 只负责插件发现、版本检查和受控安装；不要自动复制 DLL、覆盖 IDA 二进制、修改主配置或把 Rust crate 当 IDA 插件安装。

能力清单见：`references/ida-plugin-capabilities.json`。它描述“插件能做什么”；运行时 graph 描述“本机现在有什么”。

## 已知问题与反思（必读）

### 踩过的坑

1. **不同版本的 idalib-mcp API 名称不同**
   - 新版通常暴露 `idb_open` / `idb_list`；旧版暴露 `idalib_open` / `idalib_list`
   - 部分代码 AI 客户端的 MCP 客户端还会对打开工具的 output schema 校验失败
   - 报错：`Structured content does not match the tool's output schema`
   - **解决办法**：使用 `scripts/open.ps1`（由 `open_idalib.py` 实现）；入口先读取 `tools/list`，自动选择新旧 API，再通过 HTTP API 直调，绕过 MCP 校验层
   - 文件打开后，数据库绑定到共享上下文，其他所有 `idapro_*` 工具可直接使用

2. **`C:\Windows\System32\` 文件无权限打开**
   - idalib 无法直接读取 System32 目录下的文件
   - **解决办法**：`open.ps1` 自动检测并复制到 `临时目录` 目录后再打开

3. **启动服务器命令阻塞对话**
   - `idalib-mcp` 启动后会持续输出 INFO 日志到控制台
   - **解决办法**：使用 `scripts/start.ps1`（由 `start_idalib_mcp.py` 后台静默启动）
   - 脚本会等待服务就绪后自动退出，不阻塞对话

4. **MCP 服务器名不能用横线**
   - 之前用 `ida-pro-mcp` 作为服务器名，可能引起工具注册问题
   - **当前配置**：服务器名 `idapro`，工具前缀 `idapro_*`

5. **Remote HTTP vs Local Stdio**
   - `type:"local"`（stdio）模式：打开工具同样可能有 schema 校验问题
   - `type:"remote"`（HTTP）模式：可以先用脚本直开文件，再用 MCP 工具
   - **当前方案**：Remote HTTP 模式

6. **PR #389 修复了部分 schema 问题**
   - 作者 mrexodia 在 issue #388 后通过 PR #389 合并了修复
   - 修复了 HTTP 模式下的 structuredContent schema，但 部分代码 AI 客户端 侧校验仍有问题
   - 已安装最新 `main` 分支版本

7. **idalib 超时留下孤儿 worker 进程锁文件**
   - 第一次 `open.ps1` 超时后，idalib 的 python worker 子进程变成孤儿进程，咬着 `.id0`/`.id1`/`.nam` 不放
   - 后续任何工具或手动拖入 IDA GUI 都会报"权限不足"
   - **解决办法**：默认复用现有服务；只有显式传 `-ForceRestart` 时才定位当前端口对应的 `idalib-mcp` PID，再用 `taskkill /F /T` 清理该进程树
   - **兜底**：`open.ps1` 加了自动降级，检测到旧库被锁自动复制到 Temp 并加 GUID 前缀

8. **带自动分析打开看起来像卡死**
   - `idb_open`/`idalib_open`（`run_auto_analysis=true`）可能长时间不回包，但后端实际上仍在继续打开和分析
   - 之前用户侧看到的是“PowerShell 一直无输出”，容易误判成脚本卡死
   - **当前解决办法**：`open.ps1` 新增 `-TimeoutSeconds`，并改为后台请求 + 前台轮询 + 定时进度输出
   - 轮询到会话已就绪时会提前返回 `OK:文件名:session_id`，超时则返回 `ERR:open_timeout_xxs`

### 工作流程原则

| 步骤 | 做什么 | 用什么 |
|------|--------|--------|
| 1 | 确保 HTTP 服务器在运行 | `scripts/start.ps1`（无参数） |
| 2 | 打开目标二进制文件 | `scripts/open.ps1 -Path "xxx.exe"` |
| 3 | 使用服务实际暴露的 MCP 工具 | 读取服务的 `tools/list`，按实际暴露的 `idb_*`/`idalib_*`/其他工具调用 |
| 4 | 分析完毕 | 工具自动可用 |

## 脚本资源

### start.ps1 — 启动 MCP HTTP 服务器

路径：`scripts/start.ps1`

- 核心实现：`scripts/start_idalib_mcp.py`；`start.ps1` 只保留旧调用方需要的兼容参数
- 默认复用现有 `idalib-mcp` 服务；只有传 `-ForceRestart` 才清理当前端口已核验的旧进程树 → 后台启动服务 → 等待就绪（最多 15 秒）
- 成功输出实际工具数量，例如 `OK:66`，失败输出 `ERR:timeout`
- 服务器在后台运行，不阻塞对话

**调用方式**：
```
powershell -File "<skill-root>\ida-reverse\scripts\start.ps1"
```

### open.ps1 — 打开二进制文件

路径：`scripts/open.ps1`

- 核心实现：`scripts/open_idalib.py`；`open.ps1` 只保留旧调用方需要的兼容参数
- 通过 HTTP API 直调当前服务实际暴露的 `idb_open` 或兼容旧版的 `idalib_open`，绕过 MCP schema 校验
- 自动检测 System32 路径并复制到临时目录
- 自动清理同名旧数据库文件（`.id0`/`.id1`/`.nam`/`.til`/`.i64`）
- 旧库被锁时自动降级：复制到 Temp 加 GUID 前缀后打开，不报错
- 将打开请求放到后台执行，避免长时间同步等待导致脚本无响应
- 支持 `-TimeoutSeconds`，超时后返回 `ERR:open_timeout_xxs`，不会无限卡住
- 每隔 10 秒输出一次 `INFO:opening:已用时/超时秒数`，便于判断仍在分析中
- 成功输出 `OK:文件名:session_id`，降级时加 `(temp copy)` 标记
- 结构化打开失败时自动重试走 Temp 副本；超时或服务连接失败不会重复等待或重复提交

**调用方式**：
```
powershell -File "<skill-root>\ida-reverse\scripts\open.ps1" -Path "C:\path\to\file.exe"
```

**可选参数**：
```
# 指定 SessionId
powershell -File "scripts\open.ps1" -Path "file.exe" -SessionId "my_session"

# 跳过自动分析（大文件推荐）
powershell -File "scripts\open.ps1" -Path "large.exe" -NoAutoAnalysis

# 设置超时，避免带自动分析时长时间无返回
powershell -File "scripts\open.ps1" -Path "file.exe" -TimeoutSeconds 600
```

**输出约定**：
```
# 分析进行中（每 10 秒输出一次）
INFO:opening:11/600s

# 成功打开
OK:sample.exe:abcd1234

# 成功打开，但因锁文件降级到 Temp 副本
OK:1234abcd-sample.exe:abcd1234 (temp copy)

# 达到超时上限
ERR:open_timeout_600s
```

**实测说明**：
- `Snipaste.exe` 带自动分析实测约 `324s` 才返回成功，属于“分析很久”而不是“脚本死锁”
- 因此遇到 GUI 程序或较复杂样本时，建议优先显式设置 `-TimeoutSeconds 600`

## 核心工具列表

### 概况分析（第一步）
- `idapro_survey_binary(detail_level="minimal")` — 快速概况：函数数、字符串、段、入口点、导入分类（加密/网络/文件IO）
- `idapro_list_funcs(queries)` — 列出函数（分页、按名称过滤）
- `idapro_list_globals(queries)` — 列出全局变量
- `idapro_entity_query(kind, filter)` — 统一查询：functions/globals/imports/strings/names

### 反编译与反汇编
- `idapro_decompile(addr)` — 反编译为伪代码
- `idapro_disasm(addr, max_instructions=N)` — 反汇编
- `idapro_analyze_function(addr, include_asm=false)` — 综合分析（伪代码+字符串+常量+调用者+被调用者+块）
- `idapro_func_profile(queries)` — 函数概要指标

### 交叉引用与数据流
- `idapro_xrefs_to(addrs)` — 查谁引用目标地址
- `idapro_xref_query(addr, direction)` — 高级 xref 查询（方向/类型过滤）
- `idapro_callees(addrs)` — 子函数列表
- `idapro_callgraph(roots, max_depth)` — 调用图
- `idapro_trace_data_flow(addr, direction, max_depth)` — 数据流追踪（forward/backward）

### 搜索
- `idapro_find_regex(pattern, limit)` — 正则搜字符串
- `idapro_search_text(pattern)` — 在反汇编列表中搜文本
- `idapro_find_bytes(patterns, limit)` — 字节模式搜索（支持 ?? 通配符）
- `idapro_find(type, targets)` — 高级搜索（立即数/字符串/引用）

### 内存与数据
- `idapro_get_bytes(addrs)` — 读原始字节
- `idapro_get_string(addrs)` — 读字符串
- `idapro_get_int(queries)` — 读整数值
- `idapro_get_global_value(queries)` — 读全局变量值
- `idapro_read_struct(queries)` — 读结构体字段值
- `idapro_search_structs(filter)` — 搜索结构体

### 修改操作
- `idapro_set_comments(items)` — 添加注释（反汇编+反编译双向同步）
- `idapro_append_comments(items)` — 追加注释
- `idapro_rename(batch)` — 批量重命名（函数/全局/局部/栈变量）
- `idapro_patch_asm(items)` — Patch 汇编指令
- `idapro_patch(patches)` — Patch 字节
- `idapro_define_func(items)` — 定义函数
- `idapro_undefine(items)` — 取消定义
- `idapro_define_code(items)` — 将字节转为代码

### 类型系统
- `idapro_declare_type(decls)` — 声明 C 结构体/枚举/联合体
- `idapro_set_type(edits)` — 应用类型到函数/全局/局部
- `idapro_infer_types(addrs)` — 推断类型
- `idapro_type_query(queries)` — 查询已声明类型
- `idapro_type_inspect(queries)` — 查看类型详情

### 栈帧
- `idapro_stack_frame(addrs)` — 查看栈帧变量
- `idapro_declare_stack(items)` — 声明栈变量
- `idapro_delete_stack(items)` — 删除栈变量

### 签名
- `idapro_make_signature(addrs)` — 为地址生成唯一字节签名
- `idapro_make_signature_for_function(addrs)` — 为函数生成签名
- `idapro_find_xref_signatures(addrs)` — 为引用地址的代码生成签名

### 调试器（需要 ?ext=dbg）
- `idapro_open_file(file_path)` — 在 GUI IDA 实例中打开文件
- 调试器工具默认隐藏，可通过 URL 参数 `?ext=dbg` 启用

### 会话管理
- `idapro_idalib_open(input_path)` — ⚠️ 有 schema 校验 BUG，改用 `open.ps1` 脚本
- `idapro_idalib_list()` — 列出所有 session
- `idapro_idalib_current()` — 当前上下文绑定的 session
- `idapro_idalib_switch(session_id)` — 切换到其他 session
- `idapro_idalib_close(session_id)` — 关闭 session
- `idapro_idalib_save(path)` — 保存数据库
- `idapro_idalib_health(session_id)` — 检查 worker 健康状态

### 其他
- `idapro_int_convert(inputs)` — 进制转换（**必须用这个，不要自己算进制！**）
- `idapro_export_funcs(addrs, format)` — 导出函数（json/c_header/prototypes）
- `idapro_py_eval(code)` — 在 IDA 上下文执行 Python
- `idapro_server_health()` — 服务器健康检查
- `idapro_server_warmup()` — 预热子系统（字符串缓存、Hex-Rays 等）

## 逆向分析完整工作流

### IDA 9.4 原生能力优先级

不要把 9.4 当作只会反编译的通用入口。先使用内建分析，再把第三方插件限制在明确的增强角色：

| 场景 | 首选 9.4 能力 | 可自动执行的 MCP 证据 | 不能伪自动化的边界 |
|---|---|---|---|
| 可达性、调用路径、污点方向 | Pathfinder / Xrefs Graph | `xref_query` → `callgraph` → `trace_data_flow` | Pathfinder 与 Xrefs Graph 本身是 GUI 小部件；需要 `mode=gui` |
| Rust | rustc 版本、crate、panic 位置和 Rust 调用约定恢复 | `survey_binary`、`entity_query`、`decompile`、`type_query` | HappyIDA 是可选可读性增强，未 smoke 不得阻塞原生分析 |
| Swift | `__swiftcall`、async、throwing 与参数恢复 | `survey_binary`、`decompile`、`type_query`、`func_profile` | 不自动写入或覆盖人工确认的类型 |
| Go | pclntab、buildinfo、类型、参数/返回值恢复 | `survey_binary`、`decompile`、`func_profile`、`callgraph` | 识别结果必须以具体函数/类型证据复核 |
| Dyld Shared Cache | 9.4 专用 DSC 小部件与组件间导航 | 无 | 只允许 `mode=gui`；当前 MCP 没有等价 DSC API |
| 团队协作 | IDA Teams / `git-ida` | 无 | `git-ida.exe` 存在不代表有 Teams 授权、服务器或工作区；只按显式任务 smoke |

路由器会校验计划中的 MCP 操作是否实际出现在 `tools/list`。缺少 API 合同时降级/阻塞；GUI-only 功能在未声明 `mode=gui` 时显示为 `deferred`，而不是虚报已执行。

### IDA 9.4 Teams：Git 后端协作

新的协作项目优先使用 9.4 内置的 Teams Git 后端：`git-ida` 管理 IDB 的 Git 存储、过滤器和 Git 属性，IDA GUI 负责语义差异与冲突合并。它不需要专用 Teams/Vault 服务器，但需要有效的 IDA Teams 附加授权和系统 Git。

在任何初始化、拉取、推送或 IDB 写入前，必须先运行只读预检：

```powershell
python "scripts/teams_preflight.py" --repo "<目标 IDB Git 仓库>" --pretty
```

- 预检不会执行 `git-ida initialize`、修改 Git 配置、连接远端或启动 IDA。
- 每个 agent 只能在自己的分支/工作树中处理明确分配的 `.i64`；集成人员才可在 IDA 中执行 Pull、语义 merge 和 Push。
- 只有用户明确指定实际 IDB 仓库后，才允许在那个目录执行初始化；不得在本 skill 仓库或无 `.i64` 的源码仓库中猜测性初始化。
- 路由器使用 `--repo-path` 将 “IDA Teams / git-ida / 团队协作” 分派到这个预检；`mode=gui` 才会提出独立的 Teams GUI/授权烟测。

多 agent 实验先写在私有 lab 目录外置的合同中，模板见 `references/teams-collaboration.contract.example.json`：

```powershell
python "scripts/teams_collaboration.py" --contract "<private-contract.json>" --pretty
```

合同必须将 `lab_repo_path` 与 `source_project_path` 分离，要求唯一 `integrator`，并为每位静态/运行时分析者指定不同的 `teams/*` 分支和作用域。合同中禁止出现账号、token、密码或其他凭据。此检查器只生成计划；不会创建 worktree、初始化 Git/`git-ida`、修改 IDB 或写入源码项目。

遇到脏源码仓时，先从**已提交基线**创建隔离 lab；模板在 `references/teams-worktree-lab.contract.example.json`，合同必须放在私有位置，不得写入项目身份、路径或数据到本 skill：

```text
python "scripts/teams_worktree_lab.py" --contract "<private-worktree-contract.json>" --pretty
python "scripts/teams_worktree_lab.py" --contract "<private-worktree-contract.json>" --apply --pretty
```

- 默认命令只读：记录提交点和脏文件数量，但不改源仓。
- `--apply` 仅在合同指定的、尚不存在的 lab 根目录创建 `control` clone 和每位参与者自己的 worktree；克隆使用 `--no-local`，因此不包含源仓未提交修改。
- 此阶段不创建/复制 `.i64`、不初始化 `git-ida`、不请求许可证、也不触碰远端。需要 Teams 语义合并时，先在某个隔离 worktree 中显式创建 IDB，再单独运行上面的只读预检和 GUI smoke。

### Step 1: 启动服务器
确保 HTTP 服务在后台运行。
```
powershell -File "scripts/start.ps1"
```
输出 `OK:<工具数量>` 表示就绪；工具数量以当前服务的 `tools/list` 为准。

### Step 2: 打开文件
```
powershell -File "scripts/open.ps1" -Path "C:\目标.exe" -TimeoutSeconds 600
```
输出 `OK:文件名:session_id` 表示成功（后带 `(temp copy)` 表示自动降级到临时副本）。
若分析时间较长，会周期性输出 `INFO:opening:...`；若达到超时则输出 `ERR:open_timeout_xxs`。

### Step 3: 全局概览
```
idapro_survey_binary(detail_level="minimal")
```
关注：
- 架构（x86/x64/ARM）
- 入口点（main/WinMain/DllMain）
- 有趣的字符串（URL、路径、错误消息）
- 导入分类（加密函数？网络 API？文件操作？）
- 热门函数（高 xref 计数的函数通常是关键逻辑）

### Step 4: 深入关键函数
```
idapro_analyze_function(addr="关键函数名")
```
或：
```
idapro_decompile(addr="函数名")
idapro_disasm(addr="函数名", max_instructions=50)
```

### Step 5: 数据流和交叉引用
```
idapro_xrefs_to(addrs="关键地址/字符串")
idapro_callgraph(roots=["关键函数"], max_depth=3)
idapro_trace_data_flow(addr="关键地址", direction="backward", max_depth=5)
```

### Step 6: 记录和优化
```
idapro_set_comments(items=[{"addr": "0x140001000", "comment": "你的理解"}])
idapro_rename(batch={"func": [{"addr": "函数地址", "name": "有意义的名字"}]})
```

### Step 7: 输出报告
分析完成后，生成 `report.md` 记录发现和步骤。

## Prompt 工程准则

1. **不要手动算进制** — 任何时候需要转换数字，用 `idapro_int_convert`
2. **先 survey 后深入** — 先看概况再针对性分析
3. **持续加注释和重命名** — 分析过程中不断更新函数名和变量名，提升后续分析的准确性
4. **跟踪交叉引用** — 发现有趣的数据/字符串，用 `xrefs_to` 看谁引用了它
5. **遇到混淆代码** — 先做字符串解密、导入哈希去除、控制流平坦化去除等预处理
6. **C++ STL 代码** — 用 FLIRT/Lumina 识别库函数后，再分析业务逻辑
7. **不要暴力破解** — 分析应从反汇编中推导解决方案，用简单 Python 辅助计算
8. **遇到 "No database bound"** — 还没有打开任何二进制文件，先执行 `open.ps1`
9. **遇到 "Failed to open database"** — 可能是旧数据库文件被锁，`open.ps1` 会自动降级到 Temp 副本（输出含 `(temp copy)` 标记）
10. **带自动分析打开 GUI/复杂样本时** — 默认加 `-TimeoutSeconds 600`，不要把长时间 `INFO:opening:...` 误判成脚本卡死

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

## 发现、维护与受控安装

- 先运行 `refresh-ida-capabilities.ps1`，读取 `generated\ida-capability-report.md` 和 JSON 图。
- IDA 插件优先由 HCLI 管理；仓库外的 AIDA、BinSync、DeepExtract 只记录为已安装，不能假定 HCLI 能升级它们。
- `idalib-mcp` 是外部 MCP 工具，不是普通 IDA 插件；先检查路径、版本和服务端口，再决定是否配置客户端。
- `installed` 不等于 `functional`：GUI 插件、API provider、YARA 规则、IDA license、Rust idalib crate 都是独立门槛。
- `compatible_preflight` 只证明 manifest/入口/版本/Python 静态检查；必须在可丢弃 IDB 上完成 GUI 加载与一个具体动作，才能分别提升为 `runtime_loaded` 与 `action_verified`。
- 缺失项先输出“需要安装什么、为什么、来源和兼容性”；只有用户明确要求且门槛清楚时才执行安装。
- 禁止自动覆盖现有 `ida-pro-mcp`、修改 IDA 主配置、复制跨版本 DLL 或从错误的 `ida-mcp` 包替换当前安装。
