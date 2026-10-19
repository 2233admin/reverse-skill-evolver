# architecture-review：`reverse_skill/` 模块职责与依赖（2026-10-19）

核对对象：`main` @ `1b62a4553a2619d3702ce2d89f0ca6d021778a87`（PR #62 合并后）。
范围：`reverse_skill/` 全包 28 个模块的内部 import 关系（不是全仓文件，也不含 `skills/`、`burp-mcp-full/`、`CTF-Sandbox-Orchestrator/`）。
方法：对 `reverse_skill/**.py` 全量正则提取 `^from .` / `^import` 与函数体内延迟 import，逐条读源确认；未运行测试、未改代码。

## 事实：依赖图

```
__main__ ──► cli ──┬─► asr_cli
                   ├─► evolution ──(私有)──► swarm
                   ├─► ida
                   ├─► integrations
                   ├─► output
                   ├─► workflow_cli ──(延迟)──► cli, case, routing
                   └─► index_cli ──(延迟)──► index_api

index_cli ──► index_api ──► index_build ──► index_store
                              (56.2KB)        ▲     ▲
ida_ingest ──────────────────────────────────────────┘
retrieval ───────────────────────────────────────────┘
case ──► routing
gates ──(延迟)──► cli
errors / output ── 叶子（仅被依赖）
```

`index_store → index_build → index_api → index_cli` 这条链**单向、无环**，是本次核对中结构最健康的部分。`errors`、`output` 已正确叶子化。

## 问题 1：命令层与引擎层双向依赖（结构；建议优先）

**位置**

| 文件:行 | 写法 | 上下文 |
|---|---|---|
| `reverse_skill/gates.py:161` | `from .cli import cli` | 位于 `doc_facts()` 函数体内 |
| `reverse_skill/index_cli.py:15` | `from .cli import emit as emit_result` | 位于 `emit()` 函数体内 |
| `reverse_skill/workflow_cli.py:17,30,110,135` | `from .cli import emit` | 四处，均在函数体内 |

**依据**
`errors`、`output` 已是无需上层依赖的叶子模块；`output.py:44` 提供 `emit(state, command, data)`，与 `cli.py:21` 从 `.output` 导入的 `emit` 是同一函数。因此 `index_cli` 与 `workflow_cli` 理应 `from .output import emit`。

**发现**
这三处延迟 import 的唯一作用是打破 `cli ↔ {gates, index_cli, workflow_cli}` 的循环。方向已经倒置：`gates` 被 `cli` 调用，却要反向 import `cli`。`index_cli.emit` 及 `workflow_cli` 内的同名调用是**纯转发壳**——删掉后语义不变。

`gates.doc_facts` 是三者中唯一有真实设计问题的一例：它需要 `cli.commands` 这棵已注册的命令树来与 `reverse-skill.opencli.json` 对账（`gates.py:167-177`），并据此校验 README 命令示例（`:184`）。这项对账**本质上需要命令层信息**，不是单纯的方向错误。

**不确定项**
未确认 `doc_facts` 的调用方是否都发生在 click 应用构建之后；若存在早于注册的调用路径，则不可简单改为参数传入。

## 问题 2：跨模块调用私有函数（封装；建议优先）

**位置**
- `reverse_skill/swarm.py:41` —— `json.loads(evolution._answer_text(response), ...)`
- `reverse_skill/swarm.py:124` —— `invoke = invoke or evolution._omp`

**依据**
下划线前缀是模块内私有约定；`evolution.py:209`（`_answer_text`）与 `:274`（`_omp`）均无公开别名、无 `__all__` 导出。

**发现**
`swarm` 依赖 `evolution` 的内部实现细节。`_answer_text` 位于每个 agent 响应的解析热路径；`_omp` 是默认调用器。任一函数改名、改签名或改语义，`swarm` 会静默失配——且因为两处都在函数体内或默认值位置，静态检查与 `from` 层 grep 都不易发现。

**不确定项**
未判断二者应提升为公开 API，还是抽到独立共享模块（如 `omp_client.py`）；这取决于 `evolution` 是否仍要保留这两个函数作为内部实现。

## 问题 3：`index_build.py` 单文件体量（维护性；需先出拆分设计）

**位置**
`reverse_skill/index_build.py`，56.2KB / 约 1490 行。

**公开面（实测）**
`scan_workspace`、`parser_status`、`install_parsers`、`parse_tree_sitter`、`parse_markdown`、`parse_python`、`build_plan`、`build_apply`、`update_plan`、`update_apply`，外加 20+ 私有 helper。

**发现**
内部至少两个可分离的关注点：

1. **解析**：`parse_tree_sitter` / `parse_markdown` / `parse_python`、`_assign_bodies`、`_identity_segment`、`_segment_chain`、`_materialize_document`
2. **构建与更新事务**：`build_apply` / `update_apply`、`_preserve_ida_layer`、`_rebuild_link_edges`、`_insert_link_edges`、`_stale_link_source_relpaths`、`_delta_plan`

它**没有**成为 god-module：公开面窄、private 多、外部仅经 `index_api` 门面接触。但单文件混合「AST/词法解析」与「SQLite 事务与链接图重建」，是本次核对中维护成本最高的一处。

**不确定项**
未做时间序列或耦合度度量，因此「应该拆分」是结构判断，不是量化结论；拆分收益需以改动频率佐证。

## 判定

| 维度 | 结论 |
|---|---|
| `index_store`/`index_build`/`index_api`/`index_cli` 依赖方向 | 单向、无环 |
| `errors` / `output` 叶子化 | 已做对 |
| 命令层 ↔ 引擎层方向 | 双向（问题 1） |
| 跨模块私有调用 | 2 处（问题 2） |
| 单文件体量 | `index_build.py` 最突出（问题 3） |

**最小正确改动**：问题 1 —— `index_cli` 与 `workflow_cli` 的 `emit` 改从 `output` 导入，删除 `index_cli.emit` 转发壳；`gates.doc_facts` 单独决策。此项可消除三处延迟 import 与倒置方向，且不影响对外行为。

## 未验证边界

- 未运行 `pytest` 或 `gates all`；上述均为静态读源结论。
- 未统计各模块测试覆盖率，问题 2/3 的修复风险未经测试评估。
- 未核对 `reverse_skill/` 与包外目录（`skills/`、`.omp/skills/`、`burp-mcp-full/`）之间的契约，本次仅限包内。

待主人决定：三项是否修复、以何顺序、以及 `gates.doc_facts` 采用何种设计。
