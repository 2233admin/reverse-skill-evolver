# PR #42 独立审查修正

范围：根会话对固定 `6c6b3a6` 的独立审查指出两项 #40 运行缺陷及两项 OMP 证据措辞错误，用户已授权本 Session 定点修复、验证、提交推送。其他代码冻结，不调用模型、不合并。#41 正文更新窗口唯一写入者为根会话，本 Session 只读；#43/#44 也由根会话负责。

## R1：Windows console-script launcher 归属

缺陷成立：distlib 的 `idalib-mcp.exe` 启动 Python 子进程，由子进程监听；直接比对监听者 ExecutablePath 与 launcher 路径会误拒绝本服务。新增真实隔离 launcher 回归在旧实现上 **1 failed、4 passed**，失败为 `does not match the selected executable`。测试直接使用本机 pip 附带的 distlib 生成只监听自有 loopback socket 的 exe，不安装或调用 IDA。

修正：直接 executable 归属路径保留；console-script 路径要求精确选定 launcher、Python 的实际 launcher 参数及 `--host 127.0.0.1 --port <目标端口>`、存活父子链（最多四层，支持 Windows venv redirector）、祖先创建时间不晚于子进程。每层先持有 process handle，再将 CIM 的路径/创建时间与该 handle 的进程匹配；停止前重读创建时间、父 PID、路径和命令行，并核对目标监听者未变化。只停止持有 handle 的监听进程，launcher 自行随子进程退出，不清理祖先、其他端口或进程树。证据不足时保留进程并诊断。

| 结论 | 验证方式 | 结果与局限 |
| --- | --- | --- |
| 实际 launcher 可清理且其他 launcher 保留 | `test_replace_real_distlib_launcher_preserves_other_launcher[current/venv]`；真实不同 PID，含自建无 pip venv 的 redirector 链，连接伴随 socket | 两种实际入口通过；仅自有 socket 服务，没有真实 IDA 服务 |
| 任意 Python / 错 launcher 或端点不被接受 | `test_replace_distlib_listener_rejects_unrelated_identity[launcher/port/host/parent]`；真实进程/端口 | 四种负例均保留进程，socket 仍可连接 |
| 既有健康复用/未知归属/多端口/退出日志仍可用 | `python -m pytest tests/test_ida.py -q --tb=short`，TEMP/TMP 指向本 worktree | **17 passed，28.16 秒，退出码 0**；首次绿检查中只更新了一项旧的变量名字符串断言 |
| PID 复用竞态 | 核查 handle、CIM 创建时间、父子先后、二次身份及端口重读的拒绝分支 | 源码核查；未制造操作系统精确 PID 复用，不能写成实测覆盖 |

测试产生的进程由各自 stdin EOF 结束；异常回收只使用本测试持有的 listener handle 和 Popen handle。没有重启、附加或杀共享服务，也没有模型调用。

## R2：整轮 readiness 截止

缺陷成立：原 probe 将剩余时间分别给 discovery 和 tools/list 的 HTTP 请求，串行请求可超过整轮截止后仍报告 ready。新增负例在旧实现上 **4 failed、1 passed，2.64 秒**：现代与 legacy probe 都晚到仍返回工具数；启动流程的真实两请求后端及故意晚到的 probe 都没有拒绝成功。

修正：probe 建立单调时钟的绝对 deadline，McpClient 的 discovery、fallback/legacy 握手、通知、tools/list 及 DELETE 清理均使用该轮剩余时间；每次响应返回后核查截止，到期不再发送后续请求。启动调用不再设置超过剩余时间的 0.1 秒下限，并在成功 probe 返回后重核启动 deadline，过时成功进入原 PID/日志/退出码超时诊断。超时不停止启动子进程，保持原检查与恢复边界。

| 结论 | 验证方式 | 结果与局限 |
| --- | --- | --- |
| 两请求和 legacy 多请求共享 budget | `test_real_multirequest_probe_shares_deadline[False/True]`，真实自有 loopback MCP，现代每请求 0.3 秒 / legacy 每请求 0.15 秒 | 0.4 秒预算返回 -1，总耗时小于 0.6 秒，到期不追加 DELETE，HTTP client 已关闭；仅本地受控响应，不保证任意外部 I/O 被强制取消 |
| 过时成功不得报告 ready，及时成功可用 | `test_start_real_multirequest_probe_checks_deadline[False/True]` 与 `test_start_does_not_accept_probe_success_after_deadline` | 两个真实现代 MCP 请求晚到时进入带 PID 的超时错误；快速请求仍返回工具数；故意忽略预算的晚到 probe 也不能成功。Popen/IDA 发现用替身，没有操作真实服务 |
| 受影响调用合同与原诊断保留 | `python -m pytest tests/test_ida.py tests/test_mcp.py tests/test_cli.py tests/test_contract.py -q --tb=short` | **114 passed，51.99 秒，退出码 0**；包含 R1 两种真实 launcher、负例、原健康复用及日志检查 |

