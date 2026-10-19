# code-review：PR #62 vs `main`（第二轮全量复核）

标准来源：仓库无 `REVIEW.md`、无仓库级 release policy；核对 `RULES.md:153–164`（授权、脱敏日志、不确定结论标注）与已发布 beta.1 的既有惯例。

需求来源：`openspec/changes/release-beta2/proposal.md`、`tasks.md`、PR #62 维护者结尾评论；**无独立 SRS**（全仓 `*REVIEW.md` / `*SRS*` / `*requirement*` glob 零命中）。

改动范围：merge-base `05a884cbff4bbf636a4fc1d873ebb351435a0cce` → head `ce46ddc4901959b056c5f3cc2d5f7909274c44c7`；12 文件 / 4 提交 / +159 −14。全部 12 个文件逐行读过 head 版本，含 README_zh.md、CHANGELOG、openspec 三件与 tests。

## 标准符合性（1 条：挡合并 0／该修不挡 1／小意见 0）

### 1. 改动中的日期早于同一提交内引用的上游合并 — 该修不挡
- 位置：`CHANGELOG.md:5`（`## [1.2.0b2] - 2026-10-14`）对照 `BETA-VALIDATION.md:3`（基线 main `05a884cb` 由 PR #63 合并产生）。
- 依据：`RULES.md:164` 要求不确定或不准确的结论被标明；既有惯例是版本节日期与 release 内容来源对齐（beta.1 的 `## [1.2.0b1]` 与其 main 同批）。
- 发现：`05a884cb` 的提交时间是 2026-10-16T22:46Z，而 1.2.0b2 的 changelog 日期写 2026-10-14。日期早于它声称包含的代码。`gates.py:138` 只校验存在 `## [version]` 小节，不校验日期，所以 CI 不会拦。属发布元数据准确性问题，不影响运行。

## 需求符合性（1 条：挡合并 1／该修不挡 0／小意见 0）

### 1. 制品来源验收未与当前 head 闭环 — 挡合并
- 位置：`openspec/changes/release-beta2/tasks.md:4–5`；`BETA-VALIDATION.md:22–28`。
- 依据：`proposal.md:3`「artifacts from a precise source commit」；`proposal.md:9`「Build and verify a full source bundle ... from the release candidate」；PR 结尾评论 “Open before merge” 第一条。
- 发现：任务清单把制品构建与字节来源核验标为完成，但同一维护者评论陈述 rebase 后 **artifact provenance、checksum 与 Draft Release assets 未重新推导，仍对应 rebase 前候选**，待办仍写 `eeac396` 而 head 已是 `ce46ddc`。缺的是当前候选对应的验收闭环，不是已证制品内容错误。

## 功能缺陷（0 条：挡合并 0／该修不挡 0／小意见 0）

第二轮逐行读完后仍无确认功能缺陷。逐项核对结果：

| 新增声明 | 核对方式 | 结果 |
|---|---|---|
| `--version` 报 `1.2.0b2` | `pyproject.toml:7`、`reverse_skill/__init__.py:3`、`cli.py:154 click.version_option`、`test_cli.py:57` | 一致；`gates.py:113` 归一化把 `-beta.2` ↔ `b2` 等价，`opencli` 三类版本互不冲突 |
| `scripts/run.py --json gates all` 可用 | `scripts/run.py:24,74–81` 透传 argv，`cli.py:29,166` 注册 `gates` | 命令存在，参数形式与实现相符 |
| swarm 三调用示例 | `swarm_cli.py:17–27`：`--goal/--context/--output/--max-calls/--max-tasks/--max-parallel/--timeout/--json` | 所有旗标存在，`--max-calls` 下界 3 与示例一致 |
| `asr list` 默认 audited、排除 MCP | `asr_cli.py:25,39,46`（`--sort-by audited`） | 相符 |
| issue #55 integration evidence 链接 | `GET issues/comments/6162700316` → 200，内容为该批合并验收 | 链接有效且内容相符 |
| `packages/`、`SHA256SUMS.txt` 布局 | beta.1 release 资产列表（zip/wheel/tar.gz/jar/SHA256SUMS 五件） | 与文档描述同构；beta.2 Draft 资产本次未取到（见待核实） |

## 待核实

- Draft Release assets 是否仍存在、内容是否对应 `ce46ddc`：API `releases?per_page=10` 只返回已发布 release（beta.1、2.0.0-beta.4…），未列出 `untagged-5460d6...`；单条 untagged 读取返回 404。故**不能**断言 asset 缺失或存在，只能确认当前无公开 phase 的外部证据。这是需求第 1 条的未闭合部分。
- `README.md:157,166,171,180` 的 `v1.2.0-beta.2` release 与 blob 链接：tag 未发布即不可解析。若在打 tag 前合并，main 的 “testing release” 入口短期指向 404。属时序耦合，未计为缺陷。

## 与第一轮的差异

第一轮只读到 diff 的约一半（README_zh.md、CHANGELOG 正文、openspec 三件、tests 其余未逐行核），漏掉了标准节那条 changelog 日期问题；需求节与功能节结论不变。无 SRS 这一条与第一轮相同。

待主人回答：这次是否有独立 SRS 或批准要求？
