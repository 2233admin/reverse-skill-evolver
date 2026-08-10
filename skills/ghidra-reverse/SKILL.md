---
name: ghidra-reverse
description: |
  Ghidra 逆向分析辅助技能（GhydraMCP）。用户提到用 Ghidra 逆向、反编译、分析二进制/PE/ELF/APK/DLL/SO，
  或明确不想用 IDA、IDA 当前不可运行时使用此技能。
  Use when the user wants to reverse engineer, decompile, or analyze a binary with Ghidra specifically,
  or as a free alternative when IDA Pro is unavailable.
  ⚠️ 本仓库尚未用真实项目验证过此技能，见下方"来源与验证状态"。本机最新版 IDA 可运行时优先用 `ida-reverse`
  （已有本仓库真机验证的踩坑记录）；本技能用于 IDA 不可运行、或用户明确要求 Ghidra 的场景。
---

# Ghidra 逆向分析技能（GhydraMCP）

## 来源与验证状态（必读）

> 来源：GhydraMCP 官方文档/README（<https://github.com/starsong-consulting/GhydraMCP>），
> 本仓库尚未实战验证，遇到新坑请补充到此文件。

本文档基于 2026-07-11 对 GhydraMCP 仓库（`starsong-consulting/GhydraMCP`，276 star，Apache 2.0，未
归档）README 和源码（`bridge_mcp_hydra.py`）的核实整理。本仓库目前没有一次真实逆向任务跑过这套工具
链。不像 `ida-reverse` 的"已知问题与反思"来自真机踩坑，这里列的都是文档/源码推断出的"可能坑"，
请在第一次真实使用后回填本文件、补充真实踩坑记录。

## 这是什么

GhydraMCP（`starsong-consulting/GhydraMCP`）把 Ghidra 通过一个 HATEOAS REST API 插件 + Python MCP
桥接脚本（`bridge_mcp_hydra.py`）+ 独立 CLI（`ghydra`）暴露给 AI 助手。它 fork 自
`LaurieWired/GhidraMCP`，新增了多实例支持、数据操作能力和 HATEOAS REST API。支持 Ghidra 11.x 和
12.x（两个版本分开打包 release，插件 `ghidraVersion` 必须和实际 Ghidra 版本精确匹配）。

官方 README 把 MCP 桥接层标注为"deprecating in favor of CLI"—— 独立 CLI `ghydra` 是更新、更推荐
的用法（同等能力 + 更好的输出格式化 + `--json` 模式），但桥接脚本仍可用，是否切换不是本文档要决
定的事，先如实记录两条路径都存在。

## 端口配置存疑（请在首次真机验证时确认）

`.kiro/settings/mcp.json` 里已有这一条注册（此前完全没有文档说明，属于"已经接入但未被记录"的状态）：

```json
"ghidra": {
  "url": "http://localhost:8765/mcp"
}
```

`kali/mcp-kali-example.json` 也有对应条目（见该文件 `ghidra` 键）。**但根据 GhydraMCP 官方 README
和 `bridge_mcp_hydra.py` 源码核实（2026-07-11 用 `gh api` 拉取 README 全文 + 用 GitHub code search
搜 `8765`/`streamable` 均零命中 + 直接 grep 源码得到下面两行）：**

```
bridge_mcp_hydra.py:31:  DEFAULT_GHIDRA_PORT = 8192
bridge_mcp_hydra.py:4261: mcp.run(transport="stdio")
```

也就是说：
- 官方桥接脚本固定走 **stdio** 传输，不是 HTTP/`url` 形式的 MCP 端点
- Ghidra 插件本身监听的默认端口是 **8192**（第一个打开的 CodeBrowser 用 8192，后续每开一个递增，
  多实例范围 8192-8447），不是 8765
- 官方文档/源码全文搜不到任何 "8765" 的引用

`http://localhost:8765/mcp` 这个配置，既不匹配 GhydraMCP 文档化的 Ghidra 实例端口范围（8192 起），
也不匹配它的 MCP 传输方式（stdio，不是 HTTP url）。可能的解释（未核实，按可能性排列）：

1. 有人在这台机器上手动跑了一个自定义 HTTP wrapper，把 stdio 桥接转成 HTTP，监听在 8765
2. 这条配置指向的其实是另一个同类 Ghidra-MCP 项目（不是 `starsong-consulting/GhydraMCP`）
3. 这条配置是占位/未验证，从未真正连通过

