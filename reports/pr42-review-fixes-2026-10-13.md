# PR #42 独立审查修正

范围：根会话对固定 `6c6b3a6` 的独立审查指出两项 #40 运行缺陷及两项 OMP 证据措辞错误，用户已授权本 Session 定点修复、验证、提交推送。其他代码冻结，不调用模型、不合并。#41 正文更新窗口唯一写入者为根会话，本 Session 只读；#43/#44 也由根会话负责。

## R1：Windows console-script launcher 归属

缺陷成立：distlib 的 `idalib-mcp.exe` 启动 Python 子进程，由子进程监听；直接比对监听者 ExecutablePath 与 launcher 路径会误拒绝本服务。新增真实隔离 launcher 回归在旧实现上 **1 failed、4 passed**，失败为 `does not match the selected executable`。测试直接使用本机 pip 附带的 distlib 生成只监听自有 loopback socket 的 exe，不安装或调用 IDA。

修正：直接 executable 归属路径保留；console-script 路径要求精确选定 launcher、Python 的实际 launcher 参数及 `--host 127.0.0.1 --port <目标端口>`、存活父子链（最多四层，支持 Windows venv redirector）、祖先创建时间不晚于子进程。每层先持有 process handle，再将 CIM 的路径/创建时间与该 handle 的进程匹配；停止前重读创建时间、父 PID、路径和命令行，并核对目标监听者未变化。只停止持有 handle 的监听进程，launcher 自行随子进程退出，不清理祖先、其他端口或进程树。证据不足时保留进程并诊断。

| 结论 | 验证方式 | 结果与局限 |
| --- | --- | --- |
| 实际 launcher 可清理且其他 launcher 保留 | `test_replace_real_distlib_launcher_preserves_other_launcher[current/venv]`；真实不同 PID，含自建无 pip venv 的 redirector 链，连接伴随 socket | 两种实际入口通过；仅自有惯性 socket 服务，没有真实 IDA 服务 |
| 任意 Python / 错 launcher 或端点不被接受 | `test_replace_distlib_listener_rejects_unrelated_identity[launcher/port/host/parent]`；真实进程/端口 | 四种负例均保留进程，socket 仍可连接 |
| 既有健康复用/未知归属/多端口/退出日志仍可用 | `python -m pytest tests/test_ida.py -q --tb=short`，TEMP/TMP 指向本 worktree | **17 passed，28.16 秒，退出码 0**；首次绿检查中只更新了一项旧的变量名字符串断言 |
| PID 复用竞态 | 核查 handle、CIM 创建时间、父子先后、二次身份及端口重读的拒绝分支 | 源码核查；未制造操作系统精确 PID 复用，不能写成实测覆盖 |

测试产生的进程由各自 stdin EOF 结束；异常回收只使用本测试持有的 listener handle 和 Popen handle。没有重启、附加或杀共享服务，也没有模型调用。
