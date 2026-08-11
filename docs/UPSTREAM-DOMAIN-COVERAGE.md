# 上游领域覆盖审计（Upstream Domain Coverage）

> 对比固定为 upstream `reverse-skill` main@50187aa6c8683c4767a763ae16686970d69c79c2（本机只读克隆：
> `C:\Users\Administrator\AppData\Local\Temp\reverse-skill-upstream-50187aa6c8`）。
> 本文是机器核对过的审计矩阵；**权威数据源是** `reverse_skill/data/upstream-route-crosswalk.json`，
> 本文的摘要数字与矩阵状态由 `reverse-skill gates routing-coherence` 与 crosswalk 逐项核对，防止漂移。

<!-- crosswalk-status: adopted=18 superseded=7 rejected=16 -->

## 结论摘要

| 状态 | 数量 | 说明 |
|---|---|---|
| adopted | 18 | 上游 R id 有稳定 route 直接承接（`mapped_route` 非空，无文档化分歧） |
| superseded | 7 | 有稳定 route 承接，但存在文档化分歧 / 非直接等价（见矩阵 note） |
| rejected | 16 | 无任何 route 承接（`mapped_route=null`），仅登记 coverage 缺口与拒绝理由 |

状态语义（与 crosswalk 一致）：
- **adopted** = 该上游域在本包有对应 route 且 benchmark 可断言等价。
- **superseded** = 有对应 route，但行为与上游不完全等价（如 radare2→native-binary 子工具链、
  protocol-reverse→protocol-pcap 双 route、attack-chain→active-security-assessment 等），
  差异已在矩阵 note 与 benchmark override 表（`scripts/regenerate_routing_benchmark.py`）显式记录。
- **rejected** = 薄清单模块（SKILL.md + references，无执行链），仅登记；**不宣称已实现工具能力**。

## 逐 R 矩阵（由 crosswalk 核对）

