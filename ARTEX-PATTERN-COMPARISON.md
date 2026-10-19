# ARTEX 可借鉴模式 → reverse-skill-evolver 对照

> 阶段：C（只读对照，未动任何一侧代码）
> 日期：2026-10-17
> 对象：`enwjx/artex-ymh`（ARTEX 二次开发版，AGPL-3.0）↔ `reverse-skill-evolver`（本仓）
> 依据：ARTEX `FUTURE.md`、`CHAINS-INTEGRATION-DESIGN.md`、`HONEYPOT-DETECTION-DESIGN.md`（均实读全文）；本仓 `skills/evolution/`、`skills/field-journal/`、`skills/overnight-run/`（均实读）。

## 0. 结论

**可移植的是四种"执行模型"，不是代码。** ARTEX 是 Go + PostgreSQL 的常驻服务；本仓是 Python + Markdown 的 skill 包，客户端驱动。两者领域重叠（渗透/逆向），但形态不重叠，**没有任何模块可以复用**。

真正值得对照的是 ARTEX 已经想清楚、本仓尚未解决的四件事：

| # | ARTEX 的机制 | 本仓现状 | 结论 |
|---|---|---|---|
| 1 | **按执行者拆分知识**（确定性信号写代码 / 纪律常驻 / 场景按需注入 / 全书 pull 兜底） | 单一 `field-journal` 层级 + `routing.json` | **最有价值，可移植** |
| 2 | **不靠模型自觉的触发**（L1 用引擎信号，100% 触发） | 全靠模型读 SKILL.md 后自行决定 | **部分可移植**（有形态差异） |
| 3 | **收尾强制自检**（Settlement 环节挂 Q 清单） | TraceCard 有 unknowns/oracle，但无强制自检动作 | **可直接移植**，成本低 |
| 4 | **置信度分级驱动处置**（双命中才封锁，单信号只降级） | 三档记忆分层已有，但不驱动行为差异 | **已有雏形，缺"处置"这一环** |

## 1. 差距的准确位置

### 1.1 ARTEX 的核心洞见（`CHAINS-INTEGRATION-DESIGN.md` §2）

ARTEX 否掉了"把知识做成 skill"的思路，理由是：

> skill 是 pull 模式——模型要先想到"我该去查"，链才进上下文。……走在错误判据上的模型不觉得需要查。纯 skills 化 = 把知识库的病按比例缩小后保留。

同一份文档给出评价标准（§1）：

> 1. **不靠模型自觉**——该出现时必须出现；
> 2. **在对的时刻出现**；
> 3. **成本固定可预期**。

**这是本仓当前的真实短板。** `SKILL.md:24-42` 要求模型自行读取 `routing.json`、选定模块、执行 workflow；`skills/evolution/SKILL.md:14-22` 的 `ACTION REQUIRED` 全是"模型应当做"。而 `field-journal/_index.md:3-5` 的复用承诺同样依赖模型：

> 新任务开始前先查阅本索引，复用已有经验，避免重复踩坑。

即：**本仓的复用链条整体建立在模型自觉之上**，与 ARTEX 明确批判的模式同构。

这一判断在本仓内部有直接印证。`skills/ROUTER.md:14-18` 用的是命令式契约而非建议：

> ## CRITICAL: 路由执行契约（必须立即执行）
> 读完本文件后，不允许只回复"已读/已理解"。必须按顺序执行：

以及 `ROUTER.md:138`：

> 新任务开始前先查索引和先例，复用已有经验

**本仓已经意识到"模型不会自觉做"，所以用大字契约去压——但契约仍是提示词，执行者仍是模型。** 这正是 ARTEX §2 那句话的本地版本：写在提示词里执行者是模型（随状态漂移）。ARTEX 的解法是把它挪到代码里；本仓可用的等价物是 CLI 门禁（见模式 B）。

### 1.2 但差距没有 ARTEX 说的那么绝对

本仓有两处**不靠自觉**的机械保证，ARTEX 文档未覆盖：

- `overnight-run/references/evolver-mapping.md:37`：**"基线封存 ↔ 被度量者不保管度量：hook 物理拦截对 `BASELINE.md` 的修改，不依赖 agent 自觉。"** —— 这正是 ARTEX §2 要的"写在代码里执行者是平台"。
- `overnight-run/references/evolver-mapping.md:36`：`night` 集成分支 + 弃置分支原样保留 = 最小可审计单元。

（注：`BASELINE.md` 与 `QUARANTINE.md` 是 overnight 运行期产物，`new-overnight.ps1` 在目标仓库中创建，不随本包预置。）

所以本仓已有一个**机械强制**的先例（pre-commit hook 拦基线改写），只是没有推广到知识注入这一层。

## 2. 四种可移植模式

