# 参赛体检报告 — reverse-skill-evolver / CTF-Sandbox-Orchestrator

日期：2026-10-20 · 基线：`main@b7e8e36` · 用途：CTF 夺旗赛 + AWD 攻防演练

## 结论

**痛点是准确的：能跑但解不出题。** 但**原因不是"设计不好"**——实测后修正为：**设计是好的，部署是空的。**

| 层次 | 状态 | 证据 |
|---|---|---|
| **架构** | ✅ **优秀** | 单一入口、43 个专项技能、48 个 CLI 命令、21 条路由 |
| **路由** | ✅ **完整** | 21/21 路由带 `success_oracles`；16 条带 `fallback_edges` |
| **降级设计** | ✅ **已考虑** | `"all_supported_ida_backends_unavailable" → radare2` |
| **工具部署** | ❌ **空** | 28 缺 15，**无任何反汇编器** |
| **swarm 工具权限** | ❌ **被禁** | `evolution.py:270-277` 带 `--no-tools` |
| **解题入口** | ⚠️ 设计定位如此 | 无 `solve`；`route` 明写不执行 |

**一句话：路由知道该走哪条路、失败该降级到哪、怎么算成功——但那两条路都没有铺。**

按杠杆排序：

| 优先级 | 缺口 | 证据 | 修复成本 |
|---|---|---|---|
| **P0** | **降级链的目标也没装**（radare2 6/6 缺、Ghidra 缺） | 实测工具检测 | **跑一次 bootstrap**（已实测链路可用） |
| **P0** | swarm 里的模型被禁止用工具 | `evolution.py:270-277` | 改一个标志位（需权衡安全） |
| **P1** | 无"解题"入口，`route` 明确不执行 | `workflow_cli.py:17-22`、`routing.py:120-129` | 需设计（但可能不该做，见下） |
| **P2** | 竞赛技能只列品类，不给具体命令 | 12 个技能全文读证 | 长期；**影响有限**（见 P2 修正） |
| **P3** | 1 个富参照文件未接线 | `competition-web-runtime/SKILL.md:41-57` | 一行 |

**核心判断：P0 两项才是"解不出题"的直接原因，且都可在数小时内修好。** 工具装上后，已有的路由 + 降级 + 判据设计**立刻开始发挥作用**——这正是这个包设计得好、却因部署缺失而未兑现的地方。

---

## P0-1：工具链缺失 — 28 缺 15，无任何反汇编器

### 实测方法

调用包自身的工具发现逻辑（非推测）：

```powershell
. skills\scripts\lib\ToolDiscovery.ps1
$reports = @(Get-ReverseToolReport)
```

### 实测结果

```
TOTAL tools defined : 28
AVAILABLE           : 13
MISSING             : 15
```

**可用的 13 个：**

| 工具 | 归属技能 | 性质 |
|---|---|---|
| `java`, `keytool` | apk-reverse | 运行时 |
| `frida`, `frida-ps`, `frida-ls-devices` | apk-reverse | **动态注入（唯一真逆向工具）** |
| `python`, `pip` | reverse-engineering | 运行时 |
| `node`, `npx`, `jshookmcp` | js-reverse | JS 运行时 |
| `agent-browser`, `playwright` | browser-automation | 浏览器自动化 |
| `nmap` | pentest-tools | 网络扫描 |

**缺失的 15 个，全部是核心解题工具：**

| 技能 | 缺失 | 后果 |
|---|---|---|
| `ida-reverse` | `idalib-mcp`, `idapro` | **IDA 全线不可用** |
| `radare2` | `r2`, `rabin2`, `rasm2`, `radiff2`, `rahash2`, `rax2` | **整族缺失（6/6）** |
| `apk-reverse` | `jadx`, `apktool`, `adb`, `apksigner`, `zipalign` | **安卓题全废** |
| `reverse-engineering` | `analyzeHeadless` | **Ghidra 不可用** |
| `pentest-tools` | `proxycat` | 代理缺失 |

### 为什么这直接导致"解不出题"

**这台机器上没有反汇编器、没有反编译器、没有调试器。**

框架（40 个技能 + `RULES.md`）反复要求模型"用 IDA 分析"、"用 radare2 反汇编"。模型照做，但工具不存在 → 只能凭训练知识**硬猜**二进制结构。这不是提示词问题，是**工具链真空**。

### 可自动修复的范围

`skills/scripts/bootstrap-manifest.json` 定义了 18 项能力的自动安装：

