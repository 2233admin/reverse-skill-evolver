# 从 ARTEX 拿过来落到 evolver：可执行移植方案

> 日期：2026-10-17｜阶段：方案（未改代码）
> 配套：`ARTEX-PATTERN-COMPARISON.md`（模式综述）；本文是它的可执行版。
> 前置核实：`reverse_skill/routing.py`、`gates.py`、`cli.py`、`workflow_cli.py`、`scripts/run.py`、`skills/routing.json` 已实读；ARTEX 文件树（`main` @ `1e0ebcc`）与 `agent/chainskel/rev.md` 已实读。

## 0. 一个必须先纠正的认知

上一份对照文档说 ARTEX 的 chains 接入"已确认方向"，措辞暗示是计划。**实读文件树后确认：已经实现了。**

```
agent/chainskel/
  ad.md  app.md  meta.md  pivot.md  priv.md  pwn.md  recon.md  rev.md  web.md   ← 9 个 L3 骨架
  chainskel.go      ← 按意图注入骨架的路由代码
  meta_rules.go     ← L2 常驻铁律
  verifier.go / pivot.go
  chainskel_test.go / pivot_verifier_test.go
```

`rev.md` 实读内容是一行行「场景|判据|转向」的可执行判据，例如：

> 场景:stripped 找 main|判据:__libc_start_main 第一参数(rdi)即 main；静态链接时 _start 首个被当参数传的地址即 main|转向:失效→xref read/scanf 倒推业务核心

**这不是模式，是内容。** 这改变了两件事的优先级：可搬运的不仅有架构，还有**已经蒸馏好的逆向判据本体**——而 evolver 的核心资产恰恰就是逆向技能。

## 1. 移植点已全部核实（三处，均有现成挂载位）

| # | 拿什么 | 落到哪 | 挂载位是否现成 |
|---|---|---|---|
| P1 | L3 场景骨架（9 类） | `field-journal/` 或新 `chains/` 目录 | ✅ `routing.py:79-94` 已按 keyword 打分，可加成信号 |
| P2 | 按意图注入（不靠模型自觉） | `reverse_skill/routing.py` `build_plan` 返回值 | ✅ 已返回结构化 JSON（`:100-108`），CLI `route` 命令已存在 |
| P3 | 收尾强制自检 | `skills/evolution/` TraceCard | ✅ schema + `tracecard-validate` 已在 |

关键证据（`reverse_skill/routing.py:100-108`，实读）：

```python
return {"schema_version": 1, "status": "selected", "target_kind": target,
        "route": {"id": route["id"], "base_id": route["id"], "skill": route["primary_skill"]},
        "score": score, "signals": signals, "executed": False,
        "requires_capabilities": ..., "success_oracles": ...,
        "preflight": {...}}
```

**`build_plan` 已经返回完整结构化路由结果，`signals` 数组已经在记录命中理由。** 加 `journal_tags` 只是往这个既有 dict 里加一个键——不是新机制。

`macro_routes` 条目已有 `intent_keywords` / `target_kinds` / `success_oracles` 四个字段（`routing.json:30-56` 实读），加 `chain_tags` 是同族扩展。

## 2. 三个移植项，按确定性排序

### P1 ＋ P2：骨架内容 + 按路由注入（合并做，否则单做 P1 无意义）

**为什么必须合并**：只搬 9 个 md 进目录，等于又造一个"等模型来查"的 pull 资源——正是 ARTEX §2 批判的病。必须同时改路由，让命中时**自动**带出。

**改动清单**

1. **新增** `skills/chains/{rev,app,web,pwn,priv,ad,recon,pivot,meta}.md`
   - 来源：ARTEX `agent/chainskel/*.md`
   - **必须处理**：这些是 ARTEX 蒸馏产物，非上游公开语料。见 §4 许可。

2. **改** `skills/routing.json`：给每个 `macro_routes` 条目加 `chain_tags`
   ```json
   {"id": "ida-reverse", "chain_tags": ["rev"], ...}
   ```

3. **改** `reverse_skill/routing.py` `build_plan`：命中后在返回值加
   ```python
   "chain_files": [ ... 本路由 chain_tags 对应文件的包内相对路径 ... ]
   ```

4. **改** `reverse_skill/data/routing.json`——**这是硬约束**：`gates.py:178-180` 实读要求
   ```python
   checks.append({"name": "packaged_routes_match", "ok": canonical == packaged, ...})
   ```
   两个 routing.json 必须逐字节相等，否则 `gates all` 直接失败。

**验证**
```bash
python scripts/run.py --json route "脱壳 UPX 的 ELF"
python scripts/run.py gates all
python -m pytest tests/test_routing_contract.py tests/test_routing_benchmark.py -q
```
其中 `test_routing_contract.py` 已在仓库中存在（实读文件树确认），是这条改动的天然回归网。

