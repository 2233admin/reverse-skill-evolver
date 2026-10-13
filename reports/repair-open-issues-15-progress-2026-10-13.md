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
| #38 | 已恢复并核对，交付 Draft PR #42 | 27 引用身份、26 实际目标、17 种子保留；1 文件名示例不当作日志 |
| #39 | 待实施 | 首次上手文档，依赖前述行为 |
| #32 | 总览，待逐项回收 | 不视为独立代码修复，不提前关闭 |
| #41 | 已有提交待形成 PR | 复用 `632cf1a`，不重写 |
| #27–#30 | 已有 Draft PR #31，待功能验证 | 依赖 Draft PR #26；复用实现 |
| #21 | 真实 suite/反思/失败路径已验证，交付 PR #42 | 31/37 逻辑调用，单次 60 秒；候选不晋级，见真实记录 |

## #40 验证

改动：移除进程名批量清理；Windows 按目标端口核实监听者 executable，持有 process handle 后核对再停止。归属不明/检查失败保留进程并诊断；健康端口始终复用。每次启动保存独立日志，返回 PID/logPath；提前退出报告实际退出码和日志尾；readiness 使用单调时钟截止，超时保留当前子进程供用户检查。

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
