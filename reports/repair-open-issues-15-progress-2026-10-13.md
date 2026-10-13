# 15 项接续修复记录

执行者：新 Session，单 Session 串行。工作区 `D:/projects/reverse-skill-evolver/repair-open-issues-15`，专属分支 `2233admin/repair-open-issues-15`，起点 `53010b3`。已核对 origin、Orca worktreeId、identity 和终端，均与交接文件一致；原 Session 已结束交接，无重叠写入。只写本工作区和专属分支，不操作其他工作区。

当前授权：2026-10-13 用户要求实际修复全部 15 项，验证、提交、推送并关联原 Issue/可审查 PR。此授权覆盖旧 Issue 的上一阶段“仅建单”说明。未获得本批全部 PR 的合并授权。Code Intel 在交接时已因缺少 DAG registry 不可用，依主机规则使用限定源码检查。

| Issue | 本轮状态 | 证据 / 下一步 |
| --- | --- | --- |
| #40 | 已推送 b0d78e9，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/40#issuecomment-6144184603)，未合并 |
| #33 | 已推送 af900b4，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/33#issuecomment-6144196773) |
| #34 | 已推送 dc09539，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/34#issuecomment-6144253174) |
| #35 | 已推送 f410993，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/35#issuecomment-6144302542) |
| #36 | 已推送 8a0ca33，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/36#issuecomment-6144429268) |
| #37 | 已推送 4b42601，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/37#issuecomment-6144782032) |
| #38 | 已推送 f762102，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/38#issuecomment-6144854900) |
| #39 | 已推送 d59699c，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/39#issuecomment-6145103261) |
| #32 | 八个UX子项交付已回写，待独立审阅 | [父级回执](https://github.com/2233admin/reverse-skill-evolver/issues/32#issuecomment-6145104135)；不提前关闭 |
| #41 | 原 632cf1a 已复验，Draft PR #44 | [PR](https://github.com/2233admin/reverse-skill-evolver/pull/44)；新复验 39 passed，67.75 秒；未重写 |
| #27 | 已推送 11d8e8e，Draft PR #42 | [回执](https://github.com/2233admin/reverse-skill-evolver/issues/27#issuecomment-6145599636)；真实 native + 22 项检查 |
| #28 | 已推送 0b63096，Draft PR #42 | 实际两版 native 输入 + 39 项检查，源码复用 |
| #29 | 已推送 9dd2079，Draft PR #42 | [回执](https://github.com/2233admin/reverse-skill-evolver/issues/29#issuecomment-6145923141)；7 个真实 Frida case + 24 检查 |
| #30 | 已推送 5223544，Draft PR #42 | [回执](https://github.com/2233admin/reverse-skill-evolver/issues/30#issuecomment-6146374727)；真实3个eval调用，累计模型32/37 |
| #21 | 真实 suite/反思/失败路径已验证，交付 PR #42 | 31/37 逻辑调用，单次 60 秒；候选不晋级，见真实记录 |

## #40 验证

改动：移除进程名批量清理；Windows 按目标端口核实监听者 executable，持有 process handle 后核对再停止。归属不明或helper未启动时保留进程并诊断；helper超时可能发生在Kill之后，明确报告目标状态未知，检查端口/PID后重试。健康端口始终复用。每次启动保存独立日志，返回 PID/logPath；提前退出报告实际退出码和日志尾；readiness 使用单调时钟截止，超时保留当前子进程供用户检查。

实际运行：`python -m pytest tests/test_ida.py tests/test_cli.py -q` → **55 passed**。包括真实隔离 Python 监听进程的两端口保护/未知归属保留，以及真实子进程退出码 17/stderr 保留、0.5 秒超时及日志/PID 检查。

完整回归：`python -m pytest -q` → **234 passed, 5 skipped**；`git diff --check` 通过。跳过项是现有可选集成/工具链检查，不能替代真实 IDA 验证。

未运行：真实 IDA 启动、替换他人服务。原因：本项以隔离进程验证生命周期和清理安全，不操作未核实归属的共享服务。未验证真实 IDA 许可证或二进制分析行为。日志保存在系统临时目录，由本次启动独立创建；超时后进程保持运行，恢复前须检查报告的 PID 和日志。