首次真机验证此技能时，请先确认 `.kiro/settings/mcp.json` 里这条 `ghidra` 到底连的是什么进程；连
不通就改用下面的官方 stdio 配置。

## 标准配置（官方 README，stdio 方式）

```json
{
  "mcpServers": {
    "ghydra": {
      "command": "uv",
      "args": ["run", "/ABSOLUTE_PATH_TO/bridge_mcp_hydra.py"],
      "env": { "GHIDRA_HYDRA_HOST": "localhost" }
    }
  }
}
```

需要先从 GhydraMCP release 下载匹配 Ghidra 版本的 "Complete" 包（含插件 zip + `bridge_mcp_hydra.py`），
把插件通过 Ghidra `File -> Install Extensions` 装好、重启 Ghidra、在 `File -> Configure -> Developer`
里确认插件已启用，插件才会在 8192 起监听。官方确认兼容 Claude Desktop、Claude Code、Cline，均走
stdio 传输。

## 安装步骤（官方文档整理，未在本仓库实战跑过）

前置条件：
- Ghidra 11.x 或 12.x（release 按版本分开打包，插件 `ghidraVersion` 必须和实际 Ghidra 版本完全匹配）
- Java 21（构建插件需要，推荐 Temurin 21）
- Python 3 + MCP SDK（跑桥接脚本需要）

```
1. 下载最新 release: https://github.com/starsong-consulting/GhydraMCP/releases
2. Ghidra 里 File -> Install Extensions -> "+" -> 选匹配版本的 Ghydra-*-ghidra<version>.zip
3. 重启 Ghidra，File -> Configure -> Developer 确认插件已启用
4. 打开一个 CodeBrowser，从控制台日志确认实际监听端口（第一个实例通常是 8192，后续递增）
5. 把上面的 MCP 配置写入 Claude 的 MCP 配置文件，/ABSOLUTE_PATH_TO/ 换成实际 bridge_mcp_hydra.py 路径
6. 也可以完全不经过 MCP 客户端，直接用独立 CLI：pip install -e . 后 ghydra instances list
```

## 核心工具面（按命名空间整理自官方 README）

GhydraMCP 没有像 `idapro_*` 那样的单一共享前缀，工具按资源类型分组命名空间。以下分组是官方文档里
的整理，**本仓库尚未连上真机确认 MCP 客户端里实际列出的工具名是否完全一致，真机连上后以实际列表
为准**：

- **实例管理** `instances_*`：`instances_list`（先用这个，自动发现本机实例）、`instances_discover`、
  `instances_register`、`instances_unregister`、`instances_use`、`instances_current`
- **函数分析** `functions_*`：`functions_list`、`functions_get`、`functions_decompile`
  （`style`/`syntax_tree`/`timeout` 参数；反编译不完整时响应带 `retry_recommended` 建议）、
  `functions_disassemble`、`functions_create`、`functions_rename`（`new_name` 带 `::` 会移动命名
  空间）、`functions_set_signature`、`functions_delete`、`functions_get_variables`、
  `functions_update_variable`、`functions_set_comment`
- **数据操作** `data_*`：`data_list`、`data_list_strings`、`data_create`、`data_rename`、
  `data_delete`、`data_set_type`（支持数组语法如 `uint64_t[8]`）
- **结构体** `structs_*`：`structs_list`、`structs_get`、`structs_create`、`structs_add_field`、
  `structs_update_field`、`structs_delete`
- **内存** `memory_*`：`memory_read`（支持 hex/raw 格式，overlay-aware）、`memory_write`
- **交叉引用** `xrefs_*`：`xrefs_list`（`to_addr`/`from_addr`/`type` 过滤）
- **分析** `analysis_*`：`analysis_run`、`analysis_status`、`analysis_get_callgraph`、
  `analysis_get_dataflow`
- **工程管理** `project_*`/`projects_*`/`programs_*`：`project_info`、`project_list_files`、
  `project_open_file`、`projects_list`、`projects_get`、`programs_list`、`programs_get`、
  `programs_delete`（⚠️ 官方文档标注这个和 program import 相关路由"可能返回 NOT_IMPLEMENTED，取决
  于插件端支持情况"）
- **数据类型** `datatypes_*`：`datatypes_list`、`datatypes_search`、`datatypes_create_struct`、
  `datatypes_create_enum`、`datatypes_create_union`
