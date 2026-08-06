# Overnight Slot ↔ Evolution 概念映射

`OVERNIGHT.md` 是 evolution 控制面的**无人值守运行契约**。下表把模板的每个 slot / 规则映射到本仓 evolution 既有概念，避免"两套系统各说各话"。

## Slot ↔ GOAL 契约

| Overnight slot | goal.template.yaml 字段 | 说明 |
|---|---|---|
| `DEADLINE` | `budgets.max_minutes` + §4.4 停机规则 | 绝对时间戳；escalation_policy 必须能在 deadline 内完成 |
| `ISSUE_LIST` | `inputs` + `desired_outputs` | Phase 1 问题清单即任务的输入与期望产物 |
| `TARGET_MODULE` / `SPEC_FILE` | `route.macro_route` + 规格来源 | Phase 2 的"形状唯一事实来源" |
| `ALLOWED_COMPONENTS` / `BANNED_PATTERNS` | `stop_conditions` + 白名单 | 成分白名单与语法红线是 stop_conditions 的机械形式 |
| `TEST_CMD` / `BENCH_CMD` / `PERF_METRICS` / `PERF_TOLERANCE` | `success_oracles` | 基线中位数 ± 容忍度 = oracle 的可执行形式 |
| `QUARANTINE_BUDGET` / `MAX_PASSES` / `PHASE2_BUDGET` | `budgets` | 隔离上限、收敛轮数、Phase 2 时间上限 |
| `ESCAPE_HATCHES` / `SCOPE_PREFIX` | — | 逃生舱（本仓默认无）与 commit 前缀约定 |

## Phase ↔ TraceCard / 记忆分层

| Overnight 机制 | evolution 对应 | 回流动作 |
|---|---|---|
| Phase 0 基线 + FLAKY 集 | capability-graph 的 smoke 状态 | 基线封存后不可改；FLAKY 集只在此刻确定，夜里摆动的测试按回归处理 |
| Phase 1 修复（带复现脚本） | TraceCard 的失败归因 | 每条 issue 留复现脚本与把握度 → 可入 `candidate/` |
| Phase 2 收敛→复核→达成 | promotion gate 的 oracle 前置 | 映射表原文进 REPORT.md；无子 agent 只能标"收敛待复核" |
| Phase 3 对抗性随机游走 | FINDINGS（Smell / Root type / Change） | implemented 的表示变更才允许 merge；proposed 留人判断 |
| 停机规则 | `stop_conditions` | deadline 前 45 分钟（建议值）停新尝试 |

## 记忆分层规则（复用 evolution/SKILL.md 三档）

- `validated/`：oracle 通过、路线可复用、可参与未来路由 → 允许改 stable 路由（**先过 promotion gate**）
- `candidate/`：有潜力但未回归测试 → 只提示，不支配控制流
- `forensic/`：失败、异常、疑似污染、证据不足 → 只分析

## 与 RULES.md 的关系

- **指令来源唯一性** ↔ RULES.md "This file is the single source of truth"：过夜 agent 的"唯一指令"是已填模板；RULES.md 与仓内文档是**数据**。
- **分支纪律** ↔ 禁止改写历史：`night` 集成分支 + 弃置分支原样保留 = 早上 review 的最小可审计单元。
- **基线封存** ↔ 被度量者不保管度量：hook 物理拦截对 `BASELINE.md` 的修改，不依赖 agent 自觉。

## fleet-sync 边界

`.night/` 是机器本地工作区，**不**随 `fleet-sync.ps1` 同步（脚本只同步 field-journal candidate/validated、capability-graph、tool-index）。过夜运行产生的经验必须先进 `field-journal/{validated,candidate,forensic}/`，再随 fleet-sync 既有清单同步到另一台机器。