下一责任人：本 Session 交付 Draft PR 并继续 #33；PR 保持 Draft 待独立审阅和明确合并授权。

## #33 验证

根因与修复：`open` 将根超时限制为 30 秒，现直接传递 `state.timeout`，保留默认 120 秒、工具输出、异常传播和会话句柄。CLI contract 增加 600 秒示例。

实际运行：`python -m pytest tests/test_cli.py -q` → **50 passed**；`git diff --check` 通过。参数化检查默认 120、显式 600、短值 0.5，均通过公开 CLI 到达 MCP client；同一路径的超时仍返回退出码 4、单 JSON 错误、无成功会话且只调用一次。

未运行：真实复杂 IDA 样本的 600 秒分析。此项证明参数与错误合同，不证明真实分析完成。下一责任人：审阅者审阅 Draft PR #42；本 Session 接续 #34。

## #34 验证

修复：收集 IDA、Codex 注册、MCP 三阶段诊断和动作；注册超时仍收集 MCP 结果；MCP 错误不抹掉本地信息。失败保留原 error code/退出码、单 JSON envelope 与 `data:null`；`error.message` 的 `Diagnostics: ` 后附诊断 JSON。人工 doctor/status 提供简明阶段与动作，integrations 给出 availability/support 和下一步。

实际运行：`python -m pytest tests/test_cli.py tests/test_contract.py -q` → **64 passed**；涵盖缺少安装/注册、健康、注册超时、连接超时、协议错误，人工与 JSON 双模式，schema v1 验证和现有调用方兼容检查。`python -m reverse_skill --timeout 0.5 --url http://127.0.0.1:1/mcp doctor` 实际显示本机 IDA 9.4 和已取得的注册地址，MCP 失败有检查 endpoint、服务 PID/log 和重跑 doctor 的动作；stderr 保留错误，命令退出码 4（单独复核）。

未运行：对真实 IDA 服务的启动/分析；未写宿主注册配置。下一责任人：PR 审阅者；本 Session 接续 #35。

## #35 验证

修复：工具未加载时 tools/list 重新获取一次，并发 list 共用一次请求；成功后保留缓存。HTTP 发现有总 3 秒截止；调用有总 125 秒截止，不重试操作。校验工具数组、工具响应对象、HTTP 状态和 JSON；顶层非空 error（包括 HTTP 500 的明确操作错误）设置 isError:true 并保留文本。普通业务状态、嵌套 error 和部分结果 errors 计数不误标；连接/解析失败保留原 JSON-RPC ID，以协议错误返回。

实际运行：`node --check burp-mcp-full/mcp-bridge.js` 通过；`node --test burp-mcp-full/tests/mcp-bridge.test.js` → **6 passed, 0 failed**。真实 Node stdio + 隔离 loopback 后端覆盖后启动恢复/缓存、持续无效内容、挂起后端 3 秒截止、正常工具列表、200/500 操作错误、普通业务数据、无效调用响应、连接重置。该检查也由 Python 常规测试入口执行（缺少 Node 时明确 skip）。`git diff --check` 通过。

未运行：真实 Burp GUI/扩展/代理流量；Java 调度与攻击语义无改动。下一责任人：PR 审阅者；本 Session 接续 #36。

## #36 验证

修复：预算单位为完整 fixture-suite evaluations；实际 frozen fixture 数计算 `max_evaluations * fixture_count + max_reflections` 逻辑调用上限，provider 重试可能增加物理请求。stderr 输出预算和 baseline/curated/reflection/proposal 阶段/完成数；stdout 保持一个最终 JSON。模型调用前归档输入字节和哈希、curated 文本；逐次响应写入原子替换的 results.json。异常/中断保存失败阶段、fixture、已完成响应和可取得的失败进程 stdout/stderr/退出码，status=incomplete；部分候选没有 pass_rates，整体不生成 Pareto frontier，保持 not_promoted。错误归档也失败时保留原异常并附归档错误，不自动复跑/续跑。