| R id | 上游模块 | 状态 | 本包承接（mapped_route → mapped_skill） | 缺口 / 拒绝理由 |
|---|---|---|---|---|
| R0 | reverse-engineering（通用） | superseded | `reverse-engineering/SKILL.md`（无独立 route id） | 本包路由按工件类型，不做泛逆向兜底；benchmark override 记录 native 类 hint → native-binary |
| R1 | apk-reverse | adopted | `apk-android` → `apk-reverse/SKILL.md` | 直接映射；无 android/apk 语境的 root 检测 hint 不路由（override） |
| R2 | mobile-reverse | adopted | `mobile-reverse` → `mobile-reverse/SKILL.md` | 直接映射；无移动语境的 jailbreak hint 不路由（override） |
| R3 | js-reverse | adopted | `js-browser-signature` → `js-reverse/SKILL.md` | 抓包类 hint 走 protocol-pcap（override 记录，属于既有语义） |
| R4 | reverse-engineering/dsl-vm-reverse | rejected | 无 | 上游仅 374 行方法论文档，无执行链；JS 侧 DSL-VM 可经 js 路由，但**不宣称**专用工具能力 |
| R5 | dotnet-reverse | rejected | 无 | 薄清单（SKILL.md + 3 references），无执行链 |
| R6 | ida-reverse | adopted | `native-binary` → `ida-reverse/SKILL.md` | 本包 IDA Python 主链（MCP/plugins/teams）完整 |
| R7 | radare2 | superseded | `native-binary`（`explicit_toolchain_requested`） | radare2 是 native-binary 的子工具链，无独立 route id |
| R8 | firmware-pentest | adopted | `firmware-pentest` → `firmware-pentest/SKILL.md` | 直接映射 |
| R9 | malware-analysis | adopted | `malware-analysis` → `malware-analysis/SKILL.md` | 直接映射；webshell/勒索裸词不路由（override） |
| R10 | attack-chain | superseded | `active-security-assessment` → `pentest-tools/SKILL.md` | attack-chain/SKILL.md 存在但不作独立 route id；无安全评估语境的攻击链 hint 不路由（override） |
| R11 | pentest-tools | adopted | `active-security-assessment` → `pentest-tools/SKILL.md` | 工具名裸词不路由，报告类走 docs-generator（override 记录） |
| R12 | api-security | adopted | `api-security` → `api-security/SKILL.md` | 直接映射；越权裸词不路由（override） |
| R13 | supply-chain-security | adopted | `supply-chain-security` → `supply-chain-security/SKILL.md` | 直接映射 |
| R14 | llm-security | adopted | `llm-security` → `llm-security/SKILL.md` | 直接映射；中文 LLM 越狱裸词不路由（override） |
| R15 | binary-diff | adopted | `patch-diff` → `binary-diff/SKILL.md` | 经 patch-diff route 承接 |
| R16 | patch-diff-exploit | adopted | `patch-diff` → `patch-diff-exploit/SKILL.md` | 经 patch-diff route 承接 |
| R17 | pwn-chain | adopted | `pwn-chain` → `pwn-chain/SKILL.md` | 直接映射 |
| R18 | edr-bypass-re | adopted | `edr-bypass-re` → `edr-bypass-re/SKILL.md` | 直接映射 |
| R19 | browser-automation | superseded | `js-browser-signature` → `js-reverse/SKILL.md` | browser-automation/SKILL.md 存在但不作独立 route id；playwright 裸词不路由（override） |
| R20 | docs-generator | adopted | `docs-generator` → `docs-generator/SKILL.md` | 直接映射 |
| R21 | protocol-reverse | superseded | `protocol-pcap` / `protocol-source-implementation` → `reverse-engineering/platforms.md` | 上游薄模块未迁入；协议/pcap 由既有双 route 承接 |
| R22 | ghidra-reverse | adopted | `ghidra-reverse` → `ghidra-reverse/SKILL.md` | 与 native-binary 的 tie-break 走 native-binary（override） |
| R23 | cloud-k8s | rejected | 无 | 薄清单（SKILL.md + 1 reference），无执行链；benchmark 断言 no_route |
| R24 | windows-ad | rejected | 无 | 薄清单；AD 域渗透未在路由表 |
| R25 | digital-forensics | rejected | 无 | 薄清单；取证未在路由表 |
| R26 | code-audit | rejected | 无 | 薄清单；SAST 未在路由表 |
| R27 | threat-hunting | rejected | 无（sigma 提示词经既有 malware-analysis 别名命中，文档化分歧） | 薄清单；威胁狩猎未在路由表 |
| R28 | ot-ics | rejected | 无 | 薄清单；工控未在路由表 |
| R29 | wifi-wireless | rejected | 无 | 薄清单；无线渗透未在路由表 |
| R30 | browser-extension-reverse | superseded | `js-browser-signature` → `js-reverse/SKILL.md` | 上游薄模块未迁入；含浏览器/扩展语境的 hint 经 JS 路由承接，chrome 裸词不路由（override） |
| R31 | macos-reverse | rejected | 无 | 薄清单；Mach-O 逆向未在路由表 |
| R32 | thick-client | rejected | 无（安全测试提示词经 active-security-assessment 命中，文档化分歧） | 薄清单；厚客户端未在路由表 |
| R33 | go-rust-reverse | superseded | `native-binary` → `ida-reverse/SKILL.md` | 上游薄模块未迁入；go/rust 二进制按工件类型走 native-binary，go malware 走 malware-analysis（override） |
| R34 | hardware-security | rejected | 无 | 薄清单；硬件调试接口未在路由表 |
| R35 | database-security | rejected | 无 | 薄清单；数据库安全未在路由表 |
| R36 | email-security | rejected | 无 | 薄清单；邮件/钓鱼未在路由表 |
| R37 | identity-federation | rejected | 无 | 薄清单；SAML/OIDC 未在路由表 |
| R38 | radio-sdr | rejected | 无 | 薄清单；RF/SDR 未在路由表 |
| R39 | diagram-generator | adopted | `diagram-generator` → `diagram-generator/SKILL.md` | 直接映射；mermaid 裸词不路由（override） |
| R40 | case-review | adopted | `case-review` → `case-review/SKILL.md` | **完整迁移**：Python 执行链（`reverse-skill case review`）+ 契约冻结 + 黑盒测试 |

## 迁移边界（诚实声明）

1. **只登记 ≠ 能力实现**：所有 `rejected` 模块只进入本矩阵与 crosswalk；不创建对应 SKILL.md、
   脚本或 route。benchmark 断言这些域 `expect_local == no_route`（除非提示词命中既有 route 别名）。
2. **无关键词兜底**：本批次未向上游 rejected 域添加任何新 keyword、fallback edge 或 priority 变更；
   benchmark override 表（39 条）逐条记录既有语义的例外，供审查。
3. **DSL-VM 特殊说明**：上游 `dsl-vm-reverse/SKILL.md` 是高质量方法论文档，但无执行链。
   保持登记状态，不宣称具备 DSL-VM 工具能力；后续若出现执行链再评估迁入。
4. **一致性由门禁保证**：`reverse-skill gates routing-coherence` 核对 crosswalk 状态分布、
   rejected 域无映射、mapped_skill 存在，并校验本文 `<!-- crosswalk-status -->` 标记与统计一致。

## 关联文件

- 路由 crosswalk（权威）：`reverse_skill/data/upstream-route-crosswalk.json`
- benchmark fixture：`tests/data/routing-benchmark.json`（163 用例，`expect_local` 由
  crosswalk + 审核 override 独立推导，不来自实现）
- 推导/审核脚本：`scripts/regenerate_routing_benchmark.py`（override 表是审查对象）
- 一致性门禁：`reverse-skill gates routing-coherence`