| 工具 | bootstrapKind | 可否自动装 |
|---|---|---|
| `r2` | `github-release-zip`（`radareorg/radare2`） | **可以** |
| `jadx` | `github-release-zip`（`skylot/jadx`） | **可以** |
| `apktool` | `github-release-jar-wrapper` | **可以** |
| `idalib-mcp` / `idapro` | **不在 manifest** | **不可**（需商业许可） |

`bootstrap-reverse.ps1`（571 行）是完整实现：`Ensure-GitHubZipInstall`（`:139`）、winget 装运行时（`:33`）、PATH 刷新、失败即抛。

**估计：15 个缺失工具中至少 12 个（r2 全家 + jadx 全家 + apksigner 等）跑一次 bootstrap 即可装上。** IDA 相关的 2 个需要另想办法（Ghidra headless 是免费替代，但 `analyzeHeadless` 也缺）。

### 安装链路已实测（不只是读清单）

我实查了 `r2` 的完整安装前提，**全部成立**：

```
tag_name : 6.2.4
assets   : 23
regex    : ^radare2-.*-w64\.zip$
MATCHED  : 1
   radare2-6.2.4-w64.zip  13.0 MB
```

- 清单定义齐全（`bootstrapKind: github-release-zip`、`canAutoInstall: true`）
- GitHub 最新 release 可达
- **资产正则精确命中 1 个**，版本 `6.2.4`，13.0 MB

**所以"跑 bootstrap 能装上 r2"是已验证的，不是推测。**

**注意：`bootstrap-reverse.ps1` 不支持 `-WhatIf` 干跑**（无 `ShouldProcess`/`SupportsProcess`），只能真装。这本身是个可改进项——参赛前想预览会装什么，目前做不到。我没有实际执行安装（会真改系统，且超出诊断授权）。

### 附带的真实缺陷（未触发但存在）

`skills/scripts/lib/ToolDiscovery.ps1:104-110`：

```powershell
Name = 'idapro'
Purpose = 'Python IDA Pro MCP CLI'
Fallbacks = @( @{ Type = 'command'; Value = 'reverse-skill' } )
```

而 `pyproject.toml:28` 定义：

```toml
reverse-skill = "reverse_skill.cli:main"
```

**包自己的 CLI 就叫 `reverse-skill`。** `idapro` 的回退指向包自身，而 `Resolve-ReverseToolSpec`（`:654-668`）只做 `Get-Command`，**不检测解析到的是否是自己**。

**后果**：一旦用户按 README 正确安装（`reverse-skill` 进 PATH），`idapro` 将**永远显示可用**，无论 IDA Pro 是否存在。模型看到 `idapro ✓` 会以为能反汇编。

**当前未触发**：实测 `reverse-skill` 不在这台机器 PATH 上，所以 `idapro` 正确报 `Missing`。这是我实测的结果，不是推测。缺陷在被掩盖状态。

标注：**本条为 `[INFERENCE from code]`** —— 由两处代码推出，未在"包已安装"状态下实测。

---

## P0-2：swarm 里的模型被禁止使用工具

`reverse_skill/evolution.py:270-277` —— 每次模型调用带：

```
--no-tools --no-skills --no-rules --no-extensions
```

**含义**：`swarm` 是项目里唯一真正调用模型的组件，而它调用的模型**被剥夺了全部工具**。

对 CTF 这是致命的：40 个技能描述的 IDA/radare2/frida 操作，**swarm 里的模型一个都执行不了**。它只能分析**用户已经喂给它的文本证据**。

`swarm.py:1` 的自我定位印证这是**有意设计**：

> "Bounded, **read-only** collaboration over **supplied** reverse-engineering evidence."

`swarm.py:19-24` 的系统提示词更直接：

> "Analyze only the supplied material; **do not claim tool execution, target observation, or verified findings**."

`swarm.py:126-140` 输出 `"analysis_status": "advisory"`。

**这是可修的一行标志位**，但需要先决定：是否愿意让 swarm 获得工具权限（有安全含义）。

---

## P1：不存在"解题"入口

### 实测的命令清单

**顶层 19 个命令**（`reverse-skill --help` 实测）：

`asr`、`call`、`case`、`close`、`doctor`、`evolve`、`gates`、`index`、`install`、`integrations`、`open`、`register`、`retrieve`、`route`、`sessions`、`start`、`status`、`tools`、`tracecard-validate`、`yara-scan`

**全包共 48 个命令/组**（按装饰器计数）：

| 模块 | 命令数 |
|---|---|
| `cli.py` | 15 |
| `asr_cli.py` | **14** |
| `workflow_cli.py` | 10 |
| `index_cli.py` | 8 |
| `swarm_cli.py` | 1 |