实际运行：`python -m pytest tests/test_evolution_optimizer.py tests/test_evolution_contracts.py tests/test_cli.py tests/test_contract.py -q --tb=short` → **160 passed**。包含完整成功/预算停止/提前全通过、反思与祖先证据、非法反思原响应归档、提供方失败/超时/KeyboardInterrupt 中断、错误归档自身失败以及 CLI 单 JSON/stderr 进度，预算随 2/3 fixture 数变化。`git diff --check` 通过。

完整 Python 回归：`python -m pytest -q --tb=short` → **257 passed, 5 skipped**（包含真实 Node bridge 检查）。

尚未运行：本项检查没有真实模型调用；#21 将单独记录新获授权的真实 OMP 结果，不与本项模拟证据混同。

## #21 当前真实验证

[真实 OMP 记录](omp-live-2026-10-13/README.md)：默认 provider 首请求 402，显式 MiniMax 新 API 第一条真实路由响应通过；下一次调用遇到 Windows 临时 cwd 清理错误。累计转发 3/37，两个 run 均 incomplete。修复 cleanup 不再掩盖已取得的模型响应/错误，相关真实隔离 cwd 锁及 evolution 检查 **95 passed**。接续真实完整 suite，保持预算和 not_promoted。

最终真实结果：完整 frozen 12-case suite 的 baseline/curated 均 12/12，通过 24 调用、84.473 秒、退出码 0，提前停止不反思；另行受控单例完成 3 evaluations + 1 reflection，4 调用、14.187 秒，curated 0/1 → proposal 1/1。全批累计 31/37（含前述失败）。逐个核对 envelope、输入/候选哈希、严格原响应 parser、完整覆盖和 not_promoted 均通过。tokens/物理请求/费用 unknown；不代表下游任务或晋级通过。

## #37 验证

修复：root --url help 说明调用/注册地址，start --port help 说明独立本地 loopback 端口；root 选项置于子命令前。中英文 README、IDA skill 与 CLI contract 给出 24444 的 start/status/register/open 完整同端点例子，默认 13337 不变。同步 IDA skill 中 #40 之后的清理/PowerShell 边界，避免旧描述仍宣称清理进程树。

实际运行：`python -m reverse_skill --help`、`start --help` 均显示关系和默认值；`python -m pytest tests/test_contract.py -q` → **4 passed**；公开 CLI 隔离 start recorder 确认根远端 URL 不改变默认启动 13337、显式 port 24444 原样转发；`git diff --check` 通过。未启动真实服务、未调用远端、未写注册配置。下一责任人：审阅者；本 Session 接续 #38。

## #38 验证

恢复来源：可读 Git commit `070bf87` 的完整索引；后续新增 2026-05-26 条目以现存 `2026-05-26_pentest-newapi-rate-limit-bypass.md` 的标题、对照观察、关键词、模式和环境补齐。后续 `{target_domain}` 脱敏占位保留，不恢复历史域名。历史登记统计保持当前 22 项（17 种子 + 5 项项目记录）、28 模式、最近更新 2026-05-26；本轮未重新验证这些历史安全结论，未晋级经验。

实际核对：Python 严格 UTF-8 读取和 PowerShell `Get-Content -Encoding utf8` 均显示可读标题/正文；前后 27 个 `.md` 引用身份无丢失，26 个实际引用目标全部存在，剩余 1 个是明确的文件命名示例；17 条 `[种子]` 标记保留；`git diff --check` 通过。未增加依赖或形式化测试。

不能恢复：后续新增的先例加载顺序/授权措辞段落未找到可靠可读原文；索引明确标为未恢复，保留三个原先例链接，具体操作仍以当前任务授权为准。未对 seed/项目日志作新事实或验证等级判断。下一责任人：审阅者；本 Session 接续 #39。

## #39 验证

改动：中英文首页用同一段 CLI 任务作为入口：必要 Python/IDA/idalib/输入、native-binary → ida-reverse、启动/doctor/open/sessions/tools/survey/close、reports/first-task 证据路径、真实会话 ID 替换和逐条成功信号/失败恢复。无需用户先阅读内部维护文档。一次性安装、可选原生 MCP 注册、项目路由入口与可选全局范围分开说明，列出修改对象、备份/恢复命名块/卸载新条目和日常复用；RULES 与原 13/14/16 节同步，不因纯阅读触发配置写入。稳定 route/promotion 合同未改变。