新注释只说明 handle 的生命周期、distlib/venv 进程关系与整轮 budget；已对照真实入口和调用方检查，不改 field-journal 校验或引入结构重构。

## R3：replay 参考页的旧开发状态

末行“仅静态检查，未 functional/eval”确实与同页及既有真实报告矛盾。修订为实际 Node/Bun 合成测试与真实 OMP 持久 eval 已执行，同时明确该次显式模块导入使用 `--no-skills`，自动 skill 发现和第三方 capture 未验。仅改说明，不改变 skill 入口、模块或归档；严格 UTF-8 读取、既有 evidence 链接及 `git diff --check` 核对。

## R4：收窄 OMP 发现能力声明

原“已发现 skill”声明超出证据：`run-persistent-eval.py` 的真实命令含 `--no-skills`，prompt 指定模块绝对路径，原 frames 记录显式导入、初始化与同一 kernel 复用。因此工作流 README、进度记录、PR 正文和本人 #30 回执收窄为这三项已证实能力；自动 skill 发现标为未验，不用静态目录或模型复述替代加载证据。签名模块/原 frames/输入 DLL/冻结模型输入/调用预算及候选状态均未改，不追加模型调用。

本人 [#30 回执](https://github.com/2233admin/reverse-skill-evolver/issues/30#issuecomment-6146374727) 已定点更正并逐字回读确认；原验证数字与全部边界保留，没有删除评论或写 #41 正文。

## 最终受影响检查与冻结边界

`python -m pytest -q --tb=short`，TEMP/TMP 仅指向本 worktree `.verification/final-test-temp`：**333 passed、5 skipped，61.19 秒，退出码 0**；原始输出见 [最终 Python 日志](pr42-review-python-2026-10-13.txt)。可选 YARA 和 Windows 不支持的引号/反斜线文件名仍未执行，跳过不计通过。完整 Python 包含本次十一项新增回归及原 Node suites；不把它当作新的模型/真实IDA/BurpGUI验收。

相对6c6b3a6，`.github` 工作流、签名模块、真实模型归档和eval metadata保持相同Git内容；改动仅为#40定点源码/隔离回归及所列说明。无模型/SDK/设备/外部服务新调用，没有PID精确复用实测或自动skill发现证据。两个原OMP PR仍由本PR综合承接；#41正文只读，#43/#44不写，修复分支和#32子树所有权保留，待根会话按新固定SHA复验。

## R5：helper 超时不能承诺进程保留

根会话独立复核 dc90554 的 current/venv launcher 和四种负例 **17 passed、33.77秒**，确认身份/祖先/只停止 listener 边界未扩大；本Session引用该验收，不冒充亲跑。其另行在真实自有Python socket与真实PS脚本中仅内存于Kill后注入11秒pause：外层10秒TimeoutExpired时目标已退出4294967295，而原错误仍称processes preserved，故诊断P2成立。该暂停重演来自根会话反馈，本Session未执行。

定点修正：OSError单独报告未能启动ownership helper及processes preserved；TimeoutExpired报告inspection/replacement timed out、target state unknown，并给出目标port的Get-NetTCPConnection及OwningProcess检查动作。保留EnvironmentUnavailable/原异常cause/10秒上限，不改PS脚本、归属校验、Kill或readiness行为。

| 结论 | 验证方式 | 结果与局限 |
| --- | --- | --- |
| 两种失败的承诺不同 | 修改原两项`test_replace_inspection_failure_is_bounded_and_actionable`，先运行旧实现再修正 | 旧实现 **2 failed、20 deselected，0.22秒**；新断言区分helper未启动与超时状态未知，禁止超时错误含processes preserved，检查port/PID恢复动作与原cause |
| 诊断及公开CLI合同保持 | `python -m pytest tests/test_ida.py::test_replace_inspection_failure_is_bounded_and_actionable tests/test_cli.py tests/test_contract.py -q --tb=short` | **76 passed，20.26秒，退出码0**；[原始输出](pr42-helper-timeout-verification-2026-10-13.txt)。helper异常为替身，无强制暂停或真实服务操作 |
| 其他实现冻结 | 比对2d0e4c7的PS脚本、MCP、.github、.omp、模型及native证据归档 | 内容未变；新code diff仅拆开helper异常和两条消息，测试数量未变 |

全量Windows **333 passed/5 skipped**与日志仍属于2d0e4c7基线；本次本地验证只报告上述受影响76项，最新SHA的CI另由最终冻结回执绑定。没有模型调用，预算/候选状态不变。#41正文及快照6147112456由根会话负责，本Session保持正文只读；专属分支及#32子树写入权仍保留。
