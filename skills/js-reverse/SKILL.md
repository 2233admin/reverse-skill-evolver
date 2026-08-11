---
name: js-reverse
description: 在使用 js-reverse-mcp 做前端 JavaScript 逆向时使用，适用于签名链路定位、页面观察取证、运行时采样、本地补环境复现与证据化输出。优先适配当前环境里的 js-reverse_* 工具，需要更强的浏览器/CDP/Hook 面时联动 jshookmcp。
---

# MCP 前端 JS 逆向作业规范

## 适用范围

当任务属于以下场景时优先使用本 skill：

- 定位接口签名、加密参数、风控字段
- 观察页面请求链路与脚本来源
- 在运行时抓取函数入参与返回值
- 追踪某个 XHR/Fetch/WebSocket 的触发点
- 把页面证据带回 Node 做本地复现与补环境

如果目标是二进制、APK、PE、ELF、DLL、SO，请改用 `ida-reverse`、`radare2` 或 `reverse-engineering`。

## 当前环境默认工具映射

本 skill 不假设存在裸工具名，而是默认绑定当前客户端环境里可用的 `js-reverse_*` 工具。

如果当前任务明确提到 `jshookmcp`、`JS hook`、`CDP`、浏览器断点、网络拦截、SourceMap 或 AST 去混淆，也仍然走本 skill；只是把底层 MCP 面切到 `jshookmcp`，而不是把它当成一个新的总入口。

前提条件：`jshookmcp` 不是本地裸命令工具，而是一个要先下载/注册/启用的 MCP server。只有在 Claude MCP 配置里接入并启用后，相关工具面才真的可调用。

常用映射：

- `list_scripts` -> `js-reverse_list_scripts`
- `get_script_source` -> `js-reverse_get_script_source`
- `search_in_sources` -> `js-reverse_search_in_sources`
- `break_on_xhr` -> `js-reverse_break_on_xhr`
- `evaluate_script` -> `js-reverse_evaluate_script`
- `get_paused_info` -> `js-reverse_get_paused_info`
- `set_breakpoint_on_text` -> `js-reverse_set_breakpoint_on_text`
- `list_network_requests` -> `js-reverse_list_network_requests`
- `get_request_initiator` -> `js-reverse_get_request_initiator`
- `get_websocket_messages` -> `js-reverse_get_websocket_messages`
- `take_screenshot` -> `js-reverse_take_screenshot`
- `new_page` -> `js-reverse_new_page`
- `navigate_page` -> `js-reverse_navigate_page`
- `select_page` -> `js-reverse_select_page`
- `select_frame` -> `js-reverse_select_frame`
- `pause/resume` -> `js-reverse_pause_or_resume`

如果未来工具名前缀变化，先更新本节，不要在执行时临时猜测。

### jshookmcp 的定位

- 角色：`js-reverse` 的增强执行面，不是独立总控
- 适合：浏览器自动化、CDP 调试、JS Hook、网络拦截、SourceMap 重建、AST 辅助理解
- 调用前提：先把 `@jshookmcp/jshook` 下载并注册到 MCP 客户端配置里，然后确保该 server 已启用
- 建议入口：仍然按 `Observe → Capture → Rebuild` 执行，只是在 `Observe/Capture` 阶段优先调用 jshookmcp 的浏览器与 Hook 能力
- 与 anything-analyzer 关系：两者都能做浏览器/网络侧取证；anything-analyzer 更偏抓包与 HTTP 分析，jshookmcp 更偏 JS 运行时、CDP、Hook 和源码理解

### Chrome DevTools MCP 插件（`mcp__plugin_ecc_chrome-devtools__*`）—— 另一套 CDP 工具面

当前环境里还注册了一套独立的 CDP 工具面，来自 Chrome DevTools MCP 插件（`ecc` 插件命名空间），
和 `js-reverse_*`/`jshookmcp` 是**平行关系**，不是替代关系，也不改变上面两节已有的映射。

常用工具：`evaluate_script`、`list_network_requests`、`get_network_request`、
`list_console_messages`、`get_console_message`、`navigate_page`、`new_page`、`select_page`、
`list_pages`、`close_page`、`click`、`hover`、`drag`、`fill`、`fill_form`、`press_key`、
`upload_file`、`handle_dialog`、`take_screenshot`、`take_snapshot`、`take_heapsnapshot`、
`resize_page`、`emulate`、`wait_for`、`performance_start_trace`、`performance_stop_trace`、
`performance_analyze_insight`、`lighthouse_audit`。全部带 `mcp__plugin_ecc_chrome-devtools__` 前缀。

何时优先用它：

- 当前客户端里 `js-reverse_*`/`jshookmcp` 未注册或不可用，但 Chrome DevTools MCP 插件已启用时
- 任务只需要标准 CDP 能力（脚本求值、网络请求列表、页面导航、截图），不需要 jshookmcp 的
  Hook/SourceMap/AST 增强能力时

实测记录：这套工具面是 2026-07-11 一次真实私有 API 逆向会话（CDP 抓包 + 前端源码交叉验证 + 实测
校准方法论）里实际使用并跑通的工具面。方法论细节和踩坑记录见
`../field-journal/candidate/2026-07-11_private-api-cdp-source-cross-reference.md`。

同一条目提炼出两条通用原则，补充记录在此（来自单次会话，candidate 层级，仅供参考，不覆盖上面
已有的工具映射和五阶段工作流）：