实际运行：两种首页 console blocks 逐字相同，新增相对链接全部存在；7 条公开 CLI 命令用隔离 client/start recorder 和自建空样本执行，参数解析/流程/成功 JSON 均通过（start 为人工模式，其余 6 个单 JSON envelope）。`python -m pytest tests/test_cli.py tests/test_contract.py -q --tb=short` → **66 passed**；`git diff --check` 通过。`git diff --quiet 53010b3 -- skills/routing.md skills/routing.json skills/evolution/fixtures/route-selection.json` → 0，稳定路由/fixture 无变化；本机 `codex mcp remove --help` 核对恢复命令。

未运行：本首页 recipe 的真实 IDA 样本分析、上游交互安装、写入/撤回宿主配置、计时真实用户上手测试；未把本次文档检查宣称流失率改善。#21 的真实模型检查保持单独证据。下一责任人：Draft PR #42 审阅者；本 Session 继续 #41 交付及 OMP #27–#30 功能验证。

## #41 接续验证

远端分支 head 保持 `632cf1a`，main 仍为 53010b3，无已有对应 PR 或该 branch 的活动终端。未改其旧 worktree、实现或提交。在本 worktree 内临时目录解压精确 commit 的 git archive，仅运行相关既有检查：`python -m pytest tests/test_powershell_scripts.py tests/test_bootstrap_contract.py tests/test_routing_contract.py -q --tb=short` → **39 passed，67.75 秒**，退出码 0。原始输出见 [回读检查](issue41-resume-verification-2026-10-13.txt)。

原提交全套 256 passed/5 skipped 与性能测量仍属于旧证据，本次不冒充重测。真实安装、设备、Frida 注入、远端同步未测。接续创建原 head 的 Draft PR，待审阅/明确合并授权。

Draft PR #44 已创建，head 精确为原 632cf1a，base main；既有实现/提交未重写。下一责任人：审阅者。OMP #27–#30 将在当前专属分支复用 PR #26/#31 的 Git lineage，再串行修补和验证，不写其原分支、不合入 main。

## #27 功能验证

本地 merge 2362964 复用原 PR #26/#31 Git lineage；解决四个文档冲突，保留本轮首页/授权范围与既有 OMP 后端选择；原分支不变。合并后常规 Python 检查 **266 passed, 5 skipped**。

真实自制 x64 PE DLL 的 pinned 生产 worker open/exec 已验证字符串、导入、函数、无匹配、截断预算及非函数 xref；最新 collector 源码后重跑，输入 SHA 与保存 DLL 一致。补充回归 **22 passed**；修复 missing namespace 的明确诊断、拒绝空/错误 metadata。例子真实保存完整 JSON，避免 helper warning 混进打印输出；portable skill 的证据链接使用 HTTPS，复制技能目录仍可用。全部细节见 [scoped record](omp-workflow-verification-2026-10-13/README.md)。

没有改他人数据库/服务或宿主配置；worker 的 database_id 为调用方绑定的本地测试标识，不冒充 OMP host registry 验证。OMP 模型调用 0，#21 的 31 次保持独立。下一责任人：PR 审阅者；本 Session 继续 #28。

## #28 功能验证

真实 snapshot-v1/v2 经 CLI 对照，显式 mapping 将变名/变 RVA 的 verify_license → check_license 对应；唯一 decode_payload 符号名自动对应，padding_function 仅保留 unmatched observation。输出 comparison-v1-v2.json、mapping-v1-v2.json 可复核来源/布局/字段变化。

comparator 复用未重写，新增 17 项回归；`python -m pytest tests/test_omp_binary_diff.py tests/test_omp_analysis.py -q --tb=short` → **31 passed**。覆盖重命名、重复名字、相同 RVA 不自动对应、截断/partial bytes、错误来源/架构/位数/格式、映射冲突、fallback 与未采集、新建输出及拒绝覆盖/输入 alias/重复 JSON/NaN。`git diff --check` 通过。无模型、无 IDB 写入；不宣称结构匹配、语义等价或符号迁移。下一责任人：审阅者；本 Session 继续 #29。