**功能面比我初版报告写的"20 个"大得多**（初版少算了一半以上，漏了各子组的子命令）。实测两个子组：

- **`asr`（13 个子命令）**：`author`/`authors`/`create-goal`/`import-repo`/`install`/`install-script`/`list`/`plugin`/`record-download`/`scan`/`scan-result`/`scans`/`show` —— 一整套 ASR（审计技能仓库）管理工具
- **`index`（6 个子命令）**：`build`/`import-ida`/`inspect`/`status`/`update`/`xrefs` —— 完整的确定性 SQLite 文档索引

**且 `asr list` 实测连通**，返回真实服务数据（`pre-bounty` 技能、153 stars、commit SHA）。

**但仍无 `solve` / `analyze-challenge`。**

### `route` 明确不执行

`reverse_skill/workflow_cli.py:17-22`：`route` 的文档明写 **"does not execute or authorize"**。

`reverse_skill/routing.py:120-129` 返回值：

```python
"executed": False,
"preflight": {"status": "not_run", ...}
```

**编排器自己承认没执行、没预检。**

### 真正的执行主体是外部 LLM

`SKILL.md:24-42` 指示托管 agent：

> "Read `skills/routing.json` and `skills/routing.md`, then the selected module's `SKILL.md`."

`SKILL.md:76` 又明说：

> "Indexing is optional and **does not change skill selection**."

**所以"解题"完全由模型读 Markdown 完成，代码只提供路由建议。** 这是**包的设计定位**（技能分发 + 演进框架），不是 bug——但对参赛是根本局限。

### 存在真实的分析接缝

不能一概而论说"只是索引工具"：`open`/`call`/`yara-scan` 确实能打开二进制、调 MCP 工具、跑 YARA。`case init` 能建案件记录。**代码有真能力，但没有任何一处把它们串成"题目进 → 验证过的答案出"的闭环。**

---

## P2：技能文本只给品类，但**验证判据与降级链在路由层且完整**

### 重要修正（初版结论过重）

初版这里写"技能没有验证循环"，**不准确**。实测 `skills/routing.json`：

| 项 | 数量 |
|---|---|
| 路由条目 | **21** |
| **有 `success_oracles`（成功判据）** | **21 / 21（100%）** |
| 有 `fallback_edges`（降级链） | 16 / 21 |

`route` 实跑输出（`"脱壳一个 UPX 加壳的 ELF"`）包含：

```json
"skill": "ida-reverse/SKILL.md",
"success_oracles": ["target_function_labeled", "control_flow_evidence_recorded"],
"fallback_edges": [
  {"when": "all_supported_ida_backends_unavailable", "goto": "radare2/SKILL.md"},
  {"when": "ghidra_available_and_ida_missing",       "goto": "reverse-engineering/SKILL.md"},
  {"when": "exploitability_needed",                  "goto": "pwn-chain/SKILL.md"}
]
```

**所以：成功判据存在，降级设计存在，且设计得很好。** 它们不在技能 SKILL.md 里，在路由条目的 `success_oracles` / `fallback_edges` 字段里。

### 真正的缺口：降级链的终点也是空的

路由要求的能力集合：

```
analyzeHeadless, apktool, frida, idapro, jadx,
node, npx, python, radiff2, omp_ida_native
```

对照本机实测（可用：`frida`, `node`, `npx`, `python`）：

| 路由要求 | 本机 |
|---|---|
| `idapro`, `omp_ida_native` | ❌ 缺 |
| `radiff2`（降级目标 1） | ❌ **缺** |
| `analyzeHeadless`（降级目标 2） | ❌ **缺** |
| `jadx`, `apktool` | ❌ 缺 |

**精确因果：设计者已经预见到"IDA 不可用"并给出降级路径 —— 但降级目标（radare2、Ghidra）本身也没部署。** 所以链头断了，链尾也断。

这比我初版"工具缺失"的笼统说法有力得多，也**改变了修复的含义**：不是"设计缺降级"，而是"**降级设计已就绪，只差把目标装上**"。

### 技能文本本身（仍成立的部分）

| 技能 | 行数 | 有具体工具调用? | 有回退? |
|---|---|---|---|
| `competition-web-runtime` | 63 | **无**（参照里有一处真 `curl`） | 转路由（非失败恢复） |
| `competition-reverse-pwn` | 52 | **无** | 有限 |
| `competition-crypto-mobile` | 50 | **无** | **无** |

典型形态（`competition-reverse-pwn/SKILL.md:16-20`）：

