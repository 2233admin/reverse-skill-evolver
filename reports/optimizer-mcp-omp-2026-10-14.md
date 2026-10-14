# #58 MCP / OMP recovery and Burp callback repair

状态与授权记录见 [OpenSpec 事项入口](../openspec/changes/optimizer-mcp-omp/README.md)。关联 #58；父级 #55。本报告记录本执行者亲自运行的合成验证，不代表真实 IDA/Burp/OMP 验证或独立验收。

基线为 `d6d085364508215d0019b83f32dc58dd8f170c9e`，分支为 `2233admin/fix-optimizer-mcp-omp-20261014`。远端 issue 标题、bug/ready-for-agent 标签、原生父级 #55、父级三个子 issue 和 blocked-by=0 均已回读；没有既有本分支 PR。精确运行句柄沿用 #58 派发记录，不创建 Run/Task/Dispatch。

代码修复提交为 `1572e65713ca0e3904d0e25972783904d3858ca5`，已推送并创建 [Draft PR #60](https://github.com/2233admin/reverse-skill-evolver/pull/60)。创建后实际回读确认 base=main、Draft=true、head 分支、上述修复 head 及完整正文与本地准备稿一致。后续提交仅补本交付文档，不改变已经验证的生产/测试代码；最终 PR head 的稳定记录写在 #58 交付评论中。

## 改前与改后证据

审计源为本次交接指定的只读 `REPORT.md`、`reviewed-findings.json`、`memory.md`、`error.md`、`concurrency.md`、`security.md` 及其脚本。审计脚本先复制到自己的 `tests/tmp/optimizer-mcp-omp/`，只在副本中把源码根绑定到本工作区，并在改后调整“缺陷仍存在”的断言。没有改共享审计产物，也没有把审计局部原型当实现。

| ID / 等级 | 当前 source 原复现 | 实际修复 | 改后行为与改善证据 |
|---|---|---|---|
| MEM-02 / Medium | 原 `memory-repro.mjs` 的 VM 运行实际 bridge 行处理器：一条合法请求、`]`、1000 条合法 initialize；只得到最初 1 条响应，最后 parse 输入为 1,091,001 字符 | readline 的完整行独立 JSON.parse；坏帧输出 -32700 后返回，不保存坏前缀 | 同负载得到 1002 条响应：最初成功、1 条 parse error、之后 1000 条成功；最后单帧 parse 1091 字符。另用真实 Node 子进程与自有 HTTP 后端验证连续坏帧、空行、UTF-8 字节拆分和后续合法帧；无目标流量 |
| ER-01 / Medium | 原 `error-probe-repro.py` 调真实 probe_tool_count 配 MockTransport：0.05 秒预算仍读完 20 个每块等待 0.01 秒的空白块，返回 -1、流关闭；本机观测 0.2081 秒 | 保留同步 McpClient 与 BaseTransport 注入；默认网络由现有 HTTPX async I/O 和 Python 3.10 wait_for 驱动，可取消发送和每次读取；增量 SSE 在匹配 RPC 事件完成后关闭；DELETE 只取响应头，并共享绝对截止 | 同负载读 5 块后停止并关闭，返回 -1，本机观测 0.0526 秒。永久化测试用虚拟时钟证明第三块到期且不继续读；自有本地 HTTP 验证阻塞响应头、连续 JSON/SSE 分块、匹配后不等 EOF、清理的阻塞头/正文和一次有副作用调用不重试，关闭后所属 loop 线程停止 |
| CONC-001 / Medium | 原 HandlerRaceProof 编译并加载实际 Java server（不 start/listen）：并发首调用安装 2 回调；清空/重配后一次请求有 2 次头修改及完整请求序列化 | 专用锁覆盖首次检查、安装、active 发布、规则更改和清空；回调取一致规则快照后处理请求；安装成功才发布 active | 新 Java 行为测试把首安装阻塞到第二调用进入争用边界，断言只装 1 回调；清空后修改/序列化均为 0；重配后均为 1；再次配置不重装；安装失败显式 error，随后能重试。既有 scheduler 和行为回归一起进入 Gradle check |
| SEC-03 / Medium | 原 security_probe 的公开 triage 验证命名空间，字符串为 28 个 a 后跟 !，自定义 `^(a+)+$`；外层 3 秒 watchdog 必须终止进程 | 任一自定义模式使用一个 JSON-only regex_worker 批次，subprocess.run 的 2 秒超时负责 kill/reap；只传有界文本、模式和覆盖信息；native 枚举/xrefs/func 始终在原 worker；默认模式本地匹配 | 原 28-a 负载现在在原 triage 错误路径报告 `RuntimeError: Custom triage regex batch exceeded 2 seconds`，在 3 秒外层 watchdog 内退出。永久化测试用更长近匹配输入确保触发、核对所属子进程已退出且未查 xref，随后同 worker 正常匹配；默认/等价自定义结果逐字段相同；Python 命名组、反向引用与 lookahead 接受；缺失 helper 明确失败，无部分成功报告 |
| MEM-03 / Low | 原 memory-repro：1000 fixtures、每 input 8192 字符、maxCases=1；执行 1 次，但 structuredClone 1001 次 | 完整 JSON/fixture/唯一 ID 验证后冻结 total，只快照与哈希所选前缀；回调仍收到独立克隆 | 同负载仅 2 次 clone（1 个 baseline、1 个 callback 输入），未选中快照为 0；total=1000、processed=1、remaining=999、complete=false、passed=false。测试验证 callback 清空原数组不影响 total，选中输入/expected 隔离，尾部无效 JSON/重复 ID/非字符串 expected 仍在回调前拒绝 |

时长仅为这台机器的一次原负载对照，不是便携性能阈值、整体加速或真实服务 SLA。回归以读取/克隆/回调次数、覆盖率、错误、资源释放和结果一致性判定，没有新增计时性能断言。

## 实际检查

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| 相关行为通过 | `python -m pytest tests/test_mcp.py tests/test_optimizer_mcp_omp.py tests/test_omp_analysis.py tests/test_omp_signature_replay.py tests/test_burp_bridge.py -q` | 退出 0，60 passed；包含实际网络/stdio 子进程边界，native namespace 为合成 fixture |
| Node 回归通过 | `node --test tests/omp-signature-replay.test.mjs burp-mcp-full/tests/mcp-bridge.test.js`；最终字节拆分版本通过上行 pytest 的实际 Node 调用 | 退出 0，18 passed；重放用确定签名 fixture，Burp 后端为自有短生命周期本地 HTTP |
| 全量 Python 回归通过 | 最终 `python -m pytest -q -r s` | 退出 0，773 passed、5 skipped，211.62 秒；包含最终 DELETE 阻塞头和缺失 regex helper 测试。跳过为 1 项可选 yara 未安装、4 项 Windows 不支持字面 quote/backslash 文件名；初轮全量亦退出 0（771 passed、5 skipped） |
| Java 编译与 gate 通过 | 只在该命令环境把 JAVA_HOME 指向现有 JDK 21，然后 `burp-mcp-full/gradlew.bat -p burp-mcp-full check --no-daemon --console=plain` | 退出 0，BUILD SUCCESSFUL；behaviorRegressionTest、httpHandlerRegressionTest、schedulerRegressionTest 实际执行；JDK 21.0.2/Gradle 8.7；没有真实 Burp 进程 |
| 公开 CLI 与仓库 gate 通过 | `python -m reverse_skill --json gates all` | 退出 0，schemaVersion=1、ok=true、status=clean，doc-facts/version/routing-coherence 全 clean |
| OpenSpec 格式通过 | `openspec validate optimizer-mcp-omp --strict --no-interactive` | 退出 0，change valid |
| Python 3.10 语法与 API 检查 | 三个变更 Python 生产文件经 `ast.parse(..., feature_version=(3,10))`；核对 wait_for/zip(strict=True) 均有 3.10 支持 | 退出 0，3 文件语法接受；本机实际主回归为 Python 3.14.7，不把语法检查叫作 3.10 runtime 验证 |
| 改动边界与 whitespace | `git diff --check`；按 #58 的显式路径清单核对待提交文件 | 退出 0；新 helper 有当前调用者；所有版本化改动都在授权范围 |

原始命令输出由本 session 工具记录保留；本表和上表保存可重新执行的命令、关键返回与观测，不虚构完整日志附件。最终全量运行也暂存在自己的测试 scratch，交付前摘录到本报告。

## 验收条件逐项对应

| #58 验收条件 | 由什么验的 | 结果 |
|---|---|---|
| 坏完整 JSON 帧 -32700 后下一合法帧正常；按换行恢复 | bridge 实际 stdio 测试和原负载 VM 对照 | 通过：连续坏帧、1000 合法帧、拆分 UTF-8 均验证 |
| 绝对截止覆盖发送、持续分块、协商、清理；匹配响应后结束；超时释放且不重试 tool | `tests/test_optimizer_mcp_omp.py`：headers/json/sse、协商虚拟时钟、提前匹配、DELETE stalled-body/stalled-headers；现有 IDA probe 回归 | 本地合成路径通过；真实 server 尚未验证 |
| Python>=3.10、同步公开接口、transport 注入、output-v1、正常 JSON/SSE；不依赖 asyncio.timeout | 3.10 AST/API 检查、MCP 全部既有测试、CLI/gates 与全量回归 | 本机通过；实际 3.10 runtime 留现有 CI，未伪称本机已跑 |
| Burp 首安装原子、只一回调，清空/重配只处理一次，scheduler 限制保留 | `McpHttpHandlerRaceTest`、`McpHttpServerBehaviorTest`、`McpHttpServerSchedulerTest` | 三个 Java main 回归实际通过；没有改 scheduler |
| 自定义 regex 批次有限期限/失败，保留 Python 语法/default 结果/native 所有权且不遗留进程 | 原公开 triage 对照、`tests/test_omp_analysis.py` 的 timeout/reap/recovery、parity/owner、compile filename、missing helper 测试 | 合成 namespace 通过；真实 IDA worker 未运行 |
| 完整 fixtures 验证，冻结 total，只快照/哈希前缀，保留隔离/fingerprint/coverage/partial passed | `tests/omp-signature-replay.test.mjs` 的新增 clone/尾部拒绝测试与全部既有重放场景 | 实际 Node runtime 通过 |
| 合成与真实 IDA/Burp/OMP 分开记录，仅自有短生命周期合成服务 | 测试 HTTP fixture 的 finally、Node t.after、subprocess timeout kill/reap；本报告未验证部分 | 通过边界核对；无真实目标操作 |
| 每 ID 有原复现、改后、一致性/改善、失败/缺口单列 | 本报告第一表及失败/未验证段 | 五 ID 全覆盖 |
| 相关回归、gates all 通过；公开 CLI/JSON/版本/路由保持，测试按风险选择 | 相关 60、全量 Python、Node、Java gate；gates all | 已运行检查见上表；未修改共享 CLI/版本/路由文件 |
| 自己分支提交推送，一个自足 Draft PR 引用 #58，逐 ID 和未验证边界 | [Draft PR #60](https://github.com/2233admin/reverse-skill-evolver/pull/60) 创建后实际回读 head/base/draft/body，最终 head 由 #58 交付评论保存 | 已推送并回读确认 PR；远端回执和工作区状态由实际运行接口记录，保持 Draft 交独立审查 |

## 失败记录

- 首轮相关 Python 验证出现 3 个旧 SSE 断言失败：它们要求匹配后仍验证尾部或继续解析 unrelated event。#58 明确要求匹配响应后结束流；因此把测试边界改成只验证匹配前/匹配事件，并保留 malformed-before、错误 ID 和 non-object-before 的失败。相关回归后已通过，未放宽 #58 要求。
- 首轮 `gradlew check --no-daemon` 用主机默认 JDK 25 失败：`Unsupported class file major version 69`。从既有 Gradle daemon 记录找到现有 JDK 21，用单命令 JAVA_HOME 切换重跑成功；没有升级 Gradle、安装 Java 或修改全局环境。
- 一次修改本地审计副本的 inline Python 命令因 PowerShell 引号失败，副本仍断言原缺陷；改用 apply_patch 修改自己的副本后取得上述改后计数。该失败没有改产品或共享审计文件。
- 自动批准审查拒绝清理本工作区生成的 `tests/tmp/optimizer-mcp-omp/`、`burp-mcp-full/.gradle/` 和 `burp-mcp-full/build/`，理由仅返回 `blocked by policy`。回读已确认三目录均在本工作区内、不是 link、没有 tracked 文件；明确 literal 路径的安全尝试也被拒绝，因此保留这些本地产物且不提交，没有转用其它删除机制。最终全量原始输出保留在 `tests/tmp/optimizer-mcp-omp/full-pytest.txt`，属于未提交本地证据。

## 未运行与剩余缺口

- **真实 IDA/OMP worker**：本次没有打开真实 native 数据库或调用已安装 OMP。仍需在已授权原生 worker 上确认其解释器能启动相邻 regex helper，测试正常自定义模式、病态模式超时后 worker 可继续使用、默认报告一致性。历史报告不能替代本补丁验证。
- **真实 Burp**：没有加载扩展、真实 HTTP 请求或目标操作。还需在已授权 Burp runtime 上验证 Montoya 注册成功/失败以及清空和重配；本次 Java 是实际产品类配动态代理，属于隔离行为验证。
- **Python 3.10 和跨平台**：本机没有 Python 3.10；语法/API 检查通过，真实 3.10 Linux runtime 属于现有 GitHub CI。尚未运行其它架构/系统或真实 MCP 端点。
- **五项跳过**：可选 yara 没有安装（1 项 `tests/test_integrations.py`）；Windows 无法创建 Linux 字面 quote/backslash 文件名（4 项 journal workflow）。未安装可选依赖或改别组测试，不能把跳过列为通过。
- **预算范围**：默认网络 I/O 可取消；显式注入的同步 Python transport 只能在其返回/分块间检查截止，不能安全强杀任意阻塞 Python callback。连接关闭仍需系统/库完成资源释放，不承诺硬实时调度。正则 deadline 约束自有匹配子进程；原生完整枚举、xref/decompiler 成本不在匹配预算内，仍需 native exec 的有限 timeout。
- **审查/集成**：Draft PR 仅为本 issue 的代码交付；独立审查、CI 验收、三 PR 集成和发版由 #55 的后续执行者处理。本执行者不合并或转 ready。

## 修改与副作用

整合追加：Codex App 在原 head `e7b3b91` 指出自定义 regex 在子进程启动前预复制所有 subjects。新增回归在原实现失败，证明无界预准备及JSON超过字节预算。现在每批编码上限256 KiB，最多准备64条，匹配达到上限即停止后续批次；所有源/批次与准备阶段共用原两秒deadline。固定小批次避免max_matches=1时普通无匹配输入逐行启动解释器的开销。输出全局index、扫描数、clipping和truncation保留，默认路径和原生helper所有权不变。新增确定性时钟回归验证第二批只剩0.9秒且不会重置deadline；原故障清理测试验证所有已启动匹配子进程均退出，而不再假设整个操作恰好一个子进程。该段为整合阶段新证据，原作者完整测试记录仍保留其原快照范围。

生产改动：`reverse_skill/mcp.py`；bridge、Java server 和其 Gradle 行为 gate；原生 `ida_analysis.py`、相邻 `regex_worker.py` 和 triage 说明；JS signature-replay。测试仅为 #58 允许的 MCP/OMP/bridge/Java 文件，另有本 issue 的 OpenSpec 与本报告。

没有新依赖，没有改 README/pyproject/通用 CI/版本/路由/索引身份/ASR 优先/授权和能力门/默认只读 plan；没有另派 Agent、新建工作区、用户级安装、配置修改、main 推送、其它 PR 合并或 Release。主仓脏文件保持只读，审计目录保持只读。生成的本地构建和复现 scratch 不提交；仅使用现有工具与依赖缓存。自有 HTTP/Node/匹配子进程均在测试清理路径停止；不清理共享服务或其它 session 进程。