## #29 功能验证

模块名校验补拒绝 DEL 控制字符，相关检查 **24 passed**。真实 Frida 17.9.3 只附加自创 Python/DLL 进程，7 cases 全通过：ASLR+正确换算/命中、事件上限、伴随 listener 不被清理、未命中时间停止、错模块、错位数、错架构、地址越界、非执行区（7 个组合场景）。plan/事件/来源 hash 见 scoped record；负例 artifact 是有标记的故障注入。

首次 attach 因 C 盘仅剩约 10 MB 失败；改本 driver 的 TEMP/TMP/TMPDIR 到自己 worktree 后成功，没有宿主配置修改/清理。plan 仍 planned_not_run/preconditions unverified，运行观察单独归档，不把通用假设晋级成真。进程按自身 EOF 退出、session 只管理自己目标/监听器，模型调用 0。下一责任人审阅者；本 Session 继续 #30。

## #30 功能验证

修复 Array 子类迭代器及 Proxy trap 在 fixture 校验阶段可能执行代码的问题，保持普通 JSON 和实际 callback 合同。Node/Bun 各 9 passed/0 failed，Python+portable skill入口 9 passed。

真实 OMP 18.8.9 的一轮仅 eval 的 MiniMax 会话实际执行3个持久js cells，按显式绝对路径导入模块/定义状态/复用状态并跑全套及部分 compareSignatures。该轮使用 --no-skills，skill自动发现未验；原frames只证明显式导入、replay和kernel复用。保存JSON由Python独立HMAC oracle和原工具frames核查：完整2/2，partial remaining=1且不通过。9.501秒，一次逻辑OMP调用，全批累计32/37，物理请求/账单unknown。输入为自制固定HMAC用例，不冒充第三方capture或服务器验收。C盘空间导致native缓存失败后，按正式PI_NATIVES_DIR/私有agentdir/进程TEMP在本worktree成功，未清理宿主缓存或改配置。原响应/metadata/完整报告/driver见scoped record，凭据扫描通过。

本批15项均已有代码或既有代码复用、逐项验证和可审查交付；下一步做最终回归、远端head/CI回读及总结。PR未合并，不据此关闭Issue或宣称真实用户/任意目标验收。

## 6c6b3a6 冻结版本检查与交付状态

最终自检补修 #34 的兼容回归：原进程启动 OSError/解码 UnicodeError 保持原 internal/退出码1，阶段诊断仍保留；不是一律转为 environment/退出码3。新负例覆盖 doctor/status、两种输出，共8项；CLI/合同检查 **74 passed**。

最终全部 Python 检查：`TEMP/TMP` 指向本 worktree 私有目录运行 `python -m pytest -q --tb=short` → **322 passed, 5 skipped，37.45秒**；包含实际 Node bridge/replay suite。跳过项未计为通过。另有原 #41 commit 的独立快照 **39 passed**、Node/Bun replay各 **9 passed**、两个真实 native SDK输入、自制 Frida **7 cases PASS**、真实路由24调用及反思4调用、持久eval实际3个工具调用。不能用总测试数替代各Issue验收表。

直接回读当前Git blob验证 #21 全部 frozen 输入/候选、#27 实际 DLL SHA，均与报告一致。真实eval的实际Windows文件SHA与Git blob SHA分别记录，并绑定源提交5223544；避免混淆checkout换行和仓库源码身份。所有报告扫描无本次提供的API key；稳定候选仍not_promoted。

远端交付：Draft PR #42 承载本批UX/#21及复用的OMP #26/#31 lineage和后续修补验证；Draft PR #44的head精确为原632cf1a。main仍53010b3，原PR26/31分支head仍caa6013/920e0dd，均未改写/合并。新工作区的`.verification/`只含本轮私有运行环境/缓存，已忽略，不进入Git；没有清理旧工作区、C盘或共享缓存。