> "Start with passive triage: **type, headers, sections, imports, strings, entropy, resources**."

这是**品类清单**，不是可执行调用。缺的是 `rabin2 -I/-zz`、`objdump -d`、`checksec` 这类**具体命令与参数**。

**但这只影响"模型自己去干"时的操作细节**；当路由指向的模块被激活、工具可用时，具体命令来自对应的 `skills/*/SKILL.md`（那 299 个文件），不是这些竞赛薄技能。

**注意**：每个技能的结构（单一入口、下游化、路由、证据优先级）是**高质量**的。

---

## P3：一个富参照文件未接线

`competition-web-runtime/references/` 有 2 个文件：

| 文件 | 大小 | 是否被 SKILL.md 链接 |
|---|---|---|
| `routing-runtime.md` | 28 行清单 | ✅ `SKILL.md:43` |
| `cookie-hmac-key-reuse-auth-bypass.md` | **157 行完整实战**（Python + JS + 端点验证 + 修复） | ❌ **未提及** |

`SKILL.md:41-57` 的"Read This Reference"段列了 15 条路由，**连 `jwt-claim-confusion`/`oauth-oidc-chain` 都列了，属性最近的 cookie-HMAC 实战反而缺席**。

**资产存在但没接线。** 我验证过这是**孤例**——扫描全部 40 个技能、41 个参照文件，**只有这 1 个未被链接**。所以修复是一行，不是 40 处。

---

## 与项目自身记录的对照

项目已诚实记录了部分边界，我的实测**印证并具体化**了它们：

| 项目自述 | 位置 | 我的实测补充 |
|---|---|---|
| "tool availability … still need testing" | `README.md:144` | **28 缺 15，无任何反汇编器**（量化） |
| "Swarm outputs remain advisory" | `BETA-VALIDATION.md:35` | 根源是 `--no-tools`（`evolution.py:270-277`） |
| "Real-model swarm quality … still need testing" | `README.md:144` | swarm 的模型无工具，质量天花板受此限制 |
| "Route-selection scores on fixed fixtures do not establish downstream reverse-engineering correctness" | `README.md:144` | 证实：路由正确 ≠ 能解题 |

**`BETA-VALIDATION.md` 本身质量很高** —— 它验证了制品字节、CI、安装、跨平台。**但它验证的全部是软件工程质量，没有一行验证"能不能解题"。** 这不是疏忽，是项目定位使然。

---

## 建议的行动顺序

### 参赛前（数小时，高杠杆）

1. **跑 bootstrap 装 r2 + jadx 全家** —— 直接补齐降级链的终点。这是**唯一真正解锁已有设计**的动作
2. **决定是否给 swarm 工具权限**（`evolution.py:270-277`）—— 需权衡安全
3. **接线那个 157 行实战参照**（`competition-web-runtime/SKILL.md:41-57`）—— 一行
4. **修 `idapro` 自指缺陷**（`ToolDiscovery.ps1:104-110`）—— 防止谎报可用

**第 1 项是核心。** 做完后 `route` 的降级链（`ida 缺 → radare2`）才第一次真正走得通。

### 参赛后（工程）

5. 给 40 个竞赛技能补**具体命令**（P2，真正的能力建设，但影响有限——具体命令在 `skills/*/SKILL.md` 的 299 个文件里已有）
6. 设计"解题闭环"入口（P1）

### 不建议现在做

- 继续推**代码审计债**（#8/#10/#11 等）—— 那是**代码清洁度**，**不提升解题率**。这个包的架构与路由设计已经很好，把时间花在部署和操作深度上，回报高得多。
- 重写技能架构——架构是好的。

---

## 方法与诚实边界

- **工具可用性**：实测（真跑 `Get-ReverseToolReport`），非推测
- **r2 安装链路**：实测查询 GitHub API，正则精确命中 `radare2-6.2.4-w64.zip`
- **技能深度**：12/40 个技能全文读证，其余按抽样外推 —— **未逐字读全部 40 个**
- **参照文件接线**：全部 40 技能 / 41 参照文件**全量扫描**（非抽样），孤例结论可靠
- **`idapro` 自指**：`[INFERENCE from code]`，未在"包已安装"状态实测
- **未执行安装**：`bootstrap-reverse.ps1` 无干跑模式，实际执行会改系统，超出诊断授权
- **未做**：没有实际拿一道 CTF 题跑完整流程。**所有结论基于结构与工具检测，不是解题成功率实测。** 若需要，给一道题我可以做端到端实测。
- **未修改任何文件**：本次为只读诊断，两个侦察 lane 同为只读；唯一写入是本报告