### 模式 A：知识按执行者分层（对应 ARTEX 四层）

ARTEX 的四层（`CHAINS-INTEGRATION-DESIGN.md` §3）：

| 层 | 内容 | 形态 | 触发 | 每轮成本 |
|---|---|---|---|---|
| L1 监测 | 确定性判据（同质响应阈值、固定延迟、字节级相同） | Go 代码 | 引擎信号，100% | ~0 |
| L2 纪律 | meta-\* 蒸馏铁律，2-3KB | planner system 常驻 | 永远在场 | 固定 |
| L3 场景 | 技术链骨架 2-4KB/类 | 按意图条件注入 worker system | 代码路由 | 仅相关意图 |
| L4 全书 | 62 篇原文 | 1 个 skill + reference | 模型主动 | 按需 |

**映射到本仓**（落地构件逐条对应）：

| ARTEX 层 | 本仓现有对应物 | 差距 |
|---|---|---|
| L1 | 无 | 本仓无引擎；最接近的是 `scripts/run.py` 的 CLI 层与 `gates` 子命令 |
| L2 | `skills/ROUTER.md`（包内共享约定） | 已是常驻，但内容偏"约定"不偏"判据铁律" |
| L3 | `field-journal/{validated}/` + `precedent-*.md` | **有内容，无按意图条件注入机制** |
| L4 | `skills/field-journal/` 整包 | 已正确处于 pull 位置 ✓ |

**可落地动作**：把 `field-journal/validated/` 与 `precedent-*.md` 从"等模型来查"改为"按路由结果注入"。本仓 `routing.json` 已是机器路由，**结果里带上 `journal_tags` 即可让 `scripts/run.py route` 输出相关经验条目**——这与 ARTEX §3 "L3 的路由用平台已有的结构化数据……不需要模型判断"是同一手法。

成本估算：`routing.json` 加字段 + `run.py route` 输出附带条目。不动文献本身。

### 模式 B：触发不靠模型自觉

ARTEX 的判断：确定性判据写在提示词里执行者是模型（随状态漂移），写在代码里执行者是平台（100% 触发）。

**本仓的可行形态不是"引擎信号"，而是 CLI 门禁。** 本仓已有 `gates` 子命令族（`SKILL.md:77-79`：`gates all` 查版本/描述/路由路径，`gates leak-scan` 扫脱敏）。把"同类经验已存在"做成路由输出的一部分，就是把 L1 的"该出现时必须出现"用本仓语言实现。

**不可移植部分**：ARTEX 的 L1 依赖"流量全程过录制代理、activity 每步落库"这一数据底座。本仓无此底座，也不需要有——本仓是 skill 包不是平台。

### 模式 C：收尾强制自检（最低成本、最确定）

ARTEX（`CHAINS-INTEGRATION-DESIGN.md` §4）：

> 在 worker 收尾/写回环节加一道固定程序：本意图结束前，对照 L3 骨架里的 Q 清单自检一遍。这让"反问"从知识变成工作流里的强制动作。

**本仓对应**：`skills/evolution/SKILL.md:99-103` 已要求每个 oracle 记录 `status` + `evidence_refs`，且 `validated` 与 `promotion_candidate: true` 要求全部 oracle 通过。**已有验证骨架，缺"自检清单"这一动作**。

可落地动作：在 TraceCard schema 收尾处加一个必填的 `self_check` 数组（对照本次路由对应的经验条目逐条问"我的结果是否与已验证经验矛盾"）。落在 `skills/evolution/schemas/trace-card.schema.json`，由 `tracecard-validate` 强制。

成本：schema 加字段 + validator 加一条规则。**不依赖任何 ARTEX 代码。**

### 模式 D：置信度分级驱动处置

ARTEX（`HONEYPOT-DETECTION-DESIGN.md` §处置策略）：

| 置信度 | 处置 |
|---|---|
| 确认（双信号命中） | planner 停止派意图；guard deny |
| 疑似（单信号） | 降级交互，只读探测 |
| 全阴性 | **不能判定"非蜜罐"** |

关键设计原则：**"漏报是常态，误报是事故"** —— 所以只有双信号才升级为封锁动作。

**本仓已有对应雏形但不驱动行为**。`evolver-mapping.md:29-31` 定义了记忆三档，且 `evolution/SKILL.md:104` 明确"may remain empty when no evidence was produced"。但三档目前**只决定"是否能改 stable 路由"**，不决定"下次遇到同类任务时执行强度"。

可落地动作：让 `forensic/` 条目在下一次同类路由中成为**明确的降级信号**（如"此路线在 X 场景曾失败，建议先做只读验证"）。这与 ARTEX 的处置分级同构，且本仓 `field-journal/forensic/` 已有内容积累。

**但这条与现有明文约束冲突，实施前必须先改约束。** `skills/field-journal/forensic/README.md:5` 写死：