**成本**：中等。改 3 个文件 + 新增 9 个内容文件 + 复制同步。

### P3：TraceCard 收尾自检（独立、最低成本、可先做）

**改动清单**

1. **改** `skills/evolution/schemas/trace-card.schema.json`：加 `self_check` 数组，元素含 `chain_ref`（本次路由带出的骨架条目）+ `result`（`consistent|contradicted|not_applicable`）+ `note`
2. **改** `reverse_skill/evolution.py` 的 `validate_trace_card`：当路由选择了带 `chain_tags` 的路线时，强制 `self_check` 非空

**验证**
```bash
python scripts/run.py tracecard-validate --input trace-card.json
python -m pytest tests/test_evolution_contracts.py tests/test_evolution_evidence.py -q
```

**成本**：低。但注意与 P1/P2 的耦合——只有先有了骨架，"自检对照什么"才有内容。可先做机制（schema + validator），内容留空数组，等 P1 落地再填。

**兼容**：`evolution/SKILL.md:120` 实读明确 "New TraceCards use schema version 2; retain older version-1 records unchanged."。加字段须走 v3 或向后兼容的可选字段，**不能改 v2 的必填集**。

## 3. 明确不做的

| 项 | 理由 |
|---|---|
| 搬 `chainskel.go` / `meta_rules.go` / `verifier.go` | Go 代码，本仓是 Python skill 包；逻辑用 `routing.py` 等价实现 |
| 搬 ARTEX 的 L1（引擎信号检测） | 依赖"流量全过录制代理、activity 每步落库"的数据底座，本仓无 |
| 引入 PG / 常驻服务 | 与"skill 包即装即用"（`run.py` 用完即走）矛盾 |
| 模式 D（forensic 参与控制流） | 被 `field-journal/forensic/README.md:5` 明文禁止，需先改设计决策 |

## 4. 动手前必须解决的两件事

### 4.1 许可（**这是真正的阻塞项**）

- evolver：MIT
- ARTEX：AGPL-3.0（二次开发自 Autumn-27/ARTEX）

`agent/chainskel/*.md` 是 **ARTEX 仓库内的文件**，不是上游独立语料。**直接复制这 9 个 md 进 MIT 仓库，是引入 AGPL 内容。**

三条可选路线，**必须你定**：

| 路线 | 做法 | 后果 |
|---|---|---|
| A. 只用结构不抄文本 | 读骨架的"场景→判据→转向"**分类法**，用 evolver 自己的 `field-journal/{validated}/` 与 `precedent-reverse.md` 重写 | 干净，但工作量大；且 evolver 已有 `seed-001`～`seed-017` 现成素材 |
| B. 联系作者授权 | 向 enwjx 请求双许可或以 MIT 兼容方式授权骨架文本 | 需等待；结果不确定 |
| C. 整体转 AGPL | evolver 改 AGPL-3.0 | 与现有 MIT 定位冲突，需你判断是否可接受 |

**我倾向 A**：evolver 的 `field-journal/` 已有 `seed-001_elf-packed-loader.md`、`seed-002_go-malware-stripped.md` 等 17 个种子条目，`precedent-reverse.md` 13.5KB——**自有素材足以支撑 9 类骨架中的大部分**，只是尚未按"场景|判据|转向"三段式蒸馏。这是"用自己的内容做同样的事"，零许可风险。

### 4.2 与 evolver 现有内容去重

`field-journal/` 已有内容与 `rev.md` 主题重叠（UPX、stripped、反调试、算法识别）。**动手前必须先比一遍**，否则会造出两套说法。这是 P1 的第一步，不是收尾工作。

## 5. 建议的执行顺序

```
0. 你定许可路线（A/B/C）          ← 阻塞点，不定不能动
1. 比对 field-journal 现有内容 vs 9 类骨架主题，出重叠表
2. P3 机制先落地（schema + validator，self_check 允许空）
3. P1 内容按路线 A 用自有素材蒸馏
4. P2 路由注入 + 双 routing.json 同步
5. gates all + pytest 全绿
```

第 2 步可与第 1 步并行——它不依赖内容。

## 6. 未验证的边界

- 未读 ARTEX 的 `chainskel.go`，其**实际注入机制**（何时按什么路由）是推断自设计文档 + 文件名，未从代码确认。
- 未读 `agent/chainskel/meta.md` 全文，L2 常驻铁律的规模与形态未核实。
- P2 的改动量估计基于 `build_plan` 返回结构，**未实际试改**；`gates.py:184` 的 `doc-facts` 检查会扫文档中出现的 `reverse-skill <cmd>`，新增命令名须同步 `SKILL.md`/`README.md` 描述，否则该项失败。