- **注释** `comments_*`：`comments_set`、`comments_get`
- **UI 辅助** `ui_*`：`ui_get_current_address`、`ui_get_current_function`
- **元数据** `classes_*`/`symbols_*`/`segments_*`/`namespaces_*`/`variables_*`：列举类/符号/内存
  段/命名空间/变量

典型工作流（官方 README Example Usage）：先 `instances_list` -> `instances_use` 选定实例 ->
`functions_decompile` 反编译关键函数 -> 需要时 `structs_create`/`structs_add_field` 建结构体 ->
`xrefs_list`/`analysis_get_callgraph` 做交叉引用和调用图 -> `comments_set`/`functions_rename` 记录
发现。命名空间用 `::` 表示（如 `MyClass::method`），裸名字只在全局命名空间里解析 —— 和 IDA 的命
名习惯不完全一样，混着用容易找不到符号。

## 已知限制（来自官方文档，非本仓库实测）

- MCP 桥接层官方标注"deprecating in favor of CLI"，长期看应该优先学 `ghydra` CLI 而不是死磕桥接
- 反编译大函数超时默认较高：CLI/桥接 HTTP 超时 900 秒（`GHYDRA_TIMEOUT`），反编译超时 1200 秒
  （`GHYDRA_DECOMP_TIMEOUT`）；反编译不完整时响应会带重试建议，不要把长时间无响应当成卡死（和
  `ida-reverse` 踩过的"带自动分析打开看起来像卡死"是同一类坑，值得留意）
- `programs_delete` 和 program import 相关路由官方标注"可能返回 NOT_IMPLEMENTED"，取决于插件端版本
- 插件 `ghidraVersion` 必须和实际安装的 Ghidra 版本精确匹配，装错版本会装不上（对应已关闭 issue
  #26 "extension 装不上 Ghidra 12.0.4"，具体原因未展开）
- 官方仓库 open issue #27 是 "Support for Ghidra Server"（多人协作场景），说明当前工具面主要面向
  单机单项目
- CLI 用法示例：`ghydra instances list`、`ghydra functions decompile --name main`、
  `ghydra data list-strings --filter "password"`、`ghydra memory read --address 0x401000 --length 64`、
  `ghydra --json functions list | jq '.result[].name'`；常用 flag：`--host`、`--port`、`--json`、
  `--no-color`

## Prompt 工程准则（参照 ida-reverse，但降级为建议，未经本仓库验证）

1. 和 `ida-reverse` 一样，先 `instances_list`/`functions_list` 做概况扫描，再针对性反编译，不要
   一上来对整个二进制反编译
2. 反编译/反汇编查询优先用函数名，找不到再退到地址
3. 遇到超时优先怀疑是"分析还在跑"而不是"服务挂了"，参考上面的超时数值调大 `timeout` 参数
4. 结构体/类型系统改动（`structs_*`/`datatypes_*`）是有状态写操作，建议先 `structs_get`/
   `datatypes_search` 确认目标不存在再创建，避免重复定义报错
5. 多实例场景一定先 `instances_current` 确认当前工作实例，避免改错文件

## 路由上下文

**上游入口**: `skills/SKILL.md`（总控）、`routing.md`
**上游备选**: `ida-reverse/`（本机最新版 IDA 可运行时优先，已有本仓库真机验证的踩坑记录）；`radare2/`
（都不可用时的开源备选）
**下游出口**:
- 需要动态验证 -> `reverse-engineering/tools-dynamic.md`
- 需要通用逆向方法论 -> `reverse-engineering/SKILL.md`

**同级关联模块**: `ida-reverse/`（商业方案，已验证）、`radare2/`（另一个开源备选）

---

## 待办：首次真机验证后回填

- [ ] 确认 `.kiro/settings/mcp.json` 里 8765 端口的 `ghidra` 条目到底连的是什么，更新或删除本文件
      的"端口配置存疑"章节
- [ ] 补充真实踩过的坑到"已知限制"章节（目前全部来自文档推断，没有一条来自本仓库真机经历）
- [ ] 确认 MCP 客户端里实际暴露的工具名前缀是否和上面列的一致
- [ ] 如果稳定跑通，参照 `ida-reverse/scripts/` 补充自己的 `scripts/`（目前没有，因为没有可复用
      的真机验证脚本）