> Forensic entries are analysis material only. They must not participate in automatic control-flow decisions.

而 `evolver-mapping.md:31` 同样表述为"只分析"。**模式 D 的实质就是让 forensic 参与控制流**，因此它不是加字段，而是要**推翻一条已确立的设计决策**。这属于授权方决策，不在本对照的范围内——本文只标记冲突，不主张变更。

## 3. 本仓已有、ARTEX 尚未实现的（反向对照）

ARTEX `FUTURE.md §9` 结论：

> 真正的大头在 **engine↔worker 控制面协议** 和 **隧道/流量/文件三面写死的 loopback 假设**……建议在当前平台（单机版）完成靶场验证、功能稳定后再启动 M0。

即：**ARTEX 的分布式改造"评估完成，未动工"**。而本仓的跨机能力已落地：

- `fleet-sync.ps1`（`evolver-mapping.md:39-41`）：同步 field-journal candidate/validated、capability-graph、tool-index，且明确 `.night/` 机器本地不同步；
- 平台差异已文档化：`RULES.md`（Windows）vs `RULES-kali.md`（Kali）；
- `evolution/SKILL.md:206-210`：fleet-sync 采用**碰撞安全的增量合并**——"只复制目标端尚不存在的文件，从不覆盖、从不删除，冲突报告而非自动解决"。

**这是本仓更成熟的一侧**，反向有借鉴价值。但注意：ARTEX 的分布式是"一控制面 + N 执行节点（含诱饵角色）"，本仓的跨机是"两台机器各自跑、经验合并"。**不是一个东西**，不要混同。

## 4. 明确排除的路径

| 路径 | 排除理由 |
|---|---|
| 引入 ARTEX 的 Go 服务作为执行后端 | 本仓无服务层，跨语言跨领域；且会把完整的攻击平台代码带入 skill 包 |
| 移植 ARTEX 的 `agent/*.go` | 同上；且 AGPL-3.0 代码进入本仓会改变许可状态（见 §5） |
| 采用 PG 双图 | 本仓无数据库依赖，`field-journal` 是文件层；引入 PG 与"skill 包即装即用"矛盾 |
| 照抄 ARTEX 的 L1 引擎信号检测 | 本仓无流量录制底座；强行实现是本末倒置 |

## 5. 约束（写代码前必须守的）

1. **许可**。本仓 MIT，ARTEX AGPL-3.0。**方向是安全的**（MIT 内容进 AGPL 项目无义务），但**反向不成立**：抄入 ARTEX 实代码会使本仓受 AGPL 传染。本对照只提炼设计模式，不引用其代码。若未来真要引入，必须先解决许可，不能"先合了再说"。
2. **安全与合规叙事**。本仓在 `SKILL.md:64-71` 把授权边界做成了机制：`case init` 显式记录 scope 与 network mode 且"does not execute an analysis or grant authorization"；`gates leak-scan` 做脱敏。ARTEX 是全流程自主攻击平台。**任何"自主化"改造都必须保持在本仓现有授权边界内**——即自主的是"证据整理与经验回流"，不是"未经授权扩大目标范围"。这条是硬线。
3. **不引入常驻进程**。本仓 `scripts/run.py` 的定位是"首次运行在用户缓存中准备私有环境"，用完即走。任何借鉴都不能要求用户跑一个后台服务。

## 6. 建议的下一步（未执行）

按"确定性 × 成本"排序，三件互不依赖：

1. **模式 C（推荐先做）**：`trace-card.schema.json` 加 `self_check`，validator 加规则。改动局限在 `skills/evolution/`，可被 `tracecard-validate` 机械验证，且是纯增量（旧 v1 卡不变）。
2. **模式 A**：`routing.json` 加 `journal_tags`，`run.py route` 输出附带 `validated/` 命中的经验条目路径。需要先确认 `route` 的实际输出结构。
3. **模式 D**：把 `forensic/` 从"只分析"升级为"下次同类路由的显式降级提示"。需要先统计 `forensic/` 现有条目的场景分布。

三件都不需要网络、不需要改任何稳定路由、不触碰许可边界。

---

## 附：本文引用的 ARTEX 文档状态

| 文档 | 状态（原文标注） |
|---|---|
| `FUTURE.md` | 评估完成，未动工。评估日期 2026-09-15 |
| `CHAINS-INTEGRATION-DESIGN.md` | 已确认方向（2026-09-12 与作者讨论定稿） |
| `HONEYPOT-DETECTION-DESIGN.md` | 调研完成 + 设计评估，未动工。2026-09-18 |

即：ARTEX 侧这三份文档中，**只有 chains 接入是已确认方向的计划，另外两份是未动工的评估**。引用时不应把评估当作已实现能力。