- **实测优先于书面/推断规格**：目标前端源码（如表格列定义 JS）给出的字段语义/响应结构只是假设，
  必须用真实探测（live probe）逐项 DIFF 校准，偏差以实测为准
- **按列名而非位置解析**：响应里的字段要按列名建索引取值，不要假设固定顺序/固定下标，尤其在存
  在多个结果集时，按预期标记列名选中目标结果集，不按数组下标选

## 核心原则

- `Observe-first`
- `Hook-preferred`
- `Breakpoint-last`
- `Rebuild-oriented`
- `Evidence-first`

先页面观察，再最小化采样，再做本地补环境，不要跳过取证直接猜环境。

## 五阶段工作流

### 1. Observe

目标：先确认目标请求、相关脚本、候选函数，不猜环境。

默认动作：

- 用 `js-reverse_new_page` 或 `js-reverse_navigate_page` 打开目标页面
- 用 `js-reverse_list_network_requests` 找目标请求
- 用 `js-reverse_get_request_initiator` 回溯调用来源
- 用 `js-reverse_list_scripts`、`js-reverse_search_in_sources` 缩小脚本范围

必须产出：

- 目标请求 URL 或特征
- initiator 线索
- 可疑脚本 URL
- 初始任务记录

### 2. Capture

目标：对目标请求做最小侵入采样，拿到参数样例、调用顺序、运行时证据。

规则：

- 优先 `js-reverse_break_on_xhr`
- 优先 `js-reverse_evaluate_script` 做轻量运行时观察
- 命中后先看 `js-reverse_get_paused_info`
- 必要时再用 `js-reverse_set_breakpoint_on_text`

### 3. Rebuild

目标：把页面证据整理成本地可迭代的 Node 复现材料。

规则：

- 本地补环境必须以页面观测证据为依据
- 不允许空想式补 `window/document/navigator/crypto/storage`
- 每次只记录一个最小因果补丁决策

### 4. Patch

目标：按报错和 first divergence 驱动补环境，直到本地脚本稳定跑出目标参数。

规则：

- 先看缺什么，再补什么
- 一次只做一个最小补丁决策
- 每次补丁后立即复测
- 每次补丁都写入任务记录

### 5. DeepDive

目标：本地跑通后，再做去混淆、控制流还原、业务逻辑提纯。

规则：

- 如果当前任务只是出签名，这一阶段可以降级
- 如果要长期复用算法链路，这一阶段必须做

## 执行要求

- 所有重要步骤都要写入本地 task artifact
- 如果无法解释为什么调用某个工具，就不要调用
- 优先使用 `js-reverse_*` 或 jshookmcp 的现成 MCP 能力直接取证，不要先写脚本重造能力
- 失败时按 `references/fallbacks.md` 回退
- 输出遵循 `references/output-contract.md`

## 必读引用

- 自动化入口：`references/automation-entry.md`
- 参数默认值：`references/tool-defaults.md`
- 任务输入模板：`references/task-input-template.md`
- MCP 专用任务编排：`references/mcp-task-template.md`
- 任务产物：`references/task-artifacts.md`
- 本地复现：`references/local-rebuild.md`
- 补环境：`references/env-patching.md`
- Node 复现：`references/node-env-rebuild.md`
- 插桩：`references/instrumentation.md`
- AST 去混淆：`references/ast-deobfuscation.md`
- 回退：`references/fallbacks.md`
- 输出契约：`references/output-contract.md`

---

## 路由上下文

**上游入口**: `skills/SKILL.md`（总控）、`routing.md`
**上游备选**:
- anything-analyzer MCP（端口 23816）的浏览器工具可作为替代或补充
- jshookmcp 可作为更强的浏览器/CDP/Hook/Network/SourceMap/AST 执行面
- `reverse-engineering/SKILL.md`（如果目标不是前端 JS）

**下游出口**:
- 需补环境 → `references/env-patching.md`
- 需本地复现 → `references/local-rebuild.md` / `references/node-env-rebuild.md`
- 需去混淆 → `references/ast-deobfuscation.md`
- 走不通时回退 → `references/fallbacks.md`

**同级关联模块**: anything-analyzer MCP（浏览器自动化和 HTTP 捕获能力可以互补）

---

## 按需自举（On-Demand Bootstrap）

本 skill 依赖的 MCP 能力可通过统一自举系统自动注册。

### 自动化能力边界

| 能力 | 可自动注册 | 方式 | 说明 |
|------|-----------|------|------|
| jshookmcp | ✓ | npm-mcp（npx 启动） | 自动写入 Claude MCP 配置 |
| anything-analyzer | ✓ | local-http-mcp | 自动注册 + 可自动启动服务 |
| Node.js | ✓ | winget 安装 | 运行时依赖 |

### 自举方式

工具安装由用户显式选择（`bootstrap-manifest.json` 只作元数据；不再分发 `bootstrap-reverse.ps1` 项目脚本）：

```console
# 注册 jshookmcp 到 MCP 配置：按官方方式安装后，用 reverse-skill plugins inventory 确认
# 注册并启动 anything-analyzer：按官方方式安装后，用 reverse-skill integrations 确认
```

### 注意事项

- `jshookmcp` 注册后仍需在 AI 客户端中**启用**该 MCP server 才能调用
- `anything-analyzer` 需要 pnpm 和项目源码，bootstrap 会自动 clone 并安装依赖
- 如果 Node.js 未安装，bootstrap 会先通过 winget 安装 Node.js 22
