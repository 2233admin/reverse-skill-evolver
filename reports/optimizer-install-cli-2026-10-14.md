# #56 安装恢复与本地 CLI 修复验证

2026-10-14。关联 [#56](https://github.com/2233admin/reverse-skill-evolver/issues/56)、父级 [#55](https://github.com/2233admin/reverse-skill-evolver/issues/55)。基线 `d6d085364508215d0019b83f32dc58dd8f170c9e`；执行分支 `2233admin/fix-optimizer-install-cli-20261014`。本报告和样本随提交发布；远端 Draft PR 与交付评论绑定实际 head。

结论：九项源码修复及其行为证据已交付准备就绪；384 项相关回归、gates all、OpenSpec 严格校验通过。完整测试 **789 通过、2 失败、5 跳过**，不能声称全套通过。两个失败来自范围外零字节 JAR 夹具，下一步需父级分配测试更新所有权。

## 来源和边界

已回读远端标题、bug/ready-for-agent 标签、正文、#55 及原生父子关系；工作区分支/head 与派发一致，初始干净，无已有交付 PR。宿主及祖先指导已读取，按仓库/OpenSpec 约定执行。沿用 Code Intel 缺 DAG registry 的已记录失败，未重跑全仓发现。审计 REPORT、reviewed-findings、相关专项及 repro/JSON 为只读来源；基线文件与原 apktool repro 复制到本工作区测试存储后使用，未修改共享审计产物。原型没有被当作产品实现。

生产修改：两端 bootstrap、Windows ToolDiscovery/fleet-sync、Kali refresh、launcher、CLI/ASR/swarm 输出入口、gates/case/routing；新增轻量 `output.py`、`asr_constants.py`。测试只修改允许的 `tests/test_cli.py` 和新增 `tests/test_optimizer_install_cli.py`。OpenSpec 与本报告为 #56 专属。无新增依赖、用户级安装、全局配置、服务、真实目标、版本或共享 CI 修改；未改主目录及其已有脏状态、未改其他组文件。

## 逐 ID 改前/改后证据

全部对照为本人在本工作区执行；计时是此 Windows/Python 3.14.7 宿主的局部样本，不是整体产品或跨平台提速。样本与重跑程序见 [evidence-results.json](../openspec/changes/optimizer-install-cli/evidence-results.json) 和 [evidence.py](../openspec/changes/optimizer-install-cli/evidence.py)。计时使用交错前后试验，测试没有时间阈值断言。

| ID | 当前基线复现 | 实现 | 行为一致性与改善证据 |
|---|---|---|---|
| ER-02 | 真实 ensure_capability 条件调用，安装/chmod 失败仍 `ready` | 安装/下载/解包/复制显式传播失败；jadx 版本检查；仍收集全部能力，失败整体退出 1 | 原 `ready`→`failed`；API/下载/解包/复制/chmod/健康失败均测试；合成 release 使用真实 jq/unzip/cp 并检查版本参数，正常 `ready`；混合成功/失败保留顺序 |
| ER-03 | 原安装/发现函数：中断留下最终坏 JAR，available=true，两次调用仅下载 1 次 | 独占临时兄弟 JAR，完整性/资产长度/15 秒 Java 版本检查后原子发布；清理自有临时文件；拒绝旧坏包及其 wrapper | 原型复现已在本工作区重跑；现在无部分最终文件、available=false、第二次重新下载。PowerShell 5.1/7 测试中断/无效包/非零健康检查、修复成功、健康安装保留、外国文件不删除。完整合成 JAR 的 APK 构建/签名入口通过；未运行真实 Apktool 下载 |
| IO-01 | 实际 refresh 渲染 32 个模拟工具，版本命令执行 64 次 | 调用内 TOOL_SNAPSHOT，MD/JSON 复用 | 64→32 次；32 条 JSON 工具行一致；另一次 refresh 观察新版本，MD/JSON 同一快照；无持久缓存 |
| DATA-03 | 实际 Sync-Directory 对 4000 个同名条目逐个扫描数组 | OrdinalIgnoreCase HashSet；数组仍控制遍历和输出 | 4000 条碰撞及顺序一致；局部中位 448.139→23.881 ms（含集合构建与原调用）；两个方向及混合大小写/新增文件测试通过；未连接真实 SSH/SCP |
| SEC-01 | 实际 leak_scan 扫描 `a.` 重复长行，32k 未匹配约 790.775 ms，带 @- 约 738.031 ms | 每个最大局部串只尝试一次原邮件模式，边界查找限制在该串 | 同输入完整结果一致；32k 为 5.576 ms、带 @- 为 5.750 ms；4k/8k/16k/32k 原样本保留。27,900 个明确边界/域名组合及固定随机样本保持匹配位置/值；原 allowlist 和脱敏输出保留 |
| ALG-04 | 8000 段、1,918,890 字符报告累计复制 7,682,294,395 字符 | 原文本按位置找后续标题，仅切出 section；保留切片首字符曾被当行首的边界语义 | 8000 段完全一致，复制 1,918,890 字符；局部中位 1411.199→28.935 ms；插入标题、最终段及紧接 ID 的特殊标题边界回归通过 |
| DEAD-01 | 未匹配 plan 对同一任务文本规范化 431 次 | 调用内准备一次 normalized 文本，compact 按需一次，公开 matcher 保留 | 431→1；175 个完整计划、5 个 keyword 边界一致，其中包含全部 163 冻结例、ASR 优先、explicit override、Unicode/suffix。64/512/16384 字符局部中位 2.432/9.311/248.717→1.358/3.101/62.691 ms；executed/preflight 授权门保留 |
| BUNDLE-01 | CLI/swarm help 各加载 23 个 HTTPX 模块 | MCP import 移到网络 callback；ASR client 延迟构造、KINDS 共源；共享输出独立模块，cli 继续导出 _envelope/emit | HTTPX 模块 23→0，help stdout 相同；7 轮交错 CLI help 中位 291.048→149.687 ms，swarm 318.503→150.535 ms。新进程拒绝 HTTPX 导入时 root/ASR help 与本地 route 通过；ASR/MCP mock 行为及 output-v1 回归通过 |
| BUILD-001 | 热运行每次先健康 Python，再 CLI Python，共两个子进程 | 同一 `-I -X utf8` 子进程健康导入后 dispatch；独占信号确认 import 失败；最多修复一次 | 运行时子进程 2→1；12 轮准备完毕 runtime 的交错 help 中位 652.920→381.516 ms，stdout 一致。真实隔离子进程验证预导入失败修复一次、二次失败错误信封、命令退出 86/执行时 ImportError 不重放；原 source/signature/目录所有权/cwd/Unicode/首次安装错误契约回归保留 |

## 实际运行

原始本机日志保存在忽略目录 `.verification/optimizer-install-cli/`；远端读者可用下面的命令和已提交样本独立复核。以下摘录为实际退出码及结果。

| 检查 | 实际命令/方式 | 结果与局限 |
|---|---|---|
| 关键问题改前复现 | 新测试首先在基线执行；复制后的原 apktool AST repro；evidence.py 从 git show 取有界基线 | 原安装误报、恢复被阻止、431 次准备、HTTPX 导入及两个 child 均确认。最早测试的 report 标题夹具曾误用二级标题，已修正；它不作为产品缺陷证据 |
| 相关合同回归 | `python -m pytest tests/test_optimizer_install_cli.py tests/test_cli.py tests/test_asr.py tests/test_skill_distribution.py tests/test_repository_gates.py tests/test_case_unit.py tests/test_case_review.py tests/test_routing_contract.py tests/test_routing_benchmark.py tests/test_bootstrap_contract.py -q --tb=short` | exit 0，**384 passed**，51.86 s；`.verification/optimizer-install-cli/related-pytest.log` |
| 完整回归 | `python -m pytest -q --tb=short` | exit 1，**789 passed, 2 failed, 5 skipped**，200.81 s；`.verification/optimizer-install-cli/full-pytest.log`。运行的是最终生产代码；之后补充的合成 release 成功测试已在上述相关回归执行 |
| 跳过原因复核 | `python -m pytest tests/test_integrations.py tests/test_journal_workflow.py -q -rs --tb=short` | exit 0，27 passed, 5 skipped；YARA 未安装 1 项、Windows 不支持 literal quote/backslash 文件名 4 项 |
| 仓库 gate | `python -m reverse_skill --json gates all` | exit 0，status=clean，failures=[]；命令/版本/数据镜像/路由契约保持；`.verification/optimizer-install-cli/gates-all.json` |
| OpenSpec | `openspec validate optimizer-install-cli --strict` | exit 0，change valid |
| Shell/源代码格式 | Bash `-n` 两个修改脚本；PowerShell AST 解析三个修改脚本；`git diff --check` | 全部 exit 0；PowerShell 5.1/7 的行为测试另有覆盖 |
| Python 下限语法 | 对 10 个修改的 Python 生产文件执行 `ast.parse(..., feature_version=(3, 10))` | exit 0；只证明 3.10 语法，不等同真实 3.10 运行验证 |
| 局部性能/一致性 | `python openspec/changes/optimizer-install-cli/evidence.py`；最终 section 边界修改后重测 ALG-04；ER-03 同流程补入样本 | 原始前后计时、操作数量和等价结果已提交。首次证据脚本比较两个不同临时工具路径导致 harness 断言失败，改用同一模拟工具路径后通过；不是产品失败 |

## 失败、开放问题及最小决定

完整测试的两个失败：

- `tests/test_powershell_scripts.py::test_apk_build_needs_adb_only_when_installing[powershell-True]`
- `tests/test_powershell_scripts.py::test_apk_build_needs_adb_only_when_installing[pwsh-True]`

该测试 `jar_only=True` 用 `jar.touch()` 生成零字节 JAR。新规则正确拒绝它，夹具继而进入 auto-bootstrap，因其隔离 PATH 无 powershell.exe 报错；这是实际失败，未改成 skip/xfail、未修改范围外文件，也未放行坏 JAR。允许路径内的 `test_complete_jar_keeps_apk_build_without_adb` 使用完整合成 JAR、复用同一惰性工具 harness，两个引擎都验证原 Java build→zipalign→sign→verify 顺序与输出。

必要的最小后续决定：父级给上述测试文件分配夹具更新所有权，以完整合成 executable JAR 代替空文件，然后重新跑全量。该文件不在 #56 清单内，所以本 PR 保留其失败。本次实现/证据交付不等于审查通过、全量绿灯或发布验收。

## 验收条件对应

| #56 条件 | 验证依据 | 结果 |
|---|---|---|
| 安装/下载/解包失败准确失败；中断不发布半成品，重试修复，有效旧安装保留 | ER-02/03 原复现、故障注入、两个 PS 引擎、合成 release/JAR | 已验证合成安装路径；真实下载未测 |
| 每次工具刷新一次快照；fleet 大小写/顺序保留 | IO-01 调用计数与第二次 refresh；DATA-03 4000 碰撞/双向测试 | 通过；真实 fleet 未测 |
| 长行邮件检测覆盖；report/route 结果一致 | SEC-01 差分/长行；ALG-04 section/边界；DEAD-01 完整计划 | 通过于已列数据范围 |
| CLI 延迟网络实现；兼容 _envelope/emit | 禁止 HTTPX 导入的新进程及 output-v1/ASR/MCP 回归 | 通过 |
| launcher 隔离/所有权/签名/cwd/Unicode/错误；仅 dispatch 前修复 | skill 分发/首次失败测试、4 条真实隔离故障场景、child 计数 | 通过于本地测试；真实网络依赖恢复未测 |
| 175 完整计划/163 固化回归及 ASR/输出规则；局部性能口径 | evidence.py 和 routing-benchmark/contract、CLI schema | 通过；无整体加速声明 |
| 每个 ID 原复现、改后行为/改善，未测失败单列 | 本报告九行及样本/源码测试 | 已提供 |
| 相关回归/gates all；按风险全量；公开契约保留 | 384 回归、gates all、完整 pytest | 相关回归/gates 通过；**全量仍有 2 个旧夹具失败** |
| 自分支提交/推送，一个 main-base Draft PR，引用 #56，逐 ID/缺口 | PR 元数据、远端 head 与 #56 交付评论 | 由交付后的远端回读记录确认 |

## 未运行及剩余边界

- 真实 IDA、Burp、ASR 服务、Kali 系统安装、SSH/SCP fleet 及实际 Apktool/Jadx 下载未运行；没有安装服务或操作真实目标。HTTP/客户端验证为现有 mock，JAR/工具测试为合成输入。
- Python 3.10 不在本机已安装列表；语法检查及 3.14.7 运行不能替代真实最低版本运行。最低版本应在集成 CI 补验。
- Java 15 秒健康检查的失败返回和资源所有权经过合成进程验证；未执行需等待整个 15 秒的故意挂起包测试。
- 首次私有 runtime 安装失败、import 失败/一次修复已测；未联网重装真实缺失依赖。未升级依赖、未改 runtime 隔离约定。
- 父级仍负责两个旧夹具的所有权分配、独立审查、跨 PR 集成、真实环境及 Release 判断。

## 副作用和交付状态

仅本工作区专属源码、测试、OpenSpec、报告和忽略测试存储有写入；合成进程均等待退出/在 finally 关闭，没有共享服务或全局配置变化。Bash bootstrap 在任一能力失败时现在退出 1，仍保留全部结果；不完整托管 JAR 现在不可用，这两项是预期用户行为变化。交付保持 Draft/in-review，不直接推 main、不合并他人 PR、不发布 Release。