CI/审查边界：在5223544，Python/Java Project checks和GitGuardian成功。field-journal自动合并门失败，原日志明确“PR修改了非field-journal文件”；该门只允许纯journal变更，本批有CLI/OMP等代码，未修改或绕过此策略，没有请求自动合并。main保护API回读为“Branch not protected”，required checks未配置；不能把未配置写成全CI绿。CodeRabbit对Draft跳过审查，无提交review/inline评论。RepoWise的4个critical是复杂条件/圈复杂度告警（generate_hook_plan、validateJson、_snapshot等），并非已确认功能/安全漏洞；报告明示无AI review/无测量test map，仍保留为独立审阅关注，不据通过测试宣称消除结构风险。最新head推送后重新回读CI。

本轮交付已完成，阶段状态为**已提交推送、待独立审阅**；PR均保持Draft，Issue没有提前关闭。未验证：真实用户上手计时/该首页样本任务、真实Burp GUI/真实设备/远端同步、任意架构和生产签名capture。下一责任人：审阅者，按原Issue逐项验收并在明确授权后整合；本Session不持有长期协调或自动合并权。

## 独立审查后的定点修正

根会话在精确 6c6b3a6 只读快照上发现的两项 #40 运行缺陷成立：distlib launcher 与监听 Python 不同 PID，不能只比对 launcher 的 executable；readiness 的串行 HTTP 请求重复使用剩余 budget，过时成功仍会报告 ready。已分项提交推送 dc90554（精确 launcher 命令/存活父链/创建时间/handle/端口重核）及 d702b00（整轮绝对 deadline、每请求剩余时间、成功后截止重核），保留未知归属、其他端口/进程、日志/PID/退出诊断及超时保留子进程边界。源码和实测对应见 [独立审查修正记录](pr42-review-fixes-2026-10-13.md)。

f92196f 修正 replay 参考页的旧“仅静态检查”状态。工作流 README、本记录、PR 正文和本人 #30 回执收窄发现能力：真实运行使用 --no-skills，证据只支持显式模块导入、replay及kernel复用；自动skill发现未验。原 module/frames/DLL/模型冻结输入及预算未改，不追加模型调用。

受影响 IDA/MCP/CLI/合同 **114 passed，51.99秒**；最终全部 Python **333 passed、5 skipped，61.19秒**，均退出码0。新增六个Windows真实launcher场景（含当前解释器/venv redirector及四个拒绝负例）和五个deadline场景；原YARA缺依赖和Windows非法文件名跳过仍保留，不能计作通过。原始最终输出见 [Python检查日志](pr42-review-python-2026-10-13.txt)。CI及最终固定SHA由最新PR冻结回执绑定，不把旧head的CI冒充新head。

根会话报告其OMP独立核查56项、19冻结hash、28原response oracle、两版native对照、七个Frida case及两个HMAC oracle均未发现高置信运行bug；这是根会话在6c6b3a6的验收记录，本Session没有重跑模型或冒充亲跑上述独立验收。相应归档和模块在新head保持相同Git blob。Repowise复杂度指标不触发无关重构。

本Session保留专属分支及#32子树写入权；#41正文更新窗口唯一写入者为根会话，本Session保持正文只读。#43/#44由根会话负责，不重叠写入；#26/#31原提交已由#42综合承接，避免重复合入。PR仍Draft，未获新合并/关闭/模型预算授权。

## helper超时诊断的后续定点修正

根会话复核launcher17项通过后发现helper外层TimeoutExpired可能发生在Kill之后，原processes preserved承诺不成立。只拆分OSError（未启动helper/保留进程）和TimeoutExpired（inspection/replacement超时/目标状态未知/检查端口OwningProcess后重试），不改变PS校验、停止范围、超时值或其他代码。

原两项措辞回归在旧实现上失败；本次对应回归及CLI/合同 **76 passed，20.26秒**，原始输出及根会话实测来源见[审查修正R5](pr42-review-fixes-2026-10-13.md)。未重演正常系统11秒pause，未重新调用模型；2d0e4c7的全量Windows333/5是基线，当前局部证据与最新headCI区分记录。#41正文/远端恢复快照6147112456由根会话唯一负责，本Session只读。所有权和未合并状态保持。
